"""Lightweight artifact store for runtime compatibility tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ._shared import get_context_bucket


@dataclass
class StoredArtifact:
    artifact_id: str
    session_id: str
    kind: str
    title: str
    content_path: str
    preview_text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "title": self.title,
            "content_path": self.content_path,
            "preview_text": self.preview_text,
            "metadata": dict(self.metadata),
        }


class ArtifactStore:
    def __init__(self, storage: Any) -> None:
        self._entries = get_context_bucket(storage)["artifacts"]

    async def create_artifact(
        self,
        *,
        session_id: str,
        kind: str,
        title: str,
        content_path: str,
        preview_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        artifact = StoredArtifact(
            artifact_id=f"artifact-{uuid4().hex[:8]}",
            session_id=session_id,
            kind=kind,
            title=title,
            content_path=content_path,
            preview_text=preview_text,
            metadata=dict(metadata or {}),
        )
        self._entries.append(artifact)
        return artifact

    async def list_by_session(self, session_id: str) -> list[StoredArtifact]:
        return [artifact for artifact in self._entries if artifact.session_id == session_id]
