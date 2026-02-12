from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class SubAgent(Base):
    __tablename__ = "subagents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)  # e.g., "coder", "researcher", "reviewer"
    role = Column(String, nullable=False)  # The specialized role of this SubAgent
    description = Column(String)  # Description of what this SubAgent does
    prompt = Column(String)  # System prompt for this SubAgent
    activated_status = Column(Boolean, default=False)  # Whether the SubAgent is currently activated
    activation_timestamp = Column(DateTime, nullable=True)  # When the SubAgent was activated
    deactivation_timestamp = Column(DateTime, nullable=True)  # When the SubAgent was deactivated
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)  # Session where the SubAgent is active
    timeout_duration = Column(Integer, default=3600)  # Auto-deactivation timeout in seconds (default 1 hour)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)