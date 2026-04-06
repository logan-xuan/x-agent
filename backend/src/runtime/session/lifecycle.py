"""Session lifecycle helpers for the runtime orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass

from ..types import SessionDescriptor


@dataclass
class SessionLifecycleManager:
    """Apply simple lifecycle transitions for session descriptors."""

    async def activate(self, session: SessionDescriptor) -> SessionDescriptor:
        """Return an active session descriptor."""
        session.status = "active"
        return session

    async def mark_idle(self, session: SessionDescriptor) -> SessionDescriptor:
        """Return an idle session descriptor."""
        session.status = "idle"
        return session

    async def archive(self, session: SessionDescriptor) -> SessionDescriptor:
        """Return an archived session descriptor."""
        session.status = "archived"
        return session


__all__ = ["SessionLifecycleManager"]
