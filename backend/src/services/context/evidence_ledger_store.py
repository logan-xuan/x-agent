"""Lightweight evidence ledger store for runtime compatibility tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ._shared import get_context_bucket


@dataclass
class EvidenceLedgerEntry:
    session_id: str
    topic: str
    claim: str
    source_url: str | None = None
    source_title: str | None = None
    confidence: float | None = None
    freshness_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "claim": self.claim,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "confidence": self.confidence,
            "freshness_at": self.freshness_at.isoformat() if self.freshness_at else None,
            "metadata": dict(self.metadata),
        }


class EvidenceLedgerStore:
    def __init__(self, storage: Any) -> None:
        self._entries = get_context_bucket(storage)["evidence_entries"]

    async def create_entry(
        self,
        *,
        session_id: str,
        topic: str,
        claim: str,
        source_url: str | None = None,
        source_title: str | None = None,
        confidence: float | None = None,
        freshness_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceLedgerEntry:
        entry = EvidenceLedgerEntry(
            session_id=session_id,
            topic=topic,
            claim=claim,
            source_url=source_url,
            source_title=source_title,
            confidence=confidence,
            freshness_at=freshness_at,
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        return entry

    async def list_by_session(self, session_id: str) -> list[EvidenceLedgerEntry]:
        return [entry for entry in self._entries if entry.session_id == session_id]
