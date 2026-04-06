"""Integration tests for bounded runtime child-session flow."""

import pytest

from src.runtime.session.orchestrator import DefaultSessionOrchestrator
from src.runtime.types import ChildResult, RouteMeta, SessionDescriptor, SpawnPacket


@pytest.mark.asyncio
async def test_runtime_child_flow_prepares_and_auto_archives_child_session():
    orchestrator = DefaultSessionOrchestrator()
    parent = SessionDescriptor(
        session_key="parent",
        session_id="parent",
        route=RouteMeta(channel="web_chat", user_id="user-1"),
    )
    await orchestrator.session_store.put(parent)

    envelope = await orchestrator.prepare_child_turn(
        parent,
        SpawnPacket(
            objective="Investigate child task",
            deliverable="Return summary",
            selected_artifacts=["artifact-1"],
            tool_allowlist=["read_file"],
            timeout_ms=3000,
        ),
    )

    child = await orchestrator.session_store.get(envelope.request.session.session_key)
    assert child is not None
    assert child.parent_session_key == "parent"
    assert envelope.request.metadata["auto_archive"] is True

    payload = await orchestrator.complete_child(
        child,
        ChildResult(
            status="success",
            summary="child complete",
            artifact_refs=["artifact-1"],
            usage={"prompt_tokens": 10},
            duration_ms=250,
        ),
    )

    stored_child = await orchestrator.session_store.get(child.session_key)

    assert payload["target_session_key"] == "parent"
    assert payload["artifact_refs"] == ["artifact-1"]
    assert payload["usage"] == {"prompt_tokens": 10}
    assert stored_child is not None
    assert stored_child.status == "archived"
