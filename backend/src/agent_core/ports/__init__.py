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

from .context_port import (
    ContextPort,
    PreparedContext,
)
from .delegate_port import (
    DelegatePort,
    DelegateResult,
    DelegateTask,
)
from .llm_port import LLMPort
from .logger_port import LoggerPort
from .memory_port import MemoryPort
from .plan_port import (
    Plan,
    PlanPort,
    PlanStatus,
    PlanStep,
    StepStatus,
)
from .skill_port import (
    SkillCategory,
    SkillContext,
    SkillMetadata,
    SkillPort,
    SkillResult,
    SkillStatus,
)
from .system_prompt_port import (
    IdentityInfo,
    SystemPromptPort,
)
from .tool_port import ToolPort

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
    "DelegatePort",
    # Plan 相关类型
    "Plan",
    "PlanStep",
    "PlanStatus",
    "StepStatus",
    # Context 相关类型
    "PreparedContext",
    # SystemPrompt 相关类型
    "SystemPromptPort",
    "IdentityInfo",
    # Skill 相关类型
    "SkillMetadata",
    "SkillContext",
    "SkillResult",
    "SkillCategory",
    "SkillStatus",
    # Delegate 相关类型
    "DelegateTask",
    "DelegateResult",
]
