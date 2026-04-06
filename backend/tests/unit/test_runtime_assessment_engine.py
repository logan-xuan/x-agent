"""Unit tests for the runtime assessment engine skeleton."""

from src.runtime.turn.assessment import DefaultAssessmentEngine
from src.runtime.turn.state import ToolCallSignature, TurnState
from src.runtime.types import (
    RouteMeta,
    SessionDescriptor,
    SpawnPacket,
    TaskFrame,
    ToolExecutionResult,
    TurnRequest,
)


def _build_state(task_frame: TaskFrame | None = None) -> TurnState:
    request = TurnRequest(
        session=SessionDescriptor(session_key="session-1", session_id="session-1"),
        user_input="调研任务",
        task_frame=task_frame or TaskFrame(objective="调研任务", unresolved=["q1"]),
        route=RouteMeta(channel="test"),
    )
    return TurnState.from_request(request)


def test_assessment_finishes_when_done_definition_is_satisfied():
    engine = DefaultAssessmentEngine()
    state = _build_state(TaskFrame(objective="完成", done_definition=["总结"], unresolved=[]))

    assessment = engine.assess(state)

    assert assessment.controller_decision == "finish"
    assert assessment.finish_reason == "done_definition_satisfied"


def test_assessment_finishes_on_diminishing_returns():
    engine = DefaultAssessmentEngine()
    state = _build_state()
    state.tool_signature_counts[ToolCallSignature.from_args("web_search", {"q": "same"})] = 2
    state.last_assessment = engine.assess(state)
    state.tool_signature_counts[ToolCallSignature.from_args("web_search", {"q": "same"})] = 3

    assessment = engine.assess(state)

    assert assessment.controller_decision == "finish"
    assert assessment.finish_reason == "diminishing_returns"


def test_assessment_returns_spawn_when_spawn_packet_is_requested():
    engine = DefaultAssessmentEngine()
    packet = SpawnPacket(objective="子任务", deliverable="摘要")
    state = _build_state()
    state.request.metadata["spawn_packet"] = packet

    assessment = engine.assess(state)

    assert assessment.controller_decision == "spawn"
    assert assessment.spawn_packet == packet


def test_assessment_returns_breaker_on_repeated_failures():
    engine = DefaultAssessmentEngine()
    state = _build_state()
    for _ in range(3):
        state.record_failure("web_search:timeout", "timeout")
    state.record_tool_result(ToolExecutionResult(tool_name="web_search", success=False, error="timeout"))

    assessment = engine.assess(state)

    assert assessment.controller_decision == "finish"
    assert assessment.finish_reason == "breaker"
