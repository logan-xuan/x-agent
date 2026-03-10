"""全局连接注册表。

管理所有活跃的客户端连接（WebSocket / SSE），支持按 session_id 查找和推送。
各协议端点在连接建立时注册 ConnectionHandle，断开时注销。

设计原则：
- 全局单例，进程内共享
- 协议无关：通过 ConnectionHandle.send 闭包屏蔽协议差异
- 线程安全：使用 asyncio.Lock 保护并发修改
- 一个 session_id 可以有多个连接（如同一会话的 WS + SSE）
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from ..conversation.identity import ChannelType, ChannelProtocol

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PushStatus(str, Enum):
    """推送结果状态。"""
    DELIVERED = "delivered"
    PARTIAL = "partial"
    NO_CONNECTION = "no_connection"
    FAILED = "failed"


@dataclass
class PushResult:
    """推送操作的结果。

    Attributes:
        status: 推送状态。
        delivered_count: 成功投递的连接数。
        total_count: 尝试投递的连接总数。
        failed_channel_ids: 投递失败的 channel_id 列表。
    """
    status: PushStatus
    delivered_count: int = 0
    total_count: int = 0
    failed_channel_ids: list[str] = field(default_factory=list)


@dataclass
class ConnectionHandle:
    """连接句柄 — 协议无关的消息发送抽象。

    send 是一个闭包，由各协议端点在连接建立时注入，
    屏蔽了 WebSocket/SSE/CLI 的协议差异。

    Attributes:
        channel_id: 连接唯一标识（如 "ws-a1b2c3d4"、"sse-e5f6g7h8"）。
        channel_type: 消息来源渠道。
        channel_protocol: 底层通信协议。
        send: 异步发送闭包，返回 True 表示发送成功。
        created_at: 连接建立时间。
    """
    channel_id: str
    channel_type: ChannelType
    channel_protocol: ChannelProtocol
    send: Callable[[dict[str, Any]], Awaitable[bool]]
    created_at: datetime = field(default_factory=datetime.utcnow)


class ConnectionRegistry:
    """全局连接注册表。

    管理所有活跃的客户端连接，支持按 session_id 查找和推送。
    每个 session_id 可以有多个连接（如同一会话的 WS + SSE）。

    典型用法::

        registry = get_connection_registry()

        # WebSocket 连接建立时
        registry.register("sess-123", ConnectionHandle(
            channel_id="ws-abc",
            channel_type=ChannelType.WEB_CHAT,
            channel_protocol=ChannelProtocol.WEBSOCKET,
            send=ws_sender,
        ))

        # 推送消息
        result = await registry.push("sess-123", {"type": "notification", ...})

        # 断开时
        registry.unregister("sess-123", "ws-abc")
    """

    _instance: Optional[ConnectionRegistry] = None

    def __new__(cls) -> ConnectionRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            # session_id -> {channel_id -> ConnectionHandle}
            self._connections: dict[str, dict[str, ConnectionHandle]] = {}
            self._lock = asyncio.Lock()
            self._initialized = True

    def register(self, session_id: str, handle: ConnectionHandle) -> None:
        """注册连接。

        在 WebSocket connect / SSE subscribe 时调用。
        同一 session_id 下可以注册多个连接。

        Args:
            session_id: 会话 ID。
            handle: 连接句柄。
        """
        if session_id not in self._connections:
            self._connections[session_id] = {}

        self._connections[session_id][handle.channel_id] = handle

        logger.info(
            "Connection registered",
            extra={
                "session_id": session_id,
                "channel_id": handle.channel_id,
                "channel_type": handle.channel_type.value,
                "channel_protocol": handle.channel_protocol.value,
                "active_connections": len(self._connections[session_id]),
            },
        )

    def unregister(self, session_id: str, channel_id: str) -> None:
        """注销连接。

        在 WebSocket disconnect / SSE 断开时调用。

        Args:
            session_id: 会话 ID。
            channel_id: 连接标识。
        """
        session_handles = self._connections.get(session_id)
        if session_handles is None:
            return

        removed = session_handles.pop(channel_id, None)

        # 清理空的 session 条目
        if not session_handles:
            self._connections.pop(session_id, None)

        if removed:
            logger.info(
                "Connection unregistered",
                extra={
                    "session_id": session_id,
                    "channel_id": channel_id,
                    "remaining_connections": len(session_handles) if session_handles else 0,
                },
            )

    def get_handles(self, session_id: str) -> list[ConnectionHandle]:
        """获取某 session 的所有活跃连接。

        Args:
            session_id: 会话 ID。

        Returns:
            活跃连接句柄列表（可能为空）。
        """
        session_handles = self._connections.get(session_id)
        if not session_handles:
            return []
        return list(session_handles.values())

    def has_connections(self, session_id: str) -> bool:
        """检查某 session 是否有活跃连接。

        Args:
            session_id: 会话 ID。

        Returns:
            是否有活跃连接。
        """
        session_handles = self._connections.get(session_id)
        return bool(session_handles)

    async def push(self, session_id: str, message: dict[str, Any]) -> PushResult:
        """向指定 session 推送消息，尝试所有可用连接。

        遍历该 session 下的所有连接句柄，逐个尝试发送。
        发送失败的连接会被自动注销。

        Args:
            session_id: 目标会话 ID。
            message: 要推送的消息字典。

        Returns:
            推送结果。
        """
        handles = self.get_handles(session_id)
        if not handles:
            return PushResult(status=PushStatus.NO_CONNECTION)

        delivered_count = 0
        failed_channel_ids: list[str] = []

        for handle in handles:
            try:
                success = await handle.send(message)
                if success:
                    delivered_count += 1
                else:
                    failed_channel_ids.append(handle.channel_id)
            except Exception as exc:
                logger.warning(
                    "Push failed for connection",
                    extra={
                        "session_id": session_id,
                        "channel_id": handle.channel_id,
                        "error": str(exc),
                    },
                )
                failed_channel_ids.append(handle.channel_id)

        # 自动清理失败的连接
        for channel_id in failed_channel_ids:
            self.unregister(session_id, channel_id)

        total_count = len(handles)
        if delivered_count == 0:
            status = PushStatus.FAILED
        elif delivered_count == total_count:
            status = PushStatus.DELIVERED
        else:
            status = PushStatus.PARTIAL

        return PushResult(
            status=status,
            delivered_count=delivered_count,
            total_count=total_count,
            failed_channel_ids=failed_channel_ids,
        )

    def get_all_session_ids(self) -> list[str]:
        """获取所有有活跃连接的 session_id 列表。

        Returns:
            session_id 列表。
        """
        return list(self._connections.keys())

    def get_stats(self) -> dict[str, Any]:
        """获取注册表统计信息。

        Returns:
            包含 session 数量和连接数量的字典。
        """
        total_connections = sum(
            len(handles) for handles in self._connections.values()
        )
        return {
            "active_sessions": len(self._connections),
            "total_connections": total_connections,
        }


# ---------------------------------------------------------------------------
# 模块级单例访问
# ---------------------------------------------------------------------------

def get_connection_registry() -> ConnectionRegistry:
    """获取全局 ConnectionRegistry 单例。"""
    return ConnectionRegistry()
