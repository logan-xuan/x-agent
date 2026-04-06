"""Unit tests for runtime in-memory repositories."""

from src.runtime import CompressionEventRecord as ExportedCompressionEventRecord
from src.runtime.repositories import (
    CompressionEventRecord,
    InMemoryArtifactRepository,
    InMemoryCompressionEventRepository,
    InMemorySessionRepository,
    InMemoryStateSnapshotRepository,
    InMemorySummaryRepository,
    InMemoryTranscriptRepository,
    StateSnapshotRecord,
    SummaryRecord,
    TranscriptEntry,
)
from src.runtime.types import ArtifactRef, SessionDescriptor, TaskFrame


def test_runtime_package_exports_compression_event_record():
    assert ExportedCompressionEventRecord is CompressionEventRecord


async def test_in_memory_session_repository_patch_and_list():
    repo = InMemorySessionRepository()
    session = SessionDescriptor(session_key="sess-1", session_id="sess-1")

    await repo.put(session)
    updated = await repo.patch("sess-1", {"status": "archived"})
    listed = await repo.list()

    assert updated.status == "archived"
    assert listed[0].status == "archived"


async def test_in_memory_transcript_repository_filters_by_session():
    repo = InMemoryTranscriptRepository()
    await repo.append(
        TranscriptEntry(
            entry_id="entry-1",
            session_id="sess-1",
            turn_index=0,
            kind="user_message",
            text="hello",
        )
    )
    await repo.append(
        TranscriptEntry(
            entry_id="entry-2",
            session_id="sess-2",
            turn_index=0,
            kind="assistant_message",
            text="world",
        )
    )

    entries = await repo.list_by_session("sess-1")

    assert [entry.entry_id for entry in entries] == ["entry-1"]


async def test_in_memory_summary_repository_filters_by_session():
    repo = InMemorySummaryRepository()
    await repo.put(
        SummaryRecord(
            summary_id="sum-1",
            session_id="sess-1",
            summary_type="collapse",
            based_on_entry_ids=["entry-1"],
            objective="old",
            summary="a",
            decisions=["decide-a"],
        )
    )
    await repo.put(
        SummaryRecord(
            summary_id="sum-2",
            session_id="sess-2",
            summary_type="collapse",
            based_on_entry_ids=["entry-2"],
            objective="new",
            summary="b",
            open_questions=["q1"],
            modified_files=["app.py"],
        )
    )

    summaries = await repo.list_by_session("sess-2")

    assert [summary.summary_id for summary in summaries] == ["sum-2"]
    assert summaries[0].objective == "new"
    assert summaries[0].open_questions == ["q1"]
    assert summaries[0].modified_files == ["app.py"]


async def test_in_memory_summary_repository_returns_latest_summary():
    repo = InMemorySummaryRepository()
    await repo.put(
        SummaryRecord(
            summary_id="sum-1",
            session_id="sess-1",
            summary_type="collapse",
            summary="old",
            created_at=1.0,
        )
    )
    await repo.put(
        SummaryRecord(
            summary_id="sum-2",
            session_id="sess-1",
            summary_type="autocompact",
            summary="new",
            created_at=2.0,
        )
    )

    latest = await repo.latest_for_session("sess-1")

    assert latest is not None
    assert latest.summary_id == "sum-2"


async def test_in_memory_artifact_repository_round_trips_content():
    repo = InMemoryArtifactRepository()
    artifact = ArtifactRef(id="artifact-1", kind="tool", title="Artifact", preview="preview")

    await repo.put(artifact, "body")
    stored = await repo.get("artifact-1")

    assert stored == (artifact, "body")


async def test_in_memory_state_snapshot_repository_returns_latest_snapshot():
    repo = InMemoryStateSnapshotRepository()
    await repo.put(
        StateSnapshotRecord(
            snapshot_id="snap-1",
            session_id="sess-1",
            turn_index=1,
            task_frame=TaskFrame(objective="old"),
            unresolved=["a"],
            active_artifact_refs=["artifact-1"],
            created_at=1.0,
        )
    )
    await repo.put(
        StateSnapshotRecord(
            snapshot_id="snap-2",
            session_id="sess-1",
            turn_index=2,
            task_frame=TaskFrame(objective="new"),
            unresolved=["b"],
            active_artifact_refs=["artifact-2"],
            tool_usage_json={"read_file": 2},
            last_finish_reason="done_definition_satisfied",
            created_at=2.0,
        )
    )

    latest = await repo.latest_for_session("sess-1")

    assert latest is not None
    assert latest.snapshot_id == "snap-2"
    assert latest.turn_index == 2
    assert latest.unresolved == ["b"]
    assert latest.active_artifact_refs == ["artifact-2"]
    assert latest.tool_usage_json == {"read_file": 2}
    assert latest.last_finish_reason == "done_definition_satisfied"


async def test_in_memory_compression_event_repository_filters_by_session():
    repo = InMemoryCompressionEventRepository()
    await repo.append(
        CompressionEventRecord(
            event_id="evt-1",
            session_id="sess-1",
            turn_index=1,
            stage="collapse",
            tokens_before=1000,
            tokens_after=400,
            freed_tokens=600,
            affected_entry_ids=["entry-1"],
            affected_artifact_ids=["artifact-1"],
            fallback_used=True,
        )
    )
    await repo.append(
        CompressionEventRecord(
            event_id="evt-2",
            session_id="sess-2",
            turn_index=2,
            stage="persist",
            tokens_before=200,
            tokens_after=150,
            freed_tokens=50,
        )
    )

    events = await repo.list_by_session("sess-1")

    assert [event.event_id for event in events] == ["evt-1"]
    assert events[0].fallback_used is True
    assert events[0].affected_artifact_ids == ["artifact-1"]
