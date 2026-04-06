"""Unit tests for child-session announcement payloads."""

import pytest

from src.runtime.session.announcement_manager import AnnouncementManager
from src.runtime.types import ChildResult, SessionDescriptor


@pytest.mark.asyncio
async def test_announcement_manager_build_includes_usage_and_duration():
    manager = AnnouncementManager()
    parent = SessionDescriptor(session_key="parent", session_id="parent")
    child = SessionDescriptor(session_key="child", session_id="child", parent_session_key="parent")
    result = ChildResult(
        status="success",
        summary="done",
        unresolved=["none"],
        artifact_refs=["artifact-1"],
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        duration_ms=1234,
    )

    payload = await manager.build(parent, child, result)

    assert payload["target_session_key"] == "parent"
    assert payload["child_session_key"] == "child"
    assert payload["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
    assert payload["duration_ms"] == 1234
    assert payload["stats_line"] == "duration=1234ms"
