"""核心实体模型定义（SQLAlchemy ORM）。

包含系统的四个核心业务实体：
- User: 用户
- Agent: 智能体
- Channel: 渠道（用户通过渠道与 Agent 交互）
- ChatSession: 会话（一次完整的对话）

这些实体是持久化的业务模型，与 identity.py 中的运行时身份对象互补：
Identity 是请求级的不可变值对象，而这些实体跨请求持久存在。
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...models.base import Base


class SessionStatus(str, Enum):
    """会话生命周期状态。

    - ACTIVE: 活跃中，用户可继续对话。
    - CLOSED: 已关闭，用户主动结束。
    - ARCHIVED: 已归档，系统自动归档或用户手动归档。
    """
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class User(Base):
    """用户实体。

    系统中的终端用户，可以创建多个 Agent 和 Channel。
    """
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True,
    )

    # 关系：一个用户拥有多个 Agent
    agents: Mapped[list["Agent"]] = relationship(
        "Agent", back_populates="owner", cascade="all, delete-orphan",
    )
    # 关系：一个用户拥有多个 Channel
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", back_populates="user", cascade="all, delete-orphan",
    )
    # 关系：一个用户拥有多个会话
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, name={self.name})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class Agent(Base):
    """智能体实体。

    由用户创建的 AI Agent，具有特定的类型和人设。
    一个用户可以创建多个 Agent。
    """
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="main",
    )
    agent_persona: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), index=True,
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True,
    )

    # 关系：所属用户
    owner: Mapped["User"] = relationship("User", back_populates="agents")
    # 关系：一个 Agent 可以接入多个 Channel
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", back_populates="agent", cascade="all, delete-orphan",
    )
    # 关系：一个 Agent 参与多个会话
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="agent", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Agent(agent_id={self.agent_id}, name={self.agent_name}, type={self.agent_type})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "agent_persona": self.agent_persona,
            "user_id": self.user_id,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class Channel(Base):
    """渠道实体。

    用户通过渠道与 Agent 交互。同一用户在同一渠道类型下
    只能与同一 Agent 建立一个 Channel。

    唯一约束: (user_id, agent_id, channel_type)
    """
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", "channel_type", name="uq_user_agent_channel"),
    )

    channel_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    channel_protocol: Mapped[str] = mapped_column(
        String(20), nullable=False, default="websocket",
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.agent_id", ondelete="CASCADE"), index=True,
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True,
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="channels")
    agent: Mapped["Agent"] = relationship("Agent", back_populates="channels")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession", back_populates="channel", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Channel(channel_id={self.channel_id}, type={self.channel_type})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "channel_protocol": self.channel_protocol,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class ChatSession(Base):
    """会话实体。

    用户与 Agent 之间的一次完整对话。
    通过 Channel 建立，包含生命周期状态管理。

    agent_id 为冗余字段（可通过 channel_id → Channel.agent_id 获取），
    直接存储以提高查询效率和语义清晰度。
    """
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()),
    )
    session_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.agent_id", ondelete="CASCADE"), index=True,
    )
    channel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("channels.channel_id", ondelete="CASCADE"), index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SessionStatus.ACTIVE.value,
    )
    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), index=True,
    )

    # 关系
    user: Mapped["User"] = relationship("User", back_populates="chat_sessions")
    agent: Mapped["Agent"] = relationship("Agent", back_populates="chat_sessions")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="chat_sessions")

    def __repr__(self) -> str:
        return f"<ChatSession(session_id={self.session_id}, name={self.session_name}, status={self.status})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "status": self.status,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
