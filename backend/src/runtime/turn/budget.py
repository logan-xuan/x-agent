"""Budget manager for the bounded runtime turn loop."""

from __future__ import annotations

from dataclasses import dataclass

from ..types import BudgetDecision
from .finish_reason import FinishReason
from .state import TurnState


@dataclass
class DefaultBudgetManager:
    """Evaluate hard and soft limits for a bounded turn loop."""

    warn_threshold_pct: float = 0.85

    def evaluate(self, state: TurnState) -> BudgetDecision:
        """Evaluate whether the current turn loop can continue."""
        state.refresh_elapsed()
        snapshot = state.budget
        profile = snapshot.profile

        stop_decision = self._check_stop_limits(state)
        if stop_decision is not None:
            return stop_decision

        if (
            profile.compact_trigger_tokens > 0
            and snapshot.total_tokens >= profile.compact_trigger_tokens
        ):
            return BudgetDecision.compact(
                "compact_trigger_tokens reached",
                current=snapshot.total_tokens,
                limit=profile.compact_trigger_tokens,
                profile=snapshot.profile_name,
            )

        warnings = self._collect_warnings(state)
        if warnings:
            snapshot.warnings = warnings
            return BudgetDecision.warn(
                "; ".join(warnings),
                warnings=list(warnings),
                profile=snapshot.profile_name,
            )

        snapshot.warnings = []
        return BudgetDecision.ok()

    def _check_stop_limits(self, state: TurnState) -> BudgetDecision | None:
        snapshot = state.budget
        profile = snapshot.profile

        if self._reached(snapshot.elapsed_ms, profile.max_wall_time_ms):
            return self._stop(
                reason="max_wall_time exceeded",
                finish_reason="max_wall_time",
                current=snapshot.elapsed_ms,
                limit=profile.max_wall_time_ms,
                profile=snapshot.profile_name,
            )

        if self._reached(snapshot.turns_taken, profile.max_turns):
            return self._stop(
                reason="max_turns exceeded",
                finish_reason="max_turns",
                current=snapshot.turns_taken,
                limit=profile.max_turns,
                profile=snapshot.profile_name,
            )

        if self._reached(snapshot.total_tokens, profile.max_total_tokens):
            return self._stop(
                reason="max_total_tokens exceeded",
                finish_reason="max_tokens",
                current=snapshot.total_tokens,
                limit=profile.max_total_tokens,
                profile=snapshot.profile_name,
            )

        if profile.max_cost_usd is not None and snapshot.total_cost_usd >= profile.max_cost_usd:
            return self._stop(
                reason="max_cost_usd exceeded",
                finish_reason="max_cost",
                current=snapshot.total_cost_usd,
                limit=profile.max_cost_usd,
                profile=snapshot.profile_name,
            )

        if self._reached(snapshot.total_tool_calls, profile.max_tool_calls):
            return self._stop(
                reason="max_tool_calls exceeded",
                finish_reason="best_effort_budget_stop",
                current=snapshot.total_tool_calls,
                limit=profile.max_tool_calls,
                profile=snapshot.profile_name,
            )

        for tool_name, limit in profile.max_tool_calls_by_name.items():
            if self._reached(snapshot.per_tool_calls.get(tool_name, 0), limit):
                return self._stop(
                    reason=f"per-tool limit exceeded: {tool_name}",
                    finish_reason="best_effort_budget_stop",
                    tool_name=tool_name,
                    current=snapshot.per_tool_calls.get(tool_name, 0),
                    limit=limit,
                    profile=snapshot.profile_name,
                )

        if self._reached(state.spawn_count, profile.max_spawns):
            return self._stop(
                reason="max_spawns exceeded",
                finish_reason="best_effort_budget_stop",
                current=state.spawn_count,
                limit=profile.max_spawns,
                profile=snapshot.profile_name,
            )

        return None

    def _collect_warnings(self, state: TurnState) -> list[str]:
        snapshot = state.budget
        profile = snapshot.profile
        warnings: list[str] = []

        if self._is_near_limit(snapshot.turns_taken, profile.max_turns):
            warnings.append("turn budget nearly exhausted")

        if self._is_near_limit(snapshot.elapsed_ms, profile.max_wall_time_ms):
            warnings.append("wall time budget nearly exhausted")

        if self._is_near_limit(snapshot.total_tokens, profile.max_total_tokens):
            warnings.append("token budget nearly exhausted")

        if self._is_near_limit(snapshot.total_tool_calls, profile.max_tool_calls):
            warnings.append("tool call budget nearly exhausted")

        return warnings

    def _is_near_limit(self, value: int, limit: int) -> bool:
        if limit <= 0:
            return False
        return value >= int(limit * self.warn_threshold_pct)

    def _reached(self, value: int, limit: int) -> bool:
        if limit <= 0:
            return False
        return value >= limit

    def _stop(
        self,
        *,
        reason: str,
        finish_reason: FinishReason,
        **details: int | float | str,
    ) -> BudgetDecision:
        return BudgetDecision.stop(reason, finish_reason, **details)


__all__ = ["DefaultBudgetManager"]
