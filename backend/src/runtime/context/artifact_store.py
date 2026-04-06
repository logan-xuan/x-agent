"""Artifact store used to externalize large runtime results."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from ..types import ArtifactRef


@dataclass
class ArtifactWriteRequest:
    """Payload written into the artifact store."""

    kind: str
    title: str
    content: str
    location: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoredArtifact:
    """Stored artifact content plus its exported reference."""

    ref: ArtifactRef
    content: str


@dataclass
class InMemoryArtifactStore:
    """Simple in-memory artifact store for early runtime integration."""

    preview_chars: int = 2000
    preview_head_chars: int = 900
    preview_tail_chars: int = 700
    _items: dict[str, StoredArtifact] = field(default_factory=dict)
    _dedupe: dict[str, str] = field(default_factory=dict)

    async def put(self, item: ArtifactWriteRequest) -> ArtifactRef:
        """Persist a large result and return a compact reference."""
        dedupe_key = self._dedupe_key(item)
        if dedupe_key in self._dedupe:
            artifact_id = self._dedupe[dedupe_key]
            stored = self._items[artifact_id]
            stored.ref.preview = self._build_preview(stored.content)
            return stored.ref

        artifact_id = f"artifact:{len(self._items) + 1}"
        ref = ArtifactRef(
            id=artifact_id,
            kind=self._normalize_kind(item.kind),
            title=item.title,
            preview=self._build_preview(item.content),
            location=item.location,
            created_at=time.time(),
            metadata=dict(item.metadata),
        )
        self._items[artifact_id] = StoredArtifact(ref=ref, content=item.content)
        self._dedupe[dedupe_key] = artifact_id
        return ref

    async def get(self, artifact_id: str) -> StoredArtifact | None:
        """Return a stored artifact by id."""
        return self._items.get(artifact_id)

    def configure_preview(
        self,
        *,
        preview_chars: int,
        preview_head_chars: int,
        preview_tail_chars: int,
    ) -> None:
        """Update preview sizing parameters for subsequent artifact writes."""
        self.preview_chars = max(preview_chars, 1)
        self.preview_head_chars = max(preview_head_chars, 0)
        self.preview_tail_chars = max(preview_tail_chars, 0)

    def _dedupe_key(self, item: ArtifactWriteRequest) -> str:
        payload = f"{item.kind}\n{item.location or ''}\n{item.content}".encode("utf-8")
        return hashlib.sha1(payload).hexdigest()

    def _build_preview(self, content: str) -> str:
        if len(content) <= self.preview_chars:
            return content

        max_kept = min(self.preview_chars, len(content))
        head_keep = min(self.preview_head_chars, max_kept)
        remaining = max(max_kept - head_keep, 0)
        tail_keep = min(self.preview_tail_chars, remaining, len(content) - head_keep)

        head = content[:head_keep]
        tail = content[-tail_keep:] if tail_keep > 0 else ""
        omitted = max(len(content) - len(head) - len(tail), 0)
        return f"{head}\n...[{omitted} chars omitted]...\n{tail}"

    def _normalize_kind(self, kind: str) -> str:
        allowed = {"web", "bash", "search", "file", "tool", "summary", "memory", "other"}
        return kind if kind in allowed else "other"


__all__ = ["ArtifactWriteRequest", "InMemoryArtifactStore", "StoredArtifact"]
