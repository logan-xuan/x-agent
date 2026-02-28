"""记忆集成模块.

提供工具调用结果写入记忆的功能，包括：
- 摘要生成: 将工具调用结果转换为可存储的摘要
- 重要性过滤: 过滤不重要的工具调用
- 去重: 避免重复存储相似的工具调用
- 异步写入: 不阻塞主流程
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ports.memory_port import MemoryPort
    from .types import ToolResult

logger = logging.getLogger(__name__)

# 摘要最大长度
_MAX_SUMMARY_LEN = 1000
# 结果内容最大截取长度
_MAX_RESULT_CONTENT_LEN = 500
# 最小有意义内容长度
_MIN_MEANINGFUL_LEN = 20


def generate_tool_call_summary(
    tool_name: str,
    arguments: dict[str, Any],
    result: "ToolResult",
    is_error: bool,
    duration_ms: float,
) -> str:
    """生成工具调用摘要.

    Args:
        tool_name: 工具名称
        arguments: 调用参数
        result: 执行结果
        is_error: 是否出错
        duration_ms: 执行耗时 (ms)

    Returns:
        str: 摘要文本
    """
    status = "FAILED" if is_error else "completed successfully"

    # 格式化参数
    args_str = _format_arguments(arguments)

    # 格式化结果
    result_str = _extract_result_text(result)
    if len(result_str) > _MAX_RESULT_CONTENT_LEN:
        result_str = result_str[:_MAX_RESULT_CONTENT_LEN] + "..."

    parts = [
        f"Tool: {tool_name} ({status}, {duration_ms:.0f}ms)",
        f"Arguments: {args_str}",
    ]

    if result_str:
        parts.append(f"Result: {result_str}")

    summary = "\n".join(parts)

    if len(summary) > _MAX_SUMMARY_LEN:
        summary = summary[:_MAX_SUMMARY_LEN] + "..."

    return summary


def is_important_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    result: "ToolResult",
    is_error: bool,
) -> bool:
    """判断工具调用是否值得存储.

    错误调用总是重要的（有学习价值）。
    成功调用需要结果内容足够有意义。

    Args:
        tool_name: 工具名称
        arguments: 调用参数
        result: 执行结果
        is_error: 是否出错

    Returns:
        bool: 是否重要
    """
    # 错误总是值得记录
    if is_error:
        return True

    # 检查结果内容是否有意义
    result_text = _extract_result_text(result)
    if len(result_text.strip()) < _MIN_MEANINGFUL_LEN:
        return False

    return True


def _format_arguments(arguments: dict[str, Any]) -> str:
    """格式化参数为可读字符串."""
    if not arguments:
        return "{}"

    try:
        formatted = json.dumps(arguments, ensure_ascii=False, default=str)
        if len(formatted) > 200:
            formatted = formatted[:200] + "..."
        return formatted
    except (TypeError, ValueError):
        return str(arguments)[:200]


def _extract_result_text(result: "ToolResult") -> str:
    """提取结果的文本内容."""
    from .types import TextContent

    if not result.content:
        return ""

    parts = []
    for c in result.content:
        if isinstance(c, TextContent):
            parts.append(c.text)

    return "\n".join(parts)


class ToolCallMemoryWriter:
    """工具调用记忆写入器.

    在工具调用完成后，将重要的调用结果写入 MemoryPort。
    支持去重和重要性过滤。

    Example:
        writer = ToolCallMemoryWriter(memory=memory_port)
        await writer.write_tool_call(
            trace_id="abc",
            tool_name="web_search",
            arguments={"query": "test"},
            result=result,
            is_error=False,
            duration_ms=200.0,
        )
    """

    def __init__(self, memory: "MemoryPort | None" = None):
        self._memory = memory
        self._seen_keys: set[str] = set()
        self._total_calls = 0
        self._stored_count = 0
        self._skipped_unimportant = 0
        self._skipped_duplicate = 0
        self._write_errors = 0

    def _dedup_key(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """生成去重键.

        基于工具名 + 参数的哈希值。

        Args:
            tool_name: 工具名称
            arguments: 调用参数

        Returns:
            str: 去重键
        """
        content = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
        return hashlib.md5(content.encode()).hexdigest()

    async def write_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        result: "ToolResult",
        is_error: bool,
        duration_ms: float,
    ) -> str | None:
        """将工具调用结果写入记忆.

        Args:
            trace_id: 追踪 ID
            tool_name: 工具名称
            arguments: 调用参数
            result: 执行结果
            is_error: 是否出错
            duration_ms: 执行耗时 (ms)

        Returns:
            str | None: 记忆 ID，如果跳过则返回 None
        """
        if self._memory is None:
            return None

        self._total_calls += 1

        # 重要性过滤
        if not is_important_tool_call(tool_name, arguments, result, is_error):
            self._skipped_unimportant += 1
            return None

        # 去重检查
        dedup_key = self._dedup_key(tool_name, arguments)
        if dedup_key in self._seen_keys:
            self._skipped_duplicate += 1
            return None

        # 生成摘要
        summary = generate_tool_call_summary(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            is_error=is_error,
            duration_ms=duration_ms,
        )

        # 构造元数据
        metadata = {
            "source": "tool_call",
            "tool_name": tool_name,
            "trace_id": trace_id,
            "is_error": is_error,
            "duration_ms": duration_ms,
        }

        try:
            entry_id = await self._memory.store(content=summary, metadata=metadata)
            self._seen_keys.add(dedup_key)
            self._stored_count += 1
            return entry_id
        except Exception as e:
            self._write_errors += 1
            logger.warning("Failed to store tool call memory: %s", e)
            return None

    def get_stats(self) -> dict[str, int]:
        """获取写入统计."""
        return {
            "total_calls": self._total_calls,
            "stored_count": self._stored_count,
            "skipped_unimportant": self._skipped_unimportant,
            "skipped_duplicate": self._skipped_duplicate,
            "write_errors": self._write_errors,
        }
