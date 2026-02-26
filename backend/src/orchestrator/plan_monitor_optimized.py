"""Plan Mode Monitor for emergency braking - Optimized Version.

This module provides monitoring and emergency braking capabilities
for Plan Mode execution to prevent infinite loops and wasted iterations.

Optimizations:
1. Progressive retry mechanism with different strategies
2. Better error type tracking to detect patterns
3. More granular abort conditions
4. Enhanced user guidance with specific troubleshooting steps
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class PlanModeStatus(Enum):
    """Plan Mode execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    ABORT_USER_HELP = "abort_user_help"  # Need user assistance
    ABORT_NO_PROGRESS = "abort_no_progress"  # No progress after multiple reflections
    ABORT_TIME_LIMIT = "abort_time_limit"  # Exceeded time limit
    RETRY_WITH_NEW_STRATEGY = "retry_with_new_strategy"  # Try different approach


@dataclass
class PlanModeMetrics:
    """Metrics for tracking Plan Mode execution."""
    start_time: float = field(default_factory=time.time)
    reflection_count: int = 0
    failed_attempts: int = 0
    same_step_iterations: int = 0
    last_step: int = 0
    tool_patterns: list = field(default_factory=list)
    max_reflections: int = 5  # ✅ INCREASED: From 3 to 5 for more retry opportunities
    max_same_step_iterations: int = 5
    max_execution_time_seconds: int = 120  # ✅ INCREASED: From 60 to 120 seconds
    
    # 🔥 NEW: Progressive retry counters
    retry_with_new_strategy: int = 0
    last_error_type: str = ""
    consecutive_different_errors: int = 0
    max_strategy_retries: int = 2  # Max times to try completely new strategy
    
    def reset_for_step(self, step: int):
        """Reset counters when step changes."""
        if step != self.last_step:
            self.same_step_iterations = 0
            self.failed_attempts = 0
            self.last_step = step
            # ✅ OPTIMIZE: Don't reset reflection_count on step change to allow cross-step learning
    
    def record_error_pattern(self, error_type: str):
        """Track error patterns to detect if we're making progress."""
        if error_type != self.last_error_type:
            self.consecutive_different_errors += 1
            self.last_error_type = error_type
        else:
            self.consecutive_different_errors = 0
        
        # If trying different things and failing, might need new strategy
        if self.consecutive_different_errors >= 3:
            self.retry_with_new_strategy += 1
            self.consecutive_different_errors = 0


