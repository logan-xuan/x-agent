"""Generated image asset metadata model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GeneratedImageAsset(Base):
    """Metadata for a generated image stored in the project asset space."""

    __tablename__ = "generated_image_assets"

    asset_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    agent_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    size: Mapped[str] = mapped_column(String(32))
    mime_type: Mapped[str] = mapped_column(String(64))
    relative_path: Mapped[str] = mapped_column(String(512), unique=True)
    public_url: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
