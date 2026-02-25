"""Structured Plan models for X-Agent.

Defines the data structures for structured plans with skill bindings and tool constraints.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StepValidation:
    """步骤验证规则
    
    Attributes:
        validation_type: 验证类型 (regex/contains/json_schema/tool_output)
        pattern: 正则表达式（当 type=regex 时）
        text: 包含文本（当 type=contains 时）
        schema: JSON Schema（当 type=json_schema 时）
    """
    validation_type: Literal["regex", "contains", "json_schema", "tool_output"]
    pattern: str | None = None
    text: str | None = None
    schema: dict[str, Any] | None = None


@dataclass
class PlanStep:
    """结构化的计划步骤
    
    Attributes:
        id: 步骤唯一标识
        name: 步骤描述
        description: 详细说明（如何实现和验证）
        skill_command: 技能 CLI 命令（如果有）
        tool: 使用的工具名称
        expected_output: 预期输出描述
        validation: 验证规则
        metadata: 额外元数据
    """
    id: str
    name: str
    description: str | None = None  # 🔥 ADD: 详细说明
    skill_command: str | None = None
    tool: str | None = None
    expected_output: str | None = None
    validation: StepValidation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "skill_command": self.skill_command,
            "tool": self.tool,
            "expected_output": self.expected_output,
            "validation": {
                "type": self.validation.validation_type,
                "pattern": self.validation.pattern,
                "text": self.validation.text,
                "schema": self.validation.schema,
            } if self.validation else None,
            "metadata": self.metadata,
        }


@dataclass
class Milestone:
    """里程碑定义
    
    Attributes:
        name: 里程碑名称
        after_step: 在哪个步骤之后检查
        check_type: 检查类型 (tool_output/url_contains/file_exists/custom)
        value: 检查的值
    """
    name: str
    after_step: str
    check_type: Literal["tool_output", "url_contains", "file_exists", "custom"]
    value: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "after_step": self.after_step,
            "check_type": self.check_type,
            "value": self.value,
        }


@dataclass
class ToolConstraints:
    """工具约束
    
    Attributes:
        allowed: 允许使用的工具白名单
        forbidden: 禁止使用的工具黑名单
        source: 约束来源 (plan | skill | task_type)
        priority: 优先级（数值越大优先级越高）
    """
    allowed: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    source: str = "task_type"  # plan | skill | task_type
    priority: int = 0  # Higher number = higher priority
    
    def is_allowed(self, tool_name: str) -> bool:
        """检查工具是否被允许使用"""
        if self.forbidden and tool_name in self.forbidden:
            return False
        if self.allowed and tool_name not in self.allowed:
            return False
        return True


@dataclass
class StructuredPlan:
    """结构化计划 v2.0
    
    Attributes:
        version: 版本号
        goal: 任务目标
        skill_binding: 绑定的技能名称
        tool_constraints: 工具约束
        steps: 步骤列表
        milestones: 里程碑列表
        metadata: 额外元数据
    """
    version: str = "2.0"
    goal: str = ""
    skill_binding: str | None = None
    tool_constraints: ToolConstraints | None = None
    steps: list[PlanStep] = field(default_factory=list)
    milestones: list[Milestone] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "version": self.version,
            "goal": self.goal,
            "skill_binding": self.skill_binding,
            "tool_constraints": {
                "allowed": self.tool_constraints.allowed,
                "forbidden": self.tool_constraints.forbidden,
                "source": self.tool_constraints.source,
                "priority": self.tool_constraints.priority,
            } if self.tool_constraints else None,
            "steps": [step.to_dict() for step in self.steps],
            "milestones": [m.to_dict() for m in self.milestones],
            "metadata": self.metadata,
        }
    
    def to_prompt(self) -> str:
        """转换为 System Prompt 注入格式"""
        parts = []
        
        # 版本标识
        parts.append(f"📋 **结构化执行计划 v{self.version}**")
        parts.append(f"**目标**: {self.goal}")
        parts.append("")
        
        # 技能绑定（如果有）
        if self.skill_binding:
            parts.append(f"🔧 **绑定技能**: `{self.skill_binding}`")
            parts.append("")
        
        # 工具约束（如果有）
        if self.tool_constraints:
            if self.tool_constraints.allowed:
                parts.append(f"⚠️ **工具限制**: 只能使用以下工具：{', '.join(self.tool_constraints.allowed)}")
            if self.tool_constraints.forbidden:
                parts.append(f"❌ **禁止工具**: 不得使用：{', '.join(self.tool_constraints.forbidden)}")
            parts.append("")
        
        # 步骤列表
        parts.append("**执行步骤**:")
        for idx, step in enumerate(self.steps, 1):
            parts.append(f"{idx}. **{step.name}**")
            if step.skill_command:
                parts.append(f"   - 命令：`{step.skill_command}`")
            if step.tool:
                parts.append(f"   - 工具：`{step.tool}`")
            if step.expected_output:
                parts.append(f"   - 预期：{step.expected_output}")
        parts.append("")
        
        # 里程碑（如果有）
        if self.milestones:
            parts.append("**关键里程碑**:")
            for milestone in self.milestones:
                parts.append(f"- ✅ {milestone.name} (在 {milestone.after_step} 之后检查)")
            parts.append("")
        
        return "\n".join(parts)
