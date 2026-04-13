"""Persistence helpers for audio assets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ....config.manager import get_config
from ....models.audio_asset import AudioAsset
from ....services.storage import StorageService, get_storage_service
from ..schemas import AudioAssetRef, AudioFormat


@dataclass(slots=True)
class StoredAudioAsset:
    """Stored audio asset metadata returned to callers."""

    asset_id: str
    file_path: Path
    relative_path: str
    public_url: str
    playback_url: str
    mime_type: str
    audio_format: str
    size_bytes: int
    duration_ms: int | None = None

    def to_ref(self, *, source: str, metadata: dict[str, object] | None = None) -> AudioAssetRef:
        """Convert stored asset metadata to the shared AudioAssetRef schema."""
        return AudioAssetRef(
            asset_id=self.asset_id,
            storage_path=self.file_path,
            mime_type=self.mime_type,
            format=self.audio_format,
            source=source,
            public_url=self.public_url,
            playback_url=self.playback_url,
            size_bytes=self.size_bytes,
            duration_ms=self.duration_ms,
            metadata=metadata or {},
        )


class AudioAssetStore:
    """Store uploaded and generated audio in the project asset space."""

    _AGENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, config: object, storage: StorageService) -> None:
        self._config = config
        self._storage = storage
        self._root = self._resolve_assets_root(config.assets_dir)

    def _current_config(self) -> object:
        """Read the latest voice config so hot-reload updates take effect."""
        config = get_config().voice
        resolved_root = self._resolve_assets_root(config.assets_dir)
        if resolved_root != self._root:
            self._root = resolved_root
        self._config = config
        return config

    @staticmethod
    def _resolve_assets_root(assets_dir: str) -> Path:
        configured = Path(assets_dir).expanduser()
        if configured.is_absolute():
            return configured.resolve()
        return (Path(__file__).resolve().parents[5] / configured).resolve()

    @property
    def root(self) -> Path:
        """Return the absolute asset root."""
        return self._root

    def _sanitize_agent_id(self, agent_id: str) -> str:
        if not self._AGENT_ID_PATTERN.fullmatch(agent_id):
            raise ValueError("agent_id contains unsupported characters")
        return agent_id

    @staticmethod
    def _build_asset_url(base_url: str, relative_path: str) -> str:
        normalized_base = base_url.rstrip("/")
        normalized_path = relative_path.lstrip("/")
        return f"{normalized_base}/{normalized_path}"

    @staticmethod
    def _extension_for_audio(audio_format: str, mime_type: str) -> str:
        normalized_format = audio_format.lower().strip()
        if normalized_format:
            return f".{normalized_format}"

        normalized_mime = mime_type.lower().split(";", 1)[0].strip()
        mapping = {
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/opus": ".opus",
            "audio/webm": ".webm",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/flac": ".flac",
        }
        return mapping.get(normalized_mime, ".bin")

    async def save_generated_audio(
        self,
        *,
        agent_id: str,
        session_id: str,
        provider: str,
        voice: str | None,
        audio_bytes: bytes,
        mime_type: str,
        audio_format: AudioFormat | str,
        duration_ms: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredAudioAsset:
        """Persist generated audio bytes and metadata."""
        return await self._save_audio(
            agent_id=agent_id,
            session_id=session_id,
            purpose="generated",
            provider=provider,
            voice=voice,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            audio_format=str(audio_format),
            duration_ms=duration_ms,
            original_filename=None,
            metadata=metadata,
        )

    async def save_uploaded_audio(
        self,
        *,
        agent_id: str,
        session_id: str,
        audio_bytes: bytes,
        mime_type: str,
        audio_format: AudioFormat | str,
        original_filename: str | None,
        duration_ms: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> StoredAudioAsset:
        """Persist uploaded audio bytes and metadata."""
        config = self._current_config()
        max_bytes = int(getattr(config, "upload_max_bytes", 25 * 1024 * 1024))
        if len(audio_bytes) > max_bytes:
            raise ValueError("audio upload exceeds configured size limit")

        return await self._save_audio(
            agent_id=agent_id,
            session_id=session_id,
            purpose="upload",
            provider=None,
            voice=None,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            audio_format=str(audio_format),
            duration_ms=duration_ms,
            original_filename=original_filename,
            metadata=metadata,
        )

    async def _save_audio(
        self,
        *,
        agent_id: str,
        session_id: str,
        purpose: str,
        provider: str | None,
        voice: str | None,
        audio_bytes: bytes,
        mime_type: str,
        audio_format: str,
        duration_ms: int | None,
        original_filename: str | None,
        metadata: dict[str, object] | None,
    ) -> StoredAudioAsset:
        config = self._current_config()
        safe_agent_id = self._sanitize_agent_id(agent_id)
        date_part = datetime.now(UTC).strftime("%Y-%m-%d")
        asset_id = uuid4().hex[:8]
        extension = self._extension_for_audio(audio_format, mime_type)
        relative_path = f"{safe_agent_id}/{date_part}/audio_{asset_id}{extension}"
        file_path = (self._root / relative_path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(audio_bytes)

        public_url = self._build_asset_url(str(config.public_base_url), relative_path)
        playback_base_url = str(
            getattr(config, "playback_base_url", "") or str(config.public_base_url)
        )
        playback_url = self._build_asset_url(playback_base_url, relative_path)

        async with self._storage.session() as db:
            db.add(
                AudioAsset(
                    asset_id=asset_id,
                    agent_id=safe_agent_id,
                    session_id=session_id,
                    purpose=purpose,
                    provider=provider,
                    voice=voice,
                    mime_type=mime_type,
                    format=audio_format,
                    relative_path=relative_path,
                    public_url=public_url,
                    original_filename=original_filename,
                    size_bytes=len(audio_bytes),
                    duration_ms=duration_ms,
                    metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                )
            )

        return StoredAudioAsset(
            asset_id=asset_id,
            file_path=file_path,
            relative_path=relative_path,
            public_url=public_url,
            playback_url=playback_url,
            mime_type=mime_type,
            audio_format=audio_format,
            size_bytes=len(audio_bytes),
            duration_ms=duration_ms,
        )


_audio_asset_store: AudioAssetStore | None = None


def get_audio_asset_store() -> AudioAssetStore:
    """Return the shared audio asset store."""
    global _audio_asset_store
    if _audio_asset_store is None:
        _audio_asset_store = AudioAssetStore(get_config().voice, get_storage_service())
    return _audio_asset_store
