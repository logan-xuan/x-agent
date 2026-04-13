"""会话 DAO 层 — 核心实体模型、数据操作与启动引导。"""

from .bootstrap import (
    CLI_CHANNEL_ID,
    DEFAULT_AGENT_ID,
    DEFAULT_CHANNEL_ID,
    DEFAULT_USER_ID,
    ensure_default_entities,
)
from .dao import UserDAO
from .models import (
    Agent,
    Channel,
    SessionStatus,
    User,
)

__all__ = [
    # 模型
    "Agent",
    "Channel",
    "SessionStatus",
    "User",
    # DAO
    "UserDAO",
    # 启动引导
    "CLI_CHANNEL_ID",
    "DEFAULT_AGENT_ID",
    "DEFAULT_CHANNEL_ID",
    "DEFAULT_USER_ID",
    "ensure_default_entities",
]
