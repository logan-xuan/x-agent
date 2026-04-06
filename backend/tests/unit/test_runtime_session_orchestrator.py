"""Unit tests for runtime session orchestrator child completion behavior."""

import pytest

from src.runtime.session.orchestrator import DefaultSessionOrchestrator
from src.runtime.types import ChildResult, SessionDescriptor


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
