"""Session storage primitives for the runtime orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ..types import SessionDescriptor


@dataclass
class InMemorySessionStore:
    """In-memory session store for early runtime orchestration work."""

    _sessions: dict[str, SessionDescriptor] = field(default_factory=dict)

    async def get(self, session_key: str) -> SessionDescriptor | None:
        """Return a session descriptor by key."""
        return self._sessions.get(session_key)

    async def put(self, session: SessionDescriptor) -> None:
        """Persist or replace a session descriptor."""
        self._sessions[session.session_key] = session

    async def patch(self, session_key: str, values: dict[str, object]) -> SessionDescriptor:
        """Patch selected fields on a stored session descriptor."""
        current = self._sessions[session_key]
        updated = replace(current, **values)
        self._sessions[session_key] = updated
        return updated

    async def list(self) -> list[SessionDescriptor]:
        """Return all stored sessions."""
        return list(self._sessions.values())


__all__ = ["InMemorySessionStore"]
