"""APScheduler 4.0 integration for X-Agent.

This module provides a complete cron scheduling system using APScheduler 4.0.
All code is isolated in this directory for maintainability.

Example usage:
    from cron import get_scheduler

    scheduler = get_scheduler()
    await scheduler.start()
"""

from .chain import (
    ChainCondition,
    ChainExecutionState,
    JobChain,
    JobChainStep,
)
from .config import CronConfig, JobConfig
from .execution_mode import (
    DEFAULT_FUNCTION_CONFIG,
    DEFAULT_LIGHT_CONFIG,
    DEFAULT_STANDARD_CONFIG,
    ExecutionMode,
    ExecutionModeConfig,
)
from .retry import (
    BackoffStrategy,
    JobExecutionRecord,
    JobStatus,
    RetryPolicy,
    RetryState,
)
from .scheduler import CronScheduler, get_scheduler

__all__ = [
    # Core scheduler
    "get_scheduler",
    "CronScheduler",
    "CronConfig",
    "JobConfig",
    # Retry
    "BackoffStrategy",
    "JobStatus",
    "RetryPolicy",
    "JobExecutionRecord",
    "RetryState",
    # Chain
    "ChainCondition",
    "JobChainStep",
    "JobChain",
    "ChainExecutionState",
    # Execution Mode
    "ExecutionMode",
    "ExecutionModeConfig",
    "DEFAULT_LIGHT_CONFIG",
    "DEFAULT_STANDARD_CONFIG",
    "DEFAULT_FUNCTION_CONFIG",
]
