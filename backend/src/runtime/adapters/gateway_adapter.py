"""Bridge current gateway events into the runtime session orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..session import DefaultSessionOrchestrator
from ..types import RouteMeta, SessionDescriptor, TurnRequest


@dataclass
class GatewayAdapter:
    """Thin adapter for feeding gateway-style payloads into the runtime orchestrator."""

    orchestrator: DefaultSessionOrchestrator

    async def resolve_session(self, event: Any) -> SessionDescriptor:
        """Resolve or create a runtime session from a gateway event-like payload."""
        return await self.orchestrator.resolve_or_create(event)

    async def enqueue(self, session: SessionDescriptor, request: TurnRequest) -> TurnRequest:
        """Schedule a turn request through the session orchestrator."""
        return await self.orchestrator.enqueue_turn(session, request)

    def build_route(self, event: Any) -> RouteMeta:
        """Build a RouteMeta from an event-like payload when orchestration is not needed."""
        if isinstance(event, dict):
            return RouteMeta(channel=str(event.get("channel", "internal")))
        return RouteMeta(channel=str(getattr(event, "channel", "internal")))


__all__ = ["GatewayAdapter"]
