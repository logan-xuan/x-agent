"""Retry policy and job execution status for Cron scheduler.

This module provides retry mechanisms with configurable backoff strategies
and job execution status tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class BackoffStrategy(str, Enum):
    """Backoff strategy for retry delays."""
    FIXED = "fixed"           # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"         # 线性递增


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"  # 超过重试次数


@dataclass
class RetryPolicy:
    """Retry policy configuration.
    
    Attributes:
        max_retries: Maximum number of retry attempts
        backoff_strategy: Strategy for calculating delay between retries
        initial_delay_seconds: Initial delay for first retry
        max_delay_seconds: Maximum delay cap (default 5 minutes)
        retry_on_exceptions: List of exception type names to retry on
    """
    max_retries: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0  # 最大退避 5 分钟
    retry_on_exceptions: list[str] = field(default_factory=lambda: ["Exception"])
    
    def get_delay(self, attempt: int) -> float:
        """根据策略计算第 N 次重试的延迟。
        
        Args:
            attempt: Retry attempt number (1-based)
            
        Returns:
            Delay in seconds
        """
        if self.backoff_strategy == BackoffStrategy.FIXED:
            delay = self.initial_delay_seconds
        elif self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.initial_delay_seconds * (2 ** (attempt - 1))
        else:  # LINEAR
            delay = self.initial_delay_seconds * attempt
        return min(delay, self.max_delay_seconds)
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if the exception should trigger a retry.
        
        Args:
            exception: The exception that occurred
            attempt: Current attempt number
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.max_retries:
            return False
        
        exception_type = type(exception).__name__
        
        # Check if exception type matches any in retry_on_exceptions
        for retry_exception in self.retry_on_exceptions:
            if retry_exception == "Exception" or exception_type == retry_exception:
                return True
        
        return False


@dataclass
class JobExecutionRecord:
    """单次执行记录。
    
    Attributes:
        job_id: Unique job identifier
        execution_id: Unique execution identifier
        status: Current execution status
        started_at: Execution start time
        completed_at: Execution completion time
        error_message: Error message if failed
        attempt: Current retry attempt number
        result: Execution result data
    """
    job_id: str
    execution_id: str
    status: JobStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    attempt: int = 1
    result: dict[str, Any] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "job_id": self.job_id,
            "execution_id": self.execution_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "attempt": self.attempt,
            "result": self.result,
        }


@dataclass
class RetryState:
    """Internal retry state tracking for a job.
    
    This is used by the scheduler to track retry attempts and schedule
    the next retry.
    """
    job_id: str
    task_id: str
    attempt: int = 0
    last_error: str | None = None
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    
    def increment_attempt(self) -> int:
        """Increment attempt counter and return new value."""
        self.attempt += 1
        self.last_attempt_at = datetime.now()
        return self.attempt
    
    def calculate_next_retry(self) -> datetime:
        """Calculate the next retry time based on policy."""
        delay = self.policy.get_delay(self.attempt)
        from datetime import timedelta
        self.next_retry_at = datetime.now() + timedelta(seconds=delay)
        return self.next_retry_at
