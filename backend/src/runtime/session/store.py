"""Session storage primitives for the runtime orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass

from ..repositories import InMemorySessionRepository


@dataclass
class InMemorySessionStore(InMemorySessionRepository):
    """Backward-compatible alias for the runtime in-memory session repository."""


__all__ = ["InMemorySessionStore"]
