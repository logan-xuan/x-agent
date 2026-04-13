"""Compression event model for storing compression history."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .base import Base

# 北京时间 UTC+8
_BEIJING_TZ = timezone(timedelta(hours=8))


class CompressionEvent(Base):
    """Store compression event data for audit and analysis."""

    __tablename__ = "compression_events"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, index=True)  # Session identifier
    original_message_count = Column(Integer)  # Number of messages before compression
    compressed_message_count = Column(Integer)  # Number of messages after compression
    original_token_count = Column(Integer)  # Token count before compression
    compressed_token_count = Column(Integer)  # Token count after compression
    compression_ratio = Column(Float)  # Compression ratio
    compression_time = Column(
        DateTime(timezone=True), default=lambda: datetime.now(_BEIJING_TZ)
    )  # Time of compression (Beijing time)
    original_messages = Column(Text)  # JSON string of original messages (before compression)
    compressed_messages = Column(Text)  # JSON string of compressed messages (after compression)
    archived_message_count = Column(Integer)  # Number of archived messages
    retained_message_count = Column(Integer)  # Number of retained messages
