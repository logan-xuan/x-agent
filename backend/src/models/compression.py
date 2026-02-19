"""Compression event model for storing compression history."""

from sqlalchemy import Column, Integer, String, DateTime, Text, Float
from sqlalchemy.sql import func

from .base import Base


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
    compression_time = Column(DateTime(timezone=True), server_default=func.now())  # Time of compression
    original_messages = Column(Text)  # JSON string of original messages (before compression)
    compressed_messages = Column(Text)  # JSON string of compressed messages (after compression)
    archived_message_count = Column(Integer)  # Number of archived messages
    retained_message_count = Column(Integer)  # Number of retained messages