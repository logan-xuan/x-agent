"""核心实体模型定义（内存实体 + 数据库实体混合）。

包含系统的核心业务实体：
- User: 用户（保留数据库持久化）
- Agent: 智能体（从 x-agent.yaml 配置加载，内存实体）
- Channel: 渠道（从 x-agent.yaml 配置加载，内存实体）

Agent 和 Channel 不再读取数据库，而是直接从 x-agent.yaml 的 multi_agent 配置中加载，
确保配置与运行时行为的一致性。

Session 相关模型已迁移到 backend/src/models/session.py（Session 模型，sessions 表）。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ...config.manager import get_config
from ...models.base import Base

if TYPE_CHECKING:
    pass


class SessionStatus(StrEnum):
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

    系统中的终端用户，保留数据库持久化。
    """

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        index=True,
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


@dataclass
class Agent:
    """智能体实体（内存实体，配置驱动）。

    从 x-agent.yaml 的 multi_agent.agents 配置加载，
    不再持久化到数据库。

    Attributes:
        agent_id: 唯一标识符（对应配置中的 id）
        agent_name: 显示名称
        agent_type: 类型（main/specialized）
        agent_persona: 人设/系统提示词
        workspace: 工作空间目录
        feature: 特性标签
        user_id: 关联用户ID
        model_config: 模型配置
        enable_memory: 是否启用记忆
        enable_plan: 是否启用计划
        enable_context_compression: 是否启用上下文压缩
        enable_experience_learning: 是否启用经验学习
    """

    agent_id: str
    agent_name: str
    agent_type: str = "main"
    agent_persona: str = ""
    workspace: str = ""
    feature: str = ""
    user_id: str = "system"
    model_config: dict = field(default_factory=dict)
    voice_config: dict = field(default_factory=dict)
    enable_memory: bool = True
    enable_plan: bool = False
    enable_context_compression: bool = True
    enable_experience_learning: bool = True

    @classmethod
    def from_config(cls, agent_id: str) -> "Agent | None":
        """从配置加载 Agent。

        Args:
            agent_id: Agent 标识符

        Returns:
            Agent 实例或 None（如果不存在）
        """
        config = get_config()
        agent_cfg = config.multi_agent.get_agent(agent_id)
        if not agent_cfg:
            return None

        return cls(
            agent_id=agent_cfg.id,
            agent_name=agent_cfg.name,
            agent_type=agent_cfg.type,
            agent_persona=agent_cfg.persona,
            workspace=agent_cfg.workspace,
            feature=agent_cfg.features,
            model_config={
                "name": agent_cfg.model.name,
                "temperature": agent_cfg.model.temperature,
                "max_tokens": agent_cfg.model.max_tokens,
            },
            voice_config=agent_cfg.voice.model_dump(),
            enable_memory=agent_cfg.enable_memory,
            enable_plan=agent_cfg.enable_plan,
            enable_context_compression=agent_cfg.enable_context_compression,
            enable_experience_learning=agent_cfg.enable_experience_learning,
        )

    @classmethod
    def list_all(cls) -> list["Agent"]:
        """获取所有配置的 Agent。

        Returns:
            Agent 列表
        """
        config = get_config()
        agents: list[Agent] = []
        for a in config.multi_agent.agents:
            agent = cls.from_config(a.id)
            if agent is not None:
                agents.append(agent)
        return agents

    def __repr__(self) -> str:
        return f"<Agent(agent_id={self.agent_id}, name={self.agent_name}, type={self.agent_type})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "agent_persona": self.agent_persona,
            "workspace": self.workspace,
            "feature": self.feature,
            "user_id": self.user_id,
            "model_config": self.model_config,
            "voice_config": self.voice_config,
            "enable_memory": self.enable_memory,
            "enable_plan": self.enable_plan,
        }


