"""Compatibility adapter from legacy agent_core flows to the new runtime types."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..types import RouteMeta, SessionDescriptor, TaskFrame, TurnController, TurnRequest, TurnResult


class AgentCoreAdapter:
    """Translate legacy agent_core inputs into runtime turn requests."""

    def __init__(self, controller: TurnController) -> None:
        self._controller = controller

    def build_turn_request(
        self,
        *,
        session: SessionDescriptor,
        route: RouteMeta,
        user_input: str,
        task_frame: TaskFrame | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TurnRequest:
        """Build a normalized turn request from legacy gateway or agent_core input."""
        normalized_task_frame = task_frame or TaskFrame(objective=user_input)
        if not normalized_task_frame.objective:
            normalized_task_frame = replace(normalized_task_frame, objective=user_input)

        return TurnRequest(
            session=session,
            user_input=user_input,
            task_frame=normalized_task_frame,
            route=route,
            metadata=dict(metadata or {}),
        )

    async def run(
        self,
        *,
        session: SessionDescriptor,
        route: RouteMeta,
        user_input: str,
        task_frame: TaskFrame | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TurnResult:
        """Forward a normalized request into the new turn controller."""
        request = self.build_turn_request(
            session=session,
            route=route,
            user_input=user_input,
            task_frame=task_frame,
            metadata=metadata,
        )
        return await self._controller.run(request)

    def to_legacy_payload(self, result: TurnResult) -> dict[str, Any]:
        """Map a runtime result to a legacy-friendly payload shape."""
        return {
            "kind": result.kind,
            "finish_reason": result.finish_reason,
            "output_text": result.output_text,
            "artifact_refs": [artifact.id for artifact in result.artifact_refs],
            "spawn_packet": result.spawn_packet,
            "metadata": dict(result.metadata),
        }


__all__ = ["AgentCoreAdapter"]
