"""Shared types for the next-generation runtime package."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from .turn.finish_reason import FinishReason

if TYPE_CHECKING:
    from .turn.state import TurnState

LaneName = Literal["main", "followup", "subagent", "cron", "background_tool"]
SessionStatus = Literal["active", "idle", "compacted", "archived"]
TurnResultKind = Literal["final", "continue", "spawn", "abort", "compact"]
BudgetAction = Literal["ok", "warn", "compact", "stop"]
PromptMode = Literal["full", "minimal", "none"]
RiskLevel = Literal["low", "medium", "high"]


@dataclass
class TaskFrame:
    """Normalized task shape that the runtime can reason about."""

    objective: str = ""
    done_definition: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    deliverable: str = ""
    working_plan: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    active_artifacts: list[str] = field(default_factory=list)


@dataclass
class RouteMeta:
    """Gateway routing metadata attached to a session or turn."""

    channel: str
    account_id: str | None = None
    user_id: str | None = None
    thread_id: str | None = None
    topic_id: str | None = None
    origin_message_id: str | None = None


@dataclass
class SessionDescriptor:
    """Session-level descriptor used by the new runtime."""

    session_key: str
    session_id: str
    parent_session_key: str | None = None
    lane: LaneName = "main"
    model_profile: str = "default"
    budget_profile: str = "default"
    summary_ref: str | None = None
    memory_ref: str | None = None
    route: RouteMeta | None = None
    status: SessionStatus = "active"


@dataclass
class ArtifactRef:
    """Reference to a persisted artifact outside the active model context."""

    id: str
    kind: Literal["web", "bash", "search", "file", "tool", "summary", "memory", "other"]
    title: str
    preview: str
    location: str | None = None
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnBudgetProfile:
    """Hard and soft runtime limits for a single bounded turn loop."""

    max_turns: int = 12
    max_wall_time_ms: int = 180000
    max_total_tokens: int = 120000
    max_cost_usd: float | None = None
    max_tool_calls: int = 24
    max_parallel_tools: int = 4
    max_spawns: int = 3
    compact_trigger_tokens: int = 80000
    collapse_trigger_tokens: int = 60000
    tool_result_single_chars: int = 50000
    tool_result_per_message_chars: int = 200000
    max_tool_calls_by_name: dict[str, int] = field(default_factory=dict)


@dataclass
class ToolPolicy:
    """Runtime policy for a specific tool."""

    max_result_size_chars: int = 50000
    max_uses_per_turn: int = 8
    max_uses_per_session: int = 50
    max_parallelism: int = 2
    default_timeout_ms: int = 30000
    compactable: bool = True
    persist_large_output: bool = True
    allow_in_subagent: bool = True
    cost_weight: int = 1
    repeat_signature_limit: int = 2


@dataclass
class BudgetSnapshot:
    """Mutable budget usage snapshot for the current turn loop."""

    profile: TurnBudgetProfile = field(default_factory=TurnBudgetProfile)
    profile_name: str = "default"
    turns_taken: int = 0
    elapsed_ms: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_tool_calls: int = 0
    per_tool_calls: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_profile(
        cls,
        profile: TurnBudgetProfile | None = None,
        *,
        profile_name: str = "default",
    ) -> BudgetSnapshot:
        """Create a mutable budget snapshot from a static budget profile."""
        return cls(profile=profile or TurnBudgetProfile(), profile_name=profile_name)

    def remaining_turns(self) -> int | None:
        """Return remaining turns, or None when the limit is disabled."""
        if self.profile.max_turns <= 0:
            return None
        return max(self.profile.max_turns - self.turns_taken, 0)

    def remaining_tool_calls(self) -> int | None:
        """Return remaining tool calls, or None when the limit is disabled."""
        if self.profile.max_tool_calls <= 0:
            return None
        return max(self.profile.max_tool_calls - self.total_tool_calls, 0)

    def remaining_tokens(self) -> int | None:
        """Return remaining total tokens, or None when the limit is disabled."""
        if self.profile.max_total_tokens <= 0:
            return None
        return max(self.profile.max_total_tokens - self.total_tokens, 0)

    def token_pressure(self) -> float:
        """Return total token pressure as a ratio between 0 and 1+."""
        if self.profile.max_total_tokens <= 0:
            return 0.0
        return self.total_tokens / self.profile.max_total_tokens


@dataclass
class BudgetDecision:
    """Controller-facing decision produced by the budget manager."""

    action: BudgetAction = "ok"
    reason: str = ""
    finish_reason: FinishReason | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls) -> BudgetDecision:
        return cls(action="ok")

    @classmethod
    def warn(cls, reason: str, **details: Any) -> BudgetDecision:
        return cls(action="warn", reason=reason, details=details)

    @classmethod
    def compact(cls, reason: str, **details: Any) -> BudgetDecision:
        return cls(action="compact", reason=reason, details=details)

    @classmethod
    def stop(
        cls,
        reason: str,
        finish_reason: FinishReason,
        **details: Any,
    ) -> BudgetDecision:
        return cls(
            action="stop",
            reason=reason,
            finish_reason=finish_reason,
            details=details,
        )


@dataclass
class LoopAssessment:
    """Structured assessment for the current loop state."""

    turn: int
    unresolved_count: int
    novelty_score: float
    repeated_pattern_score: float
    risk_level: RiskLevel = "low"
    budget_remaining: BudgetSnapshot | None = None
    suggested_next_action: str = ""
    controller_decision: Literal["continue", "finish", "compact", "abort", "spawn"] = "continue"
    finish_reason: FinishReason | None = None
    spawn_packet: SpawnPacket | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class ToolCallSpec:
    """One planned tool invocation."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None


