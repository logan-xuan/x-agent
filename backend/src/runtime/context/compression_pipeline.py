"""Compression pipeline for runtime context management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..types import ArtifactRef, BudgetSnapshot, TaskFrame
from .artifact_store import ArtifactWriteRequest, InMemoryArtifactStore
from .compression_verifier import (
    CompressionPostCheck,
    CompressionVerifyRequest,
    DefaultCompressionVerifier,
)

from .memory_flush import MemoryFlushRequest, NoopMemoryFlusher


@dataclass
class CompressionPersistConfig:
    single_result_chars: int = 50000
    aggregate_result_chars: int = 200000
    artifact_preview_chars: int = 2000
    artifact_preview_head_chars: int = 900
    artifact_preview_tail_chars: int = 700


@dataclass
class CompressionPressureConfig:
    yellow_pct: float = 0.50
    orange_pct: float = 0.68
    red_pct: float = 0.82
    hard_stop_pct: float = 0.90


@dataclass
class CompressionPruningConfig:
    enabled: bool = True
    ttl_ms: int = 300000
    preserve_recent_assistants: int = 3
    min_prunable_tool_chars: int = 50000
    soft_trim_max_chars: int = 4000
    soft_trim_head_chars: int = 1500
    soft_trim_tail_chars: int = 1500
    hard_clear_enabled: bool = True
    hard_clear_placeholder: str = "[Old tool result content cleared]"


@dataclass
class CompressionMicrocompactConfig:
    enabled: bool = True
    trigger_pct: float = 0.50
    max_units_per_pass: int = 8
    preserve_error_results: bool = True


@dataclass
class CompressionCollapseConfig:
    enabled: bool = True
    trigger_pct: float = 0.68
    max_segment_tokens: int = 12000
    min_segment_turns: int = 2


@dataclass
class CompressionAutocompactConfig:
    enabled: bool = True
    trigger_pct: float = 0.82
    reserve_tokens_floor: int = 20000
    max_history_share: float = 0.50
    fallback_summary_max_chars: int = 8000


@dataclass
class CompressionMemoryFlushConfig:
    enabled: bool = True
    soft_threshold_tokens: int = 4000


@dataclass
class CompressionQualityConfig:
    min_compression_gain_tokens: int = 0
    require_post_check: bool = True
    rollback_on_invariant_failure: bool = True


@dataclass
class CompressionProfile:
    mode: str = "balanced"
    pressure: CompressionPressureConfig = field(default_factory=CompressionPressureConfig)
    persist: CompressionPersistConfig = field(default_factory=CompressionPersistConfig)
    pruning: CompressionPruningConfig = field(default_factory=CompressionPruningConfig)
    microcompact: CompressionMicrocompactConfig = field(default_factory=CompressionMicrocompactConfig)
    collapse: CompressionCollapseConfig = field(default_factory=CompressionCollapseConfig)
    autocompact: CompressionAutocompactConfig = field(default_factory=CompressionAutocompactConfig)
    memory_flush: CompressionMemoryFlushConfig = field(default_factory=CompressionMemoryFlushConfig)
    quality: CompressionQualityConfig = field(default_factory=CompressionQualityConfig)
    retain_recent_messages: int = 12


@dataclass
class CompressionContext:
    session_key: str
    turn: int
    task_frame: TaskFrame
    profile: CompressionProfile
    model_context_window: int
    estimated_input_tokens: int
    messages: list[dict[str, Any]]
    active_artifacts: list[ArtifactRef]
    budget: BudgetSnapshot
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompressionResult:
    messages: list[dict[str, Any]]
    active_artifacts: list[ArtifactRef]
    estimated_input_tokens: int
    operations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    verifier_result: CompressionPostCheck | None = None
    rollback_applied: bool = False
    rollback_reason: str | None = None


@dataclass
class DefaultCompressionPipeline:
    """Apply bounded context compression stages in a predictable order."""

    artifact_store: InMemoryArtifactStore = field(default_factory=InMemoryArtifactStore)
    verifier: DefaultCompressionVerifier = field(default_factory=DefaultCompressionVerifier)
    memory_flusher: NoopMemoryFlusher = field(default_factory=NoopMemoryFlusher)

    async def run(self, ctx: CompressionContext) -> CompressionResult:
        """Run the normal compression pipeline."""
        messages = [dict(message) for message in ctx.messages]
        artifacts = list(ctx.active_artifacts)
        operations: list[str] = []
        original_messages = [dict(message) for message in ctx.messages]
        original_artifacts = list(ctx.active_artifacts)
        self.artifact_store.configure_preview(
            preview_chars=ctx.profile.persist.artifact_preview_chars,
            preview_head_chars=ctx.profile.persist.artifact_preview_head_chars,
            preview_tail_chars=ctx.profile.persist.artifact_preview_tail_chars,
        )

        messages, artifacts, persist_applied = await self._persist_large_results(ctx, messages, artifacts)
        if persist_applied:
            operations.append("persist")

        messages, aggregate_applied = self._aggregate_budget(ctx, messages)
        if aggregate_applied:
            operations.append("aggregate_budget")

        messages, ttl_applied = self._ttl_prune(ctx, messages)
        if ttl_applied:
            operations.append("ttl_prune")

        current_estimated_tokens = self._estimate_tokens(messages)

        messages, microcompact_applied = self._microcompact(ctx, messages, current_estimated_tokens)
        if microcompact_applied:
            operations.append("microcompact")
            current_estimated_tokens = self._estimate_tokens(messages)

        messages, collapse_applied = self._collapse_history(ctx, messages, current_estimated_tokens)
        if collapse_applied:
            operations.append("collapse")
            current_estimated_tokens = self._estimate_tokens(messages)

        messages, autocompact_applied = self._autocompact(ctx, messages, current_estimated_tokens)
        if autocompact_applied:
            operations.append("autocompact")
            current_estimated_tokens = self._estimate_tokens(messages)

        if (
            ctx.profile.memory_flush.enabled
            and current_estimated_tokens >= ctx.profile.memory_flush.soft_threshold_tokens
        ):
            flush_result = await self.memory_flusher.flush(
                MemoryFlushRequest(session_key=ctx.session_key, messages=messages)
            )
            if flush_result.flushed or flush_result.notes:
                operations.append("memory_flush")

        verification: CompressionPostCheck | None = None
        if ctx.profile.quality.require_post_check:
            verification = self.verifier.verify(
                CompressionVerifyRequest(
                    task_frame=ctx.task_frame,
                    original_messages=original_messages,
                    compressed_messages=messages,
                    original_artifacts=original_artifacts,
                    compressed_artifacts=artifacts,
                    metadata={
                        "objective_out_of_band": True,
                        "compressed_unresolved": list(ctx.task_frame.unresolved),
                        "recent_failures_before": list(ctx.metadata.get("recent_failures", [])),
                        "recent_failures_after": list(ctx.metadata.get("recent_failures", [])),
                    },
                )
            )
            if not verification.ok and ctx.profile.quality.rollback_on_invariant_failure:
                rollback_reason = verification.reasons[0] if verification.reasons else "verification_failed"
                return CompressionResult(
                    messages=original_messages,
                    active_artifacts=original_artifacts,
                    estimated_input_tokens=self._estimate_tokens(original_messages),
                    operations=[*operations, "rollback"],
                    metadata={
                        "verification": verification,
                        "rollback": {
                            "applied": True,
                            "reason": rollback_reason,
                        },
                        "verifier_result": verification,
                        "rollback_applied": True,
                        "rollback_reason": rollback_reason,
                    },,
                    verifier_result=verification,
                    rollback_applied=True,
                    rollback_reason=rollback_reason,
                )

        return CompressionResult(
            messages=messages,
            active_artifacts=artifacts,
            estimated_input_tokens=current_estimated_tokens,
            operations=operations,
            metadata={
                "verification": verification,
                "rollback": {
                    "applied": False,
                    "reason": None,
                },
                "verifier_result": verification,
                "rollback_applied": False,
                "rollback_reason": None,
            },
            verifier_result=verification,
            rollback_applied=False,
            rollback_reason=None,
        )

    async def run_emergency(self, ctx: CompressionContext) -> CompressionResult:
        """Run a harder fallback compression pass for prompt overflows."""
        leading_system = [ctx.messages[0]] if ctx.messages and ctx.messages[0].get("role") == "system" else []
        working_messages = ctx.messages[1:] if leading_system else ctx.messages
        tail = working_messages[-ctx.profile.retain_recent_messages :]
        artifact_line = (
            f"Artifacts: {', '.join(artifact.id for artifact in ctx.active_artifacts)}"
            if ctx.active_artifacts
            else "Artifacts: (none)"
        )
        summary_message = {
            "role": "system",
            "content": (
                "[Emergency context summary]\n"
                f"Objective: {ctx.task_frame.objective}\n"
                f"Unresolved: {'; '.join(ctx.task_frame.unresolved) if ctx.task_frame.unresolved else '(none)'}"
                f"\n{artifact_line}"
            ),
        }
        messages = [*leading_system, summary_message, *tail]
        return CompressionResult(
            messages=messages,
            active_artifacts=list(ctx.active_artifacts),
            estimated_input_tokens=self._estimate_tokens(messages),
            operations=["emergency_compact"],
            metadata={
                "fallback_summary_used": True,
                "rollback_ready": ctx.profile.quality.rollback_on_invariant_failure,
            },
        )

    async def _persist_large_results(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        artifacts: list[ArtifactRef],
    ) -> tuple[list[dict[str, Any]], list[ArtifactRef], bool]:
        applied = False
        for index, message in enumerate(messages):
            role = message.get("role")
            content = str(message.get("content", ""))
            if role not in {"tool", "tool_result"}:
                continue
            if len(content) <= ctx.profile.persist.single_result_chars:
                continue

            ref = await self.artifact_store.put(
                ArtifactWriteRequest(
                    kind="tool",
                    title=message.get("tool_name", f"tool-result-{index}"),
                    content=content,
                    location=message.get("tool_call_id"),
                    metadata={"role": role, "index": index},
                )
            )
            artifacts.append(ref)
            message["content"] = (
                f"[Persisted large tool result: {ref.id}]\n"
                f"Preview:\n{ref.preview}"
            )
            applied = True
        return messages, artifacts, applied

    def _aggregate_budget(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        tool_indexes = [
            index for index, message in enumerate(messages) if message.get("role") in {"tool", "tool_result"}
        ]
        total_chars = sum(len(str(messages[index].get("content", ""))) for index in tool_indexes)
        if total_chars <= ctx.profile.persist.aggregate_result_chars:
            return messages, False

        applied = False
        for index in tool_indexes:
            content = str(messages[index].get("content", ""))
            if len(content) <= ctx.profile.pruning.soft_trim_max_chars:
                continue
            head = content[: ctx.profile.pruning.soft_trim_head_chars]
            tail = content[-ctx.profile.pruning.soft_trim_tail_chars :]
            messages[index]["content"] = (
                f"{head}\n...[trimmed by aggregate budget]...\n{tail}"
            )
            applied = True
            total_chars = sum(len(str(messages[i].get("content", ""))) for i in tool_indexes)
            if total_chars <= ctx.profile.persist.aggregate_result_chars:
                break
        return messages, applied

    def _ttl_prune(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.pruning.enabled:
            return messages, False

        now_ms = int(ctx.metadata.get("now_ms", 0))
        if not now_ms:
            return messages, False

        cutoff = now_ms - ctx.profile.pruning.ttl_ms
        applied = False
        for message in messages:
            role = message.get("role")
            content = str(message.get("content", ""))
            timestamp_ms = int(message.get("timestamp_ms", 0) or 0)
            if role not in {"tool", "tool_result"}:
                continue
            if timestamp_ms <= 0 or timestamp_ms >= cutoff:
                continue
            if len(content) < ctx.profile.pruning.min_prunable_tool_chars:
                continue
            if not ctx.profile.pruning.hard_clear_enabled:
                continue
            message["content"] = ctx.profile.pruning.hard_clear_placeholder
            applied = True
        return messages, applied

    def _collapse_history(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.collapse.enabled:
            return messages, False
        if estimated_input_tokens < int(ctx.model_context_window * ctx.profile.collapse.trigger_pct):
            return messages, False
        if len(messages) <= ctx.profile.retain_recent_messages:
            return messages, False

        leading_system = [messages[0]] if messages and messages[0].get("role") == "system" else []
        working_messages = messages[1:] if leading_system else messages
        recent = working_messages[-ctx.profile.retain_recent_messages :]
        archived = working_messages[: -ctx.profile.retain_recent_messages]
        if not archived:
            return messages, False

        summary = self._summarize_messages(archived)
        collapsed = [
            *leading_system,
            {
                "role": "system",
                "content": (
                    "[Collapsed history]\n"
                    f"Objective: {ctx.task_frame.objective or '(empty)'}\n"
                    f"{summary}"
                ),
            },
            *recent,
        ]
        return collapsed, True

    def _microcompact(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.microcompact.enabled:
            return messages, False
        if estimated_input_tokens < int(ctx.model_context_window * ctx.profile.microcompact.trigger_pct):
            return messages, False

        applied = False
        compacted = 0
        for index, message in enumerate(messages):
            if compacted >= ctx.profile.microcompact.max_units_per_pass:
                break
            role = message.get("role")
            if role not in {"tool", "tool_result"}:
                continue
            if ctx.profile.microcompact.preserve_error_results and message.get("is_error"):
                continue
            content = str(message.get("content", ""))
            if len(content) <= ctx.profile.pruning.soft_trim_max_chars:
                continue
            head = content[: ctx.profile.pruning.soft_trim_head_chars]
            tail = content[-ctx.profile.pruning.soft_trim_tail_chars :]
            messages[index]["content"] = f"{head}\n...[microcompact]...\n{tail}"
            compacted += 1
            applied = True
        return messages, applied

    def _autocompact(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.autocompact.enabled:
            return messages, False

        trigger_tokens = int(ctx.model_context_window * ctx.profile.autocompact.trigger_pct)
        history_share_limit = int(ctx.model_context_window * ctx.profile.autocompact.max_history_share)
        needs_autocompact = (
            estimated_input_tokens >= trigger_tokens
            or estimated_input_tokens >= history_share_limit
            or max(ctx.model_context_window - estimated_input_tokens, 0)
            < ctx.profile.autocompact.reserve_tokens_floor
        )
        if not needs_autocompact:
            return messages, False
        if len(messages) <= max(ctx.profile.retain_recent_messages // 2, 2):
            return messages, False

        leading_system = [messages[0]] if messages and messages[0].get("role") == "system" else []
        working_messages = messages[1:] if leading_system else messages
        keep_count = max(ctx.profile.retain_recent_messages // 2, 2)
        recent = working_messages[-keep_count:]
        archived = working_messages[:-keep_count]
        if not archived:
            return messages, False

        summary = self._summarize_messages(archived)
        summary = summary[: ctx.profile.autocompact.fallback_summary_max_chars]
        compacted_messages = [
            *leading_system,
            {
                "role": "system",
                "content": (
                    "[Auto-compacted history]\n"
                    f"Objective: {ctx.task_frame.objective or '(empty)'}\n"
                    f"{summary}"
                ),
            },
            *recent,
        ]
        return compacted_messages, True

    def _summarize_messages(self, messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages[:12]:
            role = message.get("role", "unknown")
            content = str(message.get("content", "")).strip().replace("\n", " ")
            if not content:
                continue
            lines.append(f"- {role}: {content[:120]}")
        return "\n".join(lines) or "- no summary available"

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        total_chars = sum(len(str(message.get("content", ""))) for message in messages)
        return max(total_chars // 4, 0)


__all__ = [
    "CompressionContext",
    "CompressionProfile",
    "CompressionResult",
    "DefaultCompressionPipeline",
]
