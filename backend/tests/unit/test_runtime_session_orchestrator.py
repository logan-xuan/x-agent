"""Unit tests for runtime session orchestrator child completion behavior."""

from dataclasses import dataclass, field

import pytest

from src.runtime.session.orchestrator import DefaultSessionOrchestrator
from src.runtime.repositories import CompressionEventRecord, StateSnapshotRecord, SummaryRecord, TranscriptEntry
from src.runtime.types import ArtifactRef, ChildResult, SessionDescriptor, SpawnPacket, TaskFrame


@pytest.mark.asyncio
async def test_orchestrator_complete_child_auto_archives_by_default():
    orchestrator = DefaultSessionOrchestrator()
    parent = SessionDescriptor(session_key="parent", session_id="parent")
    child = SessionDescriptor(
        session_key="child",
        session_id="child",
        parent_session_key="parent",
        status="active",
    )
    await orchestrator.session_store.put(parent)
    await orchestrator.session_store.put(child)

    payload = await orchestrator.complete_child(
        child,
        ChildResult(
            status="success",
            summary="child done",
            usage={"prompt_tokens": 1},
            duration_ms=88,
        ),
    )

    stored_child = await orchestrator.session_store.get("child")

    assert payload["status"] == "success"
    assert payload["usage"] == {"prompt_tokens": 1}
    assert stored_child is not None
    assert stored_child.status == "archived"


@pytest.mark.asyncio
async def test_orchestrator_complete_child_can_leave_child_idle_when_auto_archive_disabled():
    orchestrator = DefaultSessionOrchestrator()
    orchestrator.child_session_manager.policy.auto_archive = False
    parent = SessionDescriptor(session_key="parent", session_id="parent")
    child = SessionDescriptor(
        session_key="child",
        session_id="child",
        parent_session_key="parent",
        status="active",
    )
    await orchestrator.session_store.put(parent)
    await orchestrator.session_store.put(child)

    await orchestrator.complete_child(
        child,
        ChildResult(
            status="success",
            summary="child done",
            duration_ms=88,
        ),
    )

    stored_child = await orchestrator.session_store.get("child")

    assert stored_child is not None
    assert stored_child.status == "idle"


@dataclass
class SpySessionRepository:
    """Small repository stub to verify protocol-based orchestrator wiring."""

    sessions: dict[str, SessionDescriptor] = field(default_factory=dict)
    puts: list[str] = field(default_factory=list)

    async def get(self, session_key: str) -> SessionDescriptor | None:
        return self.sessions.get(session_key)

    async def put(self, session: SessionDescriptor) -> None:
        self.sessions[session.session_key] = session
        self.puts.append(session.session_key)

    async def patch(self, session_key: str, values: dict[str, object]) -> SessionDescriptor:
        current = self.sessions[session_key]
        updated = SessionDescriptor(**{**current.__dict__, **values})
        self.sessions[session_key] = updated
        return updated

    async def list(self) -> list[SessionDescriptor]:
        return list(self.sessions.values())


@pytest.mark.asyncio
async def test_orchestrator_accepts_repository_protocol_implementation():
    repo = SpySessionRepository()
    orchestrator = DefaultSessionOrchestrator(session_store=repo)

    session = await orchestrator.resolve_or_create({"session_id": "sess-proto"})

    assert session.session_key == "sess-proto"
    assert repo.puts == ["sess-proto"]


@pytest.mark.asyncio
async def test_orchestrator_prepare_child_turn_unifies_spawn_and_policy_envelope():
    orchestrator = DefaultSessionOrchestrator()
    parent = SessionDescriptor(session_key="parent", session_id="parent")

    envelope = await orchestrator.prepare_child_turn(
        parent,
        SpawnPacket(
            objective="Investigate child work",
            deliverable="Return findings",
            selected_artifacts=["artifact-1"],
            tool_allowlist=["read_file"],
            timeout_ms=5000,
        ),
    )

    stored_child = await orchestrator.session_store.get(envelope.request.session.session_key)

    assert stored_child is not None
    assert stored_child.parent_session_key == "parent"
    assert envelope.prompt_mode == "minimal"
    assert envelope.request.metadata["auto_archive"] is True
    assert envelope.request.metadata["max_spawns"] == 0


