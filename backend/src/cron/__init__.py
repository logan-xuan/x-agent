"""APScheduler 4.0 integration for X-Agent.

This module provides a complete cron scheduling system using APScheduler 4.0.
All code is isolated in this directory for maintainability.

Example usage:
    from cron import get_scheduler
    
    scheduler = get_scheduler()
    await scheduler.start()
"""

from .scheduler import get_scheduler, CronScheduler
from .config import CronConfig, JobConfig
from .retry import (
    BackoffStrategy,
    JobStatus,
    RetryPolicy,
    JobExecutionRecord,
    RetryState,
)
from .chain import (
    ChainCondition,
    JobChainStep,
    JobChain,
    ChainExecutionState,
)
from .execution_mode import (
    ExecutionMode,
    ExecutionModeConfig,
    DEFAULT_LIGHT_CONFIG,
    DEFAULT_STANDARD_CONFIG,
    DEFAULT_FUNCTION_CONFIG,
)

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
