"""Finish reasons for the bounded runtime turn loop."""

from __future__ import annotations

from typing import Literal, cast, get_args


FinishReason = Literal[
    "done_definition_satisfied",
    "max_turns",
    "max_wall_time",
    "max_tokens",
    "max_cost",
    "diminishing_returns",
    "breaker",
    "controller_abort",
    "best_effort_budget_stop",
]


ALL_FINISH_REASONS = cast(tuple[FinishReason, ...], get_args(FinishReason))

BUDGET_STOP_FINISH_REASONS: frozenset[FinishReason] = frozenset(
    {
        "max_turns",
        "max_wall_time",
        "max_tokens",
        "max_cost",
        "best_effort_budget_stop",
    }
)


def is_finish_reason(value: str) -> bool:
    """Return whether a string is a valid finish reason."""
    return value in ALL_FINISH_REASONS


def is_budget_stop_reason(reason: FinishReason) -> bool:
    """Return whether a finish reason was caused by a budget guard."""
    return reason in BUDGET_STOP_FINISH_REASONS


__all__ = [
    "ALL_FINISH_REASONS",
    "BUDGET_STOP_FINISH_REASONS",
    "FinishReason",
    "is_budget_stop_reason",
    "is_finish_reason",
]
