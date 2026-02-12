from sqlalchemy import Column, String, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Configuration(Base):
    __tablename__ = "configurations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)  # Configuration key name
    value = Column(JSON, default={})  # Configuration value (can be string, number, boolean, or object)
    scope = Column(String, default="global")  # global, user, session
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Foreign key to User if user-scoped
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)  # Foreign key to Session if session-scoped
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String, nullable=False)  # User who last updated the configuration
    encrypted = Column(Boolean, default=False)  # Whether the value is encrypted (for sensitive data)