"""Plan context manager for X-Agent.

Manages plan state and builds context to inject into ReAct prompt.
Tracks progress and triggers re-planning when needed.
Adds milestone validation for hybrid scheduling.
"""

from dataclasses import dataclass, field
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PlanState:
    """计划状态
    
    Attributes:
        original_plan: 原始计划文本
        current_step: 当前步骤（1-based）
        total_steps: 总步骤数
        completed_steps: 已完成步骤描述列表
        failed_count: 连续失败次数
        last_adjustment: 上次调整原因
        react_iteration_count: ReAct 迭代次数（由外部 ReAct Loop 传入）
        tool_execution_count: 工具执行次数（内部统计）
        replan_count: 重规划次数（防止无限循环）
        milestones_validated: 已验证的里程碑列表
        structured_plan: StructuredPlan v2.0 对象（可选）
        tool_violations: 工具违反记录列表（新增）
        allowed_tools_snapshot: 允许的工具快照（新增）
    """
    original_plan: str
    current_step: int = 1
    total_steps: int = 0
    completed_steps: list[str] = field(default_factory=list)
    failed_count: int = 0
    last_adjustment: str | None = None
    react_iteration_count: int = 0  # 修改：明确为 ReAct 迭代次数
    tool_execution_count: int = 0  # 新增：工具执行次数
    replan_count: int = 0  # 新增：重规划次数
    milestones_validated: list[str] = field(default_factory=list)  # 新增：已验证里程碑
    structured_plan: Any = None  # 新增：StructuredPlan v2.0 引用
    tool_violations: list[dict] = field(default_factory=list)  # 新增：工具违反记录
    allowed_tools_snapshot: list[str] = field(default_factory=list)  # 新增：允许的工具快照
    
    def __post_init__(self):
        """初始化后计算总步骤数"""
        if self.total_steps == 0:
            # 根据换行符计算步骤数
            self.total_steps = self.original_plan.count("\n") + 1


