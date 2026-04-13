"""Session orchestration skeleton for runtime control-plane work."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..repositories import (
    ArtifactRepository,
    CompressionEventRecord,
    CompressionEventRepository,
    InMemoryArtifactRepository,
    InMemoryCompressionEventRepository,
    InMemorySessionRepository,
    InMemoryStateSnapshotRepository,
    InMemorySummaryRepository,
    InMemoryTranscriptRepository,
    ResumeSessionState,
    SessionRepository,
    StateSnapshotRecord,
    StateSnapshotRepository,
    SummaryRecord,
    SummaryRepository,
    TranscriptEntry,
    TranscriptRepository,
)
from ..types import ArtifactRef, ChildResult, SessionDescriptor, SpawnPacket, TurnRequest
from .announcement_manager import AnnouncementManager
from .child_session import ChildSessionManager, ChildTurnEnvelope
from .lane_scheduler import InMemoryLaneScheduler
from .lifecycle import SessionLifecycleManager
from .route_resolver import DefaultRouteResolver
from .spawn_manager import SpawnManager


@dataclass
class DefaultSessionOrchestrator:
    """Resolve sessions, schedule work, and manage child-session announcements."""

    session_store: SessionRepository = field(default_factory=InMemorySessionRepository)
    transcript_repository: TranscriptRepository = field(
        default_factory=InMemoryTranscriptRepository
    )
    summary_repository: SummaryRepository = field(default_factory=InMemorySummaryRepository)
    artifact_repository: ArtifactRepository = field(default_factory=InMemoryArtifactRepository)
    compression_event_repository: CompressionEventRepository = field(
        default_factory=InMemoryCompressionEventRepository
    )
    state_snapshot_repository: StateSnapshotRepository = field(
        default_factory=InMemoryStateSnapshotRepository
    )
    route_resolver: DefaultRouteResolver = field(default_factory=DefaultRouteResolver)
    lane_scheduler: InMemoryLaneScheduler = field(default_factory=InMemoryLaneScheduler)
    spawn_manager: SpawnManager = field(default_factory=SpawnManager)
    child_session_manager: ChildSessionManager = field(default_factory=ChildSessionManager)
    announcement_manager: AnnouncementManager = field(default_factory=AnnouncementManager)
    lifecycle_manager: SessionLifecycleManager = field(default_factory=SessionLifecycleManager)

    async def resolve_or_create(self, event: Any) -> SessionDescriptor:
        """Resolve a session from an event-like payload or create a new one."""
        session_key = self._event_value(event, "session_key") or self._event_value(
            event, "session_id"
        )
        if not session_key:
            session_key = f"session:{uuid4().hex[:8]}"

        existing = await self.session_store.get(session_key)
        if existing is not None:
            activated = await self.lifecycle_manager.activate(existing)
            await self.session_store.put(activated)
            return activated

        route = await self.route_resolver.resolve(event)
        session = SessionDescriptor(
            session_key=session_key,
            session_id=self._event_value(event, "session_id") or session_key,
            lane=self._lane_from_event(event),
            route=route,
            status="active",
        )
        await self.session_store.put(session)
        return session

    async def load_session(self, session_key: str) -> SessionDescriptor | None:
        """Load a session descriptor by key without mutating lifecycle state."""
        return await self.session_store.get(session_key)

    async def enqueue_turn(self, session: SessionDescriptor, request: TurnRequest) -> TurnRequest:
        """Schedule a turn request into the correct lane and return it after execution."""

        async def run() -> TurnRequest:
            _ = request
            return request

        activated = await self.lifecycle_manager.activate(session)
        await self.session_store.put(activated)
        return await self.lane_scheduler.enqueue(session.lane, run)

    async def spawn_child(
        self, parent: SessionDescriptor, packet: SpawnPacket
    ) -> SessionDescriptor:
        """Create and store a child session descriptor."""
        child = await self.spawn_manager.spawn_child(parent, packet, route=parent.route)
        await self.session_store.put(child)
        return child

    async def prepare_child_turn(
        self,
        parent: SessionDescriptor,
        packet: SpawnPacket,
    ) -> ChildTurnEnvelope:
        """Create a child session and return its bounded child-turn envelope."""
        child = await self.spawn_child(parent, packet)
        return self.child_session_manager.prepare_child_turn(
            parent=parent,
            child=child,
            packet=packet,
        )

    async def complete_child(
        self, child: SessionDescriptor, result: ChildResult
    ) -> dict[str, object]:
        """Build and queue a child completion announcement."""
        if child.parent_session_key is None:
            raise ValueError("child session has no parent_session_key")

        parent = await self.session_store.get(child.parent_session_key)
        if parent is None:
            raise KeyError(f"parent session not found: {child.parent_session_key}")

        payload = await self.announcement_manager.build(parent, child, result)
        await self.announcement_manager.enqueue(payload)
        if self.child_session_manager.policy.auto_archive:
            await self.lifecycle_manager.archive(child)
        else:
            await self.lifecycle_manager.mark_idle(child)
        await self.session_store.put(child)
        return payload

    async def consume_announcements(self, session_key: str) -> list[dict[str, object]]:
        """Drain queued child announcements for the target session."""
        return await self.announcement_manager.dequeue_for_session(session_key)

    async def archive(self, session_key: str) -> None:
        """Archive a session by key."""
        session = await self.session_store.get(session_key)
        if session is None:
            return
        archived = await self.lifecycle_manager.archive(session)
        await self.session_store.put(archived)

    async def record_summary(self, summary: SummaryRecord) -> SummaryRecord:
        """Persist a runtime summary and return it."""
        await self.summary_repository.put(summary)
        return summary

    async def append_transcript_entry(self, entry: TranscriptEntry) -> TranscriptEntry:
        """Persist one transcript entry and return it."""
        await self.transcript_repository.append(entry)
        return entry

    async def latest_summary(self, session_id: str) -> SummaryRecord | None:
        """Return the latest stored summary for a session when available."""
        return await self.summary_repository.latest_for_session(session_id)

    async def store_artifact(self, artifact: ArtifactRef, content: str) -> ArtifactRef:
        """Persist an artifact payload and return its reference."""
        await self.artifact_repository.put(artifact, content)
        return artifact

    async def append_compression_event(
        self, event: CompressionEventRecord
    ) -> CompressionEventRecord:
        """Persist one compression telemetry record and return it."""
        await self.compression_event_repository.append(event)
        return event

    async def record_state_snapshot(self, snapshot: StateSnapshotRecord) -> StateSnapshotRecord:
        """Persist a runtime state snapshot and return it."""
        await self.state_snapshot_repository.put(snapshot)
        return snapshot

    async def latest_state_snapshot(self, session_id: str) -> StateSnapshotRecord | None:
        """Return the latest stored state snapshot for a session."""
        return await self.state_snapshot_repository.latest_for_session(session_id)

    async def resume_session(
        self,
        session_key: str,
        *,
        recent_entries_limit: int = 20,
    ) -> ResumeSessionState | None:
        """Load the minimum persisted state needed to resume a runtime session."""
        session = await self.session_store.get(session_key)
        if session is None:
            return None

        latest_snapshot = await self.latest_state_snapshot(session.session_id)
        latest_summary = await self.latest_summary(session.session_id)
        summary_chain = await self.summary_repository.list_by_session(session.session_id)
        recent_entries = await self.transcript_repository.recent_by_session(
            session.session_id,
            recent_entries_limit,
        )
        return ResumeSessionState(
            session=session,
            latest_snapshot=latest_snapshot,
            latest_summary=latest_summary,
            summary_chain=summary_chain,
            recent_entries=recent_entries,
        )

    async def reconnect_session(
        self,
        session_key: str,
        *,
        recent_entries_limit: int = 20,
    ) -> ResumeSessionState | None:
        """Reactivate a stored session and return its resumable state bundle."""
        session = await self.load_session(session_key)
        if session is None:
            return None
        await self.lifecycle_manager.activate(session)
        await self.session_store.put(session)
        return await self.resume_session(session_key, recent_entries_limit=recent_entries_limit)

    def _event_value(self, event: Any, key: str) -> str | None:
        if isinstance(event, dict):
            value = event.get(key)
            return str(value) if value not in {None, ""} else None
        value = getattr(event, key, None)
        return str(value) if value not in {None, ""} else None

    def _lane_from_event(self, event: Any):
        lane = self._event_value(event, "lane")
        if lane in {"main", "followup", "subagent", "cron", "background_tool"}:
            return lane
        route = self._event_value(event, "channel")
        if route == "cron":
            return "cron"
        return "main"


__all__ = ["DefaultSessionOrchestrator"]
