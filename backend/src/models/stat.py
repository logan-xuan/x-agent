"""LLM request statistics model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LLMRequestStat(Base):
    """LLM request statistics model.
    
    Stores detailed statistics for each LLM API request,
    enabling historical analysis and multi-dimensional reporting.
    """
    
    __tablename__ = "llm_request_stats"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Provider and model info
    provider_name: Mapped[str] = mapped_column(String(100), index=True)
    model_id: Mapped[str] = mapped_column(String(100), index=True)
    
    # Request details
    session_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    request_type: Mapped[str] = mapped_column(String(20), default="chat")  # chat, embedding, etc.
    
    # Response status
    success: Mapped[int] = mapped_column(Integer, default=1)  # 1=success, 0=failure
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Token usage
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Performance metrics
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)  # Response time in milliseconds
    
    # Timestamp - use local time
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    
    def __repr__(self) -> str:
        return f"<LLMRequestStat(id={self.id[:8]}, provider={self.provider_name}, success={self.success})>"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "session_id": self.session_id,
            "request_type": self.request_type,
            "success": bool(self.success),
            "error_message": self.error_message,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
