from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from enum import Enum
import uuid
from datetime import datetime

Base = declarative_base()


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)  # Name of the scheduled task
    description = Column(Text)  # Description of what the task does
    cron_expression = Column(String(255), nullable=False)  # Cron expression defining schedule
    task_type = Column(String(255), nullable=False)  # Type of task to execute (e.g., "data_cleanup", "report_generation")
    task_params = Column(Text, nullable=True)  # Parameters to pass to the task when executed (JSON serialized)
    enabled = Column(Boolean, default=True)  # Whether the task is currently active
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_run_at = Column(DateTime(timezone=True), nullable=True)  # Timestamp of the last execution
    last_run_status = Column(SQLEnum(TaskStatus), nullable=True)  # Status of the last execution
    next_run_at = Column(DateTime(timezone=True), nullable=True)  # When the task is scheduled to run next
    max_retries = Column(Integer, default=3)  # Maximum number of retries for failed tasks
    retry_count = Column(Integer, default=0)  # Current retry count

    def __repr__(self):
        return f"<ScheduledTask(id='{self.id}', name='{self.name}', status='{self.last_run_status.value if self.last_run_status else None}')>"