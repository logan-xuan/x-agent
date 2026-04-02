"""Session 解析器。

ActiveSessionResolver 负责解析 Agent 在指定渠道的最新有效 Session。
用于通知系统和 AgentInvoker 在不知道具体 session_id 时自动定位目标会话。

核心规则：
- 单聊单 session：一个 agent_id 在一个渠道中，同时只有一个最新的 session_id 有效
- 自动创建：通知时如果没有有效 session，可自动创建新 session
- Session 失效：用户关闭窗口 → 旧 session 标记为 closed
"""

from __future__ import annotations

from uuid import uuid4

from ..conversation.identity import ChannelType
from .errors import GatewayError

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class NoActiveSessionError(GatewayError):
    """没有有效的活跃 Session。

    当 auto_create=False 且无法找到有效 session 时抛出。

    Attributes:
        agent_id: 目标 Agent ID。
        channel_type: 目标渠道类型。
    """

    def __init__(
        self,
        agent_id: str,
        channel_type: ChannelType,
        message: str = "No active session found",
    ) -> None:
        self.agent_id = agent_id
        self.channel_type = channel_type
        super().__init__(
            f"{message} (agent_id={agent_id}, channel_type={channel_type.value})"
        )


def _get_storage_service():
    """获取 StorageService 实例。"""
    from ..services.storage import get_storage_service
    return get_storage_service()


class ActiveSessionResolver:
    """解析 Agent 在指定渠道的最新有效 Session。

    核心逻辑：
    1. 查找 agent_id 下 status=ACTIVE 的最新 session
    2. 找到 → 返回该 session_id
    3. 没找到 + auto_create=True → 自动创建新 session 并返回
    4. 没找到 + auto_create=False → 抛出 NoActiveSessionError

    典型用法::

        resolver = ActiveSessionResolver()

        # 自动解析或创建
        session_id = await resolver.resolve(
            agent_id="agent-001",
            channel_type=ChannelType.WEB_CHAT,
        )

        # 仅查找，不自动创建
        session_id = await resolver.resolve(
            agent_id="agent-001",
            channel_type=ChannelType.WEB_CHAT,
            auto_create=False,
        )
    """

    async def resolve(
        self,
        agent_id: str,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        auto_create: bool = True,
    ) -> str:
        """解析最新有效的 session_id。

        Args:
            agent_id: Agent ID。
            channel_type: 渠道类型。
            auto_create: 没有有效 session 时是否自动创建。

        Returns:
            session_id。

        Raises:
            NoActiveSessionError: auto_create=False 且无有效 session。
        """
        from ..conversation.session import SessionManager

        session_manager = SessionManager()

        # 1. 查找最新的 ACTIVE session（新系统 sessions 表）
        active_session = await session_manager.get_active_session_by_agent(agent_id)

        if active_session:
            logger.debug(
                "Active session resolved",
                extra={
                    "agent_id": agent_id,
                    "channel_type": channel_type.value,
                    "session_id": active_session.id,
                },
            )
            return active_session.id

        # 2. 没有有效 session
        if not auto_create:
            raise NoActiveSessionError(agent_id, channel_type)

        # 3. 自动创建新 session（新系统 sessions 表）
        # 使用 Agent 名称作为会话标题
        from ..conversation.dao.models import Agent
        agent = Agent.from_config(agent_id)
        title = f"{agent.agent_name} 对话" if agent else f"Auto-created for {channel_type.value}"
        new_session = await session_manager.create_session(
            title=title,
            agent_id=agent_id,
        )

        logger.info(
            "Auto-created session for notification",
            extra={
                "agent_id": agent_id,
                "channel_type": channel_type.value,
                "session_id": new_session.id,
            },
        )
        return new_session.id
