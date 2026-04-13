"""Memory flush hooks used by the runtime compression pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..types import ArtifactRef
from .artifact_store import ArtifactWriteRequest, InMemoryArtifactStore


@dataclass
class MemoryFlushRequest:
    """Request envelope for pre-compaction memory flush."""

    session_key: str
    messages: list[Any]
    active_artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryFlushResult:
    """Result of a memory flush attempt."""

    flushed: bool
    messages: list[Any] | None = None
    new_artifacts: list[ArtifactRef] = field(default_factory=list)
    affected_artifact_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class NoopMemoryFlusher:
    """Default placeholder flusher for the initial runtime skeleton."""

    async def flush(self, request: MemoryFlushRequest) -> MemoryFlushResult:
        _ = request
        return MemoryFlushResult(flushed=False)


@dataclass
class ArtifactBackedMemoryFlusher:
    """Persist old long tool results and replace them with short inline references."""

    artifact_store: InMemoryArtifactStore | None = None
    max_messages_per_pass: int = 4

    async def flush(self, request: MemoryFlushRequest) -> MemoryFlushResult:
        if self.artifact_store is None:
            return MemoryFlushResult(flushed=False)

        preserve_recent_messages = int(request.metadata.get("preserve_recent_messages", 0) or 0)
        min_flush_chars = int(request.metadata.get("min_flush_chars", 0) or 0)
        tool_roles = {"tool", "tool_result"}
        protected_start = max(len(request.messages) - preserve_recent_messages, 0)
        active_artifact_ids = {artifact.id for artifact in request.active_artifacts}
        messages = [dict(message) for message in request.messages]
        new_artifacts: list[ArtifactRef] = []
        affected_artifact_ids: list[str] = []
        flushed_count = 0

        for index, message in enumerate(messages):
            if index >= protected_start or flushed_count >= self.max_messages_per_pass:
                continue
            if message.get("role") not in tool_roles:
                continue
            if message.get("is_error"):
                continue

            content = str(message.get("content", ""))
            if len(content) <= min_flush_chars:
                continue
            normalized = content.strip().lower()
            if normalized.startswith("[memory-flushed tool result]") or normalized.startswith(
                "[persisted large tool result:"
            ):
                continue

            tool_name = str(message.get("tool_name") or message.get("name") or "tool_result")
            ref = await self.artifact_store.put(
                ArtifactWriteRequest(
                    kind="tool",
                    title=tool_name,
                    content=content,
                    location=str(message.get("tool_call_id") or ""),
                    metadata={"memory_flushed": True, "message_index": index},
                )
            )
            if ref.id not in active_artifact_ids and all(
                existing.id != ref.id for existing in new_artifacts
            ):
                new_artifacts.append(ref)
                active_artifact_ids.add(ref.id)
            message["content"] = self._build_placeholder(tool_name=tool_name, ref=ref)
            affected_artifact_ids.append(ref.id)
            flushed_count += 1

        if not affected_artifact_ids:
            return MemoryFlushResult(flushed=False)

        return MemoryFlushResult(
            flushed=True,
            messages=messages,
            new_artifacts=new_artifacts,
            affected_artifact_ids=affected_artifact_ids,
            notes=["artifact_backed_memory_flush"],
        )

    def _build_placeholder(self, *, tool_name: str, ref: ArtifactRef) -> str:
        summary = " ".join(ref.preview.split()).strip()
        if len(summary) > 180:
            summary = f"{summary[:177]}..."
        return (
            "[Memory-flushed tool result]\n"
            f"Tool: {tool_name}\n"
            f"Artifact: {ref.id}\n"
            f"Summary: {summary or '(empty)'}"
        )


__all__ = [
    "ArtifactBackedMemoryFlusher",
    "MemoryFlushRequest",
    "MemoryFlushResult",
    "NoopMemoryFlusher",
]