@pytest.mark.asyncio
async def test_orchestrator_records_and_reads_latest_summary():
    orchestrator = DefaultSessionOrchestrator()

    await orchestrator.record_summary(
        SummaryRecord(
            summary_id="sum-1",
            session_id="sess-1",
            summary_type="collapse",
            summary="older",
            created_at=1.0,
        )
    )
    await orchestrator.record_summary(
        SummaryRecord(
            summary_id="sum-2",
            session_id="sess-1",
            summary_type="collapse",
            summary="newer",
            created_at=2.0,
        )
    )

    latest = await orchestrator.latest_summary("sess-1")

    assert latest is not None
    assert latest.summary_id == "sum-2"


@pytest.mark.asyncio
async def test_orchestrator_records_and_reads_latest_state_snapshot():
    orchestrator = DefaultSessionOrchestrator()

    await orchestrator.record_state_snapshot(
        StateSnapshotRecord(
            snapshot_id="snap-1",
            session_id="sess-1",
            task_frame=TaskFrame(objective="older"),
            created_at=1.0,
        )
    )
    await orchestrator.record_state_snapshot(
        StateSnapshotRecord(
            snapshot_id="snap-2",
            session_id="sess-1",
            task_frame=TaskFrame(objective="newer"),
            created_at=2.0,
        )
    )

    latest = await orchestrator.latest_state_snapshot("sess-1")

    assert latest is not None
    assert latest.snapshot_id == "snap-2"


@pytest.mark.asyncio
async def test_orchestrator_appends_transcript_entry_via_repository():
    orchestrator = DefaultSessionOrchestrator()

    entry = await orchestrator.append_transcript_entry(
        TranscriptEntry(
            entry_id="entry-1",
            session_id="sess-1",
            turn_index=0,
            kind="user_message",
            text="hello",
        )
    )

    entries = await orchestrator.transcript_repository.list_by_session("sess-1")

    assert entry.entry_id == "entry-1"
    assert [item.entry_id for item in entries] == ["entry-1"]


@pytest.mark.asyncio
async def test_orchestrator_stores_artifact_via_repository():
    orchestrator = DefaultSessionOrchestrator()
    artifact = ArtifactRef(id="artifact-1", kind="tool", title="Artifact", preview="preview")

    stored = await orchestrator.store_artifact(artifact, "body")
    round_trip = await orchestrator.artifact_repository.get("artifact-1")

    assert stored is artifact
    assert round_trip == (artifact, "body")


@pytest.mark.asyncio
async def test_orchestrator_appends_compression_event_via_repository():
    orchestrator = DefaultSessionOrchestrator()
    event = CompressionEventRecord(
        event_id="evt-1",
        session_id="sess-1",
        turn_index=1,
        stage="collapse",
        tokens_before=100,
        tokens_after=40,
        freed_tokens=60,
    )

    stored = await orchestrator.append_compression_event(event)
    events = await orchestrator.compression_event_repository.list_by_session("sess-1")

    assert stored is event
    assert [item.event_id for item in events] == ["evt-1"]


@pytest.mark.asyncio
async def test_orchestrator_resume_session_loads_snapshot_summary_and_recent_entries():
    orchestrator = DefaultSessionOrchestrator()
    session = SessionDescriptor(session_key="sess-key", session_id="sess-1")
    await orchestrator.session_store.put(session)
    await orchestrator.record_summary(
        SummaryRecord(
            summary_id="sum-1",
            session_id="sess-1",
            summary_type="collapse",
            summary="latest",
            created_at=2.0,
        )
    )
    await orchestrator.record_state_snapshot(
        StateSnapshotRecord(
            snapshot_id="snap-1",
            session_id="sess-1",
            task_frame=TaskFrame(objective="resume"),
            created_at=3.0,
        )
    )
    await orchestrator.append_transcript_entry(
        TranscriptEntry(
            entry_id="entry-1",
            session_id="sess-1",
            turn_index=0,
            kind="assistant_message",
            text="older",
        )
    )
    await orchestrator.append_transcript_entry(
        TranscriptEntry(
            entry_id="entry-2",
            session_id="sess-1",
            turn_index=1,
            kind="assistant_message",
            text="newer",
        )
    )

    resumed = await orchestrator.resume_session("sess-key", recent_entries_limit=1)

    assert resumed is not None
    assert resumed.session == session
    assert resumed.latest_summary is not None
    assert resumed.latest_snapshot is not None
    assert [entry.entry_id for entry in resumed.recent_entries] == ["entry-2"]
