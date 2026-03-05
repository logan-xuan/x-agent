"""Conversation module - context management, session handling, and system prompt building."""

from .context import (
    AgentContext,
    ContextManager,
    ContextSource,
    context_manager,
    get_current_context,
    set_current_context,
)
from .session import SessionManager
from .system_prompt_builder import SystemPromptBuilder

__all__ = [
    "AgentContext",
    "ContextManager",
    "ContextSource",
    "SessionManager",
    "SystemPromptBuilder",
    "context_manager",
    "get_current_context",
    "set_current_context",
]
