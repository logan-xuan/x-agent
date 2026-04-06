"""Session orchestration skeleton for runtime control-plane work."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4
from typing import Any

from ..repositories import InMemorySessionRepository, SessionRepository
from ..types import ChildResult, RouteMeta, SessionDescriptor, SpawnPacket, TurnRequest
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
    route_resolver: DefaultRouteResolver = field(default_factory=DefaultRouteResolver)
    lane_scheduler: InMemoryLaneScheduler = field(default_factory=InMemoryLaneScheduler)
    spawn_manager: SpawnManager = field(default_factory=SpawnManager)
    child_session_manager: ChildSessionManager = field(default_factory=ChildSessionManager)
    announcement_manager: AnnouncementManager = field(default_factory=AnnouncementManager)
    lifecycle_manager: SessionLifecycleManager = field(default_factory=SessionLifecycleManager)

    async def resolve_or_create(self, event: Any) -> SessionDescriptor:
        """Resolve a session from an event-like payload or create a new one."""
        session_key = self._event_value(event, "session_key") or self._event_value(event, "session_id")
        if not session_key:
            session_key = f"session:{uuid4().hex[:8]}"

        existing = await self.session_store.get(session_key)
        if existing is not None:
            return await self.lifecycle_manager.activate(existing)

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

    async def enqueue_turn(self, session: SessionDescriptor, request: TurnRequest) -> TurnRequest:
        """Schedule a turn request into the correct lane and return it after execution."""
        async def run() -> TurnRequest:
            _ = request
            return request

        await self.lifecycle_manager.activate(session)
        return await self.lane_scheduler.enqueue(session.lane, run)

    async def spawn_child(self, parent: SessionDescriptor, packet: SpawnPacket) -> SessionDescriptor:
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

    async def complete_child(self, child: SessionDescriptor, result: ChildResult) -> dict[str, object]:
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

    async def archive(self, session_key: str) -> None:
        """Archive a session by key."""
        session = await self.session_store.get(session_key)
        if session is None:
            return
        archived = await self.lifecycle_manager.archive(session)
        await self.session_store.put(archived)

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
