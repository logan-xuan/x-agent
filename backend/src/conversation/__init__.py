"""Conversation 模块 — 上下文管理、身份、会话处理、系统提示词构建及核心实体 DAO。"""

from .context import (
    AgentContext,
    ContextManager,
    ContextSource,  # ChannelProtocol 的向后兼容别名
    context_manager,
    get_current_context,
    set_current_context,
    clear_current_context,
)
from .identity import (
    AgentType,
    ChannelProtocol,
    ChannelType,
    Identity,
    IdentityManager,
    get_current_identity,
    get_identity_manager,
    set_current_identity,
)
from .session import SessionManager
from .system_prompt_builder import SystemPromptBuilder
from .dao import (
    Agent,
    Channel,
    SessionStatus,
    User,
    UserDAO,
)

__all__ = [
    # 身份
    "AgentType",
    "ChannelProtocol",
    "ChannelType",
    "Identity",
    "IdentityManager",
    "get_current_identity",
    "get_identity_manager",
    "set_current_identity",
    # 上下文
    "AgentContext",
    "ContextManager",
    "ContextSource",
    "context_manager",
    "get_current_context",
    "set_current_context",
    "clear_current_context",
    # 会话 & 提示词
    "SessionManager",
    "SystemPromptBuilder",
    # 核心实体模型
    "Agent",
    "Channel",
    "SessionStatus",
    "User",
    # DAO
    "UserDAO",
]
