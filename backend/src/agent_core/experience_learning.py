"""经验学习模块.

提供经验检索、注入和提取功能，包括：
- 经验检索: LLM 调用前检索相关历史经验
- 格式化注入: 将经验格式化后注入 system prompt
- 经验提取: 对话结束后分析工具调用序列，提取模式
- 模式检测: 识别 retry-success 和 fallback-success 模式
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ports.memory_port import MemoryPort

logger = logging.getLogger(__name__)

# 经验注入最大条目数
_DEFAULT_MAX_ITEMS = 5
# 单条经验最大长度
_MAX_EXPERIENCE_LEN = 300
# 经验检索默认超时 (ms)
_DEFAULT_SEARCH_TIMEOUT_MS = 200


def format_experience_for_prompt(
    experiences: list[dict[str, Any]],
    max_items: int = _DEFAULT_MAX_ITEMS,
) -> str:
    """将检索到的经验格式化为可注入 prompt 的文本.

    Args:
        experiences: 经验列表
        max_items: 最大条目数

    Returns:
        str: 格式化后的文本，空字符串表示无经验
    """
    if not experiences:
        return ""

    items = experiences[:max_items]

    lines = ["[Relevant Experience]"]
    for i, exp in enumerate(items, 1):
        content = exp.get("content", "")
        if len(content) > _MAX_EXPERIENCE_LEN:
            content = content[:_MAX_EXPERIENCE_LEN] + "..."
        score = exp.get("score", 0)
        lines.append(f"{i}. (relevance: {score:.2f}) {content}")

    return "\n".join(lines)


def detect_retry_patterns(
    tool_call_logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """检测工具调用序列中的重试/回退模式.

    模式类型:
    - retry_success: 同一工具失败后再次调用成功
    - fallback_success: 工具 A 失败后使用工具 B 成功

    Args:
        tool_call_logs: 工具调用日志列表

    Returns:
        list[dict]: 检测到的模式列表
    """
    patterns: list[dict[str, Any]] = []

    for i in range(len(tool_call_logs) - 1):
        current = tool_call_logs[i]
        next_call = tool_call_logs[i + 1]

        if not current.get("is_error", False):
            continue

        # 后续调用成功
        if next_call.get("is_error", False):
            continue

        if current["tool_name"] == next_call["tool_name"]:
            # retry_success: 同一工具重试成功
            patterns.append({
                "pattern": "retry_success",
                "tool_name": current["tool_name"],
                "failed_args": current.get("arguments", {}),
                "success_args": next_call.get("arguments", {}),
                "error_summary": current.get("result_summary", ""),
                "success_summary": next_call.get("result_summary", ""),
            })
        else:
            # fallback_success: 回退到另一工具成功
            patterns.append({
                "pattern": "fallback_success",
                "tool_name": current["tool_name"],
                "fallback_tool": next_call["tool_name"],
                "failed_args": current.get("arguments", {}),
                "success_args": next_call.get("arguments", {}),
                "error_summary": current.get("result_summary", ""),
                "success_summary": next_call.get("result_summary", ""),
            })

    return patterns


class ExperienceLearner:
    """经验学习器.

    在 LLM 调用前检索相关经验，在对话结束后提取经验。

    Example:
        learner = ExperienceLearner(memory=memory_port)

        # LLM 调用前
        experiences = await learner.retrieve_experience("search Python async")
        prompt_addition = format_experience_for_prompt(experiences)

        # 对话结束后
        await learner.extract_experience(trace_id, tool_call_logs)
    """

    def __init__(
        self,
        memory: "MemoryPort | None" = None,
        search_timeout_ms: int = _DEFAULT_SEARCH_TIMEOUT_MS,
    ):
        self._memory = memory
        self._search_timeout_s = search_timeout_ms / 1000.0

    async def retrieve_experience(
        self,
        query: str,
        tool_names: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """检索相关经验.

        Args:
            query: 查询文本（通常是用户消息或工具描述）
            tool_names: 限定工具名称（可选）
            limit: 最大返回数

        Returns:
            list[dict]: 经验列表
        """
        if self._memory is None:
            return []

        filters = {}
        if tool_names:
            filters["tool_names"] = tool_names

        try:
            results = await asyncio.wait_for(
                self._memory.search(
                    query=query,
                    limit=limit,
                    filters=filters if filters else None,
                ),
                timeout=self._search_timeout_s,
            )
            return results
        except asyncio.TimeoutError:
            logger.warning("Experience search timed out (%.0fms)", self._search_timeout_s * 1000)
            return []
        except Exception as e:
            logger.warning("Experience search failed: %s", e)
            return []

    async def extract_experience(
        self,
        trace_id: str,
        tool_call_logs: list[dict[str, Any]],
    ) -> int:
        """从工具调用序列中提取经验.

        分析工具调用序列，检测重试/回退模式，存储到记忆。

        Args:
            trace_id: 追踪 ID
            tool_call_logs: 工具调用日志列表

        Returns:
            int: 提取并存储的经验数量
        """
        if self._memory is None:
            return 0

        if not tool_call_logs:
            return 0

        patterns = detect_retry_patterns(tool_call_logs)

        stored_count = 0
        for pattern in patterns:
            content = _format_pattern_for_storage(pattern)
            metadata = {
                "source": "experience",
                "pattern_type": pattern["pattern"],
                "trace_id": trace_id,
                "tool_name": pattern["tool_name"],
            }

            try:
                await self._memory.store(content=content, metadata=metadata)
                stored_count += 1
            except Exception as e:
                logger.warning("Failed to store experience: %s", e)

        return stored_count


def _format_pattern_for_storage(pattern: dict[str, Any]) -> str:
    """格式化模式为存储文本."""
    if pattern["pattern"] == "retry_success":
        return (
            f"[Retry Success] Tool '{pattern['tool_name']}' failed initially "
            f"({pattern.get('error_summary', 'unknown error')}), "
            f"then succeeded on retry ({pattern.get('success_summary', '')})."
        )
    elif pattern["pattern"] == "fallback_success":
        return (
            f"[Fallback Success] Tool '{pattern['tool_name']}' failed "
            f"({pattern.get('error_summary', 'unknown error')}), "
            f"then tool '{pattern.get('fallback_tool', '')}' succeeded "
            f"({pattern.get('success_summary', '')})."
        )
    else:
        return f"[Pattern] {pattern}"
