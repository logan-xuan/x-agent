"""Assessment engine for bounded turn-loop convergence decisions."""

from __future__ import annotations

from dataclasses import dataclass

from ..types import LoopAssessment, SpawnPacket
from .finish_reason import FinishReason
from .state import FailureCluster, TurnState


@dataclass
class DefaultAssessmentEngine:
    """Convert loop state into a controller decision."""

    novelty_floor: float = 0.15
    compact_pressure_pct: float = 0.65
    breaker_failure_count: int = 3
    repeated_signature_finish_count: int = 3

    def assess(self, state: TurnState) -> LoopAssessment:
        """Assess whether the loop is progressing or should converge."""
        unresolved_count = len(state.task_frame.unresolved)
        novelty_score = self._novelty_score(state)
        repeated_pattern_score = self._repeated_pattern_score(state)

        decision = "continue"
        finish_reason: FinishReason | None = None
        notes: list[str] = []
        suggested_next_action = "continue current loop"
        risk_level = "low"
        spawn_packet: SpawnPacket | None = None

        if isinstance(state.request.metadata.get("spawn_packet"), SpawnPacket):
            decision = "spawn"
            spawn_packet = state.request.metadata["spawn_packet"]
            suggested_next_action = "spawn child session"
            notes.append("spawn requested by runtime metadata")
        elif state.request.metadata.get("request_compact"):
            decision = "compact"
            suggested_next_action = "compact context before next step"
            notes.append("compaction requested by runtime metadata")
        elif self._done_definition_satisfied(state):
            decision = "finish"
            finish_reason = "done_definition_satisfied"
            suggested_next_action = "finish with completed task frame"
            notes.append("all unresolved items are cleared")
        elif self._breaker_triggered(state):
            decision = "finish"
            finish_reason = "breaker"
            suggested_next_action = "stop on repeated failure breaker"
            risk_level = "high"
            notes.append("failure cluster breaker triggered")
        elif self._diminishing_returns(state, unresolved_count, novelty_score, repeated_pattern_score):
            decision = "finish"
            finish_reason = "diminishing_returns"
            suggested_next_action = "finish with best effort due to diminishing returns"
            risk_level = "medium"
            notes.append("progress stalled across consecutive assessments")
        elif (
            state.budget.profile.collapse_trigger_tokens > 0
            and state.budget.total_tokens >= state.budget.profile.collapse_trigger_tokens
        ) or state.budget.token_pressure() >= self.compact_pressure_pct:
            decision = "compact"
            suggested_next_action = "compact active context before continuing"
            notes.append("token pressure is approaching collapse threshold")

        return LoopAssessment(
            turn=state.turn_index,
            unresolved_count=unresolved_count,
            novelty_score=novelty_score,
            repeated_pattern_score=repeated_pattern_score,
            risk_level=risk_level,
            budget_remaining=state.budget,
            suggested_next_action=suggested_next_action,
            controller_decision=decision,
            finish_reason=finish_reason,
            spawn_packet=spawn_packet,
            notes=notes,
        )

    def _done_definition_satisfied(self, state: TurnState) -> bool:
        return bool(state.task_frame.done_definition) and not state.task_frame.unresolved

    def _breaker_triggered(self, state: TurnState) -> bool:
        if not state.repeated_failures:
            return False
        return max(cluster.count for cluster in state.repeated_failures) >= self.breaker_failure_count

    def _diminishing_returns(
        self,
        state: TurnState,
        unresolved_count: int,
        novelty_score: float,
        repeated_pattern_score: float,
    ) -> bool:
        if repeated_pattern_score >= 1.0:
            return True

        previous = state.last_assessment
        if previous is None:
            return False

        unresolved_stalled = unresolved_count >= previous.unresolved_count
        novelty_stalled = novelty_score < self.novelty_floor and previous.novelty_score < self.novelty_floor
        repeated_stalled = repeated_pattern_score >= 0.75 and previous.repeated_pattern_score >= 0.75
        return unresolved_stalled and (novelty_stalled or repeated_stalled)

    def _novelty_score(self, state: TurnState) -> float:
        results = state.tool_results
        if not results:
            return 0.0 if state.last_assessment else 1.0

        total = len(results)
        unique_successes = len({result.tool_name for result in results if result.success})
        success_ratio = sum(1 for result in results if result.success) / total
        diversity_ratio = unique_successes / total if total else 0.0
        signature_penalty = self._signature_penalty(state)
        score = (0.5 * success_ratio) + (0.5 * diversity_ratio) - signature_penalty
        return max(0.0, min(score, 1.0))

    def _repeated_pattern_score(self, state: TurnState) -> float:
        signature_penalty = self._signature_penalty(state)
        failure_penalty = self._failure_penalty(state.repeated_failures)
        return max(signature_penalty, failure_penalty)

    def _signature_penalty(self, state: TurnState) -> float:
        if not state.tool_signature_counts:
            return 0.0
        repeated = max(state.tool_signature_counts.values())
        return min(repeated / self.repeated_signature_finish_count, 1.0)

    def _failure_penalty(self, clusters: list[FailureCluster]) -> float:
        if not clusters:
            return 0.0
        repeated = max(cluster.count for cluster in clusters)
        return min(repeated / self.breaker_failure_count, 1.0)


__all__ = ["DefaultAssessmentEngine"]
