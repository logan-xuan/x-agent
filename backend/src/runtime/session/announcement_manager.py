"""Build and queue structured child-session announcements."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..types import ChildResult, SessionDescriptor


@dataclass
class AnnouncementManager:
    """Generate stable announcement payloads and keep a local queue."""

    queue: list[dict[str, object]] = field(default_factory=list)

    async def build(self, parent: SessionDescriptor, child: SessionDescriptor, result: ChildResult) -> dict[str, object]:
        """Build a structured announcement payload."""
        return {
            "target_session_key": parent.session_key,
            "child_session_key": child.session_key,
            "status": result.status,
            "summary": result.summary,
            "unresolved": list(result.unresolved),
            "artifact_refs": list(result.artifact_refs),
            "stats_line": f"duration={result.duration_ms}ms",
        }

    async def enqueue(self, payload: dict[str, object]) -> None:
        """Queue an announcement for later delivery."""
        self.queue.append(payload)


__all__ = ["AnnouncementManager"]
