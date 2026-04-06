"""Unit tests for the first runtime budget manager skeleton."""

import time

from src.runtime.turn.budget import DefaultBudgetManager
from src.runtime.turn.state import TurnState
from src.runtime.types import RouteMeta, SessionDescriptor, TaskFrame, TurnBudgetProfile, TurnRequest


def _build_state(profile: TurnBudgetProfile | None = None) -> TurnState:
    request = TurnRequest(
        session=SessionDescriptor(
            session_key="session-1",
            session_id="session-1",
            budget_profile="test-profile",
        ),
        user_input="整理当前任务",
        task_frame=TaskFrame(),
        route=RouteMeta(channel="test"),
    )
    return TurnState.from_request(
        request,
        budget_profile=profile,
        profile_name="test-profile",
        started_at_ms=int(time.time() * 1000),
    )


def test_turn_state_uses_user_input_as_default_objective():
    state = _build_state()

    assert state.task_frame.objective == "整理当前任务"


def test_budget_manager_stops_when_max_turns_is_reached():
    manager = DefaultBudgetManager()
    state = _build_state(TurnBudgetProfile(max_turns=2))
    state.turn_index = 2

    decision = manager.evaluate(state)

    assert decision.action == "stop"
    assert decision.finish_reason == "max_turns"


def test_budget_manager_requests_compaction_before_hard_stop():
    manager = DefaultBudgetManager()
    state = _build_state(
        TurnBudgetProfile(
            max_total_tokens=200,
            compact_trigger_tokens=100,
        )
    )
    state.record_token_usage(input_tokens=60, output_tokens=60)

    decision = manager.evaluate(state)

    assert decision.action == "compact"
    assert decision.reason == "compact_trigger_tokens reached"


def test_budget_manager_stops_on_per_tool_limit():
    manager = DefaultBudgetManager()
    state = _build_state(
        TurnBudgetProfile(
            max_tool_calls=10,
            max_tool_calls_by_name={"web_search": 2},
        )
    )
    state.record_tool_call("web_search")
    state.record_tool_call("web_search")

    decision = manager.evaluate(state)

    assert decision.action == "stop"
    assert decision.finish_reason == "best_effort_budget_stop"
    assert decision.details["tool_name"] == "web_search"
