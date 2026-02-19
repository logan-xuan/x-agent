"""Context compression manager - main entry point."""

import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from uuid import uuid4

from ...config.models import CompressionConfig
from ...utils.logger import get_logger
from .compressor import CompressionResult, ContextCompressor
from .token_counter import TokenCounter
from ...models.compression import CompressionEvent
from ...services.storage import get_storage_service

logger = get_logger(__name__)


@dataclass
class PreparedContext:
    """Prepared context for LLM."""
    
    messages: list[dict]              # Final message list
    summary: str | None = None        # Summary if compression occurred
    total_tokens: int = 0             # Total token count


class ContextCompressionManager:
    """Context compression manager - main entry point.
    
    Handles:
    - Token counting and budget management
    - Compression triggering logic
    - Context preparation for LLM
    
    Note: 
    - Configuration is read dynamically from ConfigManager to support hot-reload.
    - Summary is NOT stored to memory files to avoid duplication with SmartMemoryService,
      which already analyzes and records important content in real-time.
    """
    
    def __init__(self, config: CompressionConfig, workspace_path: str, llm_service=None):
        """Initialize compression manager.
        
        Args:
            config: Compression configuration (initial value, will be read dynamically)
            workspace_path: Path to workspace directory
            llm_service: Optional LLM service for summary generation
        """
        # Store reference to read config dynamically for hot-reload support
        self._initial_config = config
        self.workspace_path = Path(workspace_path)
        self.token_counter = TokenCounter()
        self.llm_service = llm_service
        
        # Initialize compressor if LLM service is available
        if llm_service:
            self.compressor = ContextCompressor(llm_service, self.token_counter)
        else:
            self.compressor = None
        
        logger.info(
            "ContextCompressionManager initialized",
            extra={
                "threshold_rounds": self.config.threshold_rounds,
                "threshold_tokens": self.config.threshold_tokens,
                "retention_count": self.config.retention_count,
            }
        )
    
    @property
    def config(self) -> CompressionConfig:
        """Get current configuration, reading from ConfigManager for hot-reload support."""
        try:
            from ...config.manager import ConfigManager
            return ConfigManager().config.compression
        except Exception:
            # Fallback to initial config if ConfigManager fails
            return self._initial_config
    
    async def prepare_context(
        self,
        session_id: str,
        current_messages: list[dict],
        system_prompt: str = ""
    ) -> PreparedContext:
        """Prepare context for LLM, compressing if needed.
        
        Args:
            session_id: Session identifier
            current_messages: Current conversation messages
            system_prompt: System prompt text
            
        Returns:
            Prepared context with optional compression
        """
        # 1. Calculate current token usage
        total_tokens = self.token_counter.count_messages(current_messages)
        if system_prompt:
            total_tokens += self.token_counter.count_text(system_prompt)
        
        # 2. Check if compression is needed
        needs_compression = self._check_compression_needed(
            len(current_messages),
            total_tokens
        )
        
        # Always log compression check details for debugging
        logger.info(
            "Compression check",
            extra={
                "session_id": session_id,
                "message_count": len(current_messages),
                "token_count": total_tokens,
                "threshold_rounds": self.config.threshold_rounds,
                "threshold_tokens": self.config.threshold_tokens,
                "needs_compression": needs_compression,
            }
        )
        
        if not needs_compression:
            return PreparedContext(
                messages=current_messages,
                summary=None,
                total_tokens=total_tokens
            )
        
        # 3. Execute compression
        logger.info(
            "Compression triggered",
            extra={
                "session_id": session_id,
                "message_count": len(current_messages),
                "token_count": total_tokens,
            }
        )
        
        return await self._compress_context(session_id, current_messages)
    
    async def _compress_context(
        self,
        session_id: str,
        messages: list[dict]
    ) -> PreparedContext:
        """Execute compression flow.

        Args:
            session_id: Session identifier
            messages: Messages to compress

        Returns:
            Compressed context
        """
        if not self.compressor:
            logger.warning(
                "Compression requested but no LLM service available",
                extra={"session_id": session_id}
            )
            # Return original messages if no compressor
            return PreparedContext(
                messages=messages,
                summary=None,
                total_tokens=self.token_counter.count_messages(messages)
            )

        # 1. Compress
        result = await self.compressor.compress(
            messages,
            self.config.retention_count
        )

        # 2. Store compression event to track history
        await self._store_compression_event(
            session_id=session_id,
            original_messages=messages,
            compressed_result=result
        )

    async def _store_compression_event(
        self,
        session_id: str,
        original_messages: list[dict],
        compressed_result: CompressionResult
    ) -> None:
        """Store compression event to database for audit and analysis.

        Args:
            session_id: Session identifier
            original_messages: Original messages before compression
            compressed_result: Result of compression operation
        """
        try:
            from datetime import datetime
            import uuid

            # Generate unique ID for this compression event
            event_id = f"comp-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"

            # Prepare compression event data
            compression_event = CompressionEvent(
                id=event_id,
                session_id=session_id,
                original_message_count=len(original_messages),
                compressed_message_count=len(compressed_result.compressed_messages),
                original_token_count=compressed_result.original_token_count,
                compressed_token_count=compressed_result.compressed_token_count,
                compression_ratio=(
                    (compressed_result.original_token_count - compressed_result.compressed_token_count) /
                    compressed_result.original_token_count
                    if compressed_result.original_token_count > 0 else 0
                ),
                original_messages=json.dumps(original_messages, ensure_ascii=False),
                compressed_messages=json.dumps(compressed_result.compressed_messages, ensure_ascii=False),
                archived_message_count=len(compressed_result.archived_messages),
                retained_message_count=len(compressed_result.recent_messages)
            )

            # Store in database
            storage = get_storage_service()
            async with storage.session() as db:
                db.add(compression_event)
                await db.commit()

            logger.info(
                "Compression event stored to database",
                extra={
                    "event_id": event_id,
                    "session_id": session_id,
                    "original_message_count": len(original_messages),
                    "compressed_message_count": len(compressed_result.compressed_messages),
                }
            )

        except Exception as e:
            logger.error(
                "Failed to store compression event",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )

        # Note: Summary is NOT stored to memory files to avoid duplication.
        # SmartMemoryService already analyzes and records important content in real-time.
        # The summary generated here is only used for LLM context understanding.

        logger.info(
            "Compression completed",
            extra={
                "session_id": session_id,
                "original_tokens": result.original_token_count,
                "compressed_tokens": result.compressed_token_count,
                "archived_count": len(result.archived_messages),
                "retained_count": len(result.recent_messages),
            }
        )

        return PreparedContext(
            messages=result.compressed_messages,
            summary=result.summary,
            total_tokens=result.compressed_token_count
        )
    
    def _check_compression_needed(
        self,
        message_count: int,
        token_count: int
    ) -> bool:
        """Check if compression is needed.
        
        Args:
            message_count: Number of messages
            token_count: Number of tokens
            
        Returns:
            True if compression is needed
        """
        return (
            message_count > self.config.threshold_rounds or
            token_count > self.config.threshold_tokens
        )
