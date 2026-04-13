"""Agent 消息总线实现.

提供 Agent 间的消息传递能力，支持:
- 请求-响应模式（带超时）
- 单向通知
- 广播通知
- 消息订阅

设计原则：
- 零外部依赖，仅使用 Python 标准库
- 使用 dataclass 定义所有类型
- 线程安全的异步实现
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class AgentMessageType(StrEnum):
    """Agent 消息类型."""

    REQUEST = "request"  # 请求-响应
    RESPONSE = "response"  # 响应
    NOTIFICATION = "notification"  # 单向通知
    ERROR = "error"  # 错误响应


@dataclass(frozen=True)
class AgentBusMessage:
    """Agent 间通信的消息.

    消息是不可变的值对象，一旦创建就不能修改。

    Attributes:
        message_id: 消息唯一标识符
        message_type: 消息类型
        source_agent_id: 发送方 Agent ID
        target_agent_id: 接收方 Agent ID（"*" 表示广播）
        payload: 消息内容
        timestamp: 消息创建时间
        correlation_id: 关联的请求 message_id（用于请求-响应关联）
        trace_id: 分布式追踪 ID
        delegation_chain: 委派链路（记录消息经过的 Agent）
        ttl_seconds: 超时时间（秒）
    """

    message_id: str
    message_type: AgentMessageType
    source_agent_id: str
    target_agent_id: str
    payload: dict[str, Any]
    timestamp: datetime

    # 请求-响应关联
    correlation_id: str | None = None  # 关联的请求 message_id

    # 元数据
    trace_id: str | None = None
    delegation_chain: tuple[str, ...] = ()  # 委派链路
    ttl_seconds: float | None = None  # 超时时间

    @classmethod
    def create_request(
        cls,
        source: str,
        target: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
        ttl: float = 60.0,
        delegation_chain: tuple[str, ...] = (),
    ) -> AgentBusMessage:
        """创建请求消息.

        Args:
            source: 发送方 Agent ID
            target: 接收方 Agent ID
            payload: 消息内容
            trace_id: 分布式追踪 ID
            ttl: 超时时间（秒）
            delegation_chain: 委派链路

        Returns:
            AgentBusMessage: 请求消息
        """
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=AgentMessageType.REQUEST,
            source_agent_id=source,
            target_agent_id=target,
            payload=payload,
            timestamp=datetime.now(),
            trace_id=trace_id,
            ttl_seconds=ttl,
            delegation_chain=delegation_chain,
        )

    @classmethod
    def create_response(
        cls,
        request: AgentBusMessage,
        payload: dict[str, Any],
    ) -> AgentBusMessage:
        """创建响应消息.

        Args:
            request: 原始请求消息
            payload: 响应内容

        Returns:
            AgentBusMessage: 响应消息
        """
        # 扩展委派链
        new_chain = request.delegation_chain + (request.target_agent_id,)

        return cls(
            message_id=str(uuid.uuid4()),
            message_type=AgentMessageType.RESPONSE,
            source_agent_id=request.target_agent_id,
            target_agent_id=request.source_agent_id,
            payload=payload,
            timestamp=datetime.now(),
            correlation_id=request.message_id,
            trace_id=request.trace_id,
            delegation_chain=new_chain,
        )

    @classmethod
    def create_notification(
        cls,
        source: str,
        target: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> AgentBusMessage:
        """创建通知消息.

        Args:
            source: 发送方 Agent ID
            target: 接收方 Agent ID（"*" 表示广播）
            payload: 通知内容
            trace_id: 分布式追踪 ID

        Returns:
            AgentBusMessage: 通知消息
        """
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=AgentMessageType.NOTIFICATION,
            source_agent_id=source,
            target_agent_id=target,
            payload=payload,
            timestamp=datetime.now(),
            trace_id=trace_id,
        )

    @classmethod
    def create_error(
        cls,
        request: AgentBusMessage,
        error: str,
        details: dict[str, Any] | None = None,
    ) -> AgentBusMessage:
        """创建错误响应消息.

        Args:
            request: 原始请求消息
            error: 错误信息
            details: 错误详情

        Returns:
            AgentBusMessage: 错误响应消息
        """
        error_payload = {
            "error": error,
            "details": details or {},
        }

        return cls(
            message_id=str(uuid.uuid4()),
            message_type=AgentMessageType.ERROR,
            source_agent_id=request.target_agent_id,
            target_agent_id=request.source_agent_id,
            payload=error_payload,
            timestamp=datetime.now(),
            correlation_id=request.message_id,
            trace_id=request.trace_id,
        )

    def is_broadcast(self) -> bool:
        """检查是否为广播消息."""
        return self.target_agent_id == "*"

    def is_request(self) -> bool:
        """检查是否为请求消息."""
        return self.message_type == AgentMessageType.REQUEST

    def is_response(self) -> bool:
        """检查是否为响应消息."""
        return self.message_type in (AgentMessageType.RESPONSE, AgentMessageType.ERROR)


class AgentBus:
    """Agent 间消息总线.

    支持:
    - 请求-响应模式（带超时）
    - 单向通知
    - 广播通知
    - 消息订阅（按 agent_id）

    Example:
        bus = AgentBus()

        # Agent 订阅消息
        queue = bus.subscribe("agent-001")

        # 发送请求并等待响应
        request = AgentBusMessage.create_request(
            source="agent-001",
            target="agent-002",
            payload={"task": "analyze"},
        )
        response = await bus.request(request, timeout=30.0)

        # 广播通知
        notification = AgentBusMessage.create_notification(
            source="agent-001",
            target="*",
            payload={"event": "shutdown"},
        )
        await bus.send(notification)
    """

    def __init__(self, max_history: int = 500):
        """初始化消息总线.

        Args:
            max_history: 最大消息历史记录数
        """
        self._subscribers: dict[str, asyncio.Queue[AgentBusMessage]] = {}
        self._pending_requests: dict[str, asyncio.Future[AgentBusMessage]] = {}
        self._message_history: list[AgentBusMessage] = []
        self._max_history: int = max_history
        self._lock = asyncio.Lock()

    def subscribe(self, agent_id: str, queue_size: int = 100) -> asyncio.Queue[AgentBusMessage]:
        """Agent 订阅消息.

        Args:
            agent_id: Agent ID
            queue_size: 消息队列大小

        Returns:
            asyncio.Queue: 消息队列
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = asyncio.Queue(maxsize=queue_size)
        return self._subscribers[agent_id]

    def unsubscribe(self, agent_id: str) -> None:
        """Agent 取消订阅.

        Args:
            agent_id: Agent ID
        """
        self._subscribers.pop(agent_id, None)

    async def send(self, message: AgentBusMessage) -> None:
        """发送消息（单向）.

        如果是广播（target="*"），发送给所有订阅者（除发送者）。
        如果是定向消息，只发送给目标。
        如果是响应，还需要解析 pending_requests 的 Future。

        Args:
            message: 要发送的消息
        """
        async with self._lock:
            # 记录到历史
            self._message_history.append(message)
            if len(self._message_history) > self._max_history:
                self._message_history = self._message_history[-self._max_history :]

        # 处理响应消息
        if message.is_response() and message.correlation_id:
            future = self._pending_requests.pop(message.correlation_id, None)
            if future and not future.done():
                future.set_result(message)
            return

        # 处理广播消息
        if message.is_broadcast():
            for agent_id, queue in self._subscribers.items():
                if agent_id != message.source_agent_id:
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(message)
            return

        # 处理定向消息
        target_queue = self._subscribers.get(message.target_agent_id)
        if target_queue:
            with contextlib.suppress(asyncio.QueueFull):
                target_queue.put_nowait(message)

    async def request(
        self,
        message: AgentBusMessage,
        timeout: float | None = None,
    ) -> AgentBusMessage:
        """发送请求并等待响应（带超时）.

        Args:
            message: 请求消息
            timeout: 超时时间（秒），默认使用消息的 ttl_seconds 或 60 秒

        Returns:
            AgentBusMessage: 响应消息

        Raises:
            asyncio.TimeoutError: 超时未收到响应
        """
        if not message.is_request():
            raise ValueError("消息类型必须是 REQUEST")

        timeout = timeout or message.ttl_seconds or 60.0

        # 创建 Future
        loop = asyncio.get_event_loop()
        future: asyncio.Future[AgentBusMessage] = loop.create_future()

        async with self._lock:
            self._pending_requests[message.message_id] = future

        # 发送消息
        await self.send(message)

        # 等待响应
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except TimeoutError:
            async with self._lock:
                self._pending_requests.pop(message.message_id, None)
            raise

    async def receive(
        self,
        agent_id: str,
        timeout: float | None = None,
    ) -> AgentBusMessage | None:
        """接收消息（阻塞式）.

        Args:
            agent_id: Agent ID
            timeout: 超时时间（秒）

        Returns:
            AgentBusMessage | None: 接收到的消息，超时返回 None
        """
        queue = self._subscribers.get(agent_id)
        if not queue:
            return None

        try:
            if timeout:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                message = await queue.get()
            return message
        except TimeoutError:
            return None

    def get_pending_count(self, agent_id: str) -> int:
        """获取待处理消息数.

        Args:
            agent_id: Agent ID

        Returns:
            int: 待处理消息数
        """
        queue = self._subscribers.get(agent_id)
        return queue.qsize() if queue else 0

    def get_statistics(self) -> dict[str, Any]:
        """获取总线统计信息.

        Returns:
            dict: 统计信息
        """
        return {
            "subscriber_count": len(self._subscribers),
            "subscribers": list(self._subscribers.keys()),
            "pending_requests": len(self._pending_requests),
            "history_size": len(self._message_history),
            "max_history": self._max_history,
        }

    def get_history(
        self,
        agent_id: str | None = None,
        message_type: AgentMessageType | None = None,
        limit: int = 100,
    ) -> list[AgentBusMessage]:
        """获取消息历史.

        Args:
            agent_id: 过滤 Agent ID（可选）
            message_type: 过滤消息类型（可选）
            limit: 返回数量限制

        Returns:
            list[AgentBusMessage]: 消息历史
        """
        history = self._message_history

        if agent_id:
            history = [
                m for m in history if m.source_agent_id == agent_id or m.target_agent_id == agent_id
            ]

        if message_type:
            history = [m for m in history if m.message_type == message_type]

        return history[-limit:]

    async def clear(self) -> None:
        """清空消息总线和历史."""
        async with self._lock:
            self._message_history.clear()
            # 取消所有 pending requests
            for future in self._pending_requests.values():
                if not future.done():
                    future.cancel()
            self._pending_requests.clear()
            # 清空所有队列
            for queue in self._subscribers.values():
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break


# 全局 AgentBus 实例
_global_bus: AgentBus | None = None


def get_agent_bus() -> AgentBus:
    """获取全局 AgentBus 实例.

    Returns:
        AgentBus: 全局消息总线实例
    """
    global _global_bus
    if _global_bus is None:
        _global_bus = AgentBus()
    return _global_bus


def reset_agent_bus() -> None:
    """重置全局 AgentBus 实例（用于测试）."""
    global _global_bus
    _global_bus = None
