from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"))
    message_id = Column(String, ForeignKey("messages.id"))
    tool_name = Column(String, nullable=False)
    parameters = Column(JSON, default={})
    execution_status = Column(String, default="queued")  # queued, running, succeeded, failed, cancelled
    started_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)
    result_data = Column(JSON)
    error_message = Column(Text, nullable=True)
    execution_metadata = Column(JSON, default={})