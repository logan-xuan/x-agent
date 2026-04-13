"""Audio asset metadata model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AudioAsset(Base):
    """Metadata for uploaded or generated audio stored in the project asset space."""

    __tablename__ = "audio_assets"

    asset_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voice: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(64))
    format: Mapped[str] = mapped_column(String(32))
    relative_path: Mapped[str] = mapped_column(String(512), unique=True)
    public_url: Mapped[str] = mapped_column(String(1024))
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
