"""Job chain support for Cron scheduler.

This module provides task chaining capabilities, allowing jobs to be
linked together with conditional execution based on success/failure.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ChainCondition(str, Enum):
    """Predefined chain conditions."""
    ALWAYS = "always"           # 总是执行下一步
    ON_SUCCESS = "on_success"   # 仅在成功时执行
    ON_FAILURE = "on_failure"   # 仅在失败时执行
    NEVER = "never"             # 从不执行下一步


@dataclass
class JobChainStep:
    """A single step in a job chain.
    
    Attributes:
        job_id: The job ID for this step
        step_id: Unique identifier for this step in the chain
        on_success: Next step_id to execute on success (None = end chain)
        on_failure: Next step_id to execute on failure (None = end chain)
        condition: Custom condition function (overrides on_success/on_failure if set)
        timeout_seconds: Maximum execution time for this step
        retry_count: Number of retries for this step within the chain
    """
    job_id: str
    step_id: str | None = None
    on_success: str | None = None   # 下一步 step_id（成功时）
    on_failure: str | None = None   # 下一步 step_id（失败时）
    condition: Callable[[Any, bool], str | None] | None = None  # 自定义条件函数
    timeout_seconds: float = 300.0  # 默认 5 分钟超时
    retry_count: int = 0  # 链内重试次数（独立于 job 自身的 retry_policy）
    
    def __post_init__(self):
        """Auto-generate step_id if not provided."""
        if self.step_id is None:
            self.step_id = self.job_id
    
    def get_next_step_id(self, result: Any, success: bool) -> str | None:
        """Determine the next step based on execution result.
        
        Args:
            result: The result from the current step execution
            success: Whether the current step succeeded
            
        Returns:
            Next step_id or None to end chain
        """
        # Custom condition function takes precedence
        if self.condition is not None:
            try:
                return self.condition(result, success)
            except Exception:
                # If custom condition fails, fall back to default behavior
                pass
        
        # Use on_success/on_failure
        return self.on_success if success else self.on_failure


@dataclass
class JobChain:
    """A chain of jobs to be executed in sequence.
    
    Attributes:
        chain_id: Unique identifier for this chain
        name: Human-readable name for the chain
        steps: List of steps in the chain
        description: Optional description
        enabled: Whether this chain is enabled
        max_concurrent_runs: Maximum number of concurrent chain executions
        created_at: Creation timestamp
    """
    chain_id: str
    name: str
    steps: list[JobChainStep]
    description: str = ""
    enabled: bool = True
    max_concurrent_runs: int = 1
    created_at: str | None = None
    
    def __post_init__(self):
        """Validate chain configuration."""
        if not self.steps:
            raise ValueError("JobChain must have at least one step")
        
        # Validate step references
        step_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            if step.on_success and step.on_success not in step_ids:
                raise ValueError(f"Step {step.step_id} references unknown on_success: {step.on_success}")
            if step.on_failure and step.on_failure not in step_ids:
                raise ValueError(f"Step {step.step_id} references unknown on_failure: {step.on_failure}")
    
    def get_first_step(self) -> JobChainStep:
        """Get the first step in the chain."""
        return self.steps[0]
    
    def get_step(self, step_id: str) -> JobChainStep | None:
        """Get a step by its ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def get_next_step(self, current_step_id: str, result: Any, success: bool) -> JobChainStep | None:
        """Get the next step based on current step execution result.
        
        Args:
            current_step_id: The current step's ID
            result: Execution result from current step
            success: Whether current step succeeded
            
        Returns:
            Next step or None if chain ends
        """
        current_step = self.get_step(current_step_id)
        if current_step is None:
            return None
        
        next_step_id = current_step.get_next_step_id(result, success)
        if next_step_id is None:
            return None
        
        return self.get_step(next_step_id)
    
    def get_all_job_ids(self) -> list[str]:
        """Get all job IDs in this chain."""
        return [step.job_id for step in self.steps]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert chain to dictionary representation."""
        return {
            "chain_id": self.chain_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "max_concurrent_runs": self.max_concurrent_runs,
            "created_at": self.created_at,
            "steps": [
                {
                    "job_id": step.job_id,
                    "step_id": step.step_id,
                    "on_success": step.on_success,
                    "on_failure": step.on_failure,
                    "timeout_seconds": step.timeout_seconds,
                    "retry_count": step.retry_count,
                }
                for step in self.steps
            ],
        }


@dataclass
class ChainExecutionState:
    """Tracks the execution state of a running chain.
    
    This is used internally by the scheduler to track chain progress.
    """
    chain_id: str
    execution_id: str
    current_step_id: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None
    status: str = "running"  # running, completed, failed, cancelled
    
    def mark_step_complete(self, step_id: str, result: Any) -> None:
        """Mark a step as completed."""
        self.completed_steps.append(step_id)
        self.results[step_id] = result
    
    def mark_step_failed(self, step_id: str, error: str) -> None:
        """Mark a step as failed."""
        self.failed_steps.append(step_id)
        self.results[step_id] = {"error": error}
    
    def move_to_step(self, step_id: str | None) -> None:
        """Move to the next step."""
        self.current_step_id = step_id
    
    def is_complete(self) -> bool:
        """Check if chain execution is complete."""
        return self.status in ("completed", "failed", "cancelled")
