"""Unit tests for the runtime turn controller skeleton."""

from src.runtime.turn.assessment import DefaultAssessmentEngine
from src.runtime.turn.controller import DefaultTurnController
from src.runtime.turn.state import TurnState
from src.runtime.turn.tool_governor import DefaultToolGovernor
from src.runtime.types import (
    GovernedToolPlan,
    LoopAssessment,
    RouteMeta,
    SessionDescriptor,
    SpawnPacket,
    TaskFrame,
    ToolCallSpec,
    ToolExecutionPlan,
    ToolExecutionResult,
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
