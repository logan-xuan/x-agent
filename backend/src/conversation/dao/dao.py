"""核心实体数据访问层（DAO）。

为 User、Agent、Channel、ChatSession 提供异步 CRUD 操作，
基于 StorageService 的 async session 实现。

典型用法::

    from ..services.storage import get_storage_service

    storage = get_storage_service()
    user_dao = UserDAO(storage)
    user = await user_dao.create(name="玄哥")
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ...services.storage import StorageService
from ...utils.logger import get_logger
from .models import Agent, Channel, ChatSession, SessionStatus, User

logger = get_logger(__name__)


class UserDAO:
    """用户数据访问对象。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def create(self, name: str, user_id: Optional[str] = None) -> User:
        """创建用户。

        Args:
            name: 用户名称。
            user_id: 可选的用户 ID，省略时自动生成。

        Returns:
            创建的 User 实例。
        """
        user = User(name=name)
        if user_id is not None:
            user.user_id = user_id

        async with self._storage.session() as db_session:
            db_session.add(user)
            await db_session.flush()
            await db_session.refresh(user)

        logger.info("创建用户", extra={"user_id": user.user_id, "name": name})
        return user

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """根据 ID 获取用户。"""
        async with self._storage.session() as db_session:
            return await db_session.get(User, user_id)

    async def list_all(self, limit: int = 100) -> list[User]:
        """列出所有用户，按创建时间倒序。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(User).order_by(User.create_time.desc()).limit(limit)
            )
            return list(result.scalars().all())

    async def update_name(self, user_id: str, name: str) -> Optional[User]:
        """更新用户名称。

        Args:
            user_id: 用户 ID。
            name: 新名称。

        Returns:
            更新后的 User，不存在时返回 None。
        """
        async with self._storage.session() as db_session:
            user = await db_session.get(User, user_id)
            if user is None:
                return None
            user.name = name
            await db_session.flush()
            await db_session.refresh(user)

        logger.info("更新用户名称", extra={"user_id": user_id, "name": name})
        return user

    async def delete(self, user_id: str) -> bool:
        """删除用户（级联删除关联的 Agent、Channel、ChatSession）。

        Returns:
            是否成功删除（用户不存在时返回 False）。
        """
        async with self._storage.session() as db_session:
            user = await db_session.get(User, user_id)
            if user is None:
                return False
            await db_session.delete(user)

        logger.info("删除用户", extra={"user_id": user_id})
        return True


class AgentDAO:
    """智能体数据访问对象。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def create(
        self,
        agent_name: str,
        user_id: str,
        agent_type: str = "main",
        agent_persona: str = "",
        agent_id: Optional[str] = None,
    ) -> Agent:
        """创建 Agent。

        Args:
            agent_name: Agent 名称。
            user_id: 创建者用户 ID。
            agent_type: Agent 层级角色（main/partner/sub）。
            agent_persona: Agent 人设描述。
            agent_id: 可选的 Agent ID，省略时自动生成。

        Returns:
            创建的 Agent 实例。
        """
        agent = Agent(
            agent_name=agent_name,
            user_id=user_id,
            agent_type=agent_type,
            agent_persona=agent_persona,
        )
        if agent_id is not None:
            agent.agent_id = agent_id

        async with self._storage.session() as db_session:
            db_session.add(agent)
            await db_session.flush()
            await db_session.refresh(agent)

        logger.info(
            "创建 Agent",
            extra={"agent_id": agent.agent_id, "agent_name": agent_name, "user_id": user_id},
        )
        return agent

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        """根据 ID 获取 Agent。"""
        async with self._storage.session() as db_session:
            return await db_session.get(Agent, agent_id)

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[Agent]:
        """列出指定用户的所有 Agent，按创建时间倒序。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Agent)
                .where(Agent.user_id == user_id)
                .order_by(Agent.create_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def update_name(self, agent_id: str, agent_name: str) -> Optional[Agent]:
        """更新 Agent 名称。

        Args:
            agent_id: Agent ID。
            agent_name: 新名称。

        Returns:
            更新后的 Agent，不存在时返回 None。
        """
        async with self._storage.session() as db_session:
            agent = await db_session.get(Agent, agent_id)
            if agent is None:
                return None
            agent.agent_name = agent_name
            await db_session.flush()
            await db_session.refresh(agent)

        logger.info("更新 Agent 名称", extra={"agent_id": agent_id, "agent_name": agent_name})
        return agent

    async def update_persona(self, agent_id: str, agent_persona: str) -> Optional[Agent]:
        """更新 Agent 人设描述。

        Args:
            agent_id: Agent ID。
            agent_persona: 新的人设描述。

        Returns:
            更新后的 Agent，不存在时返回 None。
        """
        async with self._storage.session() as db_session:
            agent = await db_session.get(Agent, agent_id)
            if agent is None:
                return None
            agent.agent_persona = agent_persona
            await db_session.flush()
            await db_session.refresh(agent)

        logger.info(
            "更新 Agent 人设",
            extra={"agent_id": agent_id, "persona_length": len(agent_persona)},
        )
        return agent

    async def delete(self, agent_id: str) -> bool:
        """删除 Agent（级联删除关联的 Channel、ChatSession）。"""
        async with self._storage.session() as db_session:
            agent = await db_session.get(Agent, agent_id)
            if agent is None:
                return False
            await db_session.delete(agent)

        logger.info("删除 Agent", extra={"agent_id": agent_id})
        return True


class ChannelDAO:
    """渠道数据访问对象。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def create(
        self,
        channel_type: str,
        user_id: str,
        agent_id: str,
        channel_protocol: str = "websocket",
        channel_id: Optional[str] = None,
    ) -> Channel:
        """创建渠道。

        如果 (user_id, agent_id, channel_type) 已存在，抛出 IntegrityError。

        Args:
            channel_type: 用户交互渠道（web_chat/cli/dingtalk/wechat）。
            user_id: 所属用户 ID。
            agent_id: 接入的 Agent ID。
            channel_protocol: 底层通信协议（websocket/rest_api/sse）。
            channel_id: 可选的渠道 ID，省略时自动生成。

        Returns:
            创建的 Channel 实例。

        Raises:
            IntegrityError: 违反唯一约束 (user_id, agent_id, channel_type)。
        """
        channel = Channel(
            channel_type=channel_type,
            channel_protocol=channel_protocol,
            user_id=user_id,
            agent_id=agent_id,
        )
        if channel_id is not None:
            channel.channel_id = channel_id

        async with self._storage.session() as db_session:
            db_session.add(channel)
            await db_session.flush()
            await db_session.refresh(channel)

        logger.info(
            "创建渠道",
            extra={
                "channel_id": channel.channel_id,
                "channel_type": channel_type,
                "user_id": user_id,
                "agent_id": agent_id,
            },
        )
        return channel

    async def get_by_id(self, channel_id: str) -> Optional[Channel]:
        """根据 ID 获取渠道。"""
        async with self._storage.session() as db_session:
            return await db_session.get(Channel, channel_id)

    async def get_by_unique_key(
        self, user_id: str, agent_id: str, channel_type: str,
    ) -> Optional[Channel]:
        """根据唯一约束 (user_id, agent_id, channel_type) 获取渠道。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Channel).where(
                    Channel.user_id == user_id,
                    Channel.agent_id == agent_id,
                    Channel.channel_type == channel_type,
                )
            )
            return result.scalar_one_or_none()

    async def get_or_create(
        self,
        channel_type: str,
        user_id: str,
        agent_id: str,
        channel_protocol: str = "websocket",
    ) -> tuple[Channel, bool]:
        """获取或创建渠道。

        根据唯一约束查找，不存在则创建。

        Returns:
            (Channel, created) — created 为 True 表示新创建。
        """
        existing = await self.get_by_unique_key(user_id, agent_id, channel_type)
        if existing is not None:
            return existing, False

        channel = await self.create(
            channel_type=channel_type,
            user_id=user_id,
            agent_id=agent_id,
            channel_protocol=channel_protocol,
        )
        return channel, True

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[Channel]:
        """列出指定用户的所有渠道。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Channel)
                .where(Channel.user_id == user_id)
                .order_by(Channel.create_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def list_by_agent(self, agent_id: str, limit: int = 100) -> list[Channel]:
        """列出指定 Agent 的所有渠道。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Channel)
                .where(Channel.agent_id == agent_id)
                .order_by(Channel.create_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def delete(self, channel_id: str) -> bool:
        """删除渠道（级联删除关联的 ChatSession）。"""
        async with self._storage.session() as db_session:
            channel = await db_session.get(Channel, channel_id)
            if channel is None:
                return False
            await db_session.delete(channel)

        logger.info("删除渠道", extra={"channel_id": channel_id})
        return True


class ChatSessionDAO:
    """会话数据访问对象。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def create(
        self,
        user_id: str,
        agent_id: str,
        channel_id: str,
        session_name: str = "",
        session_id: Optional[str] = None,
    ) -> ChatSession:
        """创建会话。

        Args:
            user_id: 所属用户 ID。
            agent_id: 关联的 Agent ID。
            channel_id: 所属渠道 ID。
            session_name: 会话名称（可选）。
            session_id: 可选的会话 ID，省略时自动生成。

        Returns:
            创建的 ChatSession 实例。
        """
        chat_session = ChatSession(
            session_name=session_name,
            user_id=user_id,
            agent_id=agent_id,
            channel_id=channel_id,
        )
        if session_id is not None:
            chat_session.session_id = session_id

        async with self._storage.session() as db_session:
            db_session.add(chat_session)
            await db_session.flush()
            await db_session.refresh(chat_session)

        logger.info(
            "创建会话",
            extra={
                "session_id": chat_session.session_id,
                "session_name": session_name,
                "user_id": user_id,
                "agent_id": agent_id,
                "channel_id": channel_id,
            },
        )
        return chat_session

    async def get_by_id(self, session_id: str) -> Optional[ChatSession]:
        """根据 ID 获取会话。"""
        async with self._storage.session() as db_session:
            return await db_session.get(ChatSession, session_id)

    async def list_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[ChatSession]:
        """列出指定用户的会话，按更新时间倒序。

        Args:
            user_id: 用户 ID。
            status: 可选的状态过滤（active/closed/archived）。
            limit: 最大返回数量。
        """
        async with self._storage.session() as db_session:
            query = select(ChatSession).where(ChatSession.user_id == user_id)
            if status is not None:
                query = query.where(ChatSession.status == status)
            query = query.order_by(ChatSession.updated_at.desc()).limit(limit)
            result = await db_session.execute(query)
            return list(result.scalars().all())

    async def list_by_channel(
        self,
        channel_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[ChatSession]:
        """列出指定渠道的会话，按更新时间倒序。"""
        async with self._storage.session() as db_session:
            query = select(ChatSession).where(ChatSession.channel_id == channel_id)
            if status is not None:
                query = query.where(ChatSession.status == status)
            query = query.order_by(ChatSession.updated_at.desc()).limit(limit)
            result = await db_session.execute(query)
            return list(result.scalars().all())

    async def list_by_agent(
        self,
        agent_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[ChatSession]:
        """列出指定 Agent 的会话，按更新时间倒序。"""
        async with self._storage.session() as db_session:
            query = select(ChatSession).where(ChatSession.agent_id == agent_id)
            if status is not None:
                query = query.where(ChatSession.status == status)
            query = query.order_by(ChatSession.updated_at.desc()).limit(limit)
            result = await db_session.execute(query)
            return list(result.scalars().all())

    async def update_status(self, session_id: str, status: SessionStatus) -> Optional[ChatSession]:
        """更新会话状态。

        Args:
            session_id: 会话 ID。
            status: 新状态。

        Returns:
            更新后的 ChatSession，不存在时返回 None。
        """
        async with self._storage.session() as db_session:
            chat_session = await db_session.get(ChatSession, session_id)
            if chat_session is None:
                return None
            chat_session.status = status.value
            chat_session.updated_at = datetime.now()
            await db_session.flush()
            await db_session.refresh(chat_session)

        logger.info(
            "更新会话状态",
            extra={"session_id": session_id, "status": status.value},
        )
        return chat_session

    async def touch(self, session_id: str) -> Optional[ChatSession]:
        """更新会话的最后活跃时间。"""
        async with self._storage.session() as db_session:
            chat_session = await db_session.get(ChatSession, session_id)
            if chat_session is None:
                return None
            chat_session.updated_at = datetime.now()
            await db_session.flush()
            await db_session.refresh(chat_session)
        return chat_session

    async def close(self, session_id: str) -> Optional[ChatSession]:
        """关闭会话。"""
        return await self.update_status(session_id, SessionStatus.CLOSED)

    async def archive(self, session_id: str) -> Optional[ChatSession]:
        """归档会话。"""
        return await self.update_status(session_id, SessionStatus.ARCHIVED)

    async def delete(self, session_id: str) -> bool:
        """删除会话。"""
        async with self._storage.session() as db_session:
            chat_session = await db_session.get(ChatSession, session_id)
            if chat_session is None:
                return False
            await db_session.delete(chat_session)

        logger.info("删除会话", extra={"session_id": session_id})
        return True
