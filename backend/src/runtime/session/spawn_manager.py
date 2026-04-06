"""Spawn child-session descriptors from bounded parent requests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ..types import RouteMeta, SessionDescriptor, SpawnPacket


@dataclass
class SpawnManager:
    """Create child session descriptors from structured spawn packets."""

    child_lane: str = "subagent"

    async def spawn_child(
        self,
        parent: SessionDescriptor,
        packet: SpawnPacket,
        route: RouteMeta | None = None,
    ) -> SessionDescriptor:
        """Build a child session descriptor without running the child turn."""
        child_id = str(uuid4())
        return SessionDescriptor(
            session_key=f"{parent.session_key}:child:{child_id[:8]}",
            session_id=child_id,
            parent_session_key=parent.session_key,
            lane="subagent",
            model_profile=parent.model_profile,
            budget_profile=packet.budget_profile,
            route=route or parent.route,
            status="active",
        )


__all__ = ["SpawnManager"]
