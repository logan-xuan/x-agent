"""Persistence helpers for generated image assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...config.models import ImageGenerationConfig
from ...models.generated_asset import GeneratedImageAsset
from ..storage import StorageService


@dataclass(slots=True)
class StoredImageAsset:
    """Stored image asset metadata returned to callers."""

    asset_id: str
    file_path: Path
    relative_path: str
    public_url: str
    mime_type: str


class ImageAssetStore:
    """Store generated image bytes in the project asset space."""

    _AGENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, config: ImageGenerationConfig, storage: StorageService) -> None:
        self._config = config
        self._storage = storage
        self._root = self._resolve_assets_root(config.assets_dir)

    @staticmethod
    def _resolve_assets_root(assets_dir: str) -> Path:
        configured = Path(assets_dir).expanduser()
        if configured.is_absolute():
            return configured.resolve()
        return (Path(__file__).resolve().parents[4] / configured).resolve()

    @property
    def root(self) -> Path:
        """Return the absolute asset root."""

        return self._root

    def _sanitize_agent_id(self, agent_id: str) -> str:
        if not self._AGENT_ID_PATTERN.fullmatch(agent_id):
            raise ValueError("agent_id contains unsupported characters")
        return agent_id

    @staticmethod
    def _extension_for_mime_type(mime_type: str, image_bytes: bytes) -> str:
        normalized = mime_type.lower().split(";", 1)[0].strip()
        if normalized == "image/png":
            return ".png"
        if normalized == "image/jpeg":
            return ".jpg"
        if normalized == "image/webp":
            return ".webp"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return ".webp"
        return ".bin"

    async def save_generated_image(
        self,
        *,
        agent_id: str,
        session_id: str,
        prompt: str,
        model: str,
        size: str,
        image_bytes: bytes,
        mime_type: str,
    ) -> StoredImageAsset:
        """Persist generated image bytes and metadata."""

        safe_agent_id = self._sanitize_agent_id(agent_id)
        date_part = datetime.now(UTC).strftime("%Y-%m-%d")
        asset_id = uuid4().hex[:8]
        extension = self._extension_for_mime_type(mime_type, image_bytes)
        relative_path = f"{safe_agent_id}/{date_part}/img_{asset_id}{extension}"
        file_path = (self._root / relative_path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(image_bytes)

        public_url = f"{str(self._config.public_base_url).rstrip('/')}/{relative_path}"

        async with self._storage.session() as db:
            db.add(
                GeneratedImageAsset(
                    asset_id=asset_id,
                    agent_id=safe_agent_id,
                    session_id=session_id,
                    prompt=prompt,
                    model=model,
                    size=size,
                    mime_type=mime_type,
                    relative_path=relative_path,
                    public_url=public_url,
                )
            )

        return StoredImageAsset(
            asset_id=asset_id,
            file_path=file_path,
            relative_path=relative_path,
            public_url=public_url,
            mime_type=mime_type,
        )
