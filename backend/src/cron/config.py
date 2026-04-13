"""APScheduler configuration models."""

from typing import Any, Literal

from pydantic import BaseModel, Field

# Define TriggerType as a Literal type
TriggerType = Literal["interval", "cron", "date"]


class JobConfig(BaseModel):
    """Configuration for a scheduled job."""

    id: str = Field(..., description="Unique job identifier")
    func: str = Field(..., description="Function to execute")
    trigger_type: TriggerType = Field(..., description="Trigger type")
    trigger_args: dict[str, Any] = Field(..., description="Trigger arguments")
    coalesce: str = Field(default="latest", description="Coalesce policy")
    conflict_policy: str = Field(default="replace", description="Conflict policy")
    enabled: bool = Field(default=True, description="Whether the job is enabled")
    max_running_jobs: int = Field(default=1, description="Maximum number of running jobs")
    misfire_grace_time: int = Field(default=3600, description="Misfire grace time in seconds")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class CronConfig(BaseModel):
    """APScheduler configuration."""

    enabled: bool = Field(default=True, description="Enable scheduler")
    timezone: str = Field(default="Asia/Shanghai", description="Scheduler timezone")
    job_store_url: str | None = Field(
        default=None, description="Job store database URL (None for memory store)"
    )
    max_workers: int = Field(default=10, ge=1, description="Max worker threads")
    cleanup_interval: int = Field(default=3600, ge=60, description="Cleanup interval in seconds")
    task_defaults: dict[str, Any] = Field(
        default_factory=lambda: {
            "misfire_grace_time": 3600,
            "max_running_jobs": 1,
        }
    )
    jobs: list[JobConfig] = Field(default_factory=list, description="Predefined jobs")
