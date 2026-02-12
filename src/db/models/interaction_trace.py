from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class InteractionTrace(Base):
    __tablename__ = "interaction_traces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"))
    interaction_type = Column(String, nullable=False)  # user_input, ai_response, tool_call, plugin_call, subagent_call, task_update, context_update
    request_data = Column(JSON, default={})
    response_data = Column(JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)
    duration_ms = Column(Integer, default=0)
    success_status = Column(Boolean, default=True)
    trace_metadata = Column(JSON, default={})