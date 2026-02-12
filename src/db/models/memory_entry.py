from sqlalchemy import Column, String, DateTime, JSON, Text, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    entry_type = Column(String, nullable=False)  # preference, fact, interaction, summary
    content = Column(Text, nullable=False)
    embedding_vector = Column(String)  # Store vector representation as JSON string
    relevance_score = Column(Float, default=0.0)  # 0.0 to 1.0
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    expiry_date = Column(DateTime, nullable=True)
    tags = Column(JSON, default=[])  # Array of tags