"""AgentLogger - 内存缓存 + 文件持久化日志系统.

实现 LoggerPort 接口，提供：
- 内存缓存（deque 限制大小）
- 文件持久化（JSON 格式，支持滚动）
- 线程安全（Lock）
- trace_id 索引
- 实时订阅（asyncio.Queue）

验收条件:
- 内存日志限制：1000 条通用日志，100 条 LLM 调用，500 条工具调用
- 支持按 trace_id, category, level 查询
- 支持实时订阅新日志
- 文件持久化到 logs/agent-core.log
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import (
    LogLevel,
    LogCategory,
    LogEntry,
    LLMCallLog,
    ToolCallLog,
)


# 延迟导入避免循环依赖
def _get_rotating_handler():
    """延迟导入 TimedSizeRotatingFileHandler."""
    try:
        from src.utils.logger import TimedSizeRotatingFileHandler
        return TimedSizeRotatingFileHandler
    except ImportError:
        from backend.src.utils.logger import TimedSizeRotatingFileHandler
        return TimedSizeRotatingFileHandler


class AgentLogger:
    """内存缓存 + 文件持久化日志系统.
    
    实现 LoggerPort Protocol，日志数据同时保存在内存和文件中，
    支持按 trace_id/category/level 查询和实时订阅。
    
    Example:
        logger = AgentLogger()
        logger.initialize_file_persistence(log_dir="logs")  # 启用文件持久化
        
        # 记录通用日志
        logger.log(LogEntry(
            trace_id="abc123",
            event="agent_loop_start",
            message="Agent loop started",
        ))
        
        # 查询日志
        logs = logger.get_logs(trace_id="abc123")
        
        # 实时订阅
        queue = logger.subscribe()
        entry = await queue.get()
    
    Thread Safety:
        所有写操作使用 threading.Lock 保护，
        适用于多线程环境。
    
    File Persistence:
        使用 TimedSizeRotatingFileHandler，支持时间和大小双维度滚动。
        日志格式为 JSON，每行一条记录。
    """
    
    # 默认大小限制
    DEFAULT_MAX_LOGS = 1000
    DEFAULT_MAX_LLM_CALLS = 100
    DEFAULT_MAX_TOOL_CALLS = 500
    
    # 单例支持
    _instance: "AgentLogger | None" = None
    
    def __new__(cls, *args, **kwargs) -> "AgentLogger":
        """单例模式，确保全局只有一个实例."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        max_logs: int = DEFAULT_MAX_LOGS,
        max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> None:
        """初始化 AgentLogger.
        
        Args:
            max_logs: 通用日志最大条数
            max_llm_calls: LLM 调用日志最大条数
            max_tool_calls: 工具调用日志最大条数
        """
        # 避免重复初始化
        if getattr(self, '_initialized', False):
            return
        
        # 内存缓存
        self._logs: deque[LogEntry] = deque(maxlen=max_logs)
        self._llm_calls: deque[LLMCallLog] = deque(maxlen=max_llm_calls)
        self._tool_calls: deque[ToolCallLog] = deque(maxlen=max_tool_calls)
        
        # 索引（trace_id -> list of ids）
        self._trace_log_index: dict[str, list[str]] = {}
        self._trace_llm_index: dict[str, list[str]] = {}
        self._trace_tool_index: dict[str, list[str]] = {}
        
        # LLM call -> tool calls 索引
        self._llm_tool_index: dict[str, list[str]] = {}
        
        # 快速查找
        self._llm_call_map: dict[str, LLMCallLog] = {}
        self._tool_call_map: dict[str, ToolCallLog] = {}
        
        # 线程安全
        self._lock = threading.Lock()
        
        # 实时订阅
        self._subscribers: list[asyncio.Queue[LogEntry]] = []
        self._subscriber_lock = threading.Lock()
        
        # 文件持久化（延迟初始化）
        self._file_handler: Any = None
        self._log_file: Path | None = None
        self._file_persistence_enabled = False
        
        self._initialized = True
    
    def initialize_file_persistence(
        self,
        log_file: str = "logs/agent-core.log",
        max_size: str = "20MB",
        backup_count: int = 5,
        when: str = "D",
        interval: int = 1,
    ) -> None:
        """初始化文件持久化.
        
        Args:
            log_file: 日志文件路径
            max_size: 最大文件大小（如 "20MB", "100KB", "1GB"）
            backup_count: 备份文件数量
            when: 时间滚动间隔（D=天, H=小时, M=分钟, S=秒）
            interval: 滚动间隔乘数
        """
        if self._file_persistence_enabled:
            return
        
        self._log_file = Path(log_file)
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 解析 max_size
        max_size_str = max_size.upper()
        if max_size_str.endswith('MB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024)
        elif max_size_str.endswith('KB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024)
        elif max_size_str.endswith('GB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024 * 1024)
        else:
            try:
                max_bytes = int(max_size_str)
            except ValueError:
                max_bytes = 20 * 1024 * 1024  # 默认 20MB
        
        # 创建滚动文件处理器
        TimedSizeRotatingFileHandler = _get_rotating_handler()
        self._file_handler = TimedSizeRotatingFileHandler(
            filename=str(self._log_file),
            when=when,
            interval=interval,
            max_bytes=max_bytes,
            backup_count=backup_count,
            encoding='utf-8'
        )
        
        self._file_persistence_enabled = True
    
    def _write_to_file(self, entry: dict[str, Any]) -> None:
        """写入日志到文件.
        
        Args:
            entry: 日志条目字典
        """
        if not self._file_persistence_enabled or self._file_handler is None:
            return
        
        try:
            log_record = logging.LogRecord(
                name='agent_logger',
                level=logging.INFO,
                pathname=str(self._log_file) if self._log_file else '',
                lineno=0,
                msg=json.dumps(entry, ensure_ascii=False, default=str),
                args=(),
                exc_info=None
            )
            self._file_handler.emit(log_record)
        except Exception:
            pass  # 静默处理文件写入错误，不影响内存日志
    
    # ================================================================
    # LoggerPort 接口实现
    # ================================================================
    
    def log(self, entry: LogEntry) -> None:
        """记录通用日志.
        
        Args:
            entry: 日志条目
        """
        if not entry.id:
            entry.id = str(uuid.uuid4())[:12]
        
        with self._lock:
            self._logs.append(entry)
            
            if entry.trace_id:
                self._trace_log_index.setdefault(entry.trace_id, []).append(entry.id)
        
        # 写入文件
        self._write_to_file({
            "type": "log_entry",
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else datetime.now().isoformat(),
            "id": entry.id,
            "trace_id": entry.trace_id,
            "level": entry.level.value if entry.level else "INFO",
            "category": entry.category.value if entry.category else None,
            "event": entry.event,
            "message": entry.message,
            "data": entry.data,
            "duration_ms": entry.duration_ms,
            "error": entry.error,
        })
        
        self._broadcast(entry)
    
    def log_llm_call_start(self, log: LLMCallLog) -> None:
        """记录 LLM 调用开始.
        
        Args:
            log: LLM 调用日志（包含请求信息）
        """
        if not log.call_id:
            log.call_id = str(uuid.uuid4())[:8]
        
        log.status = "pending"
        
        with self._lock:
            self._llm_calls.append(log)
            self._llm_call_map[log.call_id] = log
            
            if log.trace_id:
                self._trace_llm_index.setdefault(log.trace_id, []).append(log.call_id)
        
        # 写入 LLM 调用日志文件
        self._write_to_file({
            "type": "llm_call_start",
            "timestamp": log.start_time.isoformat() if log.start_time else datetime.now().isoformat(),
            "call_id": log.call_id,
            "trace_id": log.trace_id,
            "provider": log.provider,
            "model": log.model,
            "message_count": log.message_count,
            "estimated_tokens": log.estimated_tokens,
            "messages": log.messages,  # 完整的 prompt
            "system_prompt": log.system_prompt,
        })
        
        # 同时写入通用日志
        self.log(LogEntry(
            trace_id=log.trace_id,
            level=LogLevel.INFO,
            category=LogCategory.LLM_CALL,
            event="llm_call_start",
            message=f"LLM call started: {log.model}",
            data={
                "call_id": log.call_id,
                "model": log.model,
                "provider": log.provider,
                "message_count": log.message_count,
                "estimated_tokens": log.estimated_tokens,
            },
        ))
    
    def log_llm_call_end(
        self,
        call_id: str,
        response: dict[str, Any],
        usage: dict[str, int],
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """记录 LLM 调用结束.
        
        Args:
            call_id: 调用 ID
            response: 响应内容
            usage: Token 使用统计
            duration_ms: 耗时（毫秒）
            error: 错误信息（如果有）
        """
        with self._lock:
            log = self._llm_call_map.get(call_id)
            if log is None:
                return
            
            log.end_time = datetime.now()
            log.duration_ms = duration_ms
            log.usage = usage
            log.response_content = response.get("content") if isinstance(response, dict) else None
            log.stop_reason = response.get("stop_reason") if isinstance(response, dict) else None
            
            if error:
                log.status = "error"
                log.error = error
            else:
                log.status = "completed"
        
        # 写入 LLM 调用结束日志文件
        self._write_to_file({
            "type": "llm_call_end",
            "timestamp": log.end_time.isoformat() if log.end_time else datetime.now().isoformat(),
            "call_id": call_id,
            "trace_id": log.trace_id,
            "model": log.model,
            "duration_ms": duration_ms,
            "usage": usage,
            "response_content": log.response_content,
            "stop_reason": log.stop_reason,
            "status": log.status,
            "error": error,
        })
        
        level = LogLevel.ERROR if error else LogLevel.INFO
        event_name = "llm_call_error" if error else "llm_call_end"
        
        self.log(LogEntry(
            trace_id=log.trace_id,
            level=level,
            category=LogCategory.LLM_CALL,
            event=event_name,
            message=f"LLM call {'failed' if error else 'completed'}: {call_id}",
            data={
                "call_id": call_id,
                "duration_ms": duration_ms,
                "usage": usage,
                "stop_reason": log.stop_reason,
                "error": error,
            },
            duration_ms=duration_ms,
            error=error,
        ))
    
    def log_tool_call_start(self, log: ToolCallLog) -> None:
        """记录工具调用开始.
        
        Args:
            log: 工具调用日志（包含入参信息）
        """
        if not log.call_id:
            log.call_id = str(uuid.uuid4())[:8]
        
        log.status = "executing"
        
        with self._lock:
            self._tool_calls.append(log)
            self._tool_call_map[log.call_id] = log
            
            if log.trace_id:
                self._trace_tool_index.setdefault(log.trace_id, []).append(log.call_id)
            
            if log.llm_call_id:
                self._llm_tool_index.setdefault(log.llm_call_id, []).append(log.call_id)
        
        # 写入工具调用日志文件
        self._write_to_file({
            "type": "tool_call_start",
            "timestamp": log.start_time.isoformat() if log.start_time else datetime.now().isoformat(),
            "call_id": log.call_id,
            "trace_id": log.trace_id,
            "llm_call_id": log.llm_call_id,
            "tool_name": log.tool_name,
            "arguments": log.arguments,
        })
        
        self.log(LogEntry(
            trace_id=log.trace_id,
            level=LogLevel.INFO,
            category=LogCategory.TOOL_EXEC,
            event="tool_call_start",
            message=f"Tool call started: {log.tool_name}",
            data={
                "call_id": log.call_id,
                "tool_name": log.tool_name,
                "llm_call_id": log.llm_call_id,
                "arguments": log.arguments,
            },
        ))
    
    def log_tool_call_end(
        self,
        call_id: str,
        result: Any,
        duration_ms: float,
        is_error: bool = False,
        error: str | None = None,
    ) -> None:
        """记录工具调用结束.
        
        Args:
            call_id: 调用 ID
            result: 执行结果
            duration_ms: 耗时（毫秒）
            is_error: 是否为错误
            error: 错误信息（如果有）
        """
        with self._lock:
            log = self._tool_call_map.get(call_id)
            if log is None:
                return
            
            log.end_time = datetime.now()
            log.duration_ms = duration_ms
            log.is_error = is_error
            log.result = result
            
            if error:
                log.status = "error"
                log.error = error
            else:
                log.status = "completed"
        
        # 写入工具调用结束日志文件
        self._write_to_file({
            "type": "tool_call_end",
            "timestamp": log.end_time.isoformat() if log.end_time else datetime.now().isoformat(),
            "call_id": call_id,
            "trace_id": log.trace_id,
            "tool_name": log.tool_name,
            "duration_ms": duration_ms,
            "status": log.status,
            "is_error": is_error,
            "error": error,
            "result": str(result)[:1000] if result else None,  # 限制结果长度
        })
        
        level = LogLevel.ERROR if is_error else LogLevel.INFO
        event_name = "tool_call_error" if is_error else "tool_call_end"
        
        self.log(LogEntry(
            trace_id=log.trace_id,
            level=level,
            category=LogCategory.TOOL_EXEC,
            event=event_name,
            message=f"Tool call {'failed' if is_error else 'completed'}: {log.tool_name}",
            data={
                "call_id": call_id,
                "tool_name": log.tool_name,
                "duration_ms": duration_ms,
                "is_error": is_error,
                "error": error,
            },
            duration_ms=duration_ms,
            error=error if is_error else None,
        ))
    
    # ================================================================
    # 查询方法
    # ================================================================
    
    def get_logs(
        self,
        trace_id: str | None = None,
        category: LogCategory | None = None,
        level: LogLevel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """查询日志.
        
        Args:
            trace_id: 按 trace_id 过滤
            category: 按分类过滤
            level: 按级别过滤
            limit: 返回数量上限
            offset: 分页偏移量
        
        Returns:
            符合条件的日志列表
        """
        with self._lock:
            result = list(self._logs)
        
        # 按条件过滤
        if trace_id:
            result = [e for e in result if e.trace_id == trace_id]
        if category:
            result = [e for e in result if e.category == category]
        if level:
            # 过滤大于等于指定级别的日志
            level_order = {LogLevel.DEBUG: 0, LogLevel.INFO: 1, LogLevel.WARN: 2, LogLevel.ERROR: 3}
            min_level = level_order.get(level, 0)
            result = [e for e in result if level_order.get(e.level, 0) >= min_level]
        
        # 按时间倒序
        result.sort(key=lambda e: e.timestamp, reverse=True)
        
        # 分页
        return result[offset:offset + limit]
    
    def get_llm_call(self, call_id: str) -> LLMCallLog | None:
        """获取 LLM 调用详情.
        
        Args:
            call_id: 调用 ID
        
        Returns:
            LLMCallLog 或 None
        """
        with self._lock:
            return self._llm_call_map.get(call_id)
    
    def get_llm_calls_by_trace(self, trace_id: str) -> list[LLMCallLog]:
        """获取指定 trace 的所有 LLM 调用.
        
        Args:
            trace_id: 追踪 ID
        
        Returns:
            LLM 调用日志列表
        """
        with self._lock:
            call_ids = self._trace_llm_index.get(trace_id, [])
            return [self._llm_call_map[cid] for cid in call_ids if cid in self._llm_call_map]
    
    def get_tool_call(self, call_id: str) -> ToolCallLog | None:
        """获取工具调用详情.
        
        Args:
            call_id: 调用 ID
        
        Returns:
            ToolCallLog 或 None
        """
        with self._lock:
            return self._tool_call_map.get(call_id)
    
    def get_tool_calls_by_trace(self, trace_id: str) -> list[ToolCallLog]:
        """获取指定 trace 的所有工具调用.
        
        Args:
            trace_id: 追踪 ID
        
        Returns:
            工具调用日志列表
        """
        with self._lock:
            call_ids = self._trace_tool_index.get(trace_id, [])
            return [self._tool_call_map[cid] for cid in call_ids if cid in self._tool_call_map]
    
    def get_tool_calls_by_llm(self, llm_call_id: str) -> list[ToolCallLog]:
        """获取指定 LLM 调用触发的所有工具调用.
        
        Args:
            llm_call_id: LLM 调用 ID
        
        Returns:
            工具调用日志列表
        """
        with self._lock:
            call_ids = self._llm_tool_index.get(llm_call_id, [])
            return [self._tool_call_map[cid] for cid in call_ids if cid in self._tool_call_map]
    
    # ================================================================
    # 实时订阅
    # ================================================================
    
    def subscribe(self, max_queue_size: int = 100) -> asyncio.Queue[LogEntry]:
        """订阅实时日志.
        
        Args:
            max_queue_size: 队列大小上限
        
        Returns:
            接收日志的 asyncio.Queue
        """
        queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=max_queue_size)
        with self._subscriber_lock:
            self._subscribers.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue[LogEntry]) -> None:
        """取消订阅.
        
        Args:
            queue: 要取消的队列
        """
        with self._subscriber_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)
    
    def _broadcast(self, entry: LogEntry) -> None:
        """广播日志到所有订阅者.
        
        使用 put_nowait，队列满时静默丢弃。
        
        Args:
            entry: 日志条目
        """
        with self._subscriber_lock:
            dead_queues = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(entry)
                except asyncio.QueueFull:
                    pass
                except Exception:
                    dead_queues.append(queue)
            
            for q in dead_queues:
                self._subscribers.remove(q)
    
    # ================================================================
    # 工具方法
    # ================================================================
    
    def clear(self) -> None:
        """清空所有日志."""
        with self._lock:
            self._logs.clear()
            self._llm_calls.clear()
            self._tool_calls.clear()
            self._trace_log_index.clear()
            self._trace_llm_index.clear()
            self._trace_tool_index.clear()
            self._llm_tool_index.clear()
            self._llm_call_map.clear()
            self._tool_call_map.clear()
    
    @property
    def log_count(self) -> int:
        """通用日志条数."""
        return len(self._logs)
    
    @property
    def llm_call_count(self) -> int:
        """LLM 调用日志条数."""
        return len(self._llm_calls)
    
    @property
    def tool_call_count(self) -> int:
        """工具调用日志条数."""
        return len(self._tool_calls)
    
    def create_log_entry(
        self,
        trace_id: str,
        event: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        category: LogCategory = LogCategory.AGENT_LOOP,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> LogEntry:
        """便捷方法：创建并记录日志条目.
        
        Args:
            trace_id: 追踪 ID
            event: 事件名称
            message: 日志消息
            level: 日志级别
            category: 日志分类
            data: 附加数据
            duration_ms: 耗时
            error: 错误信息
        
        Returns:
            创建的 LogEntry
        """
        entry = LogEntry(
            trace_id=trace_id,
            level=level,
            category=category,
            event=event,
            message=message,
            data=data or {},
            duration_ms=duration_ms,
            error=error,
        )
        self.log(entry)
        return entry
