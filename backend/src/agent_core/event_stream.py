"""事件流实现.

提供异步事件发布/订阅机制，用于 agent_loop 的事件流处理。
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from .types import AgentEvent

T = TypeVar("T")


class EventStream(Generic[T]):
    """异步事件流.
    
    支持发布/订阅模式的事件流实现。
    
    Example:
        stream = EventStream[AgentEvent]()
        
        # 生产者
        await stream.push(event)
        
        # 消费者
        async for event in stream:
            print(event)
    """
    
    def __init__(self, max_buffer: int = 1000) -> None:
        """初始化事件流.
        
        Args:
            max_buffer: 最大缓冲区大小
        """
        self._queue: asyncio.Queue[T | None] = asyncio.Queue()
        self._buffer: deque[T] = deque(maxlen=max_buffer)
        self._closed = False
        self._subscribers: list[asyncio.Queue[T | None]] = []
    
    async def push(self, event: T) -> None:
        """推送事件.
        
        Args:
            event: 事件对象
        """
        if self._closed:
            return
        
        self._buffer.append(event)
        await self._queue.put(event)
        
        # 广播给订阅者
        for subscriber in self._subscribers:
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                pass
    
    def push_nowait(self, event: T) -> None:
        """非阻塞推送事件.
        
        Args:
            event: 事件对象
        """
        if self._closed:
            return
        
        self._buffer.append(event)
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            pass
        
        for subscriber in self._subscribers:
            try:
                subscriber.put_nowait(event)
            except asyncio.QueueFull:
                pass
    
    async def close(self) -> None:
        """关闭事件流."""
        self._closed = True
        await self._queue.put(None)
        
        for subscriber in self._subscribers:
            try:
                subscriber.put_nowait(None)
            except asyncio.QueueFull:
                pass
    
    def subscribe(self) -> asyncio.Queue[T | None]:
        """订阅事件流.
        
        Returns:
            asyncio.Queue: 订阅者队列
        """
        queue: asyncio.Queue[T | None] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue[T | None]) -> None:
        """取消订阅.
        
        Args:
            queue: 订阅者队列
        """
        if queue in self._subscribers:
            self._subscribers.remove(queue)
    
    def get_buffer(self) -> list[T]:
        """获取缓冲区中的所有事件.
        
        Returns:
            list: 事件列表
        """
        return list(self._buffer)
    
    @property
    def is_closed(self) -> bool:
        """检查事件流是否已关闭."""
        return self._closed
    
    def __aiter__(self) -> "EventStream[T]":
        """异步迭代器."""
        return self
    
    async def __anext__(self) -> T:
        """获取下一个事件."""
        if self._closed and self._queue.empty():
            raise StopAsyncIteration
        
        event = await self._queue.get()
        if event is None:
            raise StopAsyncIteration
        
        return event


class EventCollector(Generic[T]):
    """事件收集器.
    
    用于收集事件流中的所有事件。
    
    Example:
        collector = EventCollector[AgentEvent]()
        
        async for event in agent_loop(...):
            collector.add(event)
        
        all_events = collector.get_all()
    """
    
    def __init__(self) -> None:
        """初始化事件收集器."""
        self._events: list[T] = []
    
    def add(self, event: T) -> None:
        """添加事件.
        
        Args:
            event: 事件对象
        """
        self._events.append(event)
    
    def get_all(self) -> list[T]:
        """获取所有事件.
        
        Returns:
            list: 事件列表
        """
        return self._events.copy()
    
    def get_by_type(self, event_type: type) -> list[T]:
        """按类型获取事件.
        
        Args:
            event_type: 事件类型
        
        Returns:
            list: 匹配的事件列表
        """
        return [e for e in self._events if isinstance(e, event_type)]
    
    def clear(self) -> None:
        """清空事件."""
        self._events.clear()
    
    def __len__(self) -> int:
        """获取事件数量."""
        return len(self._events)
