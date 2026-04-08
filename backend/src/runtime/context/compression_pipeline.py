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
class AnalyzedMessage:
    raw: dict[str, Any]
    index: int
    role: str
    content: str
    semantic_priority: str
    message_kind: str
    message_signature: str | None = None
    task_id: str | None = None
    state_label: str | None = None
    superseded_by_terminal: bool = False
    compressible: bool = True
    droppable: bool = False


@dataclass
class CollapseState:
    objective: str
    active_constraints: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    finalized_tasks: list[str] = field(default_factory=list)
    active_failures: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    evidence_summaries: list[str] = field(default_factory=list)


@dataclass
class CompressionBudgetState:
    current_tokens: int
    observe_tokens: int
    target_tokens: int
    must_fit_tokens: int
    remaining_tokens: int
    pressure_level: str
    repeated_summary_ratio: float = 0.0
    history_share_ratio: float = 0.0
    overflow_risk: bool = False


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
        result_metadata: dict[str, Any] = {
            "objective_out_of_band": bool(ctx.metadata.get("objective_out_of_band", False))
        }
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
        budget_state = self._build_budget_state(ctx, self._analyze_messages(messages), current_estimated_tokens)
        result_metadata["budget_state"] = {
            "current_tokens": budget_state.current_tokens,
            "observe_tokens": budget_state.observe_tokens,
            "target_tokens": budget_state.target_tokens,
            "must_fit_tokens": budget_state.must_fit_tokens,
            "remaining_tokens": budget_state.remaining_tokens,
            "pressure_level": budget_state.pressure_level,
            "repeated_summary_ratio": budget_state.repeated_summary_ratio,
            "history_share_ratio": budget_state.history_share_ratio,
            "overflow_risk": budget_state.overflow_risk,
        }

        messages, microcompact_applied = self._microcompact(ctx, messages, current_estimated_tokens)
        if microcompact_applied:
            operations.append("microcompact")
            current_estimated_tokens = self._estimate_tokens(messages)

        messages, collapse_applied = self._collapse_history(ctx, messages, current_estimated_tokens)
        if collapse_applied:
            operations.append("collapse")
            result_metadata["objective_out_of_band"] = False
            current_estimated_tokens = self._estimate_tokens(messages)

        messages, autocompact_applied = self._autocompact(ctx, messages, current_estimated_tokens)
        if autocompact_applied:
            operations.append("autocompact")
            result_metadata["objective_out_of_band"] = False
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
        if current_estimated_tokens > self._must_fit_tokens(ctx):
            emergency_result = await self.run_emergency(
                CompressionContext(
                    session_key=ctx.session_key,
                    turn=ctx.turn,
                    task_frame=ctx.task_frame,
                    profile=ctx.profile,
                    model_context_window=ctx.model_context_window,
                    estimated_input_tokens=current_estimated_tokens,
                    messages=messages,
                    active_artifacts=artifacts,
                    budget=ctx.budget,
                    metadata=dict(ctx.metadata),
                )
            )
            messages = emergency_result.messages
            artifacts = emergency_result.active_artifacts
            current_estimated_tokens = emergency_result.estimated_input_tokens
            result_metadata.update(emergency_result.metadata)
            operations.append("emergency_compact")

        if ctx.profile.quality.require_post_check:
            verification = self.verifier.verify(
                CompressionVerifyRequest(
                    task_frame=ctx.task_frame,
                    original_messages=original_messages,
                    compressed_messages=messages,
                    original_artifacts=original_artifacts,
                    compressed_artifacts=artifacts,
                    metadata=self._build_verification_metadata(ctx, messages, result_metadata),
                )
            )
            if not verification.ok and ctx.profile.quality.rollback_on_invariant_failure:
                rollback_reason = verification.reasons[0] if verification.reasons else "verification_failed"
                original_estimated_tokens = self._estimate_tokens(original_messages)
                if (
                    current_estimated_tokens <= self._must_fit_tokens(ctx)
                    and original_estimated_tokens > self._must_fit_tokens(ctx)
                ):
                    return CompressionResult(
                        messages=messages,
                        active_artifacts=artifacts,
                        estimated_input_tokens=current_estimated_tokens,
                        operations=operations,
                        metadata={
                            **result_metadata,
                            "verification": verification,
                            "rollback": {
                                "applied": False,
                                "reason": rollback_reason,
                                "skipped": "original_context_exceeds_must_fit",
                            },
                            "verifier_result": verification,
                            "rollback_applied": False,
                            "rollback_reason": rollback_reason,
                        },
                        verifier_result=verification,
                        rollback_applied=False,
                        rollback_reason=rollback_reason,
                    )
                return CompressionResult(
                    messages=original_messages,
                    active_artifacts=original_artifacts,
                    estimated_input_tokens=original_estimated_tokens,
                    operations=[*operations, "rollback"],
                    metadata={
                        **result_metadata,
                        "verification": verification,
                        "rollback": {
                            "applied": True,
                            "reason": rollback_reason,
                        },
                        "verifier_result": verification,
                        "rollback_applied": True,
                        "rollback_reason": rollback_reason,
                    },
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
                **result_metadata,
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
        first_message = ctx.messages[0] if ctx.messages else None
        leading_system = (
            [first_message]
            if first_message
            and first_message.get("role") == "system"
            and not str(first_message.get("content", "")).startswith("[Collapsed history]")
            and not str(first_message.get("content", "")).startswith("[Emergency context summary]")
            else []
        )
        collapsed_summary = []
        working_messages = ctx.messages[1:] if first_message else ctx.messages
        tail = [
            self._truncate_emergency_message(message, ctx.profile.autocompact.fallback_summary_max_chars)
            for message in working_messages[-ctx.profile.retain_recent_messages :]
        ]
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
        messages = [*leading_system, summary_message, *collapsed_summary, *tail]
        must_fit_tokens = self._must_fit_tokens(ctx)
        protected_count = len(leading_system) + 1 + len(collapsed_summary)
        while len(messages) > protected_count and self._estimate_tokens(messages) > must_fit_tokens:
            messages.pop()
        while collapsed_summary and self._estimate_tokens(messages) > must_fit_tokens:
            del messages[len(leading_system) + 1]
            collapsed_summary = []
            protected_count = len(leading_system) + 1
        return CompressionResult(
            messages=messages,
            active_artifacts=list(ctx.active_artifacts),
            estimated_input_tokens=self._estimate_tokens(messages),
            operations=["emergency_compact"],
            metadata={
                "fallback_summary_used": True,
                "rollback_ready": ctx.profile.quality.rollback_on_invariant_failure,
                "objective_out_of_band": False,
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

        first_message = messages[0] if messages else None
        leading_system = (
            [first_message]
            if first_message
            and first_message.get("role") == "system"
            and not str(first_message.get("content", "")).startswith("[Collapsed history]")
            else []
        )
        working_messages = messages[1:] if leading_system else messages
        if len(working_messages) < ctx.profile.collapse.min_segment_turns:
            return messages, False

        keep_count = min(
            ctx.profile.retain_recent_messages,
            max(len(working_messages) // 3, 2),
        )
        recent = working_messages[-keep_count:]
        archived = working_messages[:-keep_count]
        if not archived:
            return messages, False

        collapse_state = self._build_collapse_state(ctx, archived)
        collapsed = [
            *leading_system,
            {
                "role": "system",
                "content": self._render_collapse_state(collapse_state),
            },
            *recent,
        ]
        target_tokens = int(ctx.model_context_window * ctx.profile.pressure.orange_pct)
        min_recent_messages = 2 if ctx.task_frame.unresolved else 1
        while (
            len(collapsed) > len(leading_system) + 1 + min_recent_messages
            and self._estimate_tokens(collapsed) > target_tokens
        ):
            del collapsed[len(leading_system) + 1]
        return collapsed, True

    def _build_collapse_state(
        self,
        ctx: CompressionContext,
        archived: list[dict[str, Any]],
    ) -> CollapseState:
        analyzed = self._analyze_messages(archived)
        finalized_tasks: list[str] = []
        active_failures: list[str] = []
        evidence_summaries: list[str] = []

        for item in analyzed:
            if item.message_kind == "status" and item.state_label in {"done", "failed", "cancelled"} and item.task_id:
                summary = f"{item.task_id} {item.state_label}"
                finalized_tasks.append(summary)
                evidence_summaries.append(summary)
                continue
            if "error" in item.content.lower() or "失败" in item.content:
                active_failures.append(item.content.strip())
                evidence_summaries.append(item.content.strip())

        return CollapseState(
            objective=ctx.task_frame.objective or "(empty)",
            active_constraints=[entry for entry in ctx.task_frame.constraints if entry],
            unresolved=[entry for entry in ctx.task_frame.unresolved if entry],
            finalized_tasks=finalized_tasks,
            active_failures=active_failures,
            artifact_refs=[artifact.id for artifact in ctx.active_artifacts],
            evidence_summaries=evidence_summaries,
        )

    def _render_collapse_state(self, collapse_state: CollapseState) -> str:
        lines = [
            "[Collapsed history]",
            f"Objective: {collapse_state.objective}",
            (
                "Constraints: "
                + (
                    "; ".join(collapse_state.active_constraints)
                    if collapse_state.active_constraints
                    else "(none)"
                )
            ),
            (
                "Unresolved: "
                + ("; ".join(collapse_state.unresolved) if collapse_state.unresolved else "(none)")
            ),
            (
                "Finalized tasks: "
                + ("; ".join(collapse_state.finalized_tasks) if collapse_state.finalized_tasks else "(none)")
            ),
            (
                "Active failures: "
                + ("; ".join(collapse_state.active_failures) if collapse_state.active_failures else "(none)")
            ),
            (
                "Artifacts: "
                + (", ".join(collapse_state.artifact_refs) if collapse_state.artifact_refs else "(none)")
            ),
            (
                "Evidence summaries: "
                + (
                    "; ".join(collapse_state.evidence_summaries)
                    if collapse_state.evidence_summaries
                    else "(none)"
                )
            ),
        ]
        return "\n".join(lines)

    def _microcompact(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.microcompact.enabled:
            return messages, False
        trigger_tokens = int(ctx.model_context_window * ctx.profile.microcompact.trigger_pct)
        if estimated_input_tokens < trigger_tokens:
            return messages, False

        analyzed = self._analyze_messages(messages)
        compacted = 0
        kept_messages: list[dict[str, Any]] = []
        applied = False

        for item in analyzed:
            if compacted >= ctx.profile.microcompact.max_units_per_pass:
                kept_messages.append(item.raw)
                continue
            if item.droppable:
                compacted += 1
                applied = True
                continue
            kept_messages.append(item.raw)

        if compacted >= ctx.profile.microcompact.max_units_per_pass:
            return kept_messages, applied

        remaining_tokens = self._estimate_tokens(kept_messages)
        if remaining_tokens < trigger_tokens:
            return kept_messages, applied

        final_messages: list[dict[str, Any]] = []
        for message in kept_messages:
            if compacted >= ctx.profile.microcompact.max_units_per_pass:
                final_messages.append(message)
                continue
            role = message.get("role")
            content = str(message.get("content", ""))
            if role in {"tool", "tool_result"}:
                if ctx.profile.microcompact.preserve_error_results and message.get("is_error"):
                    final_messages.append(message)
                    continue
                if len(content) > ctx.profile.pruning.soft_trim_max_chars:
                    head = content[: ctx.profile.pruning.soft_trim_head_chars]
                    tail = content[-ctx.profile.pruning.soft_trim_tail_chars :]
                    rewritten = dict(message)
                    rewritten["content"] = f"{head}\n...[microcompact]...\n{tail}"
                    final_messages.append(rewritten)
                    compacted += 1
                    applied = True
                    continue
            final_messages.append(message)
        return final_messages, applied


    def _autocompact(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        if not ctx.profile.autocompact.enabled:
            return messages, False

        analyzed_messages = self._analyze_messages(messages)
        budget_state = self._build_budget_state(ctx, analyzed_messages, estimated_input_tokens)
        trigger_tokens = int(ctx.model_context_window * ctx.profile.autocompact.trigger_pct)
        target_tokens = int(ctx.model_context_window * ctx.profile.pressure.orange_pct)
        has_collapsed_history = any(
            str(message.get("content", "")).lower().startswith("[collapsed history]")
            for message in messages
        )
        history_share_exceeded = (
            budget_state.history_share_ratio >= ctx.profile.autocompact.max_history_share
            and not has_collapsed_history
        )
        needs_autocompact = (
            estimated_input_tokens >= trigger_tokens
            or history_share_exceeded
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
        recent = [dict(message) for message in working_messages[-keep_count:]]
        archived = working_messages[:-keep_count]
        if not archived:
            return messages, False

        summary = self._summarize_messages(archived)
        summary_limit = ctx.profile.autocompact.fallback_summary_max_chars
        key_conclusions = self._extract_key_conclusions(archived)

        def build_candidate(current_summary: str, current_recent: list[dict[str, Any]]) -> list[dict[str, Any]]:
            conclusion_line = (
                "\nFinalized tasks: " + "; ".join(key_conclusions)
                if key_conclusions
                else ""
            )
            return [
                *leading_system,
                {
                    "role": "system",
                    "content": (
                        "[Auto-compacted history]\n"
                        f"Objective: {ctx.task_frame.objective or '(empty)'}\n"
                        f"{current_summary}{conclusion_line}"
                    ),
                },
                *current_recent,
            ]

        compacted_messages = build_candidate(summary[:summary_limit], recent)
        while self._estimate_tokens(compacted_messages) > target_tokens and summary_limit > 40:
            summary_limit = max(summary_limit // 2, 40)
            compacted_messages = build_candidate(summary[:summary_limit], recent)

        if self._estimate_tokens(compacted_messages) <= target_tokens:
            return compacted_messages, True

        trimmed_recent: list[dict[str, Any]] = []
        for message in recent:
            rewritten = dict(message)
            content = str(rewritten.get("content", ""))
            if len(content) > 48:
                rewritten["content"] = f"{content[:20]}...[autocompact]...{content[-10:]}"
            trimmed_recent.append(rewritten)
            compacted_messages = build_candidate(summary[:summary_limit], trimmed_recent + recent[len(trimmed_recent) :])
            if self._estimate_tokens(compacted_messages) <= target_tokens:
                return compacted_messages, True

        while self._estimate_tokens(compacted_messages) > target_tokens and summary_limit > 40:
            summary_limit = max(summary_limit - 10, 40)
            compacted_messages = build_candidate(summary[:summary_limit], trimmed_recent)

        return compacted_messages, True


    def _analyze_messages(self, messages: list[dict[str, Any]]) -> list[AnalyzedMessage]:
        analyzed: list[AnalyzedMessage] = []
        latest_terminal_by_task: dict[str, int] = {}

        for index, message in enumerate(messages):
            role = str(message.get("role", "unknown"))
            content = str(message.get("content", ""))
            task_id = self._extract_task_id(content)
            state_label = self._extract_state_label(content)
            message_kind = self._classify_message_kind(role, content, state_label)
            semantic_priority = self._classify_priority(message_kind, content)
            signature = self._message_signature(message_kind, content)
            analyzed.append(
                AnalyzedMessage(
                    raw=dict(message),
                    index=index,
                    role=role,
                    content=content,
                    semantic_priority=semantic_priority,
                    message_kind=message_kind,
                    message_signature=signature,
                    task_id=task_id,
                    state_label=state_label,
                    compressible=semantic_priority != "P0",
                )
            )
            if task_id and state_label in {"done", "failed", "cancelled"}:
                latest_terminal_by_task[task_id] = index

        seen_signatures: set[str] = set()
        for item in analyzed:
            if item.message_kind == "summary" and item.message_signature:
                if item.message_signature in seen_signatures:
                    item.droppable = True
                else:
                    seen_signatures.add(item.message_signature)
            if item.task_id and item.state_label in {"pending", "running", "delegated"}:
                terminal_index = latest_terminal_by_task.get(item.task_id)
                if terminal_index is not None and terminal_index > item.index:
                    item.superseded_by_terminal = True
                    item.droppable = True
            if item.message_kind == "chatter":
                item.droppable = True
        return analyzed

    def _build_budget_state(
        self,
        ctx: CompressionContext,
        analyzed_messages: list[AnalyzedMessage],
        current_tokens: int,
    ) -> CompressionBudgetState:
        observe_tokens = int(ctx.model_context_window * ctx.profile.pressure.yellow_pct)
        target_tokens = int(ctx.model_context_window * ctx.profile.pressure.orange_pct)
        must_fit_tokens = int(ctx.model_context_window * ctx.profile.pressure.red_pct)
        repeated_summaries = sum(
            1 for item in analyzed_messages if item.message_kind == "summary" and item.droppable
        )
        summary_count = sum(1 for item in analyzed_messages if item.message_kind == "summary")
        history_count = sum(1 for item in analyzed_messages if item.message_kind in {"summary", "status", "result"})
        if current_tokens >= must_fit_tokens:
            pressure_level = "red"
        elif current_tokens >= target_tokens:
            pressure_level = "orange"
        elif current_tokens >= observe_tokens:
            pressure_level = "yellow"
        else:
            pressure_level = "normal"
        return CompressionBudgetState(
            current_tokens=current_tokens,
            observe_tokens=observe_tokens,
            target_tokens=target_tokens,
            must_fit_tokens=must_fit_tokens,
            remaining_tokens=max(must_fit_tokens - current_tokens, 0),
            pressure_level=pressure_level,
            repeated_summary_ratio=(repeated_summaries / summary_count) if summary_count else 0.0,
            history_share_ratio=(history_count / len(analyzed_messages)) if analyzed_messages else 0.0,
            overflow_risk=current_tokens >= must_fit_tokens,
        )

    def _build_verification_metadata(
        self,
        ctx: CompressionContext,
        messages: list[dict[str, Any]],
        extra_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recent_failures_after: list[str] = []
        for message in messages:
            for failure in self._extract_recent_failures(message):
                if failure not in recent_failures_after:
                    recent_failures_after.append(failure)
        merged_metadata = {**ctx.metadata, **(extra_metadata or {})}
        objective = (ctx.task_frame.objective or "").strip()
        objective_after = str(
            merged_metadata.get(
                "objective_after",
                merged_metadata.get("after_objective", ""),
            )
        ).strip()
        objective_out_of_band = bool(merged_metadata.get("objective_out_of_band", False))
        if not objective_after and not objective_out_of_band and not self._contains_compaction_summary(messages):
            objective_after = objective
        compressed_unresolved = self._extract_unresolved_items(messages)
        key_conclusions_after = self._extract_key_conclusions(messages)
        key_conclusions_before = self._extract_key_conclusions(ctx.messages)
        return {
            "objective_out_of_band": objective_out_of_band,
            "objective_before": objective,
            "objective_after": objective_after,
            "compressed_unresolved": compressed_unresolved,
            "recent_failures_before": list(ctx.metadata.get("recent_failures", [])),
            "recent_failures_after": recent_failures_after,
            "key_conclusions_before": key_conclusions_before,
            "key_conclusions_after": key_conclusions_after,
        }

    def _extract_unresolved_items(self, messages: list[dict[str, Any]]) -> list[str]:
        unresolved: list[str] = []
        for message in messages:
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            normalized = content.lower()
            if normalized.startswith("[collapsed history]") or normalized.startswith("[emergency context summary]"):
                for line in content.splitlines():
                    if not line.startswith("Unresolved: "):
                        continue
                    payload = line.removeprefix("Unresolved: ").strip()
                    if payload == "(none)" or not payload:
                        return []
                    for item in payload.split(";"):
                        value = item.strip()
                        if value and value not in unresolved:
                            unresolved.append(value)
                    break
                continue
            if normalized.startswith("[auto-compacted history]"):
                continue
            if any(token in content for token in ("unresolved", "未完成", "待处理")):
                if content not in unresolved:
                    unresolved.append(content)
        return unresolved

    def _extract_key_conclusions(self, messages: list[dict[str, Any]]) -> list[str]:
        conclusions: list[str] = []
        for message in messages:
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            normalized = content.lower()
            if normalized.startswith("[collapsed history]") or normalized.startswith("[auto-compacted history]"):
                for line in content.splitlines():
                    if line.startswith("Finalized tasks: "):
                        payload = line.removeprefix("Finalized tasks: ").strip()
                        if payload != "(none)":
                            for item in payload.split(";"):
                                value = item.strip()
                                if value and value not in conclusions:
                                    conclusions.append(value)
                    if line.startswith("Evidence summaries: "):
                        payload = line.removeprefix("Evidence summaries: ").strip()
                        if payload != "(none)":
                            for item in payload.split(";"):
                                value = item.strip()
                                if value and value not in conclusions:
                                    conclusions.append(value)
                continue
            task_id = self._extract_task_id(content)
            state_label = self._extract_state_label(content)
            if task_id and state_label in {"done", "failed", "cancelled"}:
                value = f"{task_id} {state_label}"
                if value not in conclusions:
                    conclusions.append(value)
                continue
            if any(marker in content for marker in ("结论：", "Conclusion:", "conclusion:")):
                payload = content.split("：", 1)[1].strip() if "：" in content else content.split(":", 1)[1].strip()
                if payload and payload not in conclusions:
                    conclusions.append(payload)
        return conclusions

    def _extract_recent_failures(self, message: dict[str, Any]) -> list[str]:
        content = str(message.get("content", "")).strip()
        if not content:
            return []
        normalized = content.lower()
        if normalized.startswith("[collapsed history]"):
            for line in content.splitlines():
                if not line.startswith("Active failures: "):
                    continue
                payload = line.removeprefix("Active failures: ").strip()
                if payload == "(none)" or not payload:
                    return []
                return [item.strip() for item in payload.split(";") if item.strip()]
            return []
        if normalized.startswith("[auto-compacted history]"):
            return []
        if normalized.startswith("[emergency context summary]"):
            return []
        return [content] if any(token in normalized for token in ("error", "失败")) else []

    def _contains_compaction_summary(self, messages: list[dict[str, Any]]) -> bool:
        for message in messages:
            normalized = str(message.get("content", "")).strip().lower()
            if normalized.startswith("[collapsed history]"):
                return True
            if normalized.startswith("[auto-compacted history]"):
                return True
            if normalized.startswith("[emergency context summary]"):
                return True
        return False

    def _must_fit_tokens(self, ctx: CompressionContext) -> int:
        return int(ctx.model_context_window * ctx.profile.pressure.red_pct)

    def _truncate_emergency_message(
        self,
        message: dict[str, Any],
        max_chars: int,
    ) -> dict[str, Any]:
        truncated = dict(message)
        content = str(truncated.get("content", ""))
        if max_chars > 0 and len(content) > max_chars:
            truncated["content"] = content[:max_chars]
        return truncated

    def _classify_priority(self, message_kind: str, content: str) -> str:
        if message_kind in {"objective", "unresolved"}:
            return "P0"
        if message_kind in {"summary", "status", "result"}:
            return "P1"
        if message_kind == "chatter":
            return "P3"
        if "失败" in content or "error" in content.lower():
            return "P1"
        return "P2"

    def _classify_message_kind(self, role: str, content: str, state_label: str | None) -> str:
        normalized = content.lower()
        if normalized.startswith("[collapsed history]") or normalized.startswith("[auto-compacted history]"):
            return "summary"
        if state_label is not None:
            return "status"
        if role in {"tool", "tool_result"}:
            return "result"
        if any(token in content for token in ("objective:", "目标:", "当前目标")):
            return "objective"
        if any(token in content for token in ("unresolved", "未完成", "待处理")):
            return "unresolved"
        if any(token in content for token in ("请稍等", "稍后回传", "稍后同步", "emoji")):
            return "chatter"
        return "message"

    def _extract_task_id(self, content: str) -> str | None:
        marker = "task-"
        if marker not in content:
            return None
        suffix = content.split(marker, 1)[1]
        token = suffix.split()[0].strip("：:，,。.;")
        return f"task-{token}" if token else None

    def _extract_state_label(self, content: str) -> str | None:
        normalized = content.lower()
        for state in ("pending", "running", "done", "failed", "cancelled", "delegated"):
            if f"status: {state}" in normalized or f"状态: {state}" in normalized:
                return state
        return None

    def _message_signature(self, message_kind: str, content: str) -> str | None:
        normalized = " ".join(content.split())
        if message_kind in {"summary", "chatter"}:
            return normalized
        return None

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
    "AnalyzedMessage",
    "CompressionBudgetState",
    "CompressionContext",
    "CompressionProfile",
    "CompressionResult",
    "DefaultCompressionPipeline",
]
