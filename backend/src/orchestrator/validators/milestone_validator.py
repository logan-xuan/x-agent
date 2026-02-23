"""Milestone validator for X-Agent.

Validates if a milestone has been achieved after completing a plan step.
"""

from ..models.plan import StructuredPlan, Milestone, PlanStep
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MilestoneValidator:
    """里程碑验证器
    
    职责：
    - 在步骤完成后检查是否达到里程碑
    - 如果未达到，触发重规划或调整
    """
    
    def __init__(self, plan: StructuredPlan | None = None):
        """初始化里程碑验证器
        
        Args:
            plan: 当前的结构化计划
        """
        self.plan = plan
        self.completed_milestones: set[str] = set()
    
    def set_plan(self, plan: StructuredPlan) -> None:
        """设置当前计划
        
        Args:
            plan: 新的结构化计划
        """
        self.plan = plan
        self.completed_milestones.clear()
        logger.info(
            "Plan updated for milestone validation",
            extra={
                "milestones_count": len(plan.milestones),
                "skill_binding": plan.skill_binding,
            }
        )
    
    def check_milestone(self, completed_step_id: str, tool_output: str = "") -> tuple[bool, str | None]:
        """检查是否有里程碑需要验证
        
        Args:
            completed_step_id: 已完成的步骤 ID
            tool_output: 工具执行输出
            
        Returns:
            (passed, message) - 是否通过，如果没有通过则说明原因
        """
        if not self.plan:
            return True, None
        
        # 查找所有在当前步骤之后需要检查的里程碑
        milestones_to_check = [
            m for m in self.plan.milestones 
            if m.after_step == completed_step_id and m.name not in self.completed_milestones
        ]
        
        if not milestones_to_check:
            return True, None
        
        # 逐个检查里程碑
        for milestone in milestones_to_check:
            passed, message = self._validate_milestone(milestone, tool_output)
            
            if not passed:
                logger.warning(
                    "Milestone validation failed",
                    extra={
                        "milestone_name": milestone.name,
                        "after_step": completed_step_id,
                        "reason": message,
                    }
                )
                return False, message
            
            # 标记为已完成
            self.completed_milestones.add(milestone.name)
            logger.info(
                "Milestone achieved",
                extra={"milestone_name": milestone.name}
            )
        
        return True, None
    
    def _validate_milestone(self, milestone: Milestone, tool_output: str) -> tuple[bool, str | None]:
        """验证单个里程碑
        
        Args:
            milestone: 里程碑定义
            tool_output: 工具执行输出
            
        Returns:
            (passed, message) - 是否通过
        """
        check_type = milestone.check_type
        value = milestone.value
        
        if check_type == "tool_output":
            # 检查工具输出是否包含预期内容
            if not tool_output:
                return False, f"里程碑 '{milestone.name}' 要求工具输出，但未提供"
            
            if value and value not in tool_output:
                return False, f"里程碑 '{milestone.name}' 未达成：期望输出包含 '{value}'，但实际输出为：{tool_output[:100]}"
            
            return True, None
        
        elif check_type == "url_contains":
            # 检查 URL 是否包含特定参数（通用检查）
            if not value:
                return False, f"里程碑 '{milestone.name}' 缺少必需的 value 字段"
            
            # 这里需要从上下文获取当前 URL，简化处理
            # TODO: 需要从 AgentContext 中获取当前 URL
            return True, None  # 暂时假设通过
        
        elif check_type == "file_exists":
            # 检查文件是否存在
            if not value:
                return False, f"里程碑 '{milestone.name}' 缺少必需的文件路径"
            
            from pathlib import Path
            file_path = Path(value)
            if not file_path.exists():
                return False, f"里程碑 '{milestone.name}' 未达成：文件不存在 {value}"
            
            return True, None
        
        elif check_type == "custom":
            # 自定义验证逻辑（预留扩展）
            logger.debug(f"Custom milestone check: {milestone.name}")
            return True, None
        
        else:
            logger.warning(f"Unknown milestone check type: {check_type}")
            return True, None  # 未知类型默认通过
    
    def get_progress(self) -> dict:
        """获取里程碑进度"""
        if not self.plan:
            return {"total": 0, "completed": 0, "percentage": 0.0}
        
        total = len(self.plan.milestones)
        completed = len(self.completed_milestones)
        percentage = (completed / total * 100) if total > 0 else 0.0
        
        return {
            "total": total,
            "completed": completed,
            "percentage": percentage,
            "remaining": [m.name for m in self.plan.milestones if m.name not in self.completed_milestones],
        }
    
    def reset(self) -> None:
        """重置里程碑进度"""
        self.completed_milestones.clear()
        logger.debug("Milestone validator reset")
