"""Persistence service for structured session context state."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ...models.context_state import SessionContextState
from ..storage import StorageService, get_storage_service


_JSON_FIELDS = {
    "current_goal": "current_goal_json",
    "active_subtasks": "active_subtasks_json",
    "decisions": "decisions_json",
    "constraints": "constraints_json",
    "open_questions": "open_questions_json",
    "artifact_refs": "artifact_refs_json",
    "delegate_status": "delegate_status_json",
    "recent_failures": "recent_failures_json",
    "user_preferences": "user_preferences_json",
    "metadata": "metadata_json",
}


class SessionContextStateStore:
    """CRUD helpers for SessionContextState rows."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or get_storage_service()

    async def get(self, session_id: str) -> SessionContextState | None:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(SessionContextState).where(SessionContextState.session_id == session_id)
            )
            return result.scalar_one_or_none()

    async def upsert(
        self,
        session_id: str,
        *,
        mode: str | None = None,
        summary_text: str | None = None,
        token_estimate: int | None = None,
        increment_version: bool = True,
        **payload: Any,
    ) -> SessionContextState:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(SessionContextState).where(SessionContextState.session_id == session_id)
            )
            state = result.scalar_one_or_none()
            if state is None:
                state = SessionContextState(session_id=session_id, version=1)
                db_session.add(state)
            elif increment_version:
                state.version += 1

            if mode is not None:
                state.mode = mode
            if summary_text is not None:
                state.summary_text = summary_text
            if token_estimate is not None:
                state.token_estimate = token_estimate

            for field, attr in _JSON_FIELDS.items():
                if field in payload:
                    setattr(state, attr, _dump_json(payload[field]))

            state.updated_at = datetime.now()
            await db_session.flush()
            await db_session.refresh(state)
            return state

    async def delete(self, session_id: str) -> bool:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(SessionContextState).where(SessionContextState.session_id == session_id)
            )
            state = result.scalar_one_or_none()
            if state is None:
                return False
            await db_session.delete(state)
            return True


_session_context_state_store: SessionContextStateStore | None = None


def get_session_context_state_store() -> SessionContextStateStore:
    global _session_context_state_store
    if _session_context_state_store is None:
        _session_context_state_store = SessionContextStateStore()
    return _session_context_state_store


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
