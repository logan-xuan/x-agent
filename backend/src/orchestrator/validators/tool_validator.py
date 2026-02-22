"""Tool constraint validator for X-Agent.

Validates if a tool call is allowed based on the current plan's constraints.
"""

from ..models.plan import StructuredPlan, ToolConstraints
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ToolConstraintValidator:
    """工具约束验证器
    
    职责：
    - 检查工具调用是否在白名单中
    - 检查工具调用是否在黑名单中
    - 如果违反约束，触发重规划
    """
    
    def __init__(self, plan: StructuredPlan | None = None):
        """初始化工具约束验证器
        
        Args:
            plan: 当前的结构化计划
        """
        self.plan = plan
        self.violation_count = 0
    
    def set_plan(self, plan: StructuredPlan) -> None:
        """设置当前计划
        
        Args:
            plan: 新的结构化计划
        """
        self.plan = plan
        self.violation_count = 0
        logger.info(
            "Plan updated for tool constraint validation",
            extra={
                "skill_binding": plan.skill_binding,
                "has_constraints": plan.tool_constraints is not None,
            }
        )
    
    def is_tool_allowed(self, tool_name: str) -> tuple[bool, str | None]:
        """检查工具是否被允许使用
        
        Args:
            tool_name: 工具名称
            
        Returns:
            (is_allowed, reason) - 是否允许，如果不允许则说明原因
        """
        # 如果没有计划或没有工具约束，允许所有工具
        if not self.plan or not self.plan.tool_constraints:
            return True, None
        
        constraints = self.plan.tool_constraints
        
        # 检查黑名单
        if constraints.forbidden and tool_name in constraints.forbidden:
            reason = f"工具 '{tool_name}' 在当前计划的禁止列表中（{constraints.forbidden}）"
            logger.warning(
                "Tool blocked by forbidden list",
                extra={
                    "tool_name": tool_name,
                    "forbidden_tools": constraints.forbidden,
                    "skill_binding": self.plan.skill_binding,
                }
            )
            self.violation_count += 1
            return False, reason
        
        # 检查白名单
        if constraints.allowed and tool_name not in constraints.allowed:
            reason = f"工具 '{tool_name}' 不在当前计划的允许列表中（{constraints.allowed}）"
            logger.warning(
                "Tool not in allowed list",
                extra={
                    "tool_name": tool_name,
                    "allowed_tools": constraints.allowed,
                    "skill_binding": self.plan.skill_binding,
                }
            )
            self.violation_count += 1
            return False, reason
        
        # 通过检查
        logger.debug(
            "Tool allowed by constraints",
            extra={"tool_name": tool_name, "skill_binding": self.plan.skill_binding}
        )
        return True, None
    
    def should_trigger_replan(self) -> bool:
        """判断是否应该触发重规划
        
        Returns:
            True 如果违规次数超过阈值
        """
        # 如果连续违规 3 次，触发重规划
        return self.violation_count >= 3
    
    def reset_violations(self) -> None:
        """重置违规计数"""
        self.violation_count = 0
        logger.debug("Tool constraint violations reset")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "violation_count": self.violation_count,
            "should_replan": self.should_trigger_replan(),
            "has_plan": self.plan is not None,
            "skill_binding": self.plan.skill_binding if self.plan else None,
            "allowed_tools": self.plan.tool_constraints.allowed if self.plan and self.plan.tool_constraints else [],
            "forbidden_tools": self.plan.tool_constraints.forbidden if self.plan and self.plan.tool_constraints else [],
        }
