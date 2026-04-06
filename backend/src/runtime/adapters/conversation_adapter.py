"""Compatibility helpers for mapping legacy conversation inputs into runtime requests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..types import RouteMeta, SessionDescriptor, TaskFrame, TurnRequest


class ConversationAdapter:
    """Bridge current conversation-layer payloads to runtime-friendly state objects."""

    def build_task_frame(
        self,
        *,
        user_input: str,
        task_frame: TaskFrame | None = None,
        artifact_ids: list[str] | None = None,
    ) -> TaskFrame:
        """Create a normalized task frame from current conversation payloads."""
        frame = task_frame or TaskFrame(objective=user_input)
        if not frame.objective:
            frame = replace(frame, objective=user_input)
        if artifact_ids:
            frame.active_artifacts = list(dict.fromkeys([*frame.active_artifacts, *artifact_ids]))
        return frame

    def build_turn_request(
        self,
        *,
        session: SessionDescriptor,
        route: RouteMeta,
        user_input: str,
        task_frame: TaskFrame | None = None,
        artifact_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TurnRequest:
        """Build a runtime turn request without depending on agent_core."""
        normalized_task_frame = self.build_task_frame(
            user_input=user_input,
            task_frame=task_frame,
            artifact_ids=artifact_ids,
        )
        return TurnRequest(
            session=session,
            user_input=user_input,
            task_frame=normalized_task_frame,
            route=route,
            metadata=dict(metadata or {}),
        )


__all__ = ["ConversationAdapter"]
