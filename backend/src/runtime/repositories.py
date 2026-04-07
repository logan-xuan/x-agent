"""Repository interfaces for runtime storage and replay state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .types import ArtifactRef, SessionDescriptor, TaskFrame
from ..models.runtime import RuntimeRecord
from ..services.storage import StorageService


@dataclass
class TranscriptEntry:
    """One raw transcript entry captured by the runtime."""

    entry_id: str
    session_id: str
    turn_index: int
    kind: Literal[
        "user_message",
        "assistant_message",
        "tool_call",
        "tool_result",
        "system_message",
        "attachment",
        "summary_boundary",
    ]
    role: str | None = None
    text: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: float = 0.0


@dataclass
class SummaryRecord:
    """Structured runtime summary stored outside the active transcript."""

    summary_id: str
    session_id: str
    summary_type: Literal[
        "microcompact",
        "collapse",
        "autocompact",
        "memory_flush",
        "child_result",
    ]
    summary: str
    based_on_entry_ids: list[str] = field(default_factory=list)
    objective: str = ""
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    recent_failures: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class StateSnapshotRecord:
    """Persisted runtime snapshot for resume/reconnect paths."""

    snapshot_id: str
    session_id: str
    task_frame: TaskFrame
    turn_index: int = 0
    unresolved: list[str] = field(default_factory=list)
    active_artifact_refs: list[str] = field(default_factory=list)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)
    tool_usage_json: dict[str, int] = field(default_factory=dict)
    last_finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class CompressionEventRecord:
    """Telemetry/audit record for one runtime compression operation."""

    event_id: str
    session_id: str
    turn_index: int
    stage: Literal[
        "persist",
        "aggregate_budget",
        "ttl_prune",
        "microcompact",
        "collapse",
        "autocompact",
        "memory_flush",
        "emergency",
    ]
    tokens_before: int
    tokens_after: int
    freed_tokens: int
    affected_entry_ids: list[str] = field(default_factory=list)
    affected_artifact_ids: list[str] = field(default_factory=list)
    fallback_used: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class ResumeSessionState:
    """Structured persisted state bundle used by runtime resume/reconnect flows."""

    session: SessionDescriptor
    latest_snapshot: StateSnapshotRecord | None = None
    latest_summary: SummaryRecord | None = None
    summary_chain: list[SummaryRecord] = field(default_factory=list)
    recent_entries: list[TranscriptEntry] = field(default_factory=list)


@runtime_checkable
class SessionRepository(Protocol):
    """Storage interface for runtime session descriptors."""

    async def get(self, session_key: str) -> SessionDescriptor | None:
        ...

    async def put(self, session: SessionDescriptor) -> None:
        ...

    async def patch(self, session_key: str, values: dict[str, object]) -> SessionDescriptor:
        ...

    async def list(self) -> list[SessionDescriptor]:
        ...


@runtime_checkable
class TranscriptRepository(Protocol):
    """Storage interface for raw runtime transcript entries."""

    async def append(self, entry: TranscriptEntry) -> None:
        ...

    async def list_by_session(self, session_id: str) -> list[TranscriptEntry]:
        ...

    async def recent_by_session(self, session_id: str, limit: int) -> list[TranscriptEntry]:
        ...


@runtime_checkable
class SummaryRepository(Protocol):
    """Storage interface for structured runtime summaries."""

    async def put(self, summary: SummaryRecord) -> None:
        ...

    async def list_by_session(self, session_id: str) -> list[SummaryRecord]:
        ...

    async def latest_for_session(self, session_id: str) -> SummaryRecord | None:
        ...


@runtime_checkable
class ArtifactRepository(Protocol):
    """Storage interface for persisted runtime artifacts."""

    async def put(self, artifact: ArtifactRef, content: str) -> None:
        ...

    async def get(self, artifact_id: str) -> tuple[ArtifactRef, str] | None:
        ...


@runtime_checkable
class StateSnapshotRepository(Protocol):
    """Storage interface for resumable runtime state snapshots."""

    async def put(self, snapshot: StateSnapshotRecord) -> None:
        ...

    async def latest_for_session(self, session_id: str) -> StateSnapshotRecord | None:
        ...


@runtime_checkable
class CompressionEventRepository(Protocol):
    """Storage interface for runtime compression telemetry records."""

    async def append(self, event: CompressionEventRecord) -> None:
        ...

    async def list_by_session(self, session_id: str) -> list[CompressionEventRecord]:
        ...


def _task_frame_from_payload(payload: dict[str, Any]) -> TaskFrame:
    return TaskFrame(**payload)


def _session_descriptor_from_payload(payload: dict[str, Any]) -> SessionDescriptor:
    route_payload = payload.get("route")
    route = None
    if isinstance(route_payload, dict):
        from .types import RouteMeta

        route = RouteMeta(**route_payload)
    normalized = dict(payload)
    normalized["route"] = route
    return SessionDescriptor(**normalized)


def _artifact_ref_from_payload(payload: dict[str, Any]) -> ArtifactRef:
    return ArtifactRef(**payload)


def _summary_record_from_payload(payload: dict[str, Any]) -> SummaryRecord:
    return SummaryRecord(**payload)


def _transcript_entry_from_payload(payload: dict[str, Any]) -> TranscriptEntry:
    return TranscriptEntry(**payload)


def _state_snapshot_from_payload(payload: dict[str, Any]) -> StateSnapshotRecord:
    normalized = dict(payload)
    normalized["task_frame"] = _task_frame_from_payload(normalized["task_frame"])
    return StateSnapshotRecord(**normalized)


def _compression_event_from_payload(payload: dict[str, Any]) -> CompressionEventRecord:
    return CompressionEventRecord(**payload)


@dataclass
class _StorageRuntimeRepository:
    """Shared helpers for storage-backed runtime repositories."""

    storage: StorageService
    _initialized: bool = field(default=False, init=False, repr=False)

    async def _ensure_storage(self) -> None:
        if self._initialized:
            return
        await self.storage.initialize()
        self._initialized = True

    async def _get_record(self, record_id: str) -> RuntimeRecord | None:
        await self._ensure_storage()
        async with self.storage.session() as db:
            return await db.get(RuntimeRecord, record_id)

    async def _put_record(
        self,
        *,
        record_id: str,
        record_type: str,
        payload: dict[str, Any],
        session_key: str | None = None,
        session_id: str | None = None,
    ) -> None:
        await self._ensure_storage()
        serialized = json.dumps(payload, ensure_ascii=False)
        async with self.storage.session() as db:
            record = await db.get(RuntimeRecord, record_id)
            if record is None:
                record = RuntimeRecord(
                    id=record_id,
                    record_type=record_type,
                    session_key=session_key,
                    session_id=session_id,
                    payload_json=serialized,
                )
                db.add(record)
                return

            record.record_type = record_type
            record.session_key = session_key
            record.session_id = session_id
            record.payload_json = serialized

    async def _list_records(
        self,
        *,
        db: AsyncSession,
        record_type: str,
        session_id: str | None = None,
        session_key: str | None = None,
        desc: bool = False,
        limit: int | None = None,
    ) -> list[RuntimeRecord]:
        stmt = select(RuntimeRecord).where(RuntimeRecord.record_type == record_type)
        if session_id is not None:
            stmt = stmt.where(RuntimeRecord.session_id == session_id)
        if session_key is not None:
            stmt = stmt.where(RuntimeRecord.session_key == session_key)
        order_column = RuntimeRecord.created_at.desc() if desc else RuntimeRecord.created_at.asc()
        stmt = stmt.order_by(order_column)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())


@dataclass
class StorageSessionRepository(_StorageRuntimeRepository):
    """Storage-backed runtime session repository."""

    async def get(self, session_key: str) -> SessionDescriptor | None:
        record = await self._get_record(f"session:{session_key}")
        if record is None:
            return None
        return _session_descriptor_from_payload(json.loads(record.payload_json))

    async def put(self, session: SessionDescriptor) -> None:
        payload = dict(session.__dict__)
        payload["route"] = session.route.__dict__ if session.route is not None else None
        await self._put_record(
            record_id=f"session:{session.session_key}",
            record_type="session",
            session_key=session.session_key,
            session_id=session.session_id,
            payload=payload,
        )

    async def patch(self, session_key: str, values: dict[str, object]) -> SessionDescriptor:
        current = await self.get(session_key)
        if current is None:
            raise KeyError(session_key)
        updated = replace(current, **values)
        await self.put(updated)
        return updated

    async def list(self) -> list[SessionDescriptor]:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(db=db, record_type="session")
        return [_session_descriptor_from_payload(json.loads(record.payload_json)) for record in records]


@dataclass
class StorageTranscriptRepository(_StorageRuntimeRepository):
    """Storage-backed raw runtime transcript repository."""

    async def append(self, entry: TranscriptEntry) -> None:
        await self._put_record(
            record_id=entry.entry_id,
            record_type="transcript",
            session_id=entry.session_id,
            payload=entry.__dict__,
        )

    async def list_by_session(self, session_id: str) -> list[TranscriptEntry]:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(db=db, record_type="transcript", session_id=session_id)
        return [_transcript_entry_from_payload(json.loads(record.payload_json)) for record in records]

    async def recent_by_session(self, session_id: str, limit: int) -> list[TranscriptEntry]:
        if limit <= 0:
            return []
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(
                db=db,
                record_type="transcript",
                session_id=session_id,
                desc=True,
                limit=limit,
            )
        entries = [_transcript_entry_from_payload(json.loads(record.payload_json)) for record in records]
        entries.reverse()
        return entries


@dataclass
class StorageSummaryRepository(_StorageRuntimeRepository):
    """Storage-backed runtime summary repository."""

    async def put(self, summary: SummaryRecord) -> None:
        await self._put_record(
            record_id=summary.summary_id,
            record_type="summary",
            session_id=summary.session_id,
            payload=summary.__dict__,
        )

    async def list_by_session(self, session_id: str) -> list[SummaryRecord]:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(db=db, record_type="summary", session_id=session_id)
        return [_summary_record_from_payload(json.loads(record.payload_json)) for record in records]

    async def latest_for_session(self, session_id: str) -> SummaryRecord | None:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(
                db=db,
                record_type="summary",
                session_id=session_id,
                desc=True,
                limit=1,
            )
        if not records:
            return None
        return _summary_record_from_payload(json.loads(records[0].payload_json))


@dataclass
class StorageArtifactRepository(_StorageRuntimeRepository):
    """Storage-backed runtime artifact repository."""

    async def put(self, artifact: ArtifactRef, content: str) -> None:
        await self._put_record(
            record_id=artifact.id,
            record_type="artifact",
            payload={"artifact": artifact.__dict__, "content": content},
        )

    async def get(self, artifact_id: str) -> tuple[ArtifactRef, str] | None:
        record = await self._get_record(artifact_id)
        if record is None:
            return None
        payload = json.loads(record.payload_json)
        return _artifact_ref_from_payload(payload["artifact"]), str(payload["content"])


@dataclass
class StorageStateSnapshotRepository(_StorageRuntimeRepository):
    """Storage-backed state snapshot repository."""

    async def put(self, snapshot: StateSnapshotRecord) -> None:
        payload = dict(snapshot.__dict__)
        payload["task_frame"] = snapshot.task_frame.__dict__
        await self._put_record(
            record_id=snapshot.snapshot_id,
            record_type="state_snapshot",
            session_id=snapshot.session_id,
            payload=payload,
        )

    async def latest_for_session(self, session_id: str) -> StateSnapshotRecord | None:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(
                db=db,
                record_type="state_snapshot",
                session_id=session_id,
                desc=True,
                limit=1,
            )
        if not records:
            return None
        return _state_snapshot_from_payload(json.loads(records[0].payload_json))


@dataclass
class StorageCompressionEventRepository(_StorageRuntimeRepository):
    """Storage-backed runtime compression telemetry repository."""

    async def append(self, event: CompressionEventRecord) -> None:
        await self._put_record(
            record_id=event.event_id,
            record_type="compression_event",
            session_id=event.session_id,
            payload=event.__dict__,
        )

    async def list_by_session(self, session_id: str) -> list[CompressionEventRecord]:
        await self._ensure_storage()
        async with self.storage.session() as db:
            records = await self._list_records(
                db=db,
                record_type="compression_event",
                session_id=session_id,
            )
        return [_compression_event_from_payload(json.loads(record.payload_json)) for record in records]


@dataclass
class InMemorySessionRepository:
    """In-memory repository for runtime session descriptors."""

    _sessions: dict[str, SessionDescriptor] = field(default_factory=dict)

    async def get(self, session_key: str) -> SessionDescriptor | None:
        return self._sessions.get(session_key)

    async def put(self, session: SessionDescriptor) -> None:
        self._sessions[session.session_key] = session

    async def patch(self, session_key: str, values: dict[str, object]) -> SessionDescriptor:
        current = self._sessions[session_key]
        updated = replace(current, **values)
        self._sessions[session_key] = updated
        return updated

    async def list(self) -> list[SessionDescriptor]:
        return list(self._sessions.values())


@dataclass
class InMemoryTranscriptRepository:
    """In-memory repository for runtime transcript entries."""

    _entries: list[TranscriptEntry] = field(default_factory=list)

    async def append(self, entry: TranscriptEntry) -> None:
        self._entries.append(entry)

    async def list_by_session(self, session_id: str) -> list[TranscriptEntry]:
        return [entry for entry in self._entries if entry.session_id == session_id]

    async def recent_by_session(self, session_id: str, limit: int) -> list[TranscriptEntry]:
        entries = await self.list_by_session(session_id)
        if limit <= 0:
            return []
        return entries[-limit:]


@dataclass
class InMemorySummaryRepository:
    """In-memory repository for runtime summary records."""

    _summaries: list[SummaryRecord] = field(default_factory=list)

    async def put(self, summary: SummaryRecord) -> None:
        self._summaries.append(summary)

    async def list_by_session(self, session_id: str) -> list[SummaryRecord]:
        return [summary for summary in self._summaries if summary.session_id == session_id]

    async def latest_for_session(self, session_id: str) -> SummaryRecord | None:
        matches = [summary for summary in self._summaries if summary.session_id == session_id]
        if not matches:
            return None
        return max(matches, key=lambda summary: summary.created_at)


@dataclass
class InMemoryArtifactRepository:
    """In-memory repository for runtime artifact payloads."""

    _artifacts: dict[str, tuple[ArtifactRef, str]] = field(default_factory=dict)

    async def put(self, artifact: ArtifactRef, content: str) -> None:
        self._artifacts[artifact.id] = (artifact, content)

    async def get(self, artifact_id: str) -> tuple[ArtifactRef, str] | None:
        return self._artifacts.get(artifact_id)


@dataclass
class InMemoryStateSnapshotRepository:
    """In-memory repository for resumable runtime state snapshots."""

    _snapshots: list[StateSnapshotRecord] = field(default_factory=list)

    async def put(self, snapshot: StateSnapshotRecord) -> None:
        self._snapshots.append(snapshot)

    async def latest_for_session(self, session_id: str) -> StateSnapshotRecord | None:
        matches = [snapshot for snapshot in self._snapshots if snapshot.session_id == session_id]
        if not matches:
            return None
        return max(matches, key=lambda snapshot: snapshot.created_at)


@dataclass
class InMemoryCompressionEventRepository:
    """In-memory repository for runtime compression telemetry."""

    _events: list[CompressionEventRecord] = field(default_factory=list)

    async def append(self, event: CompressionEventRecord) -> None:
        self._events.append(event)

    async def list_by_session(self, session_id: str) -> list[CompressionEventRecord]:
        return [event for event in self._events if event.session_id == session_id]


__all__ = [
    "CompressionEventRecord",
    "CompressionEventRepository",
    "ResumeSessionState",
    "ArtifactRepository",
    "InMemoryArtifactRepository",
    "InMemoryCompressionEventRepository",
    "InMemorySessionRepository",
    "InMemoryStateSnapshotRepository",
    "InMemorySummaryRepository",
    "InMemoryTranscriptRepository",
    "SessionRepository",
    "StorageArtifactRepository",
    "StorageCompressionEventRepository",
    "StorageSessionRepository",
    "StorageStateSnapshotRepository",
    "StorageSummaryRepository",
    "StorageTranscriptRepository",
    "StateSnapshotRecord",
    "StateSnapshotRepository",
    "SummaryRecord",
    "SummaryRepository",
    "TranscriptEntry",
    "TranscriptRepository",
]
