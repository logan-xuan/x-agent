"""Route resolution helpers for runtime session orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..types import RouteMeta


@dataclass
class DefaultRouteResolver:
    """Resolve RouteMeta from gateway-style dicts or lightweight objects."""

    default_channel: str = "internal"

    async def resolve(self, event: Any) -> RouteMeta:
        """Resolve route metadata from an event-like payload."""
        if isinstance(event, dict):
            return RouteMeta(
                channel=str(event.get("channel", self.default_channel)),
                account_id=self._optional(event.get("account_id")),
                user_id=self._optional(event.get("user_id")),
                thread_id=self._optional(event.get("thread_id")),
                topic_id=self._optional(event.get("topic_id")),
                origin_message_id=self._optional(event.get("origin_message_id")),
            )

        return RouteMeta(
            channel=str(getattr(event, "channel", self.default_channel)),
            account_id=self._optional(getattr(event, "account_id", None)),
            user_id=self._optional(getattr(event, "user_id", None)),
            thread_id=self._optional(getattr(event, "thread_id", None)),
            topic_id=self._optional(getattr(event, "topic_id", None)),
            origin_message_id=self._optional(getattr(event, "origin_message_id", None)),
        )

    def _optional(self, value: object | None) -> str | None:
        return str(value) if value not in {None, ""} else None


__all__ = ["DefaultRouteResolver"]
