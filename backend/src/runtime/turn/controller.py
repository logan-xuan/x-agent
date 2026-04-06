"""Bounded turn controller skeleton for the new runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..types import (
    AssessmentEngine,
    BudgetDecision,
    BudgetManager,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolGovernor,
    TurnRequest,
    TurnResult,
)
from .assessment import DefaultAssessmentEngine
from .budget import DefaultBudgetManager
from .state import ToolCallSignature, TurnState
from .tool_governor import DefaultToolGovernor

PlannerFn = Callable[[TurnState], Awaitable[ToolExecutionPlan | None]]
ExecutorFn = Callable[[ToolExecutionPlan, TurnState], Awaitable[list[ToolExecutionResult]]]
CompactFn = Callable[[TurnState, str], Awaitable[TurnState]]


async def _default_planner(state: TurnState) -> ToolExecutionPlan | None:
    """Default planner stub used before model integration lands."""
    _ = state
    return ToolExecutionPlan()


async def _default_executor(
    plan: ToolExecutionPlan,
    state: TurnState,
) -> list[ToolExecutionResult]:
    """Default executor stub used before tool integration lands."""
    _ = plan
    _ = state
    return []


async def _default_compact(state: TurnState, reason: str) -> TurnState:
    """Default compaction stub that only annotates state metadata."""
    state.metadata["last_compaction_reason"] = reason
    state.metadata["compaction_count"] = state.metadata.get("compaction_count", 0) + 1
    return state


@dataclass
class DefaultTurnController:
    """Minimal bounded loop controller that orchestrates budget, tools, and assessment."""

    budget_manager: BudgetManager = field(default_factory=DefaultBudgetManager)
    assessment_engine: AssessmentEngine = field(default_factory=DefaultAssessmentEngine)
    tool_governor: ToolGovernor = field(default_factory=DefaultToolGovernor)
    planner: PlannerFn = _default_planner
    executor: ExecutorFn = _default_executor
    compact_fn: CompactFn = _default_compact

    async def run(self, request: TurnRequest) -> TurnResult:
        """Run a bounded turn loop until it converges or hits runtime controls."""
        state = TurnState.from_request(request)

        while True:
            budget_decision = self.budget_manager.evaluate(state)
            if budget_decision.action == "stop":
                return self._finish_from_budget(state, budget_decision)

            if budget_decision.action == "compact":
                state = await self.compact_fn(state, budget_decision.reason or "budget_compact")

            plan = await self.planner(state)
            tool_plan = plan or ToolExecutionPlan()
            governed_plan = self.tool_governor.validate_plan(tool_plan, state)

            for call in governed_plan.calls:
                state.record_tool_call(
                    call.tool_name,
                    signature=ToolCallSignature.from_args(call.tool_name, call.arguments),
                )

            observed = await self.executor(
                ToolExecutionPlan(calls=governed_plan.calls, allow_parallel=tool_plan.allow_parallel),
                state,
            )
            for result in observed:
                self.tool_governor.register_result(state, result)

            if not governed_plan.calls and not observed:
                state.metadata["no_op_turns"] = state.metadata.get("no_op_turns", 0) + 1
            else:
                state.metadata["no_op_turns"] = 0

            assessment = self.assessment_engine.assess(state)
            state.last_assessment = assessment

            if state.metadata.get("no_op_turns", 0) >= 1 and assessment.controller_decision == "continue":
                assessment.controller_decision = "finish"
                assessment.finish_reason = "diminishing_returns"
                assessment.notes.append("controller converted no-op turn into finish")

            decision = assessment.controller_decision
            if decision == "continue":
                state.turn_index += 1
                continue
            if decision == "compact":
                state = await self.compact_fn(state, "assessment_compact")
                state.turn_index += 1
                continue
            if decision == "spawn":
                return TurnResult(
                    kind="spawn",
                    updated_task_frame=state.task_frame,
                    artifact_refs=list(state.active_artifact_refs),
                    spawn_packet=assessment.spawn_packet,
                    metadata=self._metadata(state, assessment_notes=assessment.notes),
                )
            if decision == "abort":
                return TurnResult(
                    kind="abort",
                    finish_reason=assessment.finish_reason or "controller_abort",
                    updated_task_frame=state.task_frame,
                    artifact_refs=list(state.active_artifact_refs),
                    metadata=self._metadata(state, assessment_notes=assessment.notes),
                )

            return TurnResult(
                kind="final",
                finish_reason=assessment.finish_reason or "done_definition_satisfied",
                updated_task_frame=state.task_frame,
                artifact_refs=list(state.active_artifact_refs),
                metadata=self._metadata(state, assessment_notes=assessment.notes),
            )

    def _finish_from_budget(self, state: TurnState, decision: BudgetDecision) -> TurnResult:
        return TurnResult(
            kind="final",
            finish_reason=decision.finish_reason or "best_effort_budget_stop",
            updated_task_frame=state.task_frame,
            artifact_refs=list(state.active_artifact_refs),
            metadata=self._metadata(state, budget_reason=decision.reason, budget_details=decision.details),
        )

    def _metadata(self, state: TurnState, **extra: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "turn_index": state.turn_index,
            "budget": {
                "profile_name": state.budget.profile_name,
                "turns_taken": state.budget.turns_taken,
                "elapsed_ms": state.budget.elapsed_ms,
                "total_tokens": state.budget.total_tokens,
                "total_tool_calls": state.budget.total_tool_calls,
            },
        }
        metadata.update(extra)
        return metadata


__all__ = ["DefaultTurnController"]
