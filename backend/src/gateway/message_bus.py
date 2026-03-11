"""消息总线 — 在线推送 + 离线暂存。

MessageBus 是 ConnectionRegistry 和 Outbox 的上层封装，
统一管理在线推送和离线暂存。

推送策略：
1. 先尝试通过 ConnectionRegistry 实时推送
2. 推送失败（用户离线）→ 写入 outbox 表
3. 用户重连时 → 拉取并投递 outbox 中的未读消息

设计原则：
- 调用方无需关心用户是否在线，统一调用 MessageBus.send()
- Outbox 使用 SQLite 持久化，确保消息不丢失
- 支持按 session_id 拉取未投递消息（重连时使用）
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .connection_registry import (
    ConnectionRegistry,
    PushResult,
    PushStatus,
    get_connection_registry,
)

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DeliveryStatus(str, Enum):
    """消息投递状态。"""
    DELIVERED = "delivered"
    QUEUED = "queued"
    FAILED = "failed"


@dataclass
class OutboundMessage:
    """出站消息数据模型。

    Attributes:
        message_id: 消息唯一标识。
        session_id: 目标会话 ID（如果已知）。
        agent_id: 目标 Agent ID（用于暂存和投递）。
        message_type: 消息类型（notification/reminder/alert/conversation）。
        content: 消息内容（JSON 序列化的字典）。
        source: 消息来源（agent/cron/system）。
        created_at: 创建时间。
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    agent_id: str = ""
    message_type: str = "notification"
    content: dict[str, Any] = field(default_factory=dict)
    source: str = "system"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_ws_dict(self) -> dict[str, Any]:
        """转换为 WebSocket 推送格式。

        Returns:
            适合通过 ConnectionHandle.send() 发送的字典。
        """
        return {
            "type": "notification",
            "message_id": self.message_id,
            "message_type": self.message_type,
            "content": self.content.get("content", ""),
            "title": self.content.get("title", ""),
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class SendResult:
    """消息发送结果。

    Attributes:
        delivered: 是否实时投递成功。
        queued: 是否已暂存到 outbox。
        session_id: 目标会话 ID。
        error: 错误信息（如有）。
    """
    delivered: bool = False
    queued: bool = False
    session_id: str = ""
    error: str | None = None


class OutboxStore:
    """Outbox 持久化存储。

    使用 SQLite 存储离线消息，确保用户重连时能拉取到未读消息。
    复用现有的 StorageService 基础设施。
    """

    def __init__(self) -> None:
        self._initialized = False

    async def _ensure_table(self) -> None:
        """确保 outbox 表存在。"""
        if self._initialized:
            return

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                await db_session.execute(
                    sa.text(
                        """
                        CREATE TABLE IF NOT EXISTS outbox_messages (
                            message_id TEXT PRIMARY KEY,
                            session_id TEXT,
                            agent_id TEXT NOT NULL,
                            message_type TEXT NOT NULL DEFAULT 'notification',
                            content TEXT NOT NULL,
                            source TEXT NOT NULL DEFAULT 'system',
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            delivered_at TIMESTAMP,
                            is_delivered INTEGER NOT NULL DEFAULT 0
                        )
                        """
                    )
                )
                await db_session.execute(
                    sa.text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_outbox_session_delivered
                        ON outbox_messages (session_id, is_delivered)
                        """
                    )
                )
                await db_session.execute(
                    sa.text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_outbox_agent_delivered
                        ON outbox_messages (agent_id, is_delivered)
                        """
                    )
                )
            self._initialized = True
        except Exception as exc:
            logger.warning(
                "Failed to initialize outbox table",
                extra={"error": str(exc)},
            )

    async def save(self, message: OutboundMessage) -> None:
        """保存消息到 outbox。

        Args:
            message: 出站消息。
        """
        await self._ensure_table()

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                await db_session.execute(
                    sa.text(
                        """
                        INSERT INTO outbox_messages
                            (message_id, session_id, agent_id, message_type, content, source, created_at, is_delivered)
                        VALUES
                            (:message_id, :session_id, :agent_id, :message_type, :content, :source, :created_at, 0)
                        """
                    ),
                    {
                        "message_id": message.message_id,
                        "session_id": message.session_id or None,
                        "agent_id": message.agent_id,
                        "message_type": message.message_type,
                        "content": json.dumps(message.content, ensure_ascii=False),
                        "source": message.source,
                        "created_at": message.created_at.isoformat(),
                    },
                )

            logger.debug(
                "Message saved to outbox",
                extra={
                    "message_id": message.message_id,
                    "session_id": message.session_id,
                    "agent_id": message.agent_id,
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to save message to outbox",
                extra={
                    "message_id": message.message_id,
                    "session_id": message.session_id,
                    "agent_id": message.agent_id,
                    "error": str(exc),
                },
            )

    async def get_pending(self, session_id: str, limit: int = 50) -> list[OutboundMessage]:
        """获取指定 session 的未投递消息。

        Args:
            session_id: 会话 ID。
            limit: 最大返回数量。

        Returns:
            未投递的 OutboundMessage 列表，按创建时间升序。
        """
        await self._ensure_table()

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                result = await db_session.execute(
                    sa.text(
                        """
                        SELECT message_id, session_id, message_type, content, source, created_at
                        FROM outbox_messages
                        WHERE session_id = :session_id AND is_delivered = 0
                        ORDER BY created_at ASC
                        LIMIT :limit
                        """
                    ),
                    {"session_id": session_id, "limit": limit},
                )
                rows = result.fetchall()

            return self._rows_to_messages(rows)
        except Exception as exc:
            logger.error(
                "Failed to get pending outbox messages",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return []

    async def get_pending_by_agent(self, agent_id: str, limit: int = 50) -> list[OutboundMessage]:
        """获取指定 agent 的未投递消息（session_id 为空的暂存消息）。

        当通知发送时目标 agent 没有活跃 session，消息会以空 session_id 暂存。
        用户重连后，通过 agent_id 查找这些消息并投递。

        Args:
            agent_id: Agent ID。
            limit: 最大返回数量。

        Returns:
            未投递的 OutboundMessage 列表，按创建时间升序。
        """
        await self._ensure_table()

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                result = await db_session.execute(
                    sa.text(
                        """
                        SELECT message_id, session_id, message_type, content, source, created_at
                        FROM outbox_messages
                        WHERE agent_id = :agent_id
                          AND (session_id IS NULL OR session_id = '')
                          AND is_delivered = 0
                        ORDER BY created_at ASC
                        LIMIT :limit
                        """
                    ),
                    {"agent_id": agent_id, "limit": limit},
                )
                rows = result.fetchall()

            return self._rows_to_messages(rows)
        except Exception as exc:
            logger.error(
                "Failed to get pending outbox messages by agent",
                extra={"agent_id": agent_id, "error": str(exc)},
            )
            return []

    @staticmethod
    def _rows_to_messages(rows) -> list[OutboundMessage]:
        """将数据库行转换为 OutboundMessage 列表。"""
        messages: list[OutboundMessage] = []
        for row in rows:
            messages.append(OutboundMessage(
                message_id=row[0],
                session_id=row[1] or "",
                message_type=row[2],
                content=json.loads(row[3]) if isinstance(row[3], str) else row[3],
                source=row[4],
                created_at=datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5],
            ))
        return messages

    async def mark_delivered(self, message_ids: list[str]) -> None:
        """标记消息为已投递。

        Args:
            message_ids: 要标记的消息 ID 列表。
        """
        if not message_ids:
            return

        await self._ensure_table()

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                placeholders = ", ".join(f":id_{i}" for i in range(len(message_ids)))
                params = {f"id_{i}": mid for i, mid in enumerate(message_ids)}
                params["now"] = datetime.utcnow().isoformat()

                await db_session.execute(
                    sa.text(
                        f"""
                        UPDATE outbox_messages
                        SET is_delivered = 1, delivered_at = :now
                        WHERE message_id IN ({placeholders})
                        """
                    ),
                    params,
                )

            logger.debug(
                "Outbox messages marked as delivered",
                extra={"count": len(message_ids)},
            )
        except Exception as exc:
            logger.error(
                "Failed to mark outbox messages as delivered",
                extra={"error": str(exc)},
            )

    async def cleanup(self, max_age_days: int = 7) -> int:
        """清理已投递的过期消息。

        Args:
            max_age_days: 保留天数，超过此天数的已投递消息将被删除。

        Returns:
            删除的消息数量。
        """
        await self._ensure_table()

        try:
            from ..services.storage import get_storage_service
            import sqlalchemy as sa

            storage = get_storage_service()
            async with storage.session() as db_session:
                result = await db_session.execute(
                    sa.text(
                        """
                        DELETE FROM outbox_messages
                        WHERE is_delivered = 1
                        AND delivered_at < datetime('now', :age_offset)
                        """
                    ),
                    {"age_offset": f"-{max_age_days} days"},
                )
                deleted_count = result.rowcount or 0  # type: ignore[union-attr]

            if deleted_count > 0:
                logger.info(
                    "Outbox cleanup completed",
                    extra={"deleted_count": deleted_count, "max_age_days": max_age_days},
                )
            return deleted_count
        except Exception as exc:
            logger.error(
                "Failed to cleanup outbox",
                extra={"error": str(exc)},
            )
            return 0


class MessageBus:
    """消息总线 — 在线推送 + 离线暂存。

    推送策略：
    1. 先尝试通过 ConnectionRegistry 实时推送
    2. 推送失败（用户离线）→ 写入 outbox 表
    3. 用户重连时 → 拉取并投递 outbox 中的未读消息

    典型用法::

        bus = get_message_bus()

        # 发送消息（自动处理在线/离线）
        result = await bus.send("sess-123", OutboundMessage(
            content={"content": "你好", "title": "提醒"},
            source="cron",
        ))

        # 用户重连时拉取离线消息
        messages = await bus.drain_outbox("sess-123")
    """

    _instance: Optional[MessageBus] = None

    def __new__(cls) -> MessageBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._registry = get_connection_registry()
            self._outbox = OutboxStore()
            self._initialized = True

    async def send(
        self,
        session_id: str,
        message: OutboundMessage,
    ) -> SendResult:
        """发送消息到指定 session。

        先尝试实时推送，失败则暂存到 outbox。

        Args:
            session_id: 目标会话 ID。
            message: 出站消息。

        Returns:
            发送结果。
        """
        message.session_id = session_id

        # 1. 尝试实时推送
        push_result = await self._registry.push(session_id, message.to_ws_dict())

        if push_result.status == PushStatus.DELIVERED:
            logger.info(
                "Message delivered in real-time",
                extra={
                    "session_id": session_id,
                    "message_id": message.message_id,
                    "delivered_count": push_result.delivered_count,
                },
            )
            return SendResult(
                delivered=True,
                queued=False,
                session_id=session_id,
            )

        # 2. 推送失败 → 暂存到 outbox
        await self._outbox.save(message)

        logger.info(
            "Message queued to outbox (user offline)",
            extra={
                "session_id": session_id,
                "message_id": message.message_id,
                "push_status": push_result.status.value,
            },
        )
        return SendResult(
            delivered=False,
            queued=True,
            session_id=session_id,
        )

    async def drain_outbox(self, session_id: str) -> list[OutboundMessage]:
        """拉取并投递 outbox 中的未读消息。

        用户重连或创建新 session 时调用，将暂存的消息通过 ConnectionRegistry 推送，
        并标记为已投递。

        对于之前因没有活跃 session 而暂存到 outbox 的通知消息，
        此处负责将其持久化到 messages 表（因为暂存时没有 session_id，
        无法写入 messages 表，只有回捞时才有目标 session_id）。

        注意：有 session_id 的通知消息在 WebChatNotificationChannel.send() 中
        已经完成持久化，不会进入 outbox，因此不存在重复持久化的问题。

        Args:
            session_id: 会话 ID。

        Returns:
            成功投递的消息列表。
        """
        pending_messages = await self._outbox.get_pending(session_id)
        if not pending_messages:
            return []

        delivered_ids: list[str] = []
        delivered_messages: list[OutboundMessage] = []

        for message in pending_messages:
            push_result = await self._registry.push(session_id, message.to_ws_dict())
            if push_result.status in (PushStatus.DELIVERED, PushStatus.PARTIAL):
                # 推送成功后立即标记为已投递，避免重复投递
                await self._outbox.mark_delivered([message.message_id])
                delivered_ids.append(message.message_id)
                delivered_messages.append(message)

            # 无论推送是否成功，都持久化通知消息到 messages 表
            # 这样即使用户离线，消息也会被保存，刷新后可以加载
            await self._persist_notification_message(session_id, message)

        logger.info(
            "Outbox drained",
            extra={
                "session_id": session_id,
                "total_pending": len(pending_messages),
                "delivered": len(delivered_ids),
            },
        )

        return delivered_messages

    async def drain_outbox_by_agent(
        self,
        agent_id: str,
        session_id: str,
    ) -> list[OutboundMessage]:
        """拉取并投递 agent 级别的暂存消息。

        当通知发送时目标 agent 没有活跃 session，消息以空 session_id 暂存到 outbox。
        用户重连后，通过 agent_id 查找这些消息，绑定到当前 session_id 并投递。

        Args:
            agent_id: Agent ID。
            session_id: 当前活跃的 session ID（用于推送和持久化）。

        Returns:
            成功投递的消息列表。
        """
        pending_messages = await self._outbox.get_pending_by_agent(agent_id)
        if not pending_messages:
            return []

        delivered_ids: list[str] = []
        delivered_messages: list[OutboundMessage] = []

        for message in pending_messages:
            push_result = await self._registry.push(session_id, message.to_ws_dict())
            if push_result.status in (PushStatus.DELIVERED, PushStatus.PARTIAL):
                await self._outbox.mark_delivered([message.message_id])
                delivered_ids.append(message.message_id)
                delivered_messages.append(message)

            # 持久化到 messages 表（暂存时没有 session_id，此时才有）
            await self._persist_notification_message(session_id, message)

        logger.info(
            "Agent-level outbox drained",
            extra={
                "agent_id": agent_id,
                "session_id": session_id,
                "total_pending": len(pending_messages),
                "delivered": len(delivered_ids),
            },
        )

        return delivered_messages

    async def _persist_notification_message(self, session_id: str, message: OutboundMessage) -> None:
        """将通知消息持久化到 messages 表。

        Args:
            session_id: 会话 ID。
            message: 出站消息。
        """
        try:
            from ..conversation.session import SessionManager

            session_manager = SessionManager()
            
            # 格式化消息内容
            title = message.content.get("title", "")
            content = message.content.get("content", "")
            display_content = f"{title}\n\n{content}" if title else content

            # 持久化到 messages 表
            await session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=display_content,
                metadata={
                    "message_id": message.message_id,
                    "message_type": message.message_type,
                    "source": message.source,
                    "urgency": message.content.get("urgency", "normal"),
                },
            )

            logger.debug(
                "Notification message persisted",
                extra={
                    "session_id": session_id,
                    "message_id": message.message_id,
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to persist notification message",
                extra={
                    "session_id": session_id,
                    "message_id": message.message_id,
                    "error": str(exc),
                },
            )

    async def get_pending_count(self, session_id: str) -> int:
        """获取指定 session 的未投递消息数量。

        Args:
            session_id: 会话 ID。

        Returns:
            未投递消息数量。
        """
        pending = await self._outbox.get_pending(session_id)
        return len(pending)

    async def cleanup_outbox(self, max_age_days: int = 7) -> int:
        """清理过期的已投递消息。

        Args:
            max_age_days: 保留天数。

        Returns:
            删除的消息数量。
        """
        return await self._outbox.cleanup(max_age_days)


# ---------------------------------------------------------------------------
# 模块级单例访问
# ---------------------------------------------------------------------------

def get_message_bus() -> MessageBus:
    """获取全局 MessageBus 单例。"""
    return MessageBus()
