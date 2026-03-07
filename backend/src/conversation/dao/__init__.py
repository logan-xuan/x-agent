"""会话 DAO 层 — 核心实体模型、数据操作与启动引导。"""

from .models import (
    Agent,
    Channel,
    ChatSession,
    SessionStatus,
    User,
)
from .dao import (
    AgentDAO,
    ChannelDAO,
    ChatSessionDAO,
    UserDAO,
)
from .bootstrap import (
    DEFAULT_AGENT_ID,
    DEFAULT_CHANNEL_ID,
    DEFAULT_USER_ID,
    ensure_default_entities,
)

__all__ = [
    # 模型
    "Agent",
    "Channel",
    "ChatSession",
    "SessionStatus",
    "User",
    # DAO
    "AgentDAO",
    "ChannelDAO",
    "ChatSessionDAO",
    "UserDAO",
    # 启动引导
    "DEFAULT_AGENT_ID",
    "DEFAULT_CHANNEL_ID",
    "DEFAULT_USER_ID",
    "ensure_default_entities",
]
