"""Plan Mode Monitor - Self-Healing Version.

核心能力:
1. 多层重试机制 (Retry Layers)
2. 动态反思触发 (Dynamic Reflection)
3. 智能重规划 (Intelligent Replanning)
4. 错误模式学习 (Error Pattern Learning)
5. 渐进式降级 (Progressive Degradation)
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Optional, Dict, List


class PlanModeStatus(Enum):
    """Enhanced status with self-healing capabilities."""
    RUNNING = "running"
    COMPLETED = "completed"
    
    # Retry states
    RETRY_SAME_STEP = "retry_same_step"  # 同一步骤重试
    RETRY_WITH_ADJUSTMENT = "retry_with_adjustment"  # 调整后重试
    RETRY_WITH_NEW_STRATEGY = "retry_with_new_strategy"  # 新策略重试
    REPLAN_REQUESTED = "replan_requested"  # 请求重规划
    
    # Abort states
    ABORT_NO_PROGRESS = "abort_no_progress"
    ABORT_TIME_LIMIT = "abort_time_limit"
    ABORT_MAX_RETRIES_EXCEEDED = "abort_max_retries_exceeded"


@dataclass
class RetryConfig:
    """Retry configuration for different scenarios."""
    max_same_step_retries: int = 3  # 同一步骤最大重试
    max_strategy_changes: int = 2  # 策略调整次数
    max_replans: int = 1  # 重规划次数
    base_delay_seconds: float = 0.5  # 基础延迟
    exponential_backoff: bool = True  # 指数退避
    
    # Dynamic thresholds
    reflection_trigger_failures: int = 2  # 触发反思的失败次数
    replan_trigger_failures: int = 5  # 触发重规划的失败次数


@dataclass 
class PlanModeMetrics:
    """Enhanced metrics for self-healing."""
    start_time: float = field(default_factory=time.time)
    
    # Basic counters
    reflection_count: int = 0
    failed_attempts: int = 0
    same_step_iterations: int = 0
    last_step: int = 0
    tool_patterns: list = field(default_factory=list)
    
    # Self-healing tracking
    retry_count: int = 0
    strategy_change_count: int = 0
    replan_count: int = 0
    last_error_type: str = ""
    error_history: List[Dict] = field(default_factory=list)
    
    # Configuration
    config: RetryConfig = field(default_factory=RetryConfig)
    
    # Limits (can be loaded from config)
    max_reflections: int = 8  # Increased for self-healing
    max_execution_time_seconds: int = 300  # 5 minutes
    max_total_retries: int = 10
    
    def get_retry_delay(self) -> float:
        """Calculate delay before next retry with exponential backoff."""
        if self.config.exponential_backoff:
            return self.config.base_delay_seconds * (2 ** self.retry_count)
        return self.config.base_delay_seconds
    
    def record_error(self, error_type: str, step: int, tool: str = ""):
        """Record error for pattern learning."""
        error_record = {
            "type": error_type,
            "step": step,
            "tool": tool,
            "timestamp": time.time(),
            "retry_count": self.retry_count,
        }
        self.error_history.append(error_record)
        
        # Keep only recent errors (last 10)
        if len(self.error_history) > 10:
            self.error_history = self.error_history[-10:]
        
        self.last_error_type = error_type
        
        # Detect patterns
        if len(self.error_history) >= 3:
            recent_errors = [e["type"] for e in self.error_history[-3:]]
            if len(set(recent_errors)) == 1:
                # Same error 3 times - need strategy change
                self.strategy_change_count += 1
    
    def should_trigger_reflection(self) -> bool:
        """Check if reflection should be triggered."""
        recent_failures = sum(1 for e in self.error_history[-self.config.reflection_trigger_failures:])
        return recent_failures >= self.config.reflection_trigger_failures
    
    def should_trigger_replan(self) -> bool:
        """Check if replanning should be triggered."""
        return (self.failed_attempts >= self.config.replan_trigger_failures or
                self.strategy_change_count >= self.config.max_strategy_changes)
    
    def can_retry(self) -> bool:
        """Check if retry is still allowed."""
        return (self.retry_count < self.config.max_same_step_retries and
                self.replan_count <= self.config.max_replans and
                self.strategy_change_count <= self.config.max_strategy_changes)
    
    def reset_for_step(self, step: int):
        """Reset counters when step changes."""
        if step != self.last_step:
            self.same_step_iterations = 0
            self.failed_attempts = 0
            self.last_step = step
            # Don't reset retry count on step change to allow cross-step learning


class SelfHealingMonitor:
    """Self-healing monitor with dynamic replanning capability."""
    
    def __init__(
        self,
        max_reflections: int = 8,
        max_execution_time_seconds: int = 300,
        max_total_retries: int = 10,
        enable_replanning: bool = True,
    ):
        self.metrics = PlanModeMetrics(
            max_reflections=max_reflections,
            max_execution_time_seconds=max_execution_time_seconds,
            max_total_retries=max_total_retries,
        )
        self.enable_replanning = enable_replanning
        self._last_adjustment_reason = ""
    
    def record_reflection(
        self, 
        plan_state: any,
        error_type: str = "",
        tool_name: str = "",
    ) -> PlanModeStatus:
        """Record reflection and determine next action with self-healing logic."""
        
        self.metrics.reflection_count += 1
        
        # Record error for pattern learning
        if error_type:
            current_step = getattr(plan_state, 'current_step', 0)
            self.metrics.record_error(error_type, current_step, tool_name)
        
        # Check execution time
        elapsed = time.time() - self.metrics.start_time
        if elapsed >= self.metrics.max_execution_time_seconds:
            return PlanModeStatus.ABORT_TIME_LIMIT
        
        # Check if we've exceeded total retries
        if self.metrics.retry_count >= self.metrics.max_total_retries:
            return PlanModeStatus.ABORT_MAX_RETRIES_EXCEEDED
        
        # Check if replanning is needed
        if self.enable_replanning and self.metrics.should_trigger_replan():
            if self.metrics.replan_count < self.metrics.config.max_replans:
                self.metrics.replan_count += 1
                self._last_adjustment_reason = f"Triggered replan due to {self.metrics.failed_attempts} failures"
                return PlanModeStatus.REPLAN_REQUESTED
        
        # Check if strategy change is needed
        if self.metrics.strategy_change_count > 0 and \
           self.metrics.strategy_change_count <= self.metrics.config.max_strategy_changes:
            return PlanModeStatus.RETRY_WITH_NEW_STRATEGY
        
        # Check if simple retry is allowed
        if self.metrics.can_retry():
            self.metrics.retry_count += 1
            return PlanModeStatus.RETRY_SAME_STEP
        
        # If all retries exhausted, abort
        if self.metrics.reflection_count >= self.metrics.max_reflections:
            return PlanModeStatus.ABORT_NO_PROGRESS
        
        return PlanModeStatus.RUNNING
    
    def record_tool_call(
        self, 
        tool_name: str, 
        success: bool, 
        error_type: str = "",
        output_preview: str = "",
    ):
        """Record tool call with detailed context for learning."""
        
        self.metrics.tool_patterns.append({
            "tool": tool_name,
            "success": success,
            "error_type": error_type if not success else "",
            "output_preview": output_preview[:100] if output_preview else "",
            "timestamp": time.time(),
        })
        
        if not success:
            self.metrics.failed_attempts += 1
            current_step = getattr(self, '_current_step', 0)
            self.metrics.record_error(error_type or "unknown", current_step, tool_name)
    
    def get_healing_suggestion(self) -> Dict:
        """Get intelligent healing suggestion based on error patterns."""
        
        suggestions = {
            "action": "continue",
            "reason": "",
            "specific_steps": [],
            "alternative_approaches": [],
        }
        
        # Analyze error patterns
        if len(self.metrics.error_history) >= 3:
            recent_errors = [e["type"] for e in self.metrics.error_history[-3:]]
            
            # Pattern 1: Same error repeated
            if len(set(recent_errors)) == 1:
                suggestions["action"] = "change_strategy"
                suggestions["reason"] = f"同一错误重复出现：{recent_errors[0]}"
                suggestions["specific_steps"] = [
                    "停止当前方法",
                    "尝试完全不同的思路",
                    "检查是否有更简单的替代方案",
                ]
            
            # Pattern 2: Different errors but all failures
            elif len(set(recent_errors)) == 3:
                suggestions["action"] = "simplify_task"
                suggestions["reason"] = "多种不同错误，当前任务可能过于复杂"
                suggestions["specific_steps"] = [
                    "将任务分解为更小的子任务",
                    "优先完成核心功能",
                    "移除不必要的依赖",
                ]
        
        # Check if replanning might help
        if self.metrics.failed_attempts >= 5:
            suggestions["action"] = "replan"
            suggestions["reason"] = "多次失败后需要重新规划"
            suggestions["alternative_approaches"] = [
                "从不同角度分析问题",
                "使用不同的工具组合",
                "参考类似任务的成功案例",
            ]
        
        return suggestions
    
    def get_status_report(self) -> Dict:
        """Get comprehensive status report."""
        elapsed = time.time() - self.metrics.start_time
        
        return {
            "reflection_count": self.metrics.reflection_count,
            "failed_attempts": self.metrics.failed_attempts,
            "retry_count": self.metrics.retry_count,
            "strategy_changes": self.metrics.strategy_change_count,
            "replans": self.metrics.replan_count,
            "current_step": self.metrics.last_step,
            "elapsed_seconds": round(elapsed, 2),
            "tool_calls": len(self.metrics.tool_patterns),
            "error_diversity": len(set(e["type"] for e in self.metrics.error_history)),
            "can_continue": self.metrics.can_retry(),
            "next_retry_delay": self.metrics.get_retry_delay(),
        }
    
    def create_enhanced_abort_message(self, status: PlanModeStatus) -> str:
        """Create enhanced abort message with self-healing insights."""
        
        report = self.get_status_report()
        suggestion = self.get_healing_suggestion()
        
        if status == PlanModeStatus.ABORT_NO_PROGRESS:
            return (
                f"🚨 **计划执行中止 - 自我修复机制已耗尽**\n\n"
                f"**执行情况**:\n"
                f"- 反思次数：{report['reflection_count']} 次（上限：{self.metrics.max_reflections}）\n"
                f"- 失败尝试：{report['failed_attempts']} 次\n"
                f"- 策略调整：{report['strategy_changes']} 次\n"
                f"- 重规划：{report['replans']} 次\n"
                f"- 总重试：{report['retry_count']} 次（上限：{self.metrics.max_total_retries}）\n"
                f"- 当前步骤：Step {report['current_step']}\n"
                f"- 耗时：{report['elapsed_seconds']} 秒\n\n"
                f"**错误模式分析**:\n"
                f"- 不同错误类型：{report['error_diversity']} 种\n"
                f"- 最近错误：{self.metrics.last_error_type}\n\n"
                f"**AI 建议**:\n"
                f"{suggestion['reason']}\n\n"
                f"**建议操作步骤**:\n"
                f"{' '.join([f'{i+1}. {step}' for i, step in enumerate(suggestion['specific_steps'])])}\n\n"
                f"🆘 **需要人工介入**: 系统已尝试所有自我修复方法但仍无法完成"
            )
        
        elif status == PlanModeStatus.ABORT_TIME_LIMIT:
            return (
                f"⏱️ **计划执行中止 - 超时**\n\n"
                f"- 耗时：{report['elapsed_seconds']} 秒（上限：{self.metrics.max_execution_time_seconds}）\n"
                f"- 工具调用：{report['tool_calls']} 次\n"
                f"- 完成率：计算中...\n\n"
                f"**建议**: 任务过于复杂，请分解为多个小任务或简化目标"
            )
        
        elif status == PlanModeStatus.REPLAN_REQUESTED:
            return (
                f"🔄 **触发重规划** (第 {report['replans']} 次)\n\n"
                f"**原因**: {self._last_adjustment_reason}\n\n"
                f"**下一步**: 系统将重新生成计划，尝试不同的方法..."
            )
        
        return f"⚠️ **执行异常**\n状态：{status.value}\n报告：{report}"
    
    def set_current_step(self, step: int):
        """Helper to track current step for error recording."""
        self._current_step = step


# Quick demonstration
if __name__ == "__main__":
    print("=" * 80)
    print("Self-Healing Monitor Demonstration")
    print("=" * 80)
    
    monitor = SelfHealingMonitor(
        max_reflections=8,
        max_execution_time_seconds=300,
        max_total_retries=10,
    )
    
    class MockState:
        current_step = 1
    
    state = MockState()
    
    print("\n📊 Initial Configuration:")
    print(f"  Max reflections: {monitor.metrics.max_reflections}")
    print(f"  Max execution time: {monitor.metrics.max_execution_time_seconds}s")
    print(f"  Max total retries: {monitor.metrics.max_total_retries}")
    print(f"  Max replans: {monitor.metrics.config.max_replans}")
    
    print("\n🔬 Simulating execution with failures...")
    
    # Simulate various errors
    errors = [
        ("tool_not_found", "run_in_terminal"),
        ("permission_denied", "write_file"),
        ("invalid_parameter", "run_in_terminal"),
        ("tool_not_found", "run_in_terminal"),  # Repeat
        ("timeout", "web_search"),
        ("permission_denied", "write_file"),  # Repeat
    ]
    
    for i, (error_type, tool) in enumerate(errors, 1):
        status = monitor.record_reflection(state, error_type, tool)
        monitor.record_tool_call(tool, False, error_type)
        
        print(f"\nIteration {i}:")
        print(f"  Error: {error_type} ({tool})")
        print(f"  Status: {status.value}")
        
        if status in [PlanModeStatus.REPLAN_REQUESTED, 
                      PlanModeStatus.RETRY_WITH_NEW_STRATEGY]:
            print(f"  🔄 {monitor.create_enhanced_abort_message(status)[:200]}")
        
        if status in [PlanModeStatus.ABORT_NO_PROGRESS, 
                      PlanModeStatus.ABORT_TIME_LIMIT,
                      PlanModeStatus.ABORT_MAX_RETRIES_EXCEEDED]:
            print(f"\n{monitor.create_enhanced_abort_message(status)}")
            break
    
    print("\n" + "=" * 80)
    print("✅ Demonstration completed!")
    print("=" * 80)