@dataclass
class Channel:
    """渠道实体（内存实体，配置驱动）。

    从 x-agent.yaml 的 multi_agent.channels 配置加载，
    不再持久化到数据库。

    Attributes:
        channel_id: 唯一标识符（对应配置中的 id）
        channel_type: 渠道类型
        channel_protocol: 通信协议
        user_id: 关联用户ID
        agent_id: 关联的 Agent ID
        enabled: 是否启用
        config: 渠道特定配置
    """

    channel_id: str
    channel_type: str
    channel_protocol: str = "websocket"
    user_id: str = "system"
    agent_id: str = ""
    enabled: bool = True
    config: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, channel_id: str) -> "Channel | None":
        """从配置加载 Channel。

        支持：
        1. 配置中定义的 Channel（第三方集成）
        2. 系统自动生成的默认 Channel（web/cli）

        Args:
            channel_id: Channel 标识符，格式：
                - 配置 Channel: 任意 ID
                - 默认 web: {agent_id}-web
                - 默认 cli: {agent_id}-cli

        Returns:
            Channel 实例或 None（如果不存在）
        """
        config = get_config()

        # 1. 尝试从配置加载（第三方集成 Channel）
        ch_cfg = config.multi_agent.get_channel(channel_id)
        if ch_cfg:
            return cls(
                channel_id=ch_cfg.id,
                channel_type=ch_cfg.type,
                channel_protocol=ch_cfg.protocol,
                agent_id=ch_cfg.agent_id or "",  # agent_id 现在是可选的
                user_id=ch_cfg.default_user,
                enabled=ch_cfg.enabled,
                config=ch_cfg.config,
            )

        # 2. 尝试解析为默认 Channel（web/cli）
        # 格式: {agent_id}-web 或 {agent_id}-cli
        if channel_id.endswith("-web"):
            agent_id = channel_id[:-4]  # 去掉 "-web"
            if config.multi_agent.get_agent(agent_id):
                return cls(
                    channel_id=channel_id,
                    channel_type="web",
                    channel_protocol="websocket",
                    agent_id=agent_id,
                    user_id="admin",
                    enabled=True,
                    config={},
                )
        elif channel_id.endswith("-cli"):
            agent_id = channel_id[:-4]  # 去掉 "-cli"
            if config.multi_agent.get_agent(agent_id):
                return cls(
                    channel_id=channel_id,
                    channel_type="cli",
                    channel_protocol="stdio",
                    agent_id=agent_id,
                    user_id="admin",
                    enabled=True,
                    config={},
                )

        return None

    def resolve_agent_id(self, peer_id: str | None = None, peer_kind: str = "user") -> str | None:
        """解析此 Channel 的 Agent ID（考虑 bindings）。

        优先级：
        1. 如果 channel.agent_id 不为空，使用它（向后兼容）
        2. 否则，通过 bindings 匹配 channel + peer -> agent

        Args:
            peer_id: Peer ID（用户 ID、群组 ID 等）
            peer_kind: Peer 类型（user、group、channel）

        Returns:
            Agent ID 或 None
        """
        # 优先使用 channel.agent_id（向后兼容）
        if self.agent_id:
            return self.agent_id

        # 使用 bindings 解析
        config = get_config()
        return config.multi_agent.resolve_agent_for_channel(self.channel_id, peer_id, peer_kind)

    @classmethod
    def list_all(cls) -> list["Channel"]:
        """获取所有 Channel（仅返回配置中定义的 Channel）。

        Returns:
            Channel 列表
        """
        config = get_config()
        channels: list[Channel] = []

        for c in config.multi_agent.channels:
            ch = cls.from_config(c.id)
            if ch:
                channels.append(ch)

        return channels

    @classmethod
    def list_for_agent(cls, agent_id: str) -> list["Channel"]:
        """获取指定 Agent 的所有 Channel。

        包括：
        1. 配置中定义的 Channel（第三方集成，如 slack、email）
        2. 系统自动生成的 web 和 cli Channel（每个 Agent 默认支持）

        Args:
            agent_id: Agent 标识符

        Returns:
            Channel 列表
        """
        config = get_config()
        channels: list[Channel] = []

        # 1. 添加配置中定义的 Channel（第三方集成）
        cfg_channels = config.multi_agent.get_channels_for_agent(agent_id)
        for c in cfg_channels:
            ch = cls.from_config(c.id)
            if ch:
                channels.append(ch)

        # 2. 添加系统自动生成的 web 和 cli Channel
        # 每个 Agent 默认支持 web (websocket) 和 cli (stdio) 两种交互方式
        channels.extend(cls._get_default_channels(agent_id))

        return channels

    @classmethod
    def _get_default_channels(cls, agent_id: str) -> list["Channel"]:
        """获取 Agent 的默认 Channel（web 和 cli）。

        Args:
            agent_id: Agent 标识符

        Returns:
            默认 Channel 列表（web + cli）
        """
        return [
            cls(
                channel_id=f"{agent_id}-web",
                channel_type="web",
                channel_protocol="websocket",
                agent_id=agent_id,
                user_id="admin",  # 与 DEFAULT_USER_ID 保持一致
                enabled=True,
                config={},
            ),
            cls(
                channel_id=f"{agent_id}-cli",
                channel_type="cli",
                channel_protocol="stdio",
                agent_id=agent_id,
                user_id="admin",  # 与 DEFAULT_USER_ID 保持一致
                enabled=True,
                config={},
            ),
        ]

    def __repr__(self) -> str:
        return f"<Channel(channel_id={self.channel_id}, type={self.channel_type}, agent_id={self.agent_id})>"

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "channel_protocol": self.channel_protocol,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "enabled": self.enabled,
            "config": self.config,
        }
