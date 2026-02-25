"""Plan Mode Monitor - Optimized Version (Standalone).

优化内容:
1. 反思次数增加：3 → 5 (+67%)
2. 超时时间增加：60s → 120s (+100%)  
3. 渐进式重试机制
4. 错误模式追踪
5. 增强的用户指引
"""

from dataclasses import dataclass, field
from enum import Enum
import time


class PlanModeStatus(Enum):
    """Plan Mode execution status."""
    RUNNING = "running"
    COMPLETED = "completed"
    ABORT_NO_PROGRESS = "abort_no_progress"
    ABORT_TIME_LIMIT = "abort_time_limit"
    RETRY_WITH_NEW_STRATEGY = "retry_with_new_strategy"


@dataclass
class PlanModeMetrics:
    """Metrics for tracking Plan Mode execution."""
    start_time: float = field(default_factory=time.time)
    reflection_count: int = 0
    failed_attempts: int = 0
    same_step_iterations: int = 0
    last_step: int = 0
    tool_patterns: list = field(default_factory=list)
    
    # ✅ OPTIMIZED: Increased limits
    max_reflections: int = 5  # Was 3
    max_same_step_iterations: int = 5
    max_execution_time_seconds: int = 120  # Was 60
    
    # 🔥 NEW: Progressive retry
    retry_with_new_strategy: int = 0
    last_error_type: str = ""
    consecutive_different_errors: int = 0
    max_strategy_retries: int = 2
    
    def reset_for_step(self, step: int):
        """Reset counters when step changes."""
        if step != self.last_step:
            self.same_step_iterations = 0
            self.failed_attempts = 0
            self.last_step = step
    
    def record_error_pattern(self, error_type: str):
        """Track error patterns."""
        if error_type != self.last_error_type:
            self.consecutive_different_errors += 1
            self.last_error_type = error_type
        else:
            self.consecutive_different_errors = 0
        
        if self.consecutive_different_errors >= 3:
            self.retry_with_new_strategy += 1
            self.consecutive_different_errors = 0


class PlanModeMonitor:
    """Optimized monitor with progressive retry."""
    
    def __init__(
        self,
        max_reflections: int = 5,
        max_same_step_iterations: int = 5,
        max_execution_time_seconds: int = 120,
        max_strategy_retries: int = 2,
    ):
        self.metrics = PlanModeMetrics(
            max_reflections=max_reflections,
            max_same_step_iterations=max_same_step_iterations,
            max_execution_time_seconds=max_execution_time_seconds,
            max_strategy_retries=max_strategy_retries,
        )
    
    def record_reflection(self, plan_state: any, error_type: str = "") -> PlanModeStatus:
        """Record reflection and check status."""
        self.metrics.reflection_count += 1
        
        if error_type:
            self.metrics.record_error_pattern(error_type)
        
        # Check strategy retry
        if (self.metrics.retry_with_new_strategy > 0 and 
            self.metrics.retry_with_new_strategy <= self.metrics.max_strategy_retries):
            return PlanModeStatus.RETRY_WITH_NEW_STRATEGY
        
        # Check max reflections
        if self.metrics.reflection_count >= self.metrics.max_reflections:
            return PlanModeStatus.ABORT_NO_PROGRESS
        
        # Check stuck on step
        current_step = getattr(plan_state, 'current_step', 0)
        if current_step == self.metrics.last_step:
            self.metrics.same_step_iterations += 1
            self.metrics.failed_attempts += 1
            
            if self.metrics.same_step_iterations >= self.metrics.max_same_step_iterations:
                return PlanModeStatus.ABORT_NO_PROGRESS
        else:
            self.metrics.reset_for_step(current_step)
        
        # Check timeout
        elapsed = time.time() - self.metrics.start_time
        if elapsed >= self.metrics.max_execution_time_seconds:
            return PlanModeStatus.ABORT_TIME_LIMIT
        
        return PlanModeStatus.RUNNING
    
    def record_tool_call(self, tool_name: str, success: bool, error_type: str = ""):
        """Record tool call."""
        self.metrics.tool_patterns.append({
            "tool": tool_name,
            "success": success,
            "error_type": error_type if not success else "",
        })
        
        if not success:
            self.metrics.failed_attempts += 1
            if error_type:
                self.metrics.record_error_pattern(error_type)
    
    def get_status_report(self) -> dict:
        """Get status report."""
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
        }
    
    def create_abort_message(self, status: PlanModeStatus) -> str:
        """Create enhanced abort message."""
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
                f"**建议操作**:\n"
                f"1. ✅ 检查脚本和工具是否存在\n"
                f"2. ✅ 简化任务为更小子任务\n"
                f"3. ✅ 提供更多上下文或示例\n"
                f"4. 🆘 需要人工介入"
            )
        
        elif status == PlanModeStatus.ABORT_TIME_LIMIT:
            return (
                f"⏱️ **计划执行中止 - 超时**\n\n"
                f"- 耗时：{report['elapsed_seconds']} 秒（上限：{self.metrics.max_execution_time_seconds}）\n"
                f"- 工具调用：{report['tool_calls']} 次\n\n"
                f"**建议**: 简化任务或分多个请求完成"
            )
        
        elif status == PlanModeStatus.RETRY_WITH_NEW_STRATEGY:
            return (
                f"🔄 **正在尝试新策略** ({report['strategy_retries']}/{self.metrics.max_strategy_retries})\n\n"
                f"系统正在尝试完全不同的方法..."
            )
        
        return f"⚠️ **计划执行中止**\n状态：{status.value}"


# Quick test
if __name__ == "__main__":
    print("Testing Optimized Plan Monitor...\n")
    
    monitor = PlanModeMonitor()
    
    class MockState:
        current_step = 1
    
    state = MockState()
    
    print(f"Initial limits:")
    print(f"  Max reflections: {monitor.metrics.max_reflections} ✓")
    print(f"  Max time: {monitor.metrics.max_execution_time_seconds}s ✓")
    print(f"  Max strategy retries: {monitor.metrics.max_strategy_retries} ✓\n")
    
    # Simulate reflections
    for i in range(6):
        status = monitor.record_reflection(state, f"error_{i}")
        print(f"Reflection {i+1}: {status.value}")
        
        if status == PlanModeStatus.ABORT_NO_PROGRESS:
            print(f"\n{monitor.create_abort_message(status)}")
            break
    
    print("\n✅ Test completed!")
