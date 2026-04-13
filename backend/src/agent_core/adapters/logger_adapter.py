"""XAgentLoggerAdapter - 适配 X-Agent 日志系统到 LoggerPort.

双重输出:
1. AgentLogger (内存缓存, 支持 REST API 查询)
2. X-Agent structlog (文件持久化)
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from ..logger import AgentLogger
from ..types import (
    LLMCallLog,
    LogCategory,
    LogEntry,
    LogLevel,
    ToolCallLog,
)

if TYPE_CHECKING:
    pass


class XAgentLoggerAdapter:
    """LoggerPort 适配器，双重输出到 AgentLogger 和 structlog.

    Example:
        from agent_core.logger import AgentLogger

        agent_logger = AgentLogger()
        adapter = XAgentLoggerAdapter(agent_logger)

        config = AgentCoreConfig(logger=adapter)
    """

    def __init__(self, agent_logger: AgentLogger) -> None:
        """初始化适配器.

        Args:
            agent_logger: AgentLogger 内存缓存实例
        """
        self._agent_logger = agent_logger
        self._structlog = _get_structlog()

    # ================================================================
    # LoggerPort 接口实现
    # ================================================================

    def log(self, entry: LogEntry) -> None:
        """记录通用日志 (双重输出)."""
        # 内存缓存
        self._agent_logger.log(entry)

        # structlog 输出
        if self._structlog:
            _forward_to_structlog(self._structlog, entry)

    def log_llm_call_start(self, log: LLMCallLog) -> None:
        """记录 LLM 调用开始."""
        self._agent_logger.log_llm_call_start(log)

    def log_llm_call_end(
        self,
        call_id: str,
        response: dict[str, Any],
        usage: dict[str, int],
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """记录 LLM 调用结束."""
        self._agent_logger.log_llm_call_end(
            call_id=call_id,
            response=response,
            usage=usage,
            duration_ms=duration_ms,
            error=error,
        )

    def log_tool_call_start(self, log: ToolCallLog) -> None:
        """记录工具调用开始."""
        self._agent_logger.log_tool_call_start(log)

    def log_tool_call_end(
        self,
        call_id: str,
        result: Any,
        duration_ms: float,
        is_error: bool = False,
        error: str | None = None,
    ) -> None:
        """记录工具调用结束."""
        self._agent_logger.log_tool_call_end(
            call_id=call_id,
            result=result,
            duration_ms=duration_ms,
            is_error=is_error,
            error=error,
        )

    def get_logs(
        self,
        trace_id: str | None = None,
        category: LogCategory | None = None,
        level: LogLevel | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """查询日志."""
        return self._agent_logger.get_logs(
            trace_id=trace_id,
            category=category,
            level=level,
            limit=limit,
            offset=offset,
        )

    def get_llm_call(self, call_id: str) -> LLMCallLog | None:
        """获取 LLM 调用详情."""
        return self._agent_logger.get_llm_call(call_id)

    def get_tool_call(self, call_id: str) -> ToolCallLog | None:
        """获取工具调用详情."""
        return self._agent_logger.get_tool_call(call_id)


# ================================================================
# 内部辅助函数
# ================================================================

_LEVEL_MAP = {
    LogLevel.DEBUG: "debug",
    LogLevel.INFO: "info",
    LogLevel.WARN: "warning",
    LogLevel.ERROR: "error",
}


def _get_structlog() -> Any:
    """获取 structlog logger (可选).

    Returns:
        structlog logger 或 None
    """
    try:
        from src.utils.logger import get_logger

        return get_logger("agent_core")
    except (ImportError, Exception):
        return None


def _forward_to_structlog(logger: Any, entry: LogEntry) -> None:
    """将 LogEntry 转发到 structlog.

    Args:
        logger: structlog logger
        entry: 日志条目
    """
    method_name = _LEVEL_MAP.get(entry.level, "info")
    log_fn = getattr(logger, method_name, logger.info)

    extra = {
        "event": entry.event,
        "trace_id": entry.trace_id,
        "category": entry.category.value if entry.category else "",
    }
    if entry.data:
        extra.update(entry.data)
    if entry.duration_ms is not None:
        extra["duration_ms"] = entry.duration_ms
    if entry.error:
        extra["error"] = entry.error

    with contextlib.suppress(Exception):
        log_fn(entry.message, extra=extra)
