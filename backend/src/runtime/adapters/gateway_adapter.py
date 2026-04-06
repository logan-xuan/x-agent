"""Bridge current gateway events into the runtime session orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..adapters.conversation_adapter import ConversationAdapter
from ..session import DefaultSessionOrchestrator
from ..types import RouteMeta, SessionDescriptor, TaskFrame, TurnRequest


@dataclass
class GatewayAdapter:
    """Thin adapter for feeding gateway-style payloads into the runtime orchestrator."""

    orchestrator: DefaultSessionOrchestrator
    conversation_adapter: ConversationAdapter = field(default_factory=ConversationAdapter)

    async def resolve_session(self, event: Any) -> SessionDescriptor:
        """Resolve or create a runtime session from a gateway event-like payload."""
        return await self.orchestrator.resolve_or_create(self.build_event_payload(event))

    async def enqueue(self, session: SessionDescriptor, request: TurnRequest) -> TurnRequest:
        """Schedule a turn request through the session orchestrator."""
        return await self.orchestrator.enqueue_turn(session, request)

    async def prepare_turn(
        self,
        event: Any,
        *,
        user_input: str | None = None,
        task_frame: TaskFrame | None = None,
        artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[SessionDescriptor, TurnRequest]:
        """Resolve session and build a runtime turn request from a gateway-style event."""
        payload = self.build_event_payload(event)
        session = await self.orchestrator.resolve_or_create(payload)
        route = session.route or await self.orchestrator.route_resolver.resolve(payload)
        session.route = route
        request = self.conversation_adapter.build_turn_request(
            session=session,
            route=route,
            user_input=user_input if user_input is not None else self._content_text(payload.get("content")),
            task_frame=task_frame,
            artifact_ids=artifact_ids,
            metadata={
                **dict(payload.get("metadata", {})),
                **dict(metadata or {}),
            },
        )
        return session, request

    def build_route(self, event: Any) -> RouteMeta:
        """Build a RouteMeta from an event-like payload when orchestration is not needed."""
        payload = self.build_event_payload(event)
        return RouteMeta(
            channel=str(payload.get("channel", "internal")),
            account_id=self._optional(payload.get("account_id")),
            user_id=self._optional(payload.get("user_id")),
            thread_id=self._optional(payload.get("thread_id")),
            topic_id=self._optional(payload.get("topic_id")),
            origin_message_id=self._optional(payload.get("origin_message_id")),
        )

    def build_event_payload(self, event: Any) -> dict[str, Any]:
        """Normalize an envelope-like event into a dict suitable for runtime orchestration."""
        if isinstance(event, dict):
            payload = dict(event)
        else:
            payload = {
                "session_id": getattr(event, "session_id", None),
                "session_key": getattr(event, "session_key", None),
                "content": getattr(event, "content", None),
                "channel": getattr(event, "channel", None),
                "channel_type": getattr(event, "channel_type", None),
                "user_id": getattr(event, "user_id", None),
                "channel_id": getattr(event, "channel_id", None),
                "thread_id": getattr(event, "thread_id", None),
                "topic_id": getattr(event, "topic_id", None),
                "origin_message_id": getattr(event, "message_id", None),
                "metadata": getattr(event, "metadata", None),
                "lane": getattr(event, "lane", None),
            }

        if "channel" not in payload or not payload["channel"]:
            channel_type = payload.get("channel_type")
            if hasattr(channel_type, "value"):
                payload["channel"] = str(channel_type.value)
            elif channel_type:
                payload["channel"] = str(channel_type)
            else:
                payload["channel"] = "internal"

        if "origin_message_id" not in payload or not payload["origin_message_id"]:
            payload["origin_message_id"] = payload.get("message_id")

        payload["metadata"] = dict(payload.get("metadata", {}) or {})
        return payload

    def _optional(self, value: Any) -> str | None:
        return str(value) if value not in {None, ""} else None

    def _content_text(self, value: Any) -> str:
        if value in {None, ""}:
            return ""
        return str(value)


__all__ = ["GatewayAdapter"]
