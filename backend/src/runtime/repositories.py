"""Repository interfaces for runtime storage and replay state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, runtime_checkable

from .types import ArtifactRef, SessionDescriptor, TaskFrame


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
    "ArtifactRepository",
    "InMemoryArtifactRepository",
    "InMemoryCompressionEventRepository",
    "InMemorySessionRepository",
    "InMemoryStateSnapshotRepository",
    "InMemorySummaryRepository",
    "InMemoryTranscriptRepository",
    "SessionRepository",
    "StateSnapshotRecord",
    "StateSnapshotRepository",
    "SummaryRecord",
    "SummaryRepository",
    "TranscriptEntry",
    "TranscriptRepository",
]
