"""Context compressor for conversation history compression.

压缩模块不直接依赖任何 LLM 接口，而是通过 SummaryFn 回调生成摘要，
由调用方（adapter）负责提供具体的 LLM 调用实现。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ...utils.logger import get_logger
from .token_counter import TokenCounter

logger = get_logger(__name__)

# 摘要生成回调类型: 接收 prompt 文本，返回摘要文本
SummaryFn = Callable[[str], Awaitable[str]]


@dataclass
class CompressionResult:
    """Result of context compression."""

    compressed_messages: list[dict]  # Final message list (summary + retained)
    recent_messages: list[dict]  # Retained recent N messages
    archived_messages: list[dict]  # Archived messages
    summary: str  # Generated summary
    original_token_count: int  # Original token count
    compressed_token_count: int  # Compressed token count


class ContextCompressor:
    """Context compressor using hybrid compression strategy.

    Strategy:
    1. Separate messages into archive zone and retention zone
    2. Generate summary for archived messages (for LLM context only)
    3. Build final message list with original system prompt + summary + retained messages

    Note: Summary is NOT stored to memory files. SmartMemoryService handles
    real-time memory storage independently.
    """

    def __init__(self, summary_fn: SummaryFn, token_counter: TokenCounter):
        """Initialize compressor.

        Args:
            summary_fn: Async callback that takes a prompt string and returns summary text.
                        Caller is responsible for providing the actual LLM call implementation.
            token_counter: Token counter for statistics
        """
        self._summary_fn = summary_fn
        self.token_counter = token_counter

    _SUMMARY_MARKER = "[历史对话摘要]"

    async def compress(self, messages: list[dict], retention_count: int) -> CompressionResult:
        """Compress conversation context.

        采用「摘要拼接」策略避免信息失真：
        - 识别并剥离上一次压缩注入的旧摘要 system 消息
        - 只对新产生的 user/assistant 对话生成增量摘要
        - 将旧摘要与增量摘要拼接，保留完整历史上下文

        Args:
            messages: Full conversation history
            retention_count: Number of recent messages to retain

        Returns:
            Compression result with summary and retained messages
        """
        # 1. Separate archive and retention zones
        if len(messages) <= retention_count:
            return CompressionResult(
                compressed_messages=messages,
                recent_messages=messages,
                archived_messages=[],
                summary="",
                original_token_count=self.token_counter.count_messages(messages),
                compressed_token_count=self.token_counter.count_messages(messages),
            )

        # Extract and preserve original system prompt (AGENTS.md)
        system_message = None
        conversation_messages = messages
        if messages and messages[0].get("role") == "system":
            system_message = messages[0]
            conversation_messages = messages[1:]

        # 剥离上一次压缩注入的旧摘要 system 消息，避免"摘要的摘要"失真
        previous_summary, conversation_messages = self._extract_previous_summary(
            conversation_messages
        )

        # Adjust retention count for conversation messages only
        actual_retention = min(retention_count, len(conversation_messages))

        # Find safe split point that doesn't break tool_calls/tool pairs
        split_index = (
            len(conversation_messages) - actual_retention
            if actual_retention > 0
            else len(conversation_messages)
        )
        split_index = self._find_safe_split_point(conversation_messages, split_index)

        archive_messages = conversation_messages[:split_index]
        recent_messages = conversation_messages[split_index:]

        # 2. 只对新产生的对话消息生成增量摘要
        incremental_summary = (
            await self._generate_summary(archive_messages) if archive_messages else ""
        )

        # 3. 将旧摘要与增量摘要拼接，保留完整历史上下文
        combined_summary = self._merge_summaries(previous_summary, incremental_summary)

        # 4. Build compressed message list
        compressed_messages = self._build_compressed_messages(
            system_message, recent_messages, combined_summary
        )

        return CompressionResult(
            compressed_messages=compressed_messages,
            recent_messages=recent_messages,
            archived_messages=archive_messages,
            summary=combined_summary,
            original_token_count=self.token_counter.count_messages(messages),
            compressed_token_count=self.token_counter.count_messages(compressed_messages),
        )

    def _extract_previous_summary(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """从消息列表中剥离上一次压缩注入的摘要 system 消息.

        上一次压缩会在消息列表中插入一条 role=system、content 以
        "[历史对话摘要]" 开头的消息。本方法将其识别并提取出来，
        返回旧摘要文本和剩余的纯对话消息。

        Args:
            messages: 对话消息列表（不含原始 system prompt）

        Returns:
            (旧摘要文本, 去除摘要后的消息列表)
        """
        previous_summary = ""
        remaining_messages = []

        for msg in messages:
            content = msg.get("content", "")
            if msg.get("role") == "system" and self._SUMMARY_MARKER in content:
                # 提取摘要正文：去掉标记行和尾部提示
                summary_text = content.replace(self._SUMMARY_MARKER, "").strip()
                trailing_hint = "以上是对话的历史摘要，请结合当前对话理解上下文。"
                summary_text = summary_text.replace(trailing_hint, "").strip()
                previous_summary = summary_text
            else:
                remaining_messages.append(msg)

        if previous_summary:
            logger.info(
                "Extracted previous summary from messages",
                extra={"previous_summary_length": len(previous_summary)},
            )

        return previous_summary, remaining_messages

    @staticmethod
    def _merge_summaries(previous_summary: str, incremental_summary: str) -> str:
        """将旧摘要与增量摘要拼接为完整摘要.

        策略：
        - 如果只有一个非空，直接返回
        - 如果两个都非空，用分隔符拼接，保留完整历史脉络

        Args:
            previous_summary: 上一次压缩保留的旧摘要
            incremental_summary: 本次新生成的增量摘要

        Returns:
            合并后的完整摘要
        """
        if not previous_summary:
            return incremental_summary
        if not incremental_summary:
            return previous_summary

        return f"{previous_summary}\n\n---\n\n{incremental_summary}"

    def _find_safe_split_point(self, messages: list[dict], initial_split: int) -> int:
        """找到安全的分割点，确保不会拆分 tool_calls/tool 消息配对.

        LLM API 要求 role="tool" 的消息前面必须有对应的 assistant（带 tool_calls）消息。
        如果初始分割点把 assistant（带 tool_calls）放到归档区，而 tool 结果留在保留区，
        就会导致 API 400 错误。

        策略：从初始分割点向前扫描，如果保留区开头是 tool 消息，
        就把分割点前移到对应的 assistant（带 tool_calls）消息之前。

        Args:
            messages: 对话消息列表（不含 system message）
            initial_split: 初始分割索引

        Returns:
            安全的分割索引
        """
        if initial_split <= 0 or initial_split >= len(messages):
            return initial_split

        split = initial_split

        # 向前扫描：如果保留区开头是 tool 消息，需要把对应的 assistant 也纳入保留区
        while split > 0 and messages[split].get("role") == "tool":
            split -= 1

        # 此时 split 可能指向 assistant（带 tool_calls），这正是我们需要的——
        # 它和后面的 tool 消息是一组，必须一起保留在保留区

        return split

    async def _generate_summary(self, messages: list[dict]) -> str:
        """Generate summary for archived messages via summary_fn callback.

        Args:
            messages: Messages to summarize

        Returns:
            Generated summary text
        """
        conversation_text = "\n".join(
            [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in messages]
        )

        prompt = f"""请对以下对话历史生成简洁的摘要：

