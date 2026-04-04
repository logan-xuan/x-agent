"""Persistence service for episodic memory event cards."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from ...models.context_state import EpisodicMemoryEvent
from ..storage import StorageService, get_storage_service


class EpisodicMemoryStore:
    """CRUD helpers for EpisodicMemoryEvent rows."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or get_storage_service()

    async def create_event(
        self,
        *,
        session_id: str,
        event_type: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
        source_message_ids: list[str] | None = None,
        artifact_refs: list[str] | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> EpisodicMemoryEvent:
        event = EpisodicMemoryEvent(
            session_id=session_id,
            event_type=event_type,
            title=title,
            summary=summary,
            details_json=_dump_json(details or {}),
            source_message_ids_json=_dump_json(source_message_ids or []),
            artifact_refs_json=_dump_json(artifact_refs or []),
            tags_json=_dump_json(tags or []),
            importance=importance,
        )
        async with self._storage.session() as db_session:
            db_session.add(event)
            await db_session.flush()
            await db_session.refresh(event)
            return event

    async def list_by_session(
        self,
        session_id: str,
        *,
        limit: int = 20,
        event_type: str | None = None,
    ) -> list[EpisodicMemoryEvent]:
        async with self._storage.session() as db_session:
            query = (
                select(EpisodicMemoryEvent)
                .where(EpisodicMemoryEvent.session_id == session_id)
                .order_by(EpisodicMemoryEvent.created_at.desc())
                .limit(limit)
            )
            if event_type:
                query = query.where(EpisodicMemoryEvent.event_type == event_type)
            result = await db_session.execute(query)
            return list(result.scalars().all())

    async def get(self, event_id: str) -> EpisodicMemoryEvent | None:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(EpisodicMemoryEvent).where(EpisodicMemoryEvent.id == event_id)
            )
            return result.scalar_one_or_none()


_episodic_memory_store: EpisodicMemoryStore | None = None


def get_episodic_memory_store() -> EpisodicMemoryStore:
    global _episodic_memory_store
    if _episodic_memory_store is None:
        _episodic_memory_store = EpisodicMemoryStore()
    return _episodic_memory_store


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
