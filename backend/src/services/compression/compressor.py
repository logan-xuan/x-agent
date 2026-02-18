"""Context compressor for conversation history compression."""

from dataclasses import dataclass

from ...utils.logger import get_logger
from .token_counter import TokenCounter

logger = get_logger(__name__)


@dataclass
class CompressionResult:
    """Result of context compression."""
    
    compressed_messages: list[dict]   # Final message list (summary + retained)
    recent_messages: list[dict]       # Retained recent N messages
    archived_messages: list[dict]     # Archived messages
    summary: str                      # Generated summary
    original_token_count: int         # Original token count
    compressed_token_count: int       # Compressed token count


class ContextCompressor:
    """Context compressor using hybrid compression strategy.
    
    Strategy:
    1. Separate messages into archive zone and retention zone
    2. Generate summary for archived messages (for LLM context only)
    3. Build final message list with original system prompt + summary + retained messages
    
    Note: Summary is NOT stored to memory files. SmartMemoryService handles
    real-time memory storage independently.
    """
    
    def __init__(self, llm_service, token_counter: TokenCounter):
        """Initialize compressor.
        
        Args:
            llm_service: LLM service for summary generation
            token_counter: Token counter for statistics
        """
        self.llm = llm_service
        self.token_counter = token_counter
    
    async def compress(
        self,
        messages: list[dict],
        retention_count: int
    ) -> CompressionResult:
        """Compress conversation context.
        
        Args:
            messages: Full conversation history
            retention_count: Number of recent messages to retain
            
        Returns:
            Compression result with summary and retained messages
        """
        # 1. Separate archive and retention zones
        if len(messages) <= retention_count:
            # Not enough messages to compress
            return CompressionResult(
                compressed_messages=messages,
                recent_messages=messages,
                archived_messages=[],
                summary="",
                original_token_count=self.token_counter.count_messages(messages),
                compressed_token_count=self.token_counter.count_messages(messages)
            )
        
        # Extract and preserve system message if present
        system_message = None
        conversation_messages = messages
        if messages and messages[0].get("role") == "system":
            system_message = messages[0]
            conversation_messages = messages[1:]
        
        # Adjust retention count for conversation messages only
        actual_retention = min(retention_count, len(conversation_messages))
        
        archive_messages = conversation_messages[:-actual_retention] if actual_retention > 0 else conversation_messages
        recent_messages = conversation_messages[-actual_retention:] if actual_retention > 0 else []
        
        # 2. Generate summary for archived messages (for LLM context only)
        summary = await self._generate_summary(archive_messages) if archive_messages else ""
        
        # 3. Build compressed message list (preserving original system prompt)
        compressed_messages = self._build_compressed_messages(
            system_message, recent_messages, summary
        )
        
        return CompressionResult(
            compressed_messages=compressed_messages,
            recent_messages=recent_messages,
            archived_messages=archive_messages,
            summary=summary,
            original_token_count=self.token_counter.count_messages(messages),
            compressed_token_count=self.token_counter.count_messages(compressed_messages)
        )
    
    async def _generate_summary(self, messages: list[dict]) -> str:
        """Generate summary for archived messages using LLM.
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Generated summary text
        """
        # Build conversation text
        conversation_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in messages
        ])
        
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
            response = await self.llm.complete(prompt)
            summary = response.content.strip()
            logger.info(
                "Summary generated successfully",
                extra={
                    "summary_length": len(summary),
                    "archived_message_count": len(messages),
                }
            )
            return summary
        except Exception as e:
            logger.error(
                "Failed to generate summary, using fallback",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "archived_message_count": len(messages),
                }
            )
            # Fallback: return a simple placeholder summary
            return f"[对话历史摘要] 共{len(messages)}轮对话"
    
    def _build_compressed_messages(
        self,
        system_message: dict | None,
        recent_messages: list[dict],
        summary: str
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
            compressed.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{summary}\n\n以上是对话的历史摘要，请结合当前对话理解上下文。"
            })
        
        # 3. Add retained recent messages
        compressed.extend(recent_messages)
        
        return compressed
