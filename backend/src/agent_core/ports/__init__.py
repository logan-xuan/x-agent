"""Agent Core Port 接口定义.

本模块定义了 agent_core 的所有 Port 接口，使用 Protocol 实现结构化子类型。

Port 接口:
- LLMPort: LLM 调用接口
- ToolPort: 工具执行接口
- MemoryPort: 记忆存储接口
- LoggerPort: 日志接口
- PlanPort: 计划管理接口
- ContextPort: 上下文管理接口
- SkillPort: 技能系统接口
"""

from .llm_port import LLMPort
from .tool_port import ToolPort
from .memory_port import MemoryPort
from .logger_port import LoggerPort
from .plan_port import (
    PlanPort,
    Plan,
    PlanStep,
    PlanStatus,
    StepStatus,
)
from .context_port import (
    ContextPort,
    ContextConfig,
    CompressionResult,
    CompressionStrategy,
)
from .skill_port import (
    SkillPort,
    SkillMetadata,
    SkillContext,
    SkillResult,
    SkillCategory,
    SkillStatus,
)

__all__ = [
    # 核心 Ports
    "LLMPort",
    "ToolPort",
    "MemoryPort",
    "LoggerPort",
    # 扩展 Ports
    "PlanPort",
    "ContextPort",
    "SkillPort",
    # Plan 相关类型
    "Plan",
    "PlanStep",
    "PlanStatus",
    "StepStatus",
    # Context 相关类型
    "ContextConfig",
    "CompressionResult",
    "CompressionStrategy",
    # Skill 相关类型
    "SkillMetadata",
    "SkillContext",
    "SkillResult",
    "SkillCategory",
    "SkillStatus",
]
