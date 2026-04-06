"""Adapters that bridge legacy modules into the new runtime."""

from .agent_core_adapter import AgentCoreAdapter
from .compression_adapter import CompressionAdapter
from .conversation_adapter import ConversationAdapter
from .gateway_adapter import GatewayAdapter

__all__ = ["AgentCoreAdapter", "CompressionAdapter", "ConversationAdapter", "GatewayAdapter"]
