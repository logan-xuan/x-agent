"""Persistence service for stored artifact references."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from ...models.context_state import Artifact
from ..storage import StorageService, get_storage_service


class ArtifactStore:
    """CRUD helpers for Artifact rows."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or get_storage_service()

    async def create_artifact(
        self,
        *,
        session_id: str,
        kind: str,
        title: str,
        content_path: str,
        preview_text: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        artifact = Artifact(
            session_id=session_id,
            kind=kind,
            title=title,
            content_path=content_path,
            preview_text=preview_text,
            metadata_json=_dump_json(metadata or {}),
        )
        async with self._storage.session() as db_session:
            db_session.add(artifact)
            await db_session.flush()
            await db_session.refresh(artifact)
            return artifact

    async def get(self, artifact_id: str) -> Artifact | None:
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Artifact).where(Artifact.id == artifact_id)
            )
            return result.scalar_one_or_none()

    async def list_by_session(
        self,
        session_id: str,
        *,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[Artifact]:
        async with self._storage.session() as db_session:
            query = (
                select(Artifact)
                .where(Artifact.session_id == session_id)
                .order_by(Artifact.created_at.desc())
                .limit(limit)
            )
            if kind:
                query = query.where(Artifact.kind == kind)
            result = await db_session.execute(query)
            return list(result.scalars().all())


_artifact_store: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore()
    return _artifact_store


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
