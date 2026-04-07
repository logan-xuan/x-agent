"""Unit tests for the runtime turn controller skeleton."""

from src.runtime.turn.assessment import DefaultAssessmentEngine
from src.runtime.types import BudgetDecision
from src.runtime.turn.controller import DefaultTurnController
from src.runtime.turn.state import TurnState
from src.runtime.turn.tool_governor import DefaultToolGovernor
from src.runtime.types import (
    ToolPolicy,
    GovernedToolPlan,
    LoopAssessment,
    RouteMeta,
    SessionDescriptor,
    SpawnPacket,
    TaskFrame,
    ToolCallSpec,
    ToolExecutionPlan,
    ToolExecutionResult,
    TurnBudgetProfile,
    TurnRequest,
)


def _request(metadata: dict | None = None) -> TurnRequest:
    return TurnRequest(
        session=SessionDescriptor(session_key="session-1", session_id="session-1"),
        user_input="执行任务",
        task_frame=TaskFrame(objective="执行任务", unresolved=["step-1"]),
        route=RouteMeta(channel="test"),
        metadata=metadata or {},
    )


async def _planner_with_tool(state: TurnState) -> ToolExecutionPlan:
    _ = state
    return ToolExecutionPlan(calls=[ToolCallSpec(tool_name="web_search", arguments={"q": "runtime"})])


async def _executor(plan: ToolExecutionPlan, state: TurnState) -> list[ToolExecutionResult]:
    _ = state
    return [
        ToolExecutionResult(
            tool_name=call.tool_name,
            success=True,
            output="found evidence",
        )
        for call in plan.calls
    ]


def test_turn_controller_returns_spawn_packet_when_assessment_requests_spawn():
    controller = DefaultTurnController(
        planner=_planner_with_tool,
        executor=_executor,
    )
    packet = SpawnPacket(objective="子任务", deliverable="调研摘要")

    result = __import__("asyncio").run(controller.run(_request({"spawn_packet": packet})))

    assert result.kind == "spawn"
    assert result.spawn_packet == packet


def test_turn_controller_finishes_on_no_op_turn():
    controller = DefaultTurnController(max_no_op_turns=2)

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.finish_reason == "diminishing_returns"
    assert result.metadata["turn_index"] == 1


def test_turn_controller_finishes_after_successful_assessment():
    class FinishingAssessment(DefaultAssessmentEngine):
        def assess(self, state: TurnState) -> LoopAssessment:
            assessment = super().assess(state)
            assessment.controller_decision = "finish"
            assessment.finish_reason = "done_definition_satisfied"
            state.request.task_frame.unresolved.clear()
            state.request.task_frame.done_definition = ["deliver"]
            return assessment

    controller = DefaultTurnController(
        assessment_engine=FinishingAssessment(),
        tool_governor=DefaultToolGovernor(),
        planner=_planner_with_tool,
        executor=_executor,
    )

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.finish_reason == "done_definition_satisfied"
    assert result.output_text == "found evidence"


def test_turn_controller_passes_governed_plan_to_executor():
    observed: dict[str, object] = {}

    async def executor(plan: GovernedToolPlan, state: TurnState) -> list[ToolExecutionResult]:
        observed["max_parallelism"] = plan.max_parallelism
        observed["rejected_calls"] = len(plan.rejected_calls)
        _ = state
        return []

    class SinglePassAssessment(DefaultAssessmentEngine):
        def assess(self, state: TurnState) -> LoopAssessment:
            return LoopAssessment(
                turn=state.turn_index,
                unresolved_count=0,
                novelty_score=1.0,
                repeated_pattern_score=0.0,
                controller_decision="finish",
                finish_reason="done_definition_satisfied",
            )

    controller = DefaultTurnController(
        assessment_engine=SinglePassAssessment(),
        tool_governor=DefaultToolGovernor(),
        planner=_planner_with_tool,
        executor=executor,
        max_no_op_turns=2,
    )

    __import__("asyncio").run(controller.run(_request()))

    assert observed["max_parallelism"] == 1
    assert observed["rejected_calls"] == 0


def test_turn_controller_budget_stop_uses_best_effort_summary_not_raw_last_tool_payload():
    controller = DefaultTurnController()
    state = TurnState.from_request(_request())
    state.tool_results.extend(
        [
            ToolExecutionResult(
                tool_name="web_search",
                success=True,
                output="first useful evidence about market trends",
            ),
            ToolExecutionResult(
                tool_name="fetch_web_content",
                success=False,
                error="redirect error from source site",
            ),
        ]
    )

    result = controller._finish_from_budget(
        state,
        BudgetDecision.stop("token budget exhausted", "max_tokens"),
    )

    assert result.output_text is not None
    assert "最佳努力结果" in result.output_text
    assert "web_search" in result.output_text
    assert "fetch_web_content" in result.output_text


def test_turn_controller_requests_synthesis_when_all_planned_search_calls_are_rejected():
    async def planner(state: TurnState) -> ToolExecutionPlan:
        if state.metadata.get("runtime_synthesis_instruction"):
            state.metadata["final_output_text"] = "synthesized final answer"
            state.metadata["final_candidate_ready"] = True
            return ToolExecutionPlan()
        return ToolExecutionPlan(
            calls=[
                ToolCallSpec(tool_name="web_search", arguments={"q": "multi-agent"}),
            ]
        )

    async def executor(plan: GovernedToolPlan, state: TurnState) -> list[ToolExecutionResult]:
        _ = plan, state
        return []

    request = _request()
    request.metadata["_runtime_budget_profile"] = TurnBudgetProfile(max_total_tokens=120000)
    controller = DefaultTurnController(
        planner=planner,
        executor=executor,
        tool_governor=DefaultToolGovernor(
            policies_by_name={
                "web_search": ToolPolicy(
                    max_uses_per_turn=0,
                    repeat_signature_limit=1,
                )
            }
        ),
    )

    result = __import__("asyncio").run(controller.run(request))

    assert result.kind == "final"
    assert result.output_text == "synthesized final answer"
    assert result.finish_reason == "done_definition_satisfied"
