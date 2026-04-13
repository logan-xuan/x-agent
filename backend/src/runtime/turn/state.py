"""Explicit turn state for the new bounded runtime loop."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any

from ..types import (
    ArtifactRef,
    BudgetSnapshot,
    LoopAssessment,
    TaskFrame,
    ToolExecutionResult,
    TurnBudgetProfile,
    TurnRequest,
)


def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)


@dataclass(frozen=True)
class ToolCallSignature:
    """Stable identifier for repeated tool invocations."""

    tool_name: str
    normalized_args_hash: str

    @classmethod
    def from_args(
        cls, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> ToolCallSignature:
        """Build a signature using a normalized representation of tool arguments."""
        normalized_payload = _normalize_json_like(arguments or {})
        normalized = json.dumps(
            normalized_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(tool_name=tool_name, normalized_args_hash=sha1(normalized).hexdigest())


def _normalize_json_like(value: Any) -> Any:
    """Normalize nested JSON-like values so semantically equivalent payloads hash the same."""
    if isinstance(value, dict):
        return {str(key): _normalize_json_like(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_json_like(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_like(item) for item in value]
    return value


@dataclass
class FailureCluster:
    """Repeated failure bucket used by the assessment and breaker logic."""

    fingerprint: str
    count: int = 1
    last_message: str = ""
    last_seen_ms: int = field(default_factory=_now_ms)


@dataclass
class TurnState:
    """Current mutable state for one bounded turn loop."""

    request: TurnRequest
    turn_index: int = 0
    started_at_ms: int = field(default_factory=_now_ms)
    active_messages: list[Any] = field(default_factory=list)
    active_artifact_refs: list[ArtifactRef] = field(default_factory=list)
    budget: BudgetSnapshot = field(default_factory=BudgetSnapshot)
    tool_usage: dict[str, int] = field(default_factory=dict)
    session_tool_usage: dict[str, int] = field(default_factory=dict)
    tool_signature_counts: dict[ToolCallSignature, int] = field(default_factory=dict)
    repeated_failures: list[FailureCluster] = field(default_factory=list)
    spawn_count: int = 0
    tool_results: list[ToolExecutionResult] = field(default_factory=list)
    last_assessment: LoopAssessment | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        request: TurnRequest,
        *,
        budget_profile: TurnBudgetProfile | None = None,
        profile_name: str | None = None,
        started_at_ms: int | None = None,
    ) -> TurnState:
        """Create turn state from a normalized runtime request."""
        task_frame = request.task_frame
        if not task_frame.objective:
            task_frame = TaskFrame(
                objective=request.user_input,
                done_definition=list(task_frame.done_definition),
                constraints=list(task_frame.constraints),
                deliverable=task_frame.deliverable,
                working_plan=list(task_frame.working_plan),
                unresolved=list(task_frame.unresolved),
                active_artifacts=list(task_frame.active_artifacts),
            )
            request = TurnRequest(
                session=request.session,
                user_input=request.user_input,
                task_frame=task_frame,
                route=request.route,
                metadata=dict(request.metadata),
            )

        snapshot = BudgetSnapshot.from_profile(
            budget_profile
            or (
                request.metadata.get("_runtime_budget_profile")
                if isinstance(request.metadata.get("_runtime_budget_profile"), TurnBudgetProfile)
                else None
            ),
            profile_name=profile_name or request.session.budget_profile,
        )
        return cls(
            request=request,
            started_at_ms=started_at_ms or _now_ms(),
            budget=snapshot,
            session_tool_usage=dict(request.metadata.get("session_tool_usage", {})),
        )

    @property
    def task_frame(self) -> TaskFrame:
        """Expose the normalized task frame."""
        return self.request.task_frame

    def refresh_elapsed(self, now_ms: int | None = None) -> int:
        """Update and return elapsed time for the loop."""
        self.budget.elapsed_ms = max((now_ms or _now_ms()) - self.started_at_ms, 0)
        self.budget.turns_taken = self.turn_index
        return self.budget.elapsed_ms

    def record_token_usage(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_cost_usd: float | None = None,
    ) -> None:
        """Accumulate token and cost usage."""
        self.budget.input_tokens += max(input_tokens, 0)
        self.budget.output_tokens += max(output_tokens, 0)
        self.budget.total_tokens = self.budget.input_tokens + self.budget.output_tokens
        if total_cost_usd is not None:
            self.budget.total_cost_usd = max(total_cost_usd, 0.0)

    def record_tool_call(
        self,
        tool_name: str,
        *,
        signature: ToolCallSignature | None = None,
    ) -> None:
        """Record a tool invocation for budget and repetition checks."""
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1
        self.session_tool_usage[tool_name] = self.session_tool_usage.get(tool_name, 0) + 1
        self.budget.per_tool_calls[tool_name] = self.budget.per_tool_calls.get(tool_name, 0) + 1
        self.budget.total_tool_calls += 1
        if signature is not None:
            self.tool_signature_counts[signature] = self.tool_signature_counts.get(signature, 0) + 1

    def record_tool_result(self, result: ToolExecutionResult) -> None:
        """Persist a normalized tool execution result in the turn state."""
        self.tool_results.append(result)

    def record_spawn(self) -> None:
        """Increment child-session spawn count."""
        self.spawn_count += 1

    def record_failure(self, fingerprint: str, message: str = "") -> None:
        """Track repeated failures by fingerprint."""
        for cluster in self.repeated_failures:
            if cluster.fingerprint == fingerprint:
                cluster.count += 1
                cluster.last_message = message
                cluster.last_seen_ms = _now_ms()
                return

        self.repeated_failures.append(
            FailureCluster(
                fingerprint=fingerprint,
                count=1,
                last_message=message,
            )
        )


__all__ = [
    "FailureCluster",
    "ToolCallSignature",
    "TurnState",
]
