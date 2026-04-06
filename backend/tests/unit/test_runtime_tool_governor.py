"""Unit tests for the runtime tool governor skeleton."""

from src.runtime.turn.state import ToolCallSignature, TurnState
from src.runtime.turn.tool_governor import DefaultToolGovernor
from src.runtime.types import (
    RouteMeta,
    SessionDescriptor,
    ToolCallSpec,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolPolicy,
    TurnBudgetProfile,
    TurnRequest,
    TaskFrame,
)


def _build_state(*, lane: str = "main") -> TurnState:
    request = TurnRequest(
        session=SessionDescriptor(
            session_key="session-1",
            session_id="session-1",
            lane=lane,  # type: ignore[arg-type]
        ),
        user_input="继续执行",
        task_frame=TaskFrame(objective="继续执行"),
        route=RouteMeta(channel="test"),
    )
    return TurnState.from_request(
        request,
        budget_profile=TurnBudgetProfile(max_parallel_tools=4),
    )


def test_tool_governor_sets_default_timeout_and_parallelism():
    governor = DefaultToolGovernor(
        policies_by_name={
            "web_search": ToolPolicy(default_timeout_ms=1234, max_parallelism=2),
            "fetch": ToolPolicy(default_timeout_ms=2222, max_parallelism=1),
        }
    )
    state = _build_state()

    plan = governor.validate_plan(
        ToolExecutionPlan(
            calls=[
                ToolCallSpec(tool_name="web_search", arguments={"q": "x"}),
                ToolCallSpec(tool_name="fetch", arguments={"url": "https://example.com"}),
            ],
            allow_parallel=True,
        ),
        state,
    )

    assert [call.timeout_ms for call in plan.calls] == [1234, 2222]
    assert plan.max_parallelism == 1


def test_tool_governor_blocks_repeated_signature():
    governor = DefaultToolGovernor(
        policies_by_name={"web_search": ToolPolicy(repeat_signature_limit=2)}
    )
    state = _build_state()
    signature = ToolCallSignature.from_args("web_search", {"q": "same"})
    state.tool_signature_counts[signature] = 2

    plan = governor.validate_plan(
        ToolExecutionPlan(calls=[ToolCallSpec(tool_name="web_search", arguments={"q": "same"})]),
        state,
    )

    assert plan.calls == []
    assert len(plan.rejected_calls) == 1
    assert "repeat_signature_limit" in plan.warnings[0]


def test_tool_governor_blocks_subagent_disallowed_tool_and_records_failure():
    governor = DefaultToolGovernor(
        policies_by_name={"terminal": ToolPolicy(allow_in_subagent=False)}
    )
    state = _build_state(lane="subagent")

    plan = governor.validate_plan(
        ToolExecutionPlan(calls=[ToolCallSpec(tool_name="terminal", arguments={"cmd": "ls"})]),
        state,
    )
    governor.register_result(
        state,
        ToolExecutionResult(tool_name="terminal", success=False, error="permission denied"),
    )

    assert plan.calls == []
    assert "disabled in subagent" in plan.warnings[0]
    assert state.repeated_failures[0].fingerprint.startswith("terminal:")
