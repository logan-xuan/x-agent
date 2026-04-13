"""Agent Core Adapters.

适配器实现，连接 agent_core 与 X-Agent 现有系统。

使用延迟导入避免 import 时连带加载所有 adapter 的外部依赖，
确保 agent_core 内部模块（如 memory_adapter）可以独立使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .collaboration_adapter import CollaborationAdapter as CollaborationAdapter
    from .collaboration_adapter import create_collaboration_adapter as create_collaboration_adapter
    from .context_adapter import XAgentContextAdapter as XAgentContextAdapter
    from .context_adapter import create_context_adapter as create_context_adapter
    from .delegate_adapter import DelegateAdapter as DelegateAdapter
    from .delegate_adapter import create_delegate_adapter as create_delegate_adapter
    from .llm_adapter import XAgentLLMAdapter as XAgentLLMAdapter
    from .logger_adapter import XAgentLoggerAdapter as XAgentLoggerAdapter
    from .memory_adapter import XAgentMemoryAdapter as XAgentMemoryAdapter

    # 新增 Adapter
    from .prompt_pipeline_adapter import PromptPipelineAdapter as PromptPipelineAdapter
    from .prompt_pipeline_adapter import (
        create_prompt_pipeline_adapter as create_prompt_pipeline_adapter,
    )
    from .skill_adapter import XAgentSkillAdapter as XAgentSkillAdapter
    from .skill_adapter import create_skill_adapter as create_skill_adapter
    from .system_prompt_adapter import XAgentSystemPromptAdapter as XAgentSystemPromptAdapter
    from .system_prompt_adapter import create_system_prompt_adapter as create_system_prompt_adapter
    from .tool_adapter import XAgentToolAdapter as XAgentToolAdapter
    from .tool_middleware_adapter import ToolMiddlewareAdapter as ToolMiddlewareAdapter
    from .tool_middleware_adapter import (
        create_tool_middleware_adapter as create_tool_middleware_adapter,
    )

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
    # 新增 Adapter
    "PromptPipelineAdapter",
    "create_prompt_pipeline_adapter",
    "ToolMiddlewareAdapter",
    "create_tool_middleware_adapter",
    "DelegateAdapter",
    "create_delegate_adapter",
    "CollaborationAdapter",
    "create_collaboration_adapter",
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
    # 新增 Adapter 的延迟导入
    if name == "PromptPipelineAdapter":
        from .prompt_pipeline_adapter import PromptPipelineAdapter

        return PromptPipelineAdapter
    if name == "create_prompt_pipeline_adapter":
        from .prompt_pipeline_adapter import create_prompt_pipeline_adapter

        return create_prompt_pipeline_adapter
    if name == "ToolMiddlewareAdapter":
        from .tool_middleware_adapter import ToolMiddlewareAdapter

        return ToolMiddlewareAdapter
    if name == "create_tool_middleware_adapter":
        from .tool_middleware_adapter import create_tool_middleware_adapter

        return create_tool_middleware_adapter
    if name == "DelegateAdapter":
        from .delegate_adapter import DelegateAdapter

        return DelegateAdapter
    if name == "create_delegate_adapter":
        from .delegate_adapter import create_delegate_adapter

        return create_delegate_adapter
    if name == "CollaborationAdapter":
        from .collaboration_adapter import CollaborationAdapter

        return CollaborationAdapter
    if name == "create_collaboration_adapter":
        from .collaboration_adapter import create_collaboration_adapter

        return create_collaboration_adapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
