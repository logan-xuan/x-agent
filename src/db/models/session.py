from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    last_interaction_at = Column(DateTime, default=datetime.utcnow)
    context_data = Column(JSON, default={})
    active_status = Column(String, default="active")  # active, paused, archived
    session_metadata = Column(JSON, default={})