对话历史：
{conversation_text}

要求：
1. 用3-5句话概括主要内容
2. 保留重要的决策、约定和待办事项
3. 保留用户的关键需求和偏好
4. 使用第三人称客观描述

摘要："""

        try:
            summary = await self._summary_fn(prompt)
            summary = summary.strip()
            logger.info(
                "Summary generated successfully",
                extra={
                    "summary_length": len(summary),
                    "archived_message_count": len(messages),
                },
            )
            return summary
        except Exception as e:
            logger.error(
                "Failed to generate summary, using fallback",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "archived_message_count": len(messages),
                },
            )
            return f"[对话历史摘要] 共{len(messages)}轮对话"

    def _build_compressed_messages(
        self, system_message: dict | None, recent_messages: list[dict], summary: str
    ) -> list[dict]:
        """Build final compressed message list.

        Args:
            system_message: Original system message (from AGENTS.md)
            recent_messages: Recent messages to retain
            summary: Generated summary

        Returns:
            Final message list with:
            1. Original system prompt (preserved)
            2. Summary as context (inserted as system message)
            3. Retained recent messages
        """
        compressed = []

        # 1. Preserve original system prompt (from AGENTS.md)
        if system_message:
            compressed.append(system_message)

        # 2. Add summary as context (separate from system prompt)
        if summary:
            compressed.append(
                {
                    "role": "system",
                    "content": f"[历史对话摘要]\n{summary}\n\n以上是对话的历史摘要，请结合当前对话理解上下文。",
                }
            )

        # 3. Add retained recent messages
        compressed.extend(recent_messages)

        return compressed
