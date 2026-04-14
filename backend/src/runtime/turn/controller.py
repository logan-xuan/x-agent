"""Bounded turn controller skeleton for the new runtime."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..types import (
    AssessmentEngine,
    BudgetDecision,
    BudgetManager,
    CompactResult,
    GovernedToolPlan,
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
ExecutorFn = Callable[[GovernedToolPlan, TurnState], Awaitable[list[ToolExecutionResult]]]
CompactFn = Callable[[TurnState, str], Awaitable[TurnState | CompactResult]]


async def _default_planner(state: TurnState) -> ToolExecutionPlan | None:
    """Default planner stub used before model integration lands."""
    _ = state
    return ToolExecutionPlan()


async def _default_executor(
    plan: GovernedToolPlan,
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
    max_no_op_turns: int = 2

    async def run(self, request: TurnRequest) -> TurnResult:
        """Run a bounded turn loop until it converges or hits runtime controls."""
        state = TurnState.from_request(request)

        while True:
            budget_decision = self.budget_manager.evaluate(state)
            if budget_decision.action == "stop":
                return self._finish_from_budget(state, budget_decision)

            if budget_decision.action == "compact":
                state = self._apply_compact_result(
                    state,
                    await self.compact_fn(state, budget_decision.reason or "budget_compact"),
                )

            plan = await self.planner(state)
            tool_plan = plan or ToolExecutionPlan()
            governed_plan = self.tool_governor.validate_plan(tool_plan, state)

            for call in governed_plan.calls:
                state.record_tool_call(
                    call.tool_name,
                    signature=ToolCallSignature.from_args(call.tool_name, call.arguments),
                )

            observed = await self.executor(governed_plan, state)
            for result in observed:
                self.tool_governor.register_result(state, result)

            bridged_result = self._resolve_observed_turn_result(state, observed)
            if bridged_result is not None:
                return bridged_result

            if self._request_synthesis_after_rejected_plan(state, tool_plan, governed_plan):
                state.turn_index += 1
                continue

            if not governed_plan.calls and not observed:
                state.metadata["no_op_turns"] = state.metadata.get("no_op_turns", 0) + 1
            else:
                state.metadata["no_op_turns"] = 0

            assessment = self.assessment_engine.assess(state)
            state.last_assessment = assessment

            if (
                state.metadata.get("no_op_turns", 0) >= self.max_no_op_turns
                and assessment.controller_decision == "continue"
            ):
                assessment.controller_decision = "finish"
                assessment.finish_reason = "diminishing_returns"
                assessment.notes.append("controller converted no-op turn into finish")

            decision = assessment.controller_decision
            if decision == "continue":
                state.turn_index += 1
                continue
            if decision == "compact":
                state = self._apply_compact_result(
                    state,
                    await self.compact_fn(state, "assessment_compact"),
                )
                state.turn_index += 1
                continue
            if decision == "spawn":
                return TurnResult(
                    kind="spawn",
                    output_text=self._resolve_output_text(state),
                    updated_task_frame=state.task_frame,
                    artifact_refs=list(state.active_artifact_refs),
                    spawn_packet=assessment.spawn_packet,
                    metadata=self._metadata(state, assessment_notes=assessment.notes),
                )
            if decision == "abort":
                return TurnResult(
                    kind="abort",
                    finish_reason=assessment.finish_reason or "controller_abort",
                    output_text=self._resolve_output_text(state),
                    updated_task_frame=state.task_frame,
                    artifact_refs=list(state.active_artifact_refs),
                    metadata=self._metadata(state, assessment_notes=assessment.notes),
                )

            return TurnResult(
                kind="final",
                finish_reason=assessment.finish_reason or "done_definition_satisfied",
                output_text=self._resolve_output_text(state),
                updated_task_frame=state.task_frame,
                artifact_refs=list(state.active_artifact_refs),
                metadata=self._metadata(state, assessment_notes=assessment.notes),
            )

    def _apply_compact_result(
        self,
        state: TurnState,
        result: TurnState | CompactResult,
    ) -> TurnState:
        if isinstance(result, TurnState):
            return result

        state.active_messages = list(result.active_messages)
        state.active_artifact_refs = list(result.active_artifact_refs)
        if result.output_text:
            state.metadata["final_output_text"] = result.output_text
        if result.task_frame is not None:
            state.request.task_frame = result.task_frame
        state.metadata.update(result.metadata)
        return state

    def _finish_from_budget(
        self,
        state: TurnState,
        decision: BudgetDecision,
    ) -> TurnResult:
        return TurnResult(
            kind="final",
            finish_reason=decision.finish_reason or "best_effort_budget_stop",
            output_text=self._summarize_tool_results(state) or self._resolve_output_text(state),
            updated_task_frame=state.task_frame,
            artifact_refs=list(state.active_artifact_refs),
            metadata=self._metadata(
                state,
                budget_reason=decision.reason,
                budget_details=decision.details,
            ),
        )

    def _resolve_output_text(self, state: TurnState) -> str | None:
        final_output = state.metadata.get("final_output_text")
        if isinstance(final_output, str) and final_output:
            return self._apply_output_contract_guard(
                state,
                self._inject_generate_image_markdown(state, final_output),
            )

        for result in reversed(state.tool_results):
            if result.success and result.output:
                return self._apply_output_contract_guard(
                    state,
                    self._inject_generate_image_markdown(state, result.output),
                )
        return None

    def _apply_output_contract_guard(self, state: TurnState, text: str) -> str:
        """Block unverified success text when deterministic routing requires concrete tool evidence."""
        route_decision = state.metadata.get("runtime_route_decision")
        if not isinstance(route_decision, dict):
            return text

        policy = route_decision.get("policy")
        if not isinstance(policy, dict):
            return text
        postconditions = policy.get("postconditions")
        if not isinstance(postconditions, dict):
            return text

        required_tool = postconditions.get("require_successful_tool")
        if not isinstance(required_tool, str) or not required_tool.strip():
            return text

        has_success = any(
            result.tool_name == required_tool and result.success for result in state.tool_results
        )
        if has_success:
            return text

        violation = f"deterministic route 要求工具 `{required_tool}` 成功执行。"
        state.metadata["output_contract_violation"] = violation
        return f"未完成可验证的结果输出：{violation}"

    def _inject_generate_image_markdown(self, state: TurnState, text: str) -> str:
        """Inject first generated image markdown into final output when missing."""

        if not text.strip():
            return text
        if re.search(r"!\[[^\]]*\]\((https?:\/\/[^\s)]+)\)", text):
            return text

        image_url = self._latest_generate_image_url(state)
        if not image_url:
            return text
        return f"![生成图片]({image_url})\n\n{text}"

    def _latest_generate_image_url(self, state: TurnState) -> str | None:
        """Return the latest successful generate_image public URL."""

        for result in reversed(state.tool_results):
            if result.tool_name != "generate_image" or not result.success:
                continue
            assets = result.metadata.get("assets")
            if not isinstance(assets, list) or not assets:
                continue
            first_asset = assets[0]
            if not isinstance(first_asset, dict):
                continue
            public_url = first_asset.get("public_url")
            if isinstance(public_url, str) and public_url.strip():
                return public_url
        return None

    def _summarize_tool_results(self, state: TurnState) -> str | None:
        """Build a bounded best-effort summary instead of leaking one raw tool payload."""
        snippets: list[str] = []
        for result in state.tool_results[-4:]:
            text = (result.output or result.error or "").strip()
            if not text:
                continue
            normalized = " ".join(text.split())
            prefix = "error" if not result.success else "evidence"
            snippets.append(f"[{prefix}] {result.tool_name}: {normalized[:240]}")

        if not snippets:
            return None
        return "基于当前已获取的信息，先给出最佳努力结果：\n\n" + "\n\n".join(snippets)

    def _resolve_observed_turn_result(
        self,
        state: TurnState,
        observed: list[ToolExecutionResult],
    ) -> TurnResult | None:
        for result in reversed(observed):
            candidate = result.metadata.get("turn_result")
            if not isinstance(candidate, TurnResult):
                continue

            merged_metadata = dict(candidate.metadata)
            merged_metadata.update(
                self._metadata(
                    state,
                    bridged_by=result.tool_name,
                )
            )
            return TurnResult(
                kind=candidate.kind,
                finish_reason=candidate.finish_reason,
                output_text=candidate.output_text,
                updated_task_frame=candidate.updated_task_frame,
                artifact_refs=list(candidate.artifact_refs),
                spawn_packet=candidate.spawn_packet,
                metadata=merged_metadata,
            )
        return None

    def _request_synthesis_after_rejected_plan(
        self,
        state: TurnState,
        tool_plan: ToolExecutionPlan,
        governed_plan: GovernedToolPlan,
    ) -> bool:
        """When all planned calls are rejected, force one synthesis round instead of no-op finishing."""
        if not tool_plan.calls or governed_plan.calls or not governed_plan.rejected_calls:
            return False

        rejected_names = [call.tool_name for call in governed_plan.rejected_calls]
        disabled = state.metadata.setdefault("disabled_tool_names", set())
        disabled.update(rejected_names)
        warnings = "; ".join(governed_plan.warnings)
        state.metadata["runtime_synthesis_instruction"] = (
            "工具治理已拒绝继续调用以下工具："
            f"{', '.join(rejected_names)}。"
            "不要继续调用这些工具。"
            "请基于当前已获得的证据直接完成综合分析；"
            "如果用户要求文件交付物且仍可使用 write_file 等非搜索工具，请直接生成交付物。"
            + (f" 拒绝原因：{warnings}" if warnings else "")
        )
        state.metadata["no_op_turns"] = 0
        return True

    def _metadata(self, state: TurnState, **extra: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "turn_index": state.turn_index,
            "budget": {
                "profile_name": state.budget.profile_name,
                "turns_taken": state.budget.turns_taken,
                "elapsed_ms": state.budget.elapsed_ms,
                "total_tokens": state.budget.total_tokens,
                "total_tool_calls": state.budget.total_tool_calls,
                "per_tool_calls": dict(state.budget.per_tool_calls),
            },
        }
        if "model" in state.metadata:
            metadata["model"] = state.metadata["model"]
        if "provider" in state.metadata:
            metadata["provider"] = state.metadata["provider"]
        if "runtime_event_timeline" in state.metadata:
            metadata["runtime_event_timeline"] = list(state.metadata["runtime_event_timeline"])
        runtime_model_budget = state.metadata.get("runtime_model_budget")
        if not isinstance(runtime_model_budget, dict):
            request_budget_hints = state.request.metadata.get("_runtime_model_budget_hints")
            if isinstance(request_budget_hints, dict):
                runtime_model_budget = request_budget_hints
        if isinstance(runtime_model_budget, dict):
            metadata["runtime_model_budget"] = dict(runtime_model_budget)
        for key in (
            "compaction_source",
            "compression_operations",
            "budget_state",
            "verifier_result",
            "rollback",
            "rollback_applied",
            "rollback_reason",
            "runtime_context_summary",
        ):
            if key not in state.metadata:
                continue
            value = state.metadata[key]
            if isinstance(value, dict):
                metadata[key] = dict(value)
            elif isinstance(value, list):
                metadata[key] = list(value)
            else:
                metadata[key] = value
        metadata.update(extra)
        return metadata


__all__ = ["DefaultTurnController"]
