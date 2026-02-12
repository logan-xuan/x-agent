from sqlalchemy import Column, String, DateTime, JSON, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"))
    parent_task_id = Column(String, ForeignKey("tasks.id"), nullable=True)  # For hierarchical tasks
    title = Column(String, nullable=False)
    description = Column(Text)
    task_type = Column(String, default="planning")  # planning, research, coding, review, execution, coordination
    priority = Column(String, default="medium")  # low, medium, high, critical
    assigned_to = Column(String, default="main_agent")  # main_agent, sub_agent, tool, external_service
    sub_agent_role = Column(String, nullable=True)  # Role name if assigned to sub-agent
    status = Column(String, default="created")  # created, planned, assigned, in_progress, paused, completed, failed, cancelled
    estimated_duration = Column(Integer, nullable=True)  # Estimated completion time in seconds
    actual_duration = Column(Integer, nullable=True)  # Actual time taken in seconds
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dependencies = Column(JSON, default=[])  # List of task IDs this task depends on
    result = Column(Text, nullable=True)  # Result/output of the task
    error_message = Column(Text, nullable=True)  # Error details if task failed