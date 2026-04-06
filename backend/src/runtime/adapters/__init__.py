"""Adapters that bridge legacy modules into the new runtime."""

from .agent_core_adapter import AgentCoreAdapter
from .conversation_adapter import ConversationAdapter

__all__ = ["AgentCoreAdapter", "ConversationAdapter"]