class PlanModeMonitor:
    """Monitor for Plan Mode execution with progressive retry.
    
    This monitor tracks:
    - Number of reflections
    - Failed attempts on same step
    - Time spent on current step
    - Tool repetition patterns
    - Error type diversity (are we trying different approaches?)
    
    Progressive Retry Strategy:
    1. First failure → Reflect and adjust
    2. Second failure → Try alternative method
    3. Third failure → Suggest simplified approach
    4. Fourth failure → Request user assistance
    """
    
    def __init__(
        self,
        max_reflections: int = 5,  # ✅ INCREASED: Allow more retries
        max_same_step_iterations: int = 5,
        max_execution_time_seconds: int = 120,  # ✅ INCREASED
        max_strategy_retries: int = 2,
    ):
        """Initialize the monitor.
        
        Args:
            max_reflections: Maximum reflections before aborting
            max_same_step_iterations: Maximum iterations on same step
            max_execution_time_seconds: Maximum execution time in seconds
            max_strategy_retries: Maximum times to try completely new strategy
        """
        self.metrics = PlanModeMetrics(
            max_reflections=max_reflections,
            max_same_step_iterations=max_same_step_iterations,
            max_execution_time_seconds=max_execution_time_seconds,
            max_strategy_retries=max_strategy_retries,
        )
    
    def record_reflection(
        self, 
        plan_state: PlanState,
        error_type: str = "",
    ) -> PlanModeStatus:
        """Record a reflection event and check if we should abort or retry.
        
        Args:
            plan_state: Current plan state
            error_type: Type of error that triggered reflection (optional)
            
        Returns:
            PlanModeStatus indicating whether to continue, retry, or abort
        """
        self.metrics.reflection_count += 1
        
        # Track error patterns
        if error_type:
            self.metrics.record_error_pattern(error_type)
        
        # 🔥 NEW: Check if we should try a completely new strategy
        if (self.metrics.retry_with_new_strategy > 0 and 
            self.metrics.retry_with_new_strategy <= self.metrics.max_strategy_retries):
            # We've tried different approaches, give one more chance with new strategy
            return PlanModeStatus.RETRY_WITH_NEW_STRATEGY
        
        # Check if we've exceeded max reflections
        if self.metrics.reflection_count >= self.metrics.max_reflections:
            return PlanModeStatus.ABORT_NO_PROGRESS
        
        # Check if we're stuck on the same step
        current_step = plan_state.current_step
        if current_step == self.metrics.last_step:
            self.metrics.same_step_iterations += 1
            self.metrics.failed_attempts += 1
            
            # 🔥 OPTIMIZED: Different thresholds based on attempt number
            if self.metrics.same_step_iterations == 1:
                # First failure - just reflect
                pass
            elif self.metrics.same_step_iterations == 2:
                # Second failure - suggest alternative
                logger.warning("Second failure on same step, suggesting alternative")
            elif self.metrics.same_step_iterations >= self.metrics.max_same_step_iterations:
                # Multiple failures - abort
                return PlanModeStatus.ABORT_NO_PROGRESS
        else:
            # Step changed, reset counters
            self.metrics.reset_for_step(current_step)
        
        # Check execution time
        elapsed = time.time() - self.metrics.start_time
        if elapsed >= self.metrics.max_execution_time_seconds:
            return PlanModeStatus.ABORT_TIME_LIMIT
        
        return PlanModeStatus.RUNNING
    
    def record_tool_call(self, tool_name: str, success: bool, error_type: str = ""):
        """Record a tool call for pattern detection.
        
        Args:
            tool_name: Name of the tool called
            success: Whether the tool call was successful
            error_type: Type of error if failed (optional)
        """
        self.metrics.tool_patterns.append({
            "tool": tool_name,
            "success": success,
            "timestamp": time.time(),
            "error_type": error_type if not success else "",
        })
        
        # Track failed attempts
        if not success:
            self.metrics.failed_attempts += 1
            if error_type:
                self.metrics.record_error_pattern(error_type)
    
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
            "strategy_retries": self.metrics.retry_with_new_strategy,
            "error_diversity": self.metrics.consecutive_different_errors,
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
        elif self.metrics.retry_with_new_strategy > 0:
            return f"retrying_strategy ({self.metrics.retry_with_new_strategy}/{self.metrics.max_strategy_retries})"
        elif self.metrics.failed_attempts > 3:
            return "high_failure_rate"
        else:
            return "normal"
    
    def create_abort_message(self, status: PlanModeStatus) -> str:
        """Create a user-friendly abort message with detailed troubleshooting guidance.
        
        Args:
            status: The abort status type
            
        Returns:
            Formatted message explaining why execution was aborted
        """
        report = self.get_status_report()
        
        if status == PlanModeStatus.ABORT_NO_PROGRESS:
            return (
                f"🚨 **计划执行中止 - 多次尝试后仍无进展**\n\n"
                f"**执行情况**:\n"
                f"- 反思次数：{report['reflection_count']} 次（上限：{self.metrics.max_reflections}）\n"
                f"- 失败尝试：{report['failed_attempts']} 次\n"
                f"- 当前步骤：Step {report['current_step']}\n"
                f"- 耗时：{report['elapsed_seconds']} 秒\n"
                f"- 策略重试：{report['strategy_retries']} 次\n\n"
                f"**可能原因**:\n"
                f"1. ❌ 当前方法根本不可行\n"
                f"2. ❌ 缺少必要的依赖或资源\n"
                f"3. ❌ 任务复杂度超出当前能力\n"
                f"4. ❌ 工具配置或参数错误\n\n"
                f"**建议操作 **(按优先级排序)\n"
                f"1. ✅ **立即检查**: 确认相关脚本和工具是否存在且可用\n"
                f"   ```bash\n"
                f"   ls -la /path/to/skill/scripts/\n"
                f"   ```\n"
                f"2. ✅ **简化任务**: 将复杂任务分解为更小、更具体的子任务\n"
                f"3. ✅ **提供示例**: 给出类似的 успеш案例或参考实现\n"
                f"4. ✅ **检查权限**: 确认有足够的文件系统或 API 访问权限\n"
                f"5. 🆘 **人工介入**: 如果以上都无效，需要手动调试和协助"
            )
        
        elif status == PlanModeStatus.ABORT_TIME_LIMIT:
            return (
                f"⏱️ **计划执行中止 - 超时**\n\n"
                f"**执行情况**:\n"
                f"- 耗时：{report['elapsed_seconds']} 秒（上限：{self.metrics.max_execution_time_seconds}）\n"
                f"- 工具调用：{report['tool_calls']} 次\n"
                f"- 当前步骤：Step {report['current_step']}\n\n"
                f"**可能原因**:\n"
                f"1. 🐌 任务过于复杂\n"
                f"2. 🔄 工具执行效率低\n"
                f"3. 🔁 陷入循环或死锁\n\n"
                f"**建议操作**:\n"
                f"1. ✅ 简化任务描述，聚焦核心目标\n"
                f"2. ✅ 分多个请求完成，避免一次性处理过多内容\n"
                f"3. ✅ 检查是否有无限循环或重复调用\n"
                f"4. ✅ 考虑使用更高效的工具或算法"
            )
        
        elif status == PlanModeStatus.RETRY_WITH_NEW_STRATEGY:
            return (
                f"🔄 **正在尝试新策略** (第 {report['strategy_retries']} 次)\n\n"
                f"**当前状态**:\n"
                f"- 已反思：{report['reflection_count']} 次\n"
                f"- 失败：{report['failed_attempts']} 次\n"
                f"- 错误多样性：{report['error_diversity']} 种不同错误\n\n"
                f"**下一步**:\n"
                f"系统正在尝试完全不同的方法。如果这次仍然失败，将需要您的协助。"
            )
        
        else:
            return (
                f"⚠️ **计划执行中止**\n\n"
                f"**状态**: {status.value}\n"
                f"**详细报告**: {report}\n\n"
                f"**故障排查步骤**:\n"
                f"1. 检查任务配置和执行环境\n"
                f"2. 查看日志文件了解详细错误信息\n"
                f"3. 验证所有依赖项是否正确安装\n"
                f"4. 如有必要，联系开发团队寻求支持"
            )


# Import logger at module level
try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    # Fallback if import fails
    import logging
    logger = logging.getLogger(__name__)
