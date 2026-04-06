"""Unit tests for runtime session orchestrator child completion behavior."""

from dataclasses import dataclass, field

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
