from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class SubAgentExecution(Base):
    __tablename__ = "subagent_executions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subagent_id = Column(String, ForeignKey("subagents.id"))  # Reference to the SubAgent
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)  # Session where execution happened
    task_description = Column(String)  # Description of the task assigned to the SubAgent
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    input_data = Column(JSON, default={})  # Input provided to the SubAgent
    output_data = Column(JSON, default={})  # Output produced by the SubAgent
    execution_metadata = Column(JSON, default={})  # Execution-specific metadata
    error_message = Column(String, nullable=True)  # Error details if execution failed