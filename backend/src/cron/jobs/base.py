"""Base class for cron jobs."""

from abc import ABC, abstractmethod
from typing import Any

from apscheduler import current_job

from ...utils.logger import get_logger

# Logger for all cron jobs
job_logger = get_logger("cron.jobs")


class BaseJob(ABC):
    """Base class for all scheduled jobs.
    
    Provides:
    - Structured logging
    - Error handling
    - Execution tracking
    - Access to job context
    """
    
    def __init__(self, job_id: str, name: str) -> None:
        self.job_id = job_id
        self.name = name
        self.logger = get_logger(f"cron.jobs.{job_id}")
    
    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the job with logging and error handling.
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Job result
        """
        # Get current job context if available
        job_info = current_job.get(None)
        job_id = job_info.id if job_info else self.job_id
        
        self.logger.info(
            "Job started",
            extra={
                "job_id": job_id,
                "name": self.name,
                "args": args,
                "kwargs": list(kwargs.keys()),
            }
        )
        
        try:
            result = await self._run(*args, **kwargs)
            
            self.logger.info(
                "Job completed",
                extra={
                    "job_id": job_id,
                    "name": self.name,
                    "result_type": type(result).__name__,
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Job failed",
                extra={
                    "job_id": job_id,
                    "name": self.name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            raise
    
    @abstractmethod
    async def _run(self, *args: Any, **kwargs: Any) -> Any:
        """Actual job implementation.
        
        Override this method in subclasses.
        
        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Job result
        """
        pass
    
    def get_job_info(self) -> dict[str, Any]:
        """Get job information."""
        job_info = current_job.get(None)
        if job_info:
            return {
                "job_id": job_info.id,
                "task_id": job_info.task_id,
                "schedule_id": job_info.schedule_id,
                "scheduled_time": job_info.scheduled_time.isoformat() if job_info.scheduled_time else None,
                "started_at": job_info.started_at.isoformat() if job_info.started_at else None,
            }
        return {}
