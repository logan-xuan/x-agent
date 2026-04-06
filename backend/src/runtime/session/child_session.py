"""Bounded child-session policy and result-ingestion helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..types import ChildResult, PromptMode, SessionDescriptor, SpawnPacket, TaskFrame, TurnRequest


@dataclass
class ChildSessionPolicy:
    """Default runtime policy applied to spawned child sessions."""

    prompt_mode: PromptMode = "minimal"
    max_spawns: int = 0
    allow_session_tools: bool = False


@dataclass
class ChildTurnEnvelope:
    """Prepared child turn request plus runtime-only child metadata."""

    request: TurnRequest
    prompt_mode: PromptMode
    tool_allowlist: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChildSessionManager:
    """Prepare child turn requests and ingest child results for the parent."""

    policy: ChildSessionPolicy = field(default_factory=ChildSessionPolicy)

    def prepare_child_turn(
        self,
        *,
        parent: SessionDescriptor,
        child: SessionDescriptor,
        packet: SpawnPacket,
    ) -> ChildTurnEnvelope:
        """Build the child turn envelope from a spawn packet."""
        task_frame = TaskFrame(
            objective=packet.objective,
            deliverable=packet.deliverable,
            constraints=list(packet.constraints),
            unresolved=[packet.deliverable] if packet.deliverable else [],
            active_artifacts=list(packet.selected_artifacts),
        )
        request = TurnRequest(
            session=child,
            user_input=packet.objective,
            task_frame=task_frame,
            route=child.route or parent.route,
            metadata={
                "parent_session_key": parent.session_key,
                "parent_summary": packet.parent_summary,
                "prompt_mode": self.policy.prompt_mode,
                "tool_allowlist": list(packet.tool_allowlist),
                "session_tools_allowed": self.policy.allow_session_tools,
                "max_spawns": self.policy.max_spawns,
                "child_timeout_ms": packet.timeout_ms,
            },
        )
        return ChildTurnEnvelope(
            request=request,
            prompt_mode=self.policy.prompt_mode,
            tool_allowlist=list(packet.tool_allowlist),
            metadata={
                "session_tools_allowed": self.policy.allow_session_tools,
                "max_spawns": self.policy.max_spawns,
            },
        )

    def ingest_child_result(
        self,
        *,
        parent_task_frame: TaskFrame,
        result: ChildResult,
    ) -> dict[str, Any]:
        """Build the structured parent-ingest payload without child transcript leakage."""
        return {
            "status": result.status,
            "summary": result.summary,
            "unresolved": list(result.unresolved),
            "artifact_refs": list(result.artifact_refs),
            "usage": dict(result.usage),
            "duration_ms": result.duration_ms,
            "parent_objective": parent_task_frame.objective,
        }


__all__ = ["ChildSessionManager", "ChildSessionPolicy", "ChildTurnEnvelope"]
