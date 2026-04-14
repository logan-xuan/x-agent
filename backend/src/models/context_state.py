"""Stateful context and memory persistence models."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionContextState(Base):
    """Structured session state snapshot for prompt assembly."""

    __tablename__ = "session_context_state"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    mode: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    current_goal_json: Mapped[str] = mapped_column(Text, default="{}")
    active_subtasks_json: Mapped[str] = mapped_column(Text, default="[]")
    decisions_json: Mapped[str] = mapped_column(Text, default="[]")
    constraints_json: Mapped[str] = mapped_column(Text, default="[]")
    open_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    delegate_status_json: Mapped[str] = mapped_column(Text, default="[]")
    recent_failures_json: Mapped[str] = mapped_column(Text, default="[]")
    user_preferences_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_text: Mapped[str] = mapped_column(Text, default="")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "version": self.version,
            "mode": self.mode,
            "current_goal": _loads_json(self.current_goal_json, {}),
            "active_subtasks": _loads_json(self.active_subtasks_json, []),
            "decisions": _loads_json(self.decisions_json, []),
            "constraints": _loads_json(self.constraints_json, []),
            "open_questions": _loads_json(self.open_questions_json, []),
            "artifact_refs": _loads_json(self.artifact_refs_json, []),
            "delegate_status": _loads_json(self.delegate_status_json, []),
            "recent_failures": _loads_json(self.recent_failures_json, []),
            "user_preferences": _loads_json(self.user_preferences_json, []),
            "summary_text": self.summary_text,
            "token_estimate": self.token_estimate,
            "metadata": _loads_json(self.metadata_json, {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EpisodicMemoryEvent(Base):
    """Externalized event card for long-running sessions."""

    __tablename__ = "episodic_memory_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    source_message_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "title": self.title,
            "summary": self.summary,
            "details": _loads_json(self.details_json, {}),
            "source_message_ids": _loads_json(self.source_message_ids_json, []),
            "artifact_refs": _loads_json(self.artifact_refs_json, []),
            "tags": _loads_json(self.tags_json, []),
            "importance": self.importance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EvidenceLedgerEntry(Base):
    """Evidence record with provenance for research-heavy sessions."""

    __tablename__ = "evidence_ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="web")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    freshness_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "topic": self.topic,
            "claim": self.claim,
            "source_url": self.source_url,
            "source_title": self.source_title,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "freshness_at": self.freshness_at.isoformat() if self.freshness_at else None,
            "metadata": _loads_json(self.metadata_json, {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Artifact(Base):
    """Stored large artifact reference used during context assembly."""

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content_path: Mapped[str] = mapped_column(Text)
    preview_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "kind": self.kind,
            "title": self.title,
            "content_path": self.content_path,
            "preview_text": self.preview_text,
            "metadata": _loads_json(self.metadata_json, {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def _loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
