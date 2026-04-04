"""Persistence service for evidence ledger entries."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ...models.context_state import EvidenceLedgerEntry
from ..storage import StorageService, get_storage_service


class EvidenceLedgerStore:
    """CRUD helpers for EvidenceLedgerEntry rows."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or get_storage_service()

    async def create_entry(
        self,
        *,
        session_id: str,
        topic: str,
        claim: str,
        source_url: str | None = None,
        source_title: str | None = None,
        source_type: str = "web",
        confidence: float = 0.5,
        freshness_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            session_id=session_id,
            topic=topic,
            claim=claim,
            source_url=source_url,
            source_title=source_title,
            source_type=source_type,
            confidence=confidence,
            freshness_at=freshness_at,
            metadata_json=_dump_json(metadata or {}),
        )
        async with self._storage.session() as db_session:
            db_session.add(entry)
            await db_session.flush()
            await db_session.refresh(entry)
            return entry

    async def list_by_session(
        self,
        session_id: str,
        *,
        topic: str | None = None,
        limit: int = 20,
    ) -> list[EvidenceLedgerEntry]:
        async with self._storage.session() as db_session:
            query = (
                select(EvidenceLedgerEntry)
                .where(EvidenceLedgerEntry.session_id == session_id)
                .order_by(EvidenceLedgerEntry.created_at.desc())
                .limit(limit)
            )
            if topic:
                query = query.where(EvidenceLedgerEntry.topic == topic)
            result = await db_session.execute(query)
            return list(result.scalars().all())

    async def get(self, entry_id: str) -> EvidenceLedgerEntry | None:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(EvidenceLedgerEntry).where(EvidenceLedgerEntry.id == entry_id)
            )
            return result.scalar_one_or_none()


_evidence_ledger_store: EvidenceLedgerStore | None = None


def get_evidence_ledger_store() -> EvidenceLedgerStore:
    global _evidence_ledger_store
    if _evidence_ledger_store is None:
        _evidence_ledger_store = EvidenceLedgerStore()
    return _evidence_ledger_store


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
