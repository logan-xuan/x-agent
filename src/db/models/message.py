from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"))
    sender_type = Column(String, nullable=False)  # user, assistant, system
    sender_id = Column(String, nullable=True)  # Specific user or system component
    content = Column(Text, nullable=False)
    content_type = Column(String, default="text")  # text, image, file, tool_result
    content_metadata = Column(JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)
    processed_status = Column(String, default="pending")  # pending, processing, completed, error