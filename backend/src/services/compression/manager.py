"""Context compression manager - main entry point."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from uuid import uuid4

from ...config.models import CompressionConfig
from ...utils.logger import get_logger
from .compressor import CompressionResult, ContextCompressor, SummaryFn
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
    was_compressed: bool = False
    quality_rejected: bool = False


@dataclass
class CompressionBudgetProfile:
    """Runtime compression budget resolved from the active model configuration."""

    provider_name: str = ""
    model_id: str = ""
    model_context_limit_tokens: int = 0
    model_output_limit_tokens: int = 0
    reserved_output_tokens: int = 0
    safety_margin_tokens: int = 0
    hard_context_limit_tokens: int = 0
    trigger_tokens: int = 0


@dataclass
class _CompressionCache:
    """缓存某个 session 上次压缩的结果.

    用于判断新消息是否需要再次压缩：
    - compressed_message_count: 上次压缩时的原始消息总数
    - summary: 上次压缩生成的摘要文本
    - compressed_messages: 上次压缩后的完整消息列表（含摘要）
    """

    compressed_message_count: int     # 上次压缩时的原始消息总数
    summary: str                      # 上次压缩生成的摘要
    compressed_messages: list[dict]   # 上次压缩后的完整消息列表


class ContextCompressionManager:
    """Context compression manager - main entry point.
    
    Handles:
    - Token counting and budget management
    - Compression triggering logic
    - Context preparation for LLM
    
    Note: 
    - Configuration is read dynamically from ConfigManager to support hot-reload.
    - Compression summary is only used for LLM context understanding.
    - Important info is archived to long-term memory via MemoryManager before compression.
    """
    
    def __init__(
        self,
        config: CompressionConfig,
        workspace_path: str,
        summary_fn: SummaryFn | None = None,
        budget_resolver: Callable[[], CompressionBudgetProfile | None] | None = None,
    ):
        """Initialize compression manager.

        Args:
            config: Compression configuration (initial value, will be read dynamically)
            workspace_path: Path to workspace directory
            summary_fn: Async callback for summary generation (prompt -> summary text).
                        If None, compression will skip summary generation.
        """
        self._initial_config = config
        self.workspace_path = Path(workspace_path)
        self.token_counter = TokenCounter()
        self._budget_resolver = budget_resolver

        # 缓存每个 session 的上次压缩结果
        # key: session_id, value: _CompressionCache
        self._compression_cache: dict[str, _CompressionCache] = {}

        if summary_fn:
            self.compressor = ContextCompressor(summary_fn, self.token_counter)
        else:
            self.compressor = None
        
        logger.info(
            "ContextCompressionManager initialized",
            extra={
                "threshold_rounds": self.config.threshold_rounds,
                "threshold_tokens": self.config.threshold_tokens,
                "max_context_tokens": self.config.max_context_tokens,
                "max_tool_message_chars": self.config.max_tool_message_chars,
                "retention_count": self.config.retention_count,
            }
        )

    def _resolve_budget_profile(self) -> CompressionBudgetProfile | None:
        """Resolve runtime compression budget from the active model."""
        if self._budget_resolver is None:
            return None

        try:
            return self._budget_resolver()
        except Exception as exc:
            logger.warning(
                "Failed to resolve compression budget profile, falling back to static thresholds",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            return None
    
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
        system_prompt: str = "",
        tools: list[dict] | None = None,
    ) -> PreparedContext:
        """Prepare context for LLM, compressing if needed.

        采用缓存策略避免重复压缩：
        - 如果有缓存且新消息数未超阈值，直接用缓存的摘要 + 新消息构建上下文
        - 如果新消息数超阈值，重新压缩并更新缓存

        Args:
            session_id: Session identifier
            current_messages: Current conversation messages (from DB, no summary)
            system_prompt: System prompt text
            tools: OpenAI function/tool schema definitions for this request

        Returns:
            Prepared context with optional compression
        """
        cache = self._compression_cache.get(session_id)

        # 如果内存缓存为空，尝试从数据库恢复上次压缩记录
        if cache is None:
            cache = await self._load_cache_from_db(session_id)
            if cache:
                self._compression_cache[session_id] = cache

        # 计算新消息数：如果有缓存，只算缓存之后新增的消息
        if cache:
            new_message_count = len(current_messages) - cache.compressed_message_count
            new_messages = current_messages[cache.compressed_message_count:]
            new_token_count = self.token_counter.count_messages(new_messages)
        else:
            new_message_count = len(current_messages)
            new_token_count = self.token_counter.count_messages(current_messages)

        tool_tokens = self.token_counter.count_tool_definitions(tools)
        total_tokens = self.token_counter.count_messages(current_messages)
        if system_prompt:
            total_tokens += self.token_counter.count_text(system_prompt)
        total_tokens += tool_tokens

        budget_profile = self._resolve_budget_profile()
        hard_context_limit = self.config.max_context_tokens
        effective_trigger_tokens = min(
            hard_context_limit,
            max(
                self.config.threshold_tokens,
                int(hard_context_limit * self.config.trigger_ratio),
            ),
        )
        if budget_profile:
            hard_context_limit = budget_profile.hard_context_limit_tokens or hard_context_limit
            dynamic_trigger_tokens = budget_profile.trigger_tokens or hard_context_limit
            effective_trigger_tokens = min(
                hard_context_limit,
                max(self.config.threshold_tokens, dynamic_trigger_tokens),
            )

        needs_compression = (
            new_message_count > self.config.threshold_rounds
            or new_token_count > self.config.threshold_tokens
            or total_tokens > effective_trigger_tokens
        )

        logger.info(
            "Compression check",
            extra={
                "session_id": session_id,
                "message_count": len(current_messages),
                "new_message_count": new_message_count,
                "token_count": total_tokens,
                "new_token_count": new_token_count,
                "tool_count": len(tools or []),
                "tool_tokens": tool_tokens,
                "has_cache": cache is not None,
                "threshold_rounds": self.config.threshold_rounds,
                "threshold_tokens": self.config.threshold_tokens,
                "configured_max_context_tokens": self.config.max_context_tokens,
                "hard_context_limit_tokens": hard_context_limit,
                "effective_trigger_tokens": effective_trigger_tokens,
                "budget_provider_name": budget_profile.provider_name if budget_profile else None,
                "budget_model_id": budget_profile.model_id if budget_profile else None,
                "budget_reserved_output_tokens": budget_profile.reserved_output_tokens if budget_profile else None,
                "budget_safety_margin_tokens": budget_profile.safety_margin_tokens if budget_profile else None,
                "needs_compression": needs_compression,
            },
        )

        if not needs_compression:
            if cache:
                # 有缓存但不需要再次压缩：用缓存的压缩结果 + 新消息构建上下文
                new_messages = current_messages[cache.compressed_message_count:]
                merged_messages = list(cache.compressed_messages) + new_messages
                return PreparedContext(
                    messages=merged_messages,
                    summary=cache.summary,
                    total_tokens=(
                        self.token_counter.count_messages(merged_messages)
                        + self.token_counter.count_text(system_prompt)
                        + tool_tokens
                    ),
                    was_compressed=bool(cache.summary),
                )
            return PreparedContext(
                messages=current_messages,
                summary=None,
                total_tokens=total_tokens,
            )

        # 需要压缩
        logger.info(
            "Compression triggered",
            extra={
                "session_id": session_id,
                "message_count": len(current_messages),
                "new_message_count": new_message_count,
                "token_count": total_tokens,
                "tool_count": len(tools or []),
                "tool_tokens": tool_tokens,
            },
        )

        # 如果有缓存，构建包含旧摘要的消息列表再压缩（增量压缩）
        if cache:
            messages_for_compression = list(cache.compressed_messages) + current_messages[cache.compressed_message_count:]
        else:
            messages_for_compression = current_messages

        result = await self._compress_context(session_id, messages_for_compression)

        if result.was_compressed and not result.quality_rejected:
            self._compression_cache[session_id] = _CompressionCache(
                compressed_message_count=len(current_messages),
                summary=result.summary or "",
                compressed_messages=list(result.messages),
            )

        return PreparedContext(
            messages=result.messages,
            summary=result.summary,
            total_tokens=(
                result.total_tokens
                + self.token_counter.count_text(system_prompt)
                + tool_tokens
            ),
            was_compressed=result.was_compressed,
            quality_rejected=result.quality_rejected,
        )
    
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
                total_tokens=self.token_counter.count_messages(messages),
                was_compressed=False,
            )

        # 1. Archive important info before compression
        await self._archive_before_compression(session_id, messages)

        # 2. Compress
        result = await self.compressor.compress(
            messages,
            self.config.retention_count
        )

        quality_passed = self._passes_quality_gate(result)
        if quality_passed:
            await self._store_compression_event(
                session_id=session_id,
                original_messages=messages,
                compressed_result=result
            )
        else:
            logger.warning(
                "Compression quality gate rejected result",
                extra={
                    "session_id": session_id,
                    "original_token_count": result.original_token_count,
                    "compressed_token_count": result.compressed_token_count,
                    "compression_ratio": self._compression_ratio(result),
                    "token_savings": result.original_token_count - result.compressed_token_count,
                    "min_compression_ratio": self.config.min_compression_ratio,
                    "min_token_savings": self.config.min_token_savings,
                },
            )
            return PreparedContext(
                messages=messages,
                summary=None,
                total_tokens=self.token_counter.count_messages(messages),
                was_compressed=False,
                quality_rejected=True,
            )

        # 4. Return prepared context with compressed results
        return PreparedContext(
            messages=result.compressed_messages,
            summary=result.summary,
            total_tokens=result.compressed_token_count,
            was_compressed=True,
        )

    def _passes_quality_gate(self, result: CompressionResult) -> bool:
        """Validate whether a compression result is worth accepting."""
        if not self.config.compression_quality_gate_enabled:
            return True

        savings = result.original_token_count - result.compressed_token_count
        ratio = self._compression_ratio(result)
        return (
            savings >= self.config.min_token_savings
            or ratio >= self.config.min_compression_ratio
        )

    @staticmethod
    def _compression_ratio(result: CompressionResult) -> float:
        if result.original_token_count <= 0:
            return 0.0
        return (
            (result.original_token_count - result.compressed_token_count)
            / result.original_token_count
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
            compression_ratio = (
                (compressed_result.original_token_count - compressed_result.compressed_token_count) /
                compressed_result.original_token_count
                if compressed_result.original_token_count > 0 else 0
            )
            compression_event = CompressionEvent(
                id=event_id,
                session_id=session_id,
                original_message_count=len(original_messages),
                compressed_message_count=len(compressed_result.compressed_messages),
                original_token_count=compressed_result.original_token_count,
                compressed_token_count=compressed_result.compressed_token_count,
                compression_ratio=compression_ratio,
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

    async def _archive_before_compression(
        self,
        session_id: str,
        messages: list[dict],
    ) -> None:
        """压缩前通过 MemoryManager 归档重要信息到长期记忆.

        从即将被压缩的消息中提取关键信息，写入 MEMORY.md 和向量库，
        避免压缩后丢失重要上下文。归档失败不影响压缩流程。

        Args:
            session_id: 会话标识符
            messages: 即将被压缩的消息列表
        """
        if not messages:
            return

        try:
            from ...memory.manager import get_memory_manager
            memory_manager = get_memory_manager()
            archived = await memory_manager.archive_before_compression(
                messages=messages,
                session_id=session_id,
            )
            if archived:
                logger.info(
                    "Important info archived before compression",
                    extra={
                        "session_id": session_id,
                        "archived_count": len(archived),
                    },
                )
        except RuntimeError:
            # MemoryManager not initialized yet — skip silently
            pass
        except Exception as exc:
            logger.warning(
                "Failed to archive before compression (non-fatal)",
                extra={
                    "session_id": session_id,
                    "error": str(exc),
                },
            )

    async def _load_cache_from_db(self, session_id: str) -> _CompressionCache | None:
        """从数据库加载该 session 最近一次压缩记录，恢复缓存.

        ContextCompressionManager 每次请求都会被重新创建，内存缓存会丢失。
        通过从 CompressionEvent 表读取上次压缩的 compressed_messages 和
        original_message_count，可以恢复缓存状态，避免重复压缩。

        Args:
            session_id: 会话标识符

        Returns:
            _CompressionCache 或 None（无历史压缩记录时）
        """
        try:
            from sqlalchemy import select

            storage = get_storage_service()
            async with storage.session() as db:
                result = await db.execute(
                    select(CompressionEvent)
                    .where(CompressionEvent.session_id == session_id)
                    .order_by(CompressionEvent.compression_time.desc())
                    .limit(1)
                )
                event = result.scalar_one_or_none()

            if event is None:
                return None

            compressed_messages: list[dict] = json.loads(
                str(event.compressed_messages)
            )
            original_message_count: int = int(event.original_message_count)  # type: ignore[arg-type]

            logger.info(
                "Compression cache restored from database",
                extra={
                    "session_id": session_id,
                    "event_id": event.id,
                    "original_message_count": original_message_count,
                    "compressed_message_count": len(compressed_messages),
                },
            )

            # 从 compressed_messages 中提取摘要文本
            summary = ""
            for msg in compressed_messages:
                if (
                    msg.get("role") == "system"
                    and self._SUMMARY_MARKER in (msg.get("content") or "")
                ):
                    summary = msg.get("content", "")
                    break

            return _CompressionCache(
                compressed_message_count=original_message_count,
                summary=summary,
                compressed_messages=compressed_messages,
            )

        except Exception as exc:
            logger.warning(
                "Failed to load compression cache from database",
                extra={
                    "session_id": session_id,
                    "error": str(exc),
                },
            )
            return None

    _SUMMARY_MARKER = "[历史对话摘要]"