@dataclass
class ToolExecutionPlan:
    """Candidate set of tool calls prepared for governance."""

    calls: list[ToolCallSpec] = field(default_factory=list)
    allow_parallel: bool = False


@dataclass
class GovernedToolPlan:
    """Validated tool plan after policy and budget constraints are applied."""

    calls: list[ToolCallSpec] = field(default_factory=list)
    max_parallelism: int = 1
    rejected_calls: list[ToolCallSpec] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ToolExecutionResult:
    """Normalized representation of a tool execution result."""

    tool_name: str
    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnRequest:
    """Input envelope for the new turn controller."""

    session: SessionDescriptor
    user_input: str
    task_frame: TaskFrame
    route: RouteMeta
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpawnPacket:
    """Bounded child-session request produced by the parent turn."""

    objective: str
    deliverable: str
    constraints: list[str] = field(default_factory=list)
    parent_summary: str = ""
    selected_artifacts: list[str] = field(default_factory=list)
    tool_allowlist: list[str] = field(default_factory=list)
    budget_profile: str = "child-default"
    timeout_ms: int = 0


@dataclass
class ChildResult:
    """Structured child-session return value for parent ingestion."""

    status: Literal["success", "error", "timeout"]
    summary: str
    unresolved: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class CompactResult:
    """Structured compaction payload returned by runtime context compression."""

    active_messages: list[Any] = field(default_factory=list)
    active_artifact_refs: list[ArtifactRef] = field(default_factory=list)
    output_text: str | None = None
    task_frame: TaskFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnResult:
    """Output envelope returned by the new turn controller."""

    kind: TurnResultKind
    finish_reason: FinishReason | None = None
    output_text: str | None = None
    updated_task_frame: TaskFrame | None = None
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    spawn_packet: SpawnPacket | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeEvent:
    """Small telemetry envelope shared by runtime components."""

    type: str
    session_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = 0.0


AsyncCallable = Callable[[], Awaitable[Any]]


@runtime_checkable
class TurnController(Protocol):
    """Protocol implemented by the bounded turn controller."""

    async def run(self, request: TurnRequest) -> TurnResult:
        """Run a bounded turn loop for one session."""


@runtime_checkable
class BudgetManager(Protocol):
    """Protocol implemented by budget evaluators."""

    def evaluate(self, state: TurnState) -> BudgetDecision:
        """Evaluate whether the current state can continue."""


@runtime_checkable
class AssessmentEngine(Protocol):
    """Protocol implemented by loop assessment engines."""

    def assess(self, state: TurnState) -> LoopAssessment:
        """Assess whether the loop is still making progress."""


@runtime_checkable
class ToolGovernor(Protocol):
    """Protocol implemented by tool policy guards."""

    def validate_plan(self, plan: ToolExecutionPlan, state: TurnState) -> GovernedToolPlan:
        """Validate a planned tool execution batch."""

    def register_result(self, state: TurnState, result: ToolExecutionResult) -> None:
        """Record tool execution feedback for repeated-pattern detection."""


__all__ = [
    "ArtifactRef",
    "AssessmentEngine",
    "AsyncCallable",
    "BudgetAction",
    "BudgetDecision",
    "BudgetManager",
    "BudgetSnapshot",
    "ChildResult",
    "CompactResult",
    "FinishReason",
    "GovernedToolPlan",
    "LaneName",
    "LoopAssessment",
    "PromptMode",
    "RiskLevel",
    "RouteMeta",
    "SessionDescriptor",
    "SessionStatus",
    "SpawnPacket",
    "TaskFrame",
    "ToolCallSpec",
    "ToolExecutionPlan",
    "ToolExecutionResult",
    "ToolGovernor",
    "ToolPolicy",
    "TurnBudgetProfile",
    "TurnController",
    "TurnRequest",
    "TurnResult",
    "TurnResultKind",
]
