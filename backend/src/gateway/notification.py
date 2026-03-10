"""通知通道抽象与路由器。

定义通知系统的核心接口和实现：
- NotificationChannel: 通知通道 Protocol（有状态 / 无状态统一接口）
- NotificationTarget: 通知目标（协议无关的目标标识）
- NotificationMessage: 通知消息体
- SendResult: 发送结果
- NotificationRouter: 多通道路由器
- WebChatNotificationChannel: WebChat 通道实现（通过 ConnectionRegistry + MessageBus）
- DingTalkNotificationChannel: 钉钉通道实现（通过 Webhook）
- TelegramNotificationChannel: Telegram 通道实现（通过 Bot API）

设计原则：
- 有状态通道（WebChat/SSE/CLI）通过 ConnectionRegistry 推送，离线走 Outbox
- 无状态通道（Telegram/DingTalk/Email）通过平台 API 直接推送
- NotificationRouter 支持多通道同时通知
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable

from ..conversation.identity import ChannelType
from ..conversation.dao import DEFAULT_AGENT_ID

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class NotificationTarget:
    """通知目标 — 协议无关的目标标识。

    不同通道使用不同的字段：
    - WebChat: session_id（或 agent_id + channel_type 自动解析）
    - Telegram: chat_id
    - DingTalk: webhook_url 或 user_id
    - Email: email_address

    Attributes:
        agent_id: 目标 Agent ID（用于 Session 解析）。
        session_id: 目标会话 ID（WebChat 直接推送）。
        chat_id: Telegram chat ID。
        webhook_url: DingTalk/Slack Webhook URL。
        user_id: 平台用户 ID。
        email_address: 邮箱地址。
    """
    agent_id: str | None = None
    session_id: str | None = None
    chat_id: str | None = None
    webhook_url: str | None = None
    user_id: str | None = None
    email_address: str | None = None


@dataclass
class NotificationMessage:
    """通知消息体。

    Attributes:
        content: 消息内容。
        title: 通知标题（可选）。
        urgency: 紧急程度（low/normal/high）。
        source: 消息来源（agent/cron/system）。
        message_type: 消息类型（notification/reminder/alert/conversation）。
        metadata: 附加元数据。
        created_at: 创建时间。
    """
    content: str
    title: str | None = None
    urgency: str = "normal"
    source: str = "agent"
    message_type: str = "notification"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_ws_dict(self) -> dict[str, Any]:
        """转换为 WebSocket 推送格式。"""
        return {
            "type": "notification",
            "content": self.content,
            "title": self.title or "",
            "urgency": self.urgency,
            "source": self.source,
            "message_type": self.message_type,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ChannelSendResult:
    """单个通道的发送结果。

    Attributes:
        channel_type: 通道类型。
        delivered: 是否实时投递成功。
        queued: 是否已暂存（有状态通道离线时）。
        session_id: 目标会话 ID（有状态通道）。
        error: 错误信息（如有）。
    """
    channel_type: ChannelType
    delivered: bool = False
    queued: bool = False
    session_id: str = ""
    error: str | None = None


# ============================================================================
# 通知通道 Protocol
# ============================================================================

@runtime_checkable
class NotificationChannel(Protocol):
    """通知通道抽象 — 有状态和无状态通道的统一接口。"""

    @property
    def channel_type(self) -> ChannelType:
        """通道类型。"""
        ...

    @property
    def is_stateful(self) -> bool:
        """是否是有状态通道（需要活跃连接才能推送）。"""
        ...

    async def send(
        self,
        target: NotificationTarget,
        message: NotificationMessage,
    ) -> ChannelSendResult:
        """发送通知。

        Args:
            target: 通知目标。
            message: 通知消息。

        Returns:
            发送结果。
        """
        ...

    async def is_available(self, target: NotificationTarget) -> bool:
        """检查目标是否可达。

        Args:
            target: 通知目标。

        Returns:
            是否可达。
        """
        ...


# ============================================================================
# WebChat 通知通道（有状态）
# ============================================================================

class WebChatNotificationChannel:
    """WebChat 通知通道 — 通过 ConnectionRegistry + MessageBus 推送。

    有状态通道：需要活跃的 WebSocket/SSE 连接才能实时推送。
    用户离线时消息暂存到 Outbox，重连后自动投递。
    """

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.WEB_CHAT

    @property
    def is_stateful(self) -> bool:
        return True

    async def send(
        self,
        target: NotificationTarget,
        message: NotificationMessage,
    ) -> ChannelSendResult:
        """通过 ConnectionRegistry 推送消息。

        流程：
        1. 解析 session_id（直接使用或通过 ActiveSessionResolver 解析）
        2. 通过 MessageBus 发送（自动处理在线推送 / 离线暂存）

        Args:
            target: 通知目标。
            message: 通知消息。

        Returns:
            发送结果。
        """
        from .session_resolver import ActiveSessionResolver
        from .message_bus import MessageBus, OutboundMessage, get_message_bus

        try:
            # 1. 解析 session_id
            session_id = target.session_id
            if not session_id:
                resolver = ActiveSessionResolver()
                session_id = await resolver.resolve(
                    agent_id=target.agent_id or DEFAULT_AGENT_ID,
                    channel_type=ChannelType.WEB_CHAT,
                    auto_create=True,
                )

            # 2. 通过 MessageBus 发送
            bus = get_message_bus()
            outbound = OutboundMessage(
                session_id=session_id,
                message_type=message.message_type,
                content={
                    "content": message.content,
                    "title": message.title or "",
                    "urgency": message.urgency,
                },
                source=message.source,
                created_at=message.created_at,
            )

            result = await bus.send(session_id, outbound)

            return ChannelSendResult(
                channel_type=ChannelType.WEB_CHAT,
                delivered=result.delivered,
                queued=result.queued,
                session_id=session_id,
            )

        except Exception as exc:
            logger.error(
                "WebChat notification failed",
                extra={"error": str(exc), "target": str(target)},
            )
            return ChannelSendResult(
                channel_type=ChannelType.WEB_CHAT,
                delivered=False,
                error=str(exc),
            )

    async def is_available(self, target: NotificationTarget) -> bool:
        """检查目标是否有活跃连接。"""
        from .connection_registry import get_connection_registry

        if target.session_id:
            registry = get_connection_registry()
            return registry.has_connections(target.session_id)

        # 没有 session_id 时，WebChat 总是"可用"的（可以暂存到 outbox）
        return True


# ============================================================================
# DingTalk 通知通道（无状态）
# ============================================================================

class DingTalkNotificationChannel:
    """DingTalk 通知通道 — 通过 Webhook 或 API 推送。

    无状态通道：通过钉钉 Webhook 直接推送，不需要活跃连接。
    """

    def __init__(self, default_webhook: str | None = None) -> None:
        self._default_webhook = default_webhook

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.DINGTALK

    @property
    def is_stateful(self) -> bool:
        return False

    async def send(
        self,
        target: NotificationTarget,
        message: NotificationMessage,
    ) -> ChannelSendResult:
        """通过钉钉 Webhook 推送消息。"""
        webhook_url = target.webhook_url or self._default_webhook
        if not webhook_url:
            return ChannelSendResult(
                channel_type=ChannelType.DINGTALK,
                delivered=False,
                error="No webhook URL configured for DingTalk",
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json={
                        "msgtype": "markdown",
                        "markdown": {
                            "title": message.title or "X-Agent 通知",
                            "text": self._format_message(message),
                        },
                    },
                )

            delivered = response.is_success
            error = None if delivered else f"HTTP {response.status_code}"

            return ChannelSendResult(
                channel_type=ChannelType.DINGTALK,
                delivered=delivered,
                error=error,
            )

        except ImportError:
            return ChannelSendResult(
                channel_type=ChannelType.DINGTALK,
                delivered=False,
                error="httpx not installed, cannot send DingTalk notification",
            )
        except Exception as exc:
            logger.error(
                "DingTalk notification failed",
                extra={"error": str(exc)},
            )
            return ChannelSendResult(
                channel_type=ChannelType.DINGTALK,
                delivered=False,
                error=str(exc),
            )

    async def is_available(self, target: NotificationTarget) -> bool:
        """DingTalk 通道在有 webhook 配置时始终可用。"""
        return bool(target.webhook_url or self._default_webhook)

    @staticmethod
    def _format_message(message: NotificationMessage) -> str:
        """格式化为钉钉 Markdown 消息。"""
        parts: list[str] = []
        if message.title:
            parts.append(f"### {message.title}")
        parts.append(message.content)
        if message.urgency == "high":
            parts.append("\n> ⚠️ 紧急通知")
        return "\n\n".join(parts)


# ============================================================================
# Telegram 通知通道（无状态）
# ============================================================================

class TelegramNotificationChannel:
    """Telegram 通知通道 — 通过 Bot API 推送。

    无状态通道：通过 Telegram Bot API 直接推送，不需要活跃连接。
    """

    def __init__(
        self,
        bot_token: str | None = None,
        default_chat_id: str | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._default_chat_id = default_chat_id

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.TELEGRAM

    @property
    def is_stateful(self) -> bool:
        return False

    async def send(
        self,
        target: NotificationTarget,
        message: NotificationMessage,
    ) -> ChannelSendResult:
        """通过 Telegram Bot API 推送消息。"""
        if not self._bot_token:
            return ChannelSendResult(
                channel_type=ChannelType.TELEGRAM,
                delivered=False,
                error="Telegram bot_token not configured",
            )

        chat_id = target.chat_id or self._default_chat_id
        if not chat_id:
            return ChannelSendResult(
                channel_type=ChannelType.TELEGRAM,
                delivered=False,
                error="No chat_id configured for Telegram",
            )

        try:
            import httpx

            text = self._format_message(message)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )

            delivered = response.is_success
            error = None if delivered else f"HTTP {response.status_code}: {response.text}"

            return ChannelSendResult(
                channel_type=ChannelType.TELEGRAM,
                delivered=delivered,
                error=error,
            )

        except ImportError:
            return ChannelSendResult(
                channel_type=ChannelType.TELEGRAM,
                delivered=False,
                error="httpx not installed, cannot send Telegram notification",
            )
        except Exception as exc:
            logger.error(
                "Telegram notification failed",
                extra={"error": str(exc)},
            )
            return ChannelSendResult(
                channel_type=ChannelType.TELEGRAM,
                delivered=False,
                error=str(exc),
            )

    async def is_available(self, target: NotificationTarget) -> bool:
        """Telegram 通道在有 bot_token 和 chat_id 时可用。"""
        chat_id = target.chat_id or self._default_chat_id
        return bool(self._bot_token and chat_id)

    @staticmethod
    def _format_message(message: NotificationMessage) -> str:
        """格式化为 Telegram Markdown 消息。"""
        parts: list[str] = []
        if message.title:
            parts.append(f"*{message.title}*")
        parts.append(message.content)
        if message.urgency == "high":
            parts.append("\n⚠️ _紧急通知_")
        return "\n\n".join(parts)


# ============================================================================
# 通知路由器
# ============================================================================

class NotificationRouter:
    """通知路由器 — 根据目标自动选择通知通道。

    支持多通道同时通知（如 WebChat + DingTalk 同时推送）。

    路由策略：
    1. 指定 targets → 按 target 中的信息路由到对应通道
    2. 指定 channel_types → 向指定类型的所有已注册通道发送
    3. broadcast=True → 向所有已注册通道广播
    4. 都没指定 → 使用默认通道（WebChat）

    典型用法::

        router = get_notification_router()

        # 向 WebChat 推送
        results = await router.notify(
            NotificationMessage(content="你好"),
            targets=[NotificationTarget(agent_id="agent-001")],
        )

        # 向多个通道推送
        results = await router.notify(
            NotificationMessage(content="紧急通知", urgency="high"),
            channel_types=[ChannelType.WEB_CHAT, ChannelType.DINGTALK],
            targets=[NotificationTarget(
                agent_id="agent-001",
                webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            )],
        )
    """

    _instance: Optional[NotificationRouter] = None

    def __new__(cls) -> NotificationRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._channels: dict[ChannelType, NotificationChannel] = {}
            # 默认注册 WebChat 通道
            self.register(WebChatNotificationChannel())
            self._initialized = True

    def register(self, channel: NotificationChannel) -> None:
        """注册通知通道。

        Args:
            channel: 通知通道实例。
        """
        self._channels[channel.channel_type] = channel
        logger.info(
            "Notification channel registered",
            extra={
                "channel_type": channel.channel_type.value,
                "is_stateful": channel.is_stateful,
            },
        )

    def get_channel(self, channel_type: ChannelType) -> NotificationChannel | None:
        """获取指定类型的通知通道。

        Args:
            channel_type: 通道类型。

        Returns:
            通知通道实例，未注册时返回 None。
        """
        return self._channels.get(channel_type)

    def list_channels(self) -> list[ChannelType]:
        """列出所有已注册的通道类型。"""
        return list(self._channels.keys())

    async def notify(
        self,
        message: NotificationMessage,
        *,
        targets: list[NotificationTarget] | None = None,
        channel_types: list[ChannelType] | None = None,
        broadcast: bool = False,
    ) -> list[ChannelSendResult]:
        """发送通知。

        Args:
            message: 通知消息。
            targets: 通知目标列表（每个 target 可包含多个通道的标识）。
            channel_types: 指定通道类型列表。
            broadcast: 是否向所有已注册通道广播。

        Returns:
            每个通道的发送结果列表。
        """
        results: list[ChannelSendResult] = []

        # 确定要使用的通道
        if broadcast:
            selected_channels = list(self._channels.values())
        elif channel_types:
            selected_channels = [
                self._channels[ct]
                for ct in channel_types
                if ct in self._channels
            ]
        elif targets:
            # 根据 target 中的字段推断通道
            selected_channels = self._infer_channels_from_targets(targets)
        else:
            # 默认使用 WebChat
            webchat = self._channels.get(ChannelType.WEB_CHAT)
            selected_channels = [webchat] if webchat else []

        if not selected_channels:
            logger.warning(
                "No notification channels available",
                extra={"channel_types": [ct.value for ct in (channel_types or [])]},
            )
            return results

        # 确定目标
        effective_targets = targets or [NotificationTarget(agent_id=DEFAULT_AGENT_ID)]

        # 向每个通道发送
        for channel in selected_channels:
            for target in effective_targets:
                try:
                    result = await channel.send(target, message)
                    results.append(result)
                except Exception as exc:
                    logger.error(
                        "Notification send failed",
                        extra={
                            "channel_type": channel.channel_type.value,
                            "error": str(exc),
                        },
                    )
                    results.append(ChannelSendResult(
                        channel_type=channel.channel_type,
                        delivered=False,
                        error=str(exc),
                    ))

        delivered_count = sum(1 for r in results if r.delivered)
        queued_count = sum(1 for r in results if r.queued)
        logger.info(
            "Notification routing completed",
            extra={
                "total_channels": len(selected_channels),
                "total_targets": len(effective_targets),
                "delivered": delivered_count,
                "queued": queued_count,
            },
        )

        return results

    def _infer_channels_from_targets(
        self,
        targets: list[NotificationTarget],
    ) -> list[NotificationChannel]:
        """根据 target 中的字段推断应使用的通道。

        推断规则：
        - 有 session_id 或 agent_id → WebChat
        - 有 chat_id → Telegram
        - 有 webhook_url → DingTalk
        - 有 email_address → Email

        Args:
            targets: 通知目标列表。

        Returns:
            推断出的通道列表（去重）。
        """
        inferred_types: set[ChannelType] = set()

        for target in targets:
            if target.session_id or target.agent_id:
                inferred_types.add(ChannelType.WEB_CHAT)
            if target.chat_id:
                inferred_types.add(ChannelType.TELEGRAM)
            if target.webhook_url:
                inferred_types.add(ChannelType.DINGTALK)
            if target.email_address:
                inferred_types.add(ChannelType.EMAIL)

        # 如果没有推断出任何通道，默认 WebChat
        if not inferred_types:
            inferred_types.add(ChannelType.WEB_CHAT)

        return [
            self._channels[ct]
            for ct in inferred_types
            if ct in self._channels
        ]


# ---------------------------------------------------------------------------
# 模块级单例访问
# ---------------------------------------------------------------------------

def get_notification_router() -> NotificationRouter:
    """获取全局 NotificationRouter 单例。"""
    return NotificationRouter()
