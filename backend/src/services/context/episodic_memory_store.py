"""Lightweight episodic memory store for runtime compatibility tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._shared import get_context_bucket


@dataclass
class EpisodicMemoryEntry:
    session_id: str
    event_type: str
    title: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    importance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "event_type": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "details": dict(self.details),
            "tags": list(self.tags),
            "importance": self.importance,
        }


class EpisodicMemoryStore:
    def __init__(self, storage: Any) -> None:
        self._entries = get_context_bucket(storage)["episodic_events"]

    async def create_event(
        self,
        *,
        session_id: str,
        event_type: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        importance: float = 0.0,
    ) -> EpisodicMemoryEntry:
        entry = EpisodicMemoryEntry(
            session_id=session_id,
            event_type=event_type,
            title=title,
            summary=summary,
            details=dict(details or {}),
            tags=list(tags or []),
            importance=importance,
        )
        self._entries.append(entry)
        return entry

    async def list_by_session(self, session_id: str) -> list[EpisodicMemoryEntry]:
        return [entry for entry in self._entries if entry.session_id == session_id]
