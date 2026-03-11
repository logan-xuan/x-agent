"""统一消息信封定义。

Envelope 是 Gateway 的核心抽象——一个协议无关的消息容器。
所有上游端点（WebChat / CLI / Channel）将各自协议的消息
转换为 Envelope 后交给 Gateway 处理。

设计原则：
- 协议无关：不包含任何特定协议的细节（如 WebSocket frame）
- 自描述：携带完整的路由信息（渠道、用户、Agent）
- 不可变风格：创建后不应修改字段
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..conversation.identity import ChannelType, ChannelProtocol


class EnvelopeIntent(str, Enum):
    """消息意图。

    描述上游端点发送此消息的目的：
    - CHAT: 普通对话消息，需要 Agent 处理
    - ABORT: 中断当前正在进行的 Agent 处理
    - COMMAND: 系统命令（如 /config, /tools），由 Gateway 直接处理
    - PING: 心跳探测，Gateway 直接返回 PONG
    """

    CHAT = "chat"
    ABORT = "abort"
    COMMAND = "command"
    PING = "ping"


@dataclass
class Envelope:
    """协议无关的统一消息信封。

    所有上游端点（WebChat / CLI / Channel）将各自协议的消息
    转换为 Envelope 后交给 GatewayDispatcher 处理。

    Attributes:
        message_id:       消息唯一标识，用于去重和追踪。
        session_id:       会话标识，同一对话的消息共享此 ID。
        content:          用户消息文本内容。
        channel_type:     消息来源渠道（WEB_CHAT / CLI / DINGTALK 等）。
        channel_protocol: 底层通信协议（WEBSOCKET / REST_API / SSE）。
        images:           附带的图片列表，每项为 (base64_data, mime_type)。
        user_id:          终端用户标识，用于多用户场景。
        channel_id:       通道标识（如 WebSocket 连接 ID、钉钉群 ID）。
        agent_id:         目标 Agent ID，None 时使用默认 Agent。
        agent_name:       目标 Agent 名称，用于按名称路由（优先级低于 agent_id）。
        metadata:         渠道特有的附加数据（如钉钉的 webhook token）。
        intent:           消息意图，决定 Gateway 的处理方式。
    """

    message_id: str
    session_id: str
    content: str
    channel_type: ChannelType
    channel_protocol: ChannelProtocol

    # 可选字段
    images: list[tuple[str, str]] = field(default_factory=list)
    user_id: str | None = None
    channel_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    peer_id: str | None = None  # Peer ID（用户 ID、群组 ID 等），用于 bindings 匹配
    peer_kind: str = "user"  # Peer 类型（user、group、channel），用于 bindings 匹配
    metadata: dict[str, Any] = field(default_factory=dict)
    intent: EnvelopeIntent = EnvelopeIntent.CHAT

    @classmethod
    def create_chat(
        cls,
        content: str,
        session_id: str,
        channel_type: ChannelType,
        channel_protocol: ChannelProtocol,
        *,
        images: list[tuple[str, str]] | None = None,
        user_id: str | None = None,
        channel_id: str | None = None,
        agent_id: str | None = None,
        agent_name: str | None = None,
        peer_id: str | None = None,
        peer_kind: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> Envelope:
        """创建对话类型的 Envelope。

        Args:
            content: 用户消息文本。
            session_id: 会话标识。
            channel_type: 消息来源渠道。
            channel_protocol: 底层通信协议。
            images: 附带的图片列表。
            user_id: 终端用户标识。
            channel_id: 通道标识。
            agent_id: 目标 Agent ID。
            agent_name: 目标 Agent 名称。
            peer_id: Peer ID（用户 ID、群组 ID 等），用于 bindings 匹配。
            peer_kind: Peer 类型（user、group、channel），用于 bindings 匹配。
            metadata: 附加数据。

        Returns:
            配置好的 Envelope 实例。
        """
        return cls(
            message_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            content=content,
            channel_type=channel_type,
            channel_protocol=channel_protocol,
            images=images or [],
            user_id=user_id,
            channel_id=channel_id,
            agent_id=agent_id,
            agent_name=agent_name,
            peer_id=peer_id,
            peer_kind=peer_kind,
            metadata=metadata or {},
            intent=EnvelopeIntent.CHAT,
        )

    @classmethod
    def create_abort(
        cls,
        session_id: str,
        channel_type: ChannelType,
        channel_protocol: ChannelProtocol,
    ) -> Envelope:
        """创建中断类型的 Envelope。

        Args:
            session_id: 要中断的会话标识。
            channel_type: 消息来源渠道。
            channel_protocol: 底层通信协议。

        Returns:
            中断意图的 Envelope 实例。
        """
        return cls(
            message_id=str(uuid.uuid4())[:12],
            session_id=session_id,
            content="",
            channel_type=channel_type,
            channel_protocol=channel_protocol,
            intent=EnvelopeIntent.ABORT,
        )

    @classmethod
    def create_ping(
        cls,
        channel_type: ChannelType,
        channel_protocol: ChannelProtocol,
    ) -> Envelope:
        """创建心跳探测的 Envelope。

        Args:
            channel_type: 消息来源渠道。
            channel_protocol: 底层通信协议。

        Returns:
            心跳意图的 Envelope 实例。
        """
        return cls(
            message_id=str(uuid.uuid4())[:12],
            session_id="",
            content="",
            channel_type=channel_type,
            channel_protocol=channel_protocol,
            intent=EnvelopeIntent.PING,
        )

    def validate(self) -> list[str]:
        """验证 Envelope 的必填字段。

        这是 Envelope 验证的唯一入口，GatewayDispatcher 直接调用此方法。

        Returns:
            错误消息列表，空列表表示验证通过。
        """
        errors: list[str] = []

        if not self.message_id:
            errors.append("message_id is required")

        if self.intent == EnvelopeIntent.CHAT:
            if not self.content or not self.content.strip():
                errors.append("CHAT intent requires non-empty content")
            if not self.session_id:
                errors.append("CHAT intent requires session_id")

        if self.intent == EnvelopeIntent.ABORT:
            if not self.session_id:
                errors.append("ABORT intent requires session_id")

        return errors

    def to_log_dict(self) -> dict[str, Any]:
        """转换为日志字典（隐藏图片数据）。

        Returns:
            适合日志输出的字典。
        """
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "content_length": len(self.content),
            "channel_type": self.channel_type.value,
            "channel_protocol": self.channel_protocol.value,
            "image_count": len(self.images),
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "intent": self.intent.value,
            "metadata_keys": list(self.metadata.keys()),
        }
