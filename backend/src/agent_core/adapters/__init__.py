"""Agent Core Adapters.

适配器实现，连接 agent_core 与 X-Agent 现有系统。

使用延迟导入避免 import 时连带加载所有 adapter 的外部依赖，
确保 agent_core 内部模块（如 memory_adapter）可以独立使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_adapter import XAgentLLMAdapter as XAgentLLMAdapter
    from .tool_adapter import XAgentToolAdapter as XAgentToolAdapter
    from .memory_adapter import XAgentMemoryAdapter as XAgentMemoryAdapter
    from .logger_adapter import XAgentLoggerAdapter as XAgentLoggerAdapter
    from .context_adapter import XAgentContextAdapter as XAgentContextAdapter
    from .context_adapter import create_context_adapter as create_context_adapter
    from .skill_adapter import XAgentSkillAdapter as XAgentSkillAdapter
    from .skill_adapter import create_skill_adapter as create_skill_adapter
    from .system_prompt_adapter import XAgentSystemPromptAdapter as XAgentSystemPromptAdapter
    from .system_prompt_adapter import create_system_prompt_adapter as create_system_prompt_adapter

__all__ = [
    "XAgentLLMAdapter",
    "XAgentToolAdapter",
    "XAgentMemoryAdapter",
    "XAgentLoggerAdapter",
    "XAgentContextAdapter",
    "create_context_adapter",
    "XAgentSkillAdapter",
    "create_skill_adapter",
    "XAgentSystemPromptAdapter",
    "create_system_prompt_adapter",
]


def __getattr__(name: str):
    """延迟导入 adapter，避免 import 时加载所有外部依赖."""
    if name == "XAgentLLMAdapter":
        from .llm_adapter import XAgentLLMAdapter
        return XAgentLLMAdapter
    if name == "XAgentToolAdapter":
        from .tool_adapter import XAgentToolAdapter
        return XAgentToolAdapter
    if name == "XAgentMemoryAdapter":
        from .memory_adapter import XAgentMemoryAdapter
        return XAgentMemoryAdapter
    if name == "XAgentLoggerAdapter":
        from .logger_adapter import XAgentLoggerAdapter
        return XAgentLoggerAdapter
    if name == "XAgentContextAdapter":
        from .context_adapter import XAgentContextAdapter
        return XAgentContextAdapter
    if name == "create_context_adapter":
        from .context_adapter import create_context_adapter
        return create_context_adapter
    if name == "XAgentSkillAdapter":
        from .skill_adapter import XAgentSkillAdapter
        return XAgentSkillAdapter
    if name == "create_skill_adapter":
        from .skill_adapter import create_skill_adapter
        return create_skill_adapter
    if name == "XAgentSystemPromptAdapter":
        from .system_prompt_adapter import XAgentSystemPromptAdapter
        return XAgentSystemPromptAdapter
    if name == "create_system_prompt_adapter":
        from .system_prompt_adapter import create_system_prompt_adapter
        return create_system_prompt_adapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
