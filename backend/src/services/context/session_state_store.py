"""Lightweight in-memory session state store used by runtime compatibility tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._shared import get_context_bucket


@dataclass
class SessionContextState:
    session_id: str
    mode: str = "research"
    summary_text: str = ""
    token_estimate: int = 0
    current_goal: dict[str, Any] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    user_preferences: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    active_subtasks: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "summary_text": self.summary_text,
            "token_estimate": self.token_estimate,
            "current_goal": dict(self.current_goal),
            "open_questions": list(self.open_questions),
            "constraints": list(self.constraints),
            "user_preferences": list(self.user_preferences),
            "decisions": list(self.decisions),
            "active_subtasks": [dict(item) for item in self.active_subtasks],
            "metadata": dict(self.metadata),
        }


class SessionContextStateStore:
    """Store per-session structured context state."""

    def __init__(self, storage: Any) -> None:
        self._bucket = get_context_bucket(storage)["session_state"]

    async def upsert(
        self,
        session_id: str,
        *,
        mode: str,
        summary_text: str = "",
        token_estimate: int = 0,
        current_goal: dict[str, Any] | None = None,
        open_questions: list[str] | None = None,
        constraints: list[str] | None = None,
        user_preferences: list[str] | None = None,
        decisions: list[str] | None = None,
        active_subtasks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionContextState:
        state = self._bucket.get(session_id) or SessionContextState(session_id=session_id)
        state.mode = mode
        state.summary_text = summary_text or state.summary_text
        state.token_estimate = token_estimate or state.token_estimate
        if current_goal is not None:
            state.current_goal = dict(current_goal)
        if open_questions is not None:
            state.open_questions = list(open_questions)
        if constraints is not None:
            state.constraints = list(constraints)
        if user_preferences is not None:
            state.user_preferences = list(user_preferences)
        if decisions is not None:
            state.decisions = list(decisions)
        if active_subtasks is not None:
            state.active_subtasks = [dict(item) for item in active_subtasks]
        if metadata is not None:
            state.metadata = dict(metadata)
        self._bucket[session_id] = state
        return state

    async def get(self, session_id: str) -> SessionContextState | None:
        return self._bucket.get(session_id)
