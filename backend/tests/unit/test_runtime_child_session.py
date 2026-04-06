"""Unit tests for bounded child-session policy helpers."""

from src.runtime.session import ChildSessionManager
from src.runtime.types import ChildResult, RouteMeta, SessionDescriptor, SpawnPacket, TaskFrame


def test_child_session_manager_prepares_minimal_child_turn():
    manager = ChildSessionManager()
    parent = SessionDescriptor(
        session_key="parent",
        session_id="parent",
        route=RouteMeta(channel="web"),
    )
    child = SessionDescriptor(
        session_key="child",
        session_id="child",
        parent_session_key="parent",
        route=RouteMeta(channel="web"),
    )

    envelope = manager.prepare_child_turn(
        parent=parent,
        child=child,
        packet=SpawnPacket(
            objective="inspect issue",
            deliverable="summary",
            constraints=["be concise"],
            tool_allowlist=["web_search"],
        ),
    )

    assert envelope.prompt_mode == "minimal"
    assert envelope.request.metadata["max_spawns"] == 0
    assert envelope.request.metadata["session_tools_allowed"] is False
    assert envelope.tool_allowlist == ["web_search"]


def test_child_session_manager_ingests_only_structured_result():
    manager = ChildSessionManager()
    payload = manager.ingest_child_result(
        parent_task_frame=TaskFrame(objective="parent objective"),
        result=ChildResult(
            status="success",
            summary="child summary",
            unresolved=["remaining"],
            artifact_refs=["artifact:1"],
            usage={"tokens": 10},
            duration_ms=42,
        ),
    )

    assert payload["summary"] == "child summary"
    assert payload["artifact_refs"] == ["artifact:1"]
    assert "transcript" not in payload
