"""Message model for chat messages."""

import json
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .session import Session


class Message(Base):
    """Chat message model.
    
    Represents a single message in a conversation.
    """
    
    __tablename__ = "messages"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, role={self.role}, content={content_preview})>"
    
    def get_metadata(self) -> dict[str, Any] | None:
        """Get metadata as dictionary."""
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except json.JSONDecodeError:
                return None
        return None
    
    def set_metadata(self, value: dict[str, Any] | None) -> None:
        """Set metadata from dictionary."""
        if value:
            self.metadata_json = json.dumps(value)
        else:
            self.metadata_json = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.get_metadata(),
        }
