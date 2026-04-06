"""Unit tests for child-session default policy behavior."""

from src.runtime.session.child_session import ChildSessionManager
from src.runtime.types import RouteMeta, SessionDescriptor, SpawnPacket


def test_child_session_manager_prepare_child_turn_applies_default_restrictions():
    manager = ChildSessionManager()
    parent = SessionDescriptor(
        session_key="parent",
        session_id="parent",
        route=RouteMeta(channel="web_chat"),
    )
    child = SessionDescriptor(
        session_key="child",
        session_id="child",
        parent_session_key="parent",
        route=RouteMeta(channel="web_chat"),
    )
    packet = SpawnPacket(
        objective="Inspect child task",
        deliverable="Return a summary",
        selected_artifacts=["artifact-1"],
        tool_allowlist=["read_file"],
        timeout_ms=3000,
    )

    envelope = manager.prepare_child_turn(parent=parent, child=child, packet=packet)

    assert envelope.prompt_mode == "minimal"
    assert envelope.request.metadata["prompt_mode"] == "minimal"
    assert envelope.request.metadata["max_spawns"] == 0
    assert envelope.request.metadata["session_tools_allowed"] is False
    assert envelope.request.metadata["auto_archive"] is True
    assert envelope.metadata["auto_archive"] is True
