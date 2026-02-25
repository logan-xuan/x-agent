"""Plan Mode Monitor for emergency braking.

This module provides monitoring and emergency braking capabilities
for Plan Mode execution to prevent infinite loops and wasted iterations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

from .plan_context import PlanState


class PlanModeStatus(Enum):
    """Plan Mode execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    ABORT_USER_HELP = "abort_user_help"  # Need user assistance
    ABORT_NO_PROGRESS = "abort_no_progress"  # No progress after multiple reflections
    ABORT_TIME_LIMIT = "abort_time_limit"  # Exceeded time limit


@dataclass
class PlanModeMetrics:
    """Metrics for tracking Plan Mode execution."""
    start_time: float = field(default_factory=time.time)
    reflection_count: int = 0
    failed_attempts: int = 0
    same_step_iterations: int = 0
    last_step: int = 0
    tool_patterns: list = field(default_factory=list)
    max_reflections: int = 3
    max_same_step_iterations: int = 5
    max_execution_time_seconds: int = 60  # 1 minute timeout
    
    def reset_for_step(self, step: int):
        """Reset counters when step changes."""
        if step != self.last_step:
            self.same_step_iterations = 0
            self.failed_attempts = 0
            self.last_step = step


class PlanModeMonitor:
    """Monitor for Plan Mode execution with emergency braking.
    
    This monitor tracks:
    - Number of reflections
    - Failed attempts on same step
    - Time spent on current step
    - Tool repetition patterns
    
    It can trigger emergency braking when:
    - Too many reflections without progress
    - Stuck on same step for too long
    - Execution time exceeds limit
    """
    
    def __init__(
        self,
        max_reflections: int = 3,
        max_same_step_iterations: int = 5,
        max_execution_time_seconds: int = 60,
    ):
        """Initialize the monitor.
        
        Args:
            max_reflections: Maximum reflections before aborting
            max_same_step_iterations: Maximum iterations on same step
            max_execution_time_seconds: Maximum execution time in seconds
        """
        self.metrics = PlanModeMetrics(
            max_reflections=max_reflections,
            max_same_step_iterations=max_same_step_iterations,
            max_execution_time_seconds=max_execution_time_seconds,
        )
    
    def record_reflection(self, plan_state: PlanState) -> PlanModeStatus:
        """Record a reflection event and check if we should abort.
        
        Args:
            plan_state: Current plan state
            
        Returns:
            PlanModeStatus indicating whether to continue or abort
        """
        self.metrics.reflection_count += 1
        
        # Check if we've exceeded max reflections
        if self.metrics.reflection_count >= self.metrics.max_reflections:
            return PlanModeStatus.ABORT_NO_PROGRESS
        
        # Check if we're stuck on the same step
        current_step = plan_state.current_step
        if current_step == self.metrics.last_step:
            self.metrics.same_step_iterations += 1
            self.metrics.failed_attempts += 1
            
            if self.metrics.same_step_iterations >= self.metrics.max_same_step_iterations:
                return PlanModeStatus.ABORT_NO_PROGRESS
        else:
            # Step changed, reset counters
            self.metrics.reset_for_step(current_step)
        
        # Check execution time
        elapsed = time.time() - self.metrics.start_time
        if elapsed >= self.metrics.max_execution_time_seconds:
            return PlanModeStatus.ABORT_TIME_LIMIT
        
        return PlanModeStatus.RUNNING
    
    def record_tool_call(self, tool_name: str, success: bool):
        """Record a tool call for pattern detection.
        
        Args:
            tool_name: Name of the tool called
            success: Whether the tool call was successful
        """
        self.metrics.tool_patterns.append({
            "tool": tool_name,
            "success": success,
            "timestamp": time.time(),
        })
        
        # Track failed attempts
        if not success:
            self.metrics.failed_attempts += 1
    
    def get_status_report(self) -> dict:
        """Get a status report of the current execution.
        
        Returns:
            Dictionary with current metrics
        """
        elapsed = time.time() - self.metrics.start_time
        return {
            "reflection_count": self.metrics.reflection_count,
            "failed_attempts": self.metrics.failed_attempts,
            "same_step_iterations": self.metrics.same_step_iterations,
            "current_step": self.metrics.last_step,
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": len(self.metrics.tool_patterns),
            "status": self._determine_status(),
        }
    
    def _determine_status(self) -> str:
        """Determine current status based on metrics."""
        if self.metrics.reflection_count >= self.metrics.max_reflections:
            return "critical_reflections"
        elif self.metrics.same_step_iterations >= self.metrics.max_same_step_iterations:
            return "stuck_on_step"
        elif (time.time() - self.metrics.start_time) >= self.metrics.max_execution_time_seconds:
            return "time_limit_exceeded"
        elif self.metrics.failed_attempts > 3:
            return "high_failure_rate"
        else:
            return "normal"
    
    def create_abort_message(self, status: PlanModeStatus) -> str:
        """Create a user-friendly abort message.
        
        Args:
            status: The abort status type
            
        Returns:
            Formatted message explaining why execution was aborted
        """
        report = self.get_status_report()
        
        if status == PlanModeStatus.ABORT_NO_PROGRESS:
            return (
                f"🚨 **计划执行中止 - 多次反思后仍无进展**\n\n"
                f"**执行情况**:\n"
                f"- 反思次数：{report['reflection_count']} 次（上限：{self.metrics.max_reflections}）\n"
                f"- 失败尝试：{report['failed_attempts']} 次\n"
                f"- 当前步骤：Step {report['current_step']}\n"
                f"- 耗时：{report['elapsed_seconds']} 秒\n\n"
                f"**可能原因**:\n"
                f"1. 当前方法根本不可行\n"
                f"2. 缺少必要的依赖或资源\n"
                f"3. 任务复杂度超出当前能力\n\n"
                f"**建议操作**:\n"
                f"1. ✅ 检查相关脚本和工具是否存在\n"
                f"2. ✅ 简化任务要求或分解为更小步骤\n"
                f"3. ✅ 提供更多上下文信息或示例\n"
                f"4. 🆘 需要人工介入协助"
            )
        
        elif status == PlanModeStatus.ABORT_TIME_LIMIT:
            return (
                f"⏱️ **计划执行中止 - 超时**\n\n"
                f"**执行情况**:\n"
                f"- 耗时：{report['elapsed_seconds']} 秒（上限：{self.metrics.max_execution_time_seconds}）\n"
                f"- 工具调用：{report['tool_calls']} 次\n"
                f"- 当前步骤：Step {report['current_step']}\n\n"
                f"**可能原因**:\n"
                f"1. 任务过于复杂\n"
                f"2. 工具执行效率低\n"
                f"3. 陷入循环或死锁\n\n"
                f"**建议操作**:\n"
                f"1. ✅ 简化任务描述\n"
                f"2. ✅ 分多个请求完成\n"
                f"3. ✅ 检查是否有无限循环"
            )
        
        else:
            return (
                f"⚠️ **计划执行中止**\n\n"
                f"**状态**: {status.value}\n"
                f"**报告**: {report}\n\n"
                f"请检查任务配置和执行环境。"
            )
