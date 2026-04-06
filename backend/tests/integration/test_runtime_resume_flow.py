"""Integration tests for runtime resume/reconnect preparation paths."""

import pytest

from src.runtime.adapters import GatewayAdapter
from src.runtime.repositories import StateSnapshotRecord, SummaryRecord, TranscriptEntry
from src.runtime.session.orchestrator import DefaultSessionOrchestrator
from src.runtime.types import RouteMeta, SessionDescriptor, TaskFrame


@pytest.mark.asyncio
async def test_runtime_resume_flow_builds_resumed_turn_from_persisted_state():
    orchestrator = DefaultSessionOrchestrator()
    adapter = GatewayAdapter(orchestrator=orchestrator)
    session = SessionDescriptor(
        session_key="sess-key",
        session_id="sess-1",
        route=RouteMeta(channel="web_chat", user_id="user-1"),
    )
    await orchestrator.session_store.put(session)
    await orchestrator.record_summary(
        SummaryRecord(
            summary_id="sum-1",
            session_id="sess-1",
            summary_type="collapse",
            summary="summary",
            objective="resume objective",
            created_at=1.0,
        )
    )
    await orchestrator.record_state_snapshot(
        StateSnapshotRecord(
            snapshot_id="snap-1",
            session_id="sess-1",
            task_frame=TaskFrame(objective="resume objective", active_artifacts=["artifact-1"]),
            created_at=2.0,
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

    resumed_session, request = await adapter.prepare_resumed_turn(
        "sess-key",
        {"metadata": {"origin": "integration"}},
        user_input="continue",
    )

    assert resumed_session.session_id == "sess-1"
    assert request.route.channel == "web_chat"
    assert request.route.user_id == "user-1"
    assert request.task_frame.objective == "resume objective"
    assert request.task_frame.active_artifacts == ["artifact-1"]
    assert request.metadata["resume"] is True
    assert request.metadata["origin"] == "integration"
    assert request.metadata["summary_chain_count"] == 1
    assert request.metadata["recent_entry_count"] == 2
