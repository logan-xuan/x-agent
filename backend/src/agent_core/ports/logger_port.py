"""日志接口定义.

LoggerPort 定义了 agent_core 与日志系统交互的接口。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..types import LLMCallLog, LogCategory, LogEntry, LogLevel, ToolCallLog


class LoggerPort(Protocol):
    """日志接口.

    agent_core 通过此接口记录日志，不关心具体实现。
    实现者可以将日志输出到文件、数据库、远程服务等。

    Example:
        class FileLoggerAdapter:
            def __init__(self, log_file: str):
                self.log_file = log_file

            def log(self, entry: LogEntry) -> None:
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(entry.__dict__) + "\\n")

            def log_llm_call_start(self, log: LLMCallLog) -> None:
                self.log(LogEntry(
                    event="llm_call_start",
                    data={"call_id": log.call_id, "model": log.model},
                ))
    """

    def log(self, entry: LogEntry) -> None:
        """记录通用日志.

        Args:
            entry: 日志条目
        """
        ...

    def log_llm_call_start(self, log: LLMCallLog) -> None:
        """记录 LLM 调用开始.

        Args:
            log: LLM 调用日志（包含请求信息）
        """
        ...

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
        ...

    def log_tool_call_start(self, log: ToolCallLog) -> None:
        """记录工具调用开始.

        Args:
            log: 工具调用日志（包含入参信息）
        """
        ...

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
        ...

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
            list[LogEntry]: 日志列表
        """
        ...

    def get_llm_call(self, call_id: str) -> LLMCallLog | None:
        """获取 LLM 调用详情.

        Args:
            call_id: 调用 ID

        Returns:
            LLMCallLog | None: LLM 调用日志，不存在时返回 None
        """
        ...

    def get_tool_call(self, call_id: str) -> ToolCallLog | None:
        """获取工具调用详情.

        Args:
            call_id: 调用 ID

        Returns:
            ToolCallLog | None: 工具调用日志，不存在时返回 None
        """
        ...
