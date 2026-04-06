"""Tool governance for the bounded runtime turn loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..types import GovernedToolPlan, ToolCallSpec, ToolExecutionPlan, ToolExecutionResult, ToolPolicy
from .state import ToolCallSignature, TurnState


@dataclass
class DefaultToolGovernor:
    """Apply tool policies before execution and track repeated failures after execution."""

    default_policy: ToolPolicy = field(default_factory=ToolPolicy)
    policies_by_name: dict[str, ToolPolicy] = field(default_factory=dict)

    def get_policy(self, tool_name: str) -> ToolPolicy:
        """Return the effective policy for a tool."""
        return self.policies_by_name.get(tool_name, self.default_policy)

    def validate_plan(self, plan: ToolExecutionPlan, state: TurnState) -> GovernedToolPlan:
        """Filter a tool execution plan according to runtime policy and loop state."""
        accepted: list[ToolCallSpec] = []
        rejected: list[ToolCallSpec] = []
        warnings: list[str] = []
        max_parallelism = state.budget.profile.max_parallel_tools if plan.allow_parallel else 1

        for call in plan.calls:
            policy = self.get_policy(call.tool_name)
            reason = self._rejection_reason(call, state, policy)
            if reason is not None:
                rejected.append(call)
                warnings.append(reason)
                continue

            timeout_ms = call.timeout_ms or policy.default_timeout_ms
            accepted.append(
                ToolCallSpec(
                    tool_name=call.tool_name,
                    arguments=dict(call.arguments),
                    timeout_ms=timeout_ms,
                )
            )
            max_parallelism = min(max_parallelism, policy.max_parallelism)

        if not accepted:
            max_parallelism = 1

        return GovernedToolPlan(
            calls=accepted,
            max_parallelism=max_parallelism,
            rejected_calls=rejected,
            warnings=warnings,
        )

    def register_result(self, state: TurnState, result: ToolExecutionResult) -> None:
        """Record normalized tool execution feedback in turn state."""
        state.record_tool_result(result)
        if result.success:
            return

        fingerprint = self._failure_fingerprint(result)
        message = result.error or result.output[:200]
        state.record_failure(fingerprint, message)

    def _rejection_reason(
        self,
        call: ToolCallSpec,
        state: TurnState,
        policy: ToolPolicy,
    ) -> str | None:
        if state.request.session.lane == "subagent" and not policy.allow_in_subagent:
            return f"tool '{call.tool_name}' is disabled in subagent sessions"

        current_uses = state.tool_usage.get(call.tool_name, 0)
        if current_uses >= policy.max_uses_per_turn:
            return f"tool '{call.tool_name}' exceeded max_uses_per_turn"

        signature = ToolCallSignature.from_args(call.tool_name, call.arguments)
        signature_count = state.tool_signature_counts.get(signature, 0)
        if signature_count >= policy.repeat_signature_limit:
            return f"tool '{call.tool_name}' exceeded repeat_signature_limit"

        per_tool_limit = state.budget.profile.max_tool_calls_by_name.get(call.tool_name)
        if per_tool_limit is not None and state.budget.per_tool_calls.get(call.tool_name, 0) >= per_tool_limit:
            return f"tool '{call.tool_name}' exceeded budget profile per-tool limit"

        return None

    def _failure_fingerprint(self, result: ToolExecutionResult) -> str:
        error = result.error or str(result.metadata.get("error_type", "")) or result.output[:80]
        return f"{result.tool_name}:{error}".strip(":")


__all__ = ["DefaultToolGovernor"]