class PlanContext:
    """管理计划状态，构建注入 ReAct 的上下文
    
    核心功能：
    1. 构建注入 ReAct System Prompt 的计划上下文
    2. 追踪执行进度
    3. 判断是否需要重新规划
    4. 根据工具执行结果更新状态
    5. 里程碑验证（混合调度）
    """
    
    def __init__(self, config=None):
        """初始化 PlanContext
        
        Args:
            config: PlanConfig 实例，如果为 None 则使用默认值
        """
        if config is None:
            # 使用默认配置
            from ..config.models import PlanConfig
            config = PlanConfig()
        
        self.config = config
        # 为了向后兼容，保留类属性
        self.REPLAN_THRESHOLD = {
            "consecutive_failures": config.consecutive_failures,
            "stuck_iterations": config.stuck_iterations,
        }
        self.MAX_REPLAN_COUNT = config.max_replan_count
    
    # 需要硬验证的里程碑关键词
    MILESTONE_KEYWORDS = [
        "创建", "create", "write file", "保存",  # File creation
        "语法检查", "syntax", "compile", "编译",  # Syntax check
        "导入", "import", "模块加载",  # Import test
        "测试", "test", "验证", "verify",  # Validation
    ]
    
    def build_react_context(self, state: PlanState) -> str:
        """构建注入 ReAct System Prompt 的计划上下文
        
        Args:
            state: 当前计划状态
            
        Returns:
            str: 格式化的计划上下文文本
        """
        # Validate plan first
        if not state.original_plan or not state.original_plan.strip():
            logger.error("Empty plan detected in build_react_context")
            return "【错误】计划为空，请先使用 /plan 命令创建计划"
        
        # 解析计划步骤 with error handling
        try:
            steps = self._parse_plan_steps(state.original_plan)
        except Exception as e:
            logger.error(
                "Failed to parse plan steps",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "plan_length": len(state.original_plan),
                }
            )
            return f"【错误】计划解析失败：{str(e)}\n请检查计划格式是否正确"
        
        if not steps:
            logger.warning("No steps found in plan")
            return "【警告】计划中未找到有效步骤，请检查计划格式"
        
        # Update total steps if not set
        if state.total_steps == 0 or state.total_steps != len(steps):
            state.total_steps = len(steps)
            logger.debug(f"Updated total_steps to {len(steps)}")
        
        # 构建上下文
        context_parts = []
        
        # 当前计划
        context_parts.append("【当前计划】")
        for i, step in enumerate(steps, 1):
            if i == state.current_step:
                context_parts.append(f"{step} ← 当前步骤")
            elif i < state.current_step:
                context_parts.append(f"{step} ✓")
            else:
                context_parts.append(step)
        
        # 已完成
        if state.completed_steps:
            context_parts.append("\n【已完成】")
            for completed in state.completed_steps[-3:]:  # 只显示最近3个
                context_parts.append(f"- {completed}")
        
        # 进度 (safe division)
        progress_pct = (state.current_step / state.total_steps * 100) if state.total_steps > 0 else 0
        context_parts.append(f"\n【进度】{state.current_step}/{state.total_steps} ({progress_pct:.0f}%)")
        
        # 反思提示（如果有失败）
        if state.failed_count > 0:
            context_parts.append("\n【反思提示】")
            context_parts.append(f"当前已连续失败 {state.failed_count} 次，如果继续失败将重新规划。")
            context_parts.append("请考虑：是否需要调整方法？是否需要更多信息？")
        
        return "\n".join(context_parts)
    
    def _parse_plan_steps(self, plan_text: str) -> list[str]:
        """解析计划文本为步骤列表
        
        Args:
            plan_text: 计划文本
            
        Returns:
            list[str]: 步骤列表
        """
        steps = []
        for line in plan_text.strip().split("\n"):
            line = line.strip()
            if line:
                steps.append(line)
        return steps
    
    def should_replan(self, state: PlanState) -> tuple[bool, str]:
        """判断是否需要重新规划
            
        Args:
            state: 当前计划状态
                
        Returns:
            tuple[bool, str]: (是否需要重规划，原因)
        """
        # 检查是否已达到最大重规划次数
        if state.replan_count >= self.MAX_REPLAN_COUNT:
            logger.warning(
                "Max replan count reached, stopping",
                extra={
                    "replan_count": state.replan_count,
                    "max_replan_count": self.MAX_REPLAN_COUNT,
                    "threshold_type": "max_replan_count",
                }
            )
            return False, ""  # 不再重规划，让任务自然结束
            
        # 检查连续失败
        if state.failed_count >= self.REPLAN_THRESHOLD["consecutive_failures"]:
            reason = f"连续失败 {state.failed_count} 次"
            logger.warning(
                "Replan triggered by consecutive failures",
                extra={
                    "reason": reason,
                    "failed_count": state.failed_count,
                    "threshold": self.REPLAN_THRESHOLD["consecutive_failures"],
                    "threshold_type": "consecutive_failures",
                    "last_step": state.completed_steps[-1] if state.completed_steps else None,
                    "replan_count": state.replan_count,
                }
            )
            return True, reason
            
        # 检查是否卡住（迭代次数过多但进度缓慢）
        if state.react_iteration_count >= self.REPLAN_THRESHOLD["stuck_iterations"]:
            if state.completed_steps:  # 有进展
                return False, ""
            reason = f"迭代 {state.react_iteration_count} 次但无进展"
            logger.warning(
                "Replan triggered by stuck iteration",
                extra={
                    "reason": reason,
                    "react_iteration_count": state.react_iteration_count,
                    "threshold": self.REPLAN_THRESHOLD["stuck_iterations"],
                    "threshold_type": "stuck_iterations",
                    "replan_count": state.replan_count,
                }
            )
            return True, reason
            
        return False, ""
    
    def record_replan(self, state: PlanState, reason: str) -> None:
        """记录重规划事件
        
        Args:
            state: 计划状态（会被修改）
            reason: 重规划原因
        """
        state.replan_count += 1
        state.last_adjustment = reason
        state.failed_count = 0  # 重置失败计数
        logger.info(
            "Replan recorded",
            extra={
                "replan_count": state.replan_count,
                "reason": reason,
                "max_replan_count": self.MAX_REPLAN_COUNT,
                "remaining_replans": self.MAX_REPLAN_COUNT - state.replan_count,
            }
        )
    
    def update_from_tool_result(
        self,
        state: PlanState,
        tool_name: str,
        success: bool,
        output: str,
    ) -> None:
        """根据工具执行结果更新计划状态
            
        Args:
            state: 计划状态（会被修改）
            tool_name: 工具名称
            success: 是否成功
            output: 输出内容
        """
        # 更新工具执行计数（不是ReAct迭代）
        state.tool_execution_count += 1
            
        if success:
            # 成功：重置失败计数，记录完成步骤
            state.failed_count = 0
            # 截取输出前 50 字符作为摘要
            output_summary = output[:50] if output else "完成"
            state.completed_steps.append(f"{tool_name}: {output_summary}")
                
            # 尝试推断是否完成当前步骤
            # 简单逻辑：每成功执行一个工具，认为完成了一步
            if len(state.completed_steps) >= state.current_step:
                state.current_step = min(state.current_step + 1, state.total_steps)
                
            logger.info(
                "Plan state updated",
                extra={
                    "current_step": state.current_step,
                    "total_steps": state.total_steps,
                    "completed_count": len(state.completed_steps),
                    "failed_count": state.failed_count,
                    "tool_execution_count": state.tool_execution_count,
                    "progress": f"{state.current_step}/{state.total_steps}",
                }
            )
        else:
            # 失败：增加失败计数
            state.failed_count += 1
            logger.info(
                "Plan state updated (failure)",
                extra={
                    "current_step": state.current_step,
                    "failed_count": state.failed_count,
                    "tool_name": tool_name,
                    "tool_execution_count": state.tool_execution_count,
                }
            )
        
    def validate_milestone(
        self,
        state: PlanState,
        milestone_name: str,
        context: dict,
    ) -> tuple[bool, str]:
        """验证里程碑（混合调度：硬验证）
            
        Args:
            state: 计划状态
            milestone_name: 里程碑名称
            context: 验证上下文（文件路径、模块名等）
                
        Returns:
            tuple[bool, str]: (是否通过，消息)
        """
        # Use old MilestoneValidator for v1.0 plans (backward compatibility)
        from . import milestone_validator as legacy_milestone_validator
        validator = legacy_milestone_validator.get_milestone_validator()
        result = validator.validate(milestone_name, context)
            
        if result.passed:
            # 记录已验证的里程碑
            state.milestones_validated.append(milestone_name)
            logger.info(
                "Milestone validated",
                extra={
                    "milestone": milestone_name,
                    "validation_type": result.validation_type,
                }
            )
            return True, result.message
        else:
            logger.warning(
                "Milestone validation failed",
                extra={
                    "milestone": milestone_name,
                    "reason": result.message,
                    "suggestions": result.suggestions,
                }
            )
            return False, result.message
        
    def should_validate_milestone(self, step_description: str) -> bool:
        """判断是否需要硬验证里程碑
            
        Args:
            step_description: 步骤描述
                
        Returns:
            bool: 是否需要硬验证
        """
        desc_lower = step_description.lower()
        return any(kw in desc_lower for kw in self.MILESTONE_KEYWORDS)
    
    def advance_step(self, state: PlanState) -> None:
        """手动推进到下一步
        
        Args:
            state: 计划状态（会被修改）
        """
        if state.current_step < state.total_steps:
            state.current_step += 1
            logger.info(
                "Plan step advanced",
                extra={
                    "new_step": state.current_step,
                    "total_steps": state.total_steps,
                }
            )
    
    def is_complete(self, state: PlanState) -> bool:
        """检查计划是否完成
        
        Args:
            state: 计划状态
            
        Returns:
            bool: 是否完成
        """
        return state.current_step > state.total_steps or (
            state.total_steps > 0 and len(state.completed_steps) >= state.total_steps
        )
    
    def record_tool_violation(
        self,
        state: PlanState,
        tool_name: str,
        violation_type: str,
        details: dict | None = None,
    ) -> None:
        """记录工具违反事件
        
        Args:
            state: 计划状态（会被修改）
            tool_name: 工具名称
            violation_type: 违反类型（如 'forbidden_tool', 'not_in_allowed_list'）
            details: 额外详情
        """
        violation_record = {
            "tool_name": tool_name,
            "violation_type": violation_type,
            "details": details or {},
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        
        state.tool_violations.append(violation_record)
        
        logger.warning(
            "Tool violation recorded",
            extra={
                "tool_name": tool_name,
                "violation_type": violation_type,
                "total_violations": len(state.tool_violations),
                "allowed_tools": state.allowed_tools_snapshot,
            }
        )
    
    def update_allowed_tools_snapshot(
        self,
        state: PlanState,
        allowed_tools: list[str],
    ) -> None:
        """更新允许的工具快照
        
        Args:
            state: 计划状态（会被修改）
            allowed_tools: 允许的工具列表
        """
        state.allowed_tools_snapshot = allowed_tools.copy()
        
        logger.debug(
            "Updated allowed tools snapshot",
            extra={
                "allowed_tools": allowed_tools,
            }
        )


# 全局实例
_plan_context: PlanContext | None = None


def get_plan_context() -> PlanContext:
    """获取全局 PlanContext 实例"""
    global _plan_context
    if _plan_context is None:
        _plan_context = PlanContext()
    return _plan_context
