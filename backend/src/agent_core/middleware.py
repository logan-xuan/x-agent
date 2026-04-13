"""中间件模式实现.

提供消息处理的管道模式，支持链式处理。
中间件按顺序执行，每个中间件可以：
    1. 在处理前执行逻辑
    2. 调用下一个处理器
    3. 在处理后执行逻辑

中间件类型:
    - MessageMiddleware: 处理 AgentMessage
    - ToolMiddleware: 处理工具调用
    - ContextMiddleware: 处理上下文

Example:
    # 创建中间件链
    chain = MiddlewareChain[AgentMessage]()

    # 添加中间件
    chain.add(LoggingMiddleware())
    chain.add(CompressionMiddleware())
    chain.add(ValidationMiddleware())

    # 执行
    result = await chain.execute(message, final_handler)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Protocol,
    TypeVar,
)

if TYPE_CHECKING:
    from .types import AgentMessage, ToolResult

logger = logging.getLogger(__name__)

# 泛型类型
T = TypeVar("T")
R = TypeVar("R")


# ============================================================
# 中间件基础接口
# ============================================================


class Middleware(Protocol, Generic[T, R]):
    """中间件接口.

    通用的中间件协议，支持任意类型的输入输出。

    Example:
        class LoggingMiddleware:
            async def process(self, data, next_handler):
                print(f"Before: {data}")
                result = await next_handler(data)
                print(f"After: {result}")
                return result
    """

    async def process(
        self,
        data: T,
        next_handler: Callable[[T], Awaitable[R]],
    ) -> R:
        """处理数据.

        Args:
            data: 输入数据
            next_handler: 下一个处理器

        Returns:
            R: 处理结果
        """
        ...


# ============================================================
# 消息中间件
# ============================================================


class MessageMiddleware(Protocol):
    """消息处理中间件.

    专门用于处理 AgentMessage 列表的中间件。

    Example:
        class CompressionMiddleware:
            def __init__(self, max_tokens: int = 4000):
                self.max_tokens = max_tokens

            async def process(self, messages, next_handler):
                # 压缩逻辑
                if self._needs_compression(messages):
                    messages = await self._compress(messages)
                return await next_handler(messages)
    """

    async def process(
        self,
        messages: list[AgentMessage],
        next_handler: Callable[[list[AgentMessage]], Awaitable[list[AgentMessage]]],
    ) -> list[AgentMessage]:
        """处理消息列表.

        Args:
            messages: 消息列表
            next_handler: 下一个处理器

        Returns:
            list[AgentMessage]: 处理后的消息列表
        """
        ...


# ============================================================
# 工具中间件
# ============================================================


@dataclass
class ToolCallContext:
    """工具调用上下文.

    Attributes:
        tool_name: 工具名称
        arguments: 调用参数
        trace_id: 追踪ID
        metadata: 元数据
    """

    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """工具调用结果.

    Attributes:
        tool_name: 工具名称
        result: 执行结果
        is_error: 是否错误
        duration_ms: 执行耗时
        metadata: 元数据
    """

    tool_name: str = ""
    result: ToolResult | None = None
    is_error: bool = False
    duration_ms: float = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolMiddleware(Protocol):
    """工具执行中间件.

    用于在工具执行前后注入逻辑，如：
    - 日志记录
    - 权限检查
    - 参数验证
    - 结果缓存
    - 性能监控

    Example:
        class CacheMiddleware:
            def __init__(self, cache):
                self.cache = cache

            async def process(self, ctx, next_handler):
                # 检查缓存
                cache_key = self._make_key(ctx)
                cached = self.cache.get(cache_key)
                if cached:
                    return ToolCallResult(tool_name=ctx.tool_name, result=cached)

                # 执行并缓存
                result = await next_handler(ctx)
                self.cache.set(cache_key, result.result)
                return result
    """

    async def process(
        self,
        ctx: ToolCallContext,
        next_handler: Callable[[ToolCallContext], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        """处理工具调用.

        Args:
            ctx: 调用上下文
            next_handler: 下一个处理器

        Returns:
            ToolCallResult: 调用结果
        """
        ...


# ============================================================
# 中间件链
# ============================================================


class MiddlewareChain(Generic[T, R]):
    """中间件链.

    管理和执行中间件链。

    Example:
        chain = MiddlewareChain[list[AgentMessage], list[AgentMessage]]()
        chain.add(LoggingMiddleware())
        chain.add(CompressionMiddleware())

        result = await chain.execute(messages, final_handler)
    """

    def __init__(self):
        """初始化中间件链."""
        self._middlewares: list[Middleware[T, R]] = []

    def add(self, middleware: Middleware[T, R]) -> MiddlewareChain[T, R]:
        """添加中间件.

        Args:
            middleware: 中间件实例

        Returns:
            self: 支持链式调用
        """
        self._middlewares.append(middleware)
        return self

    def remove(self, middleware: Middleware[T, R]) -> bool:
        """移除中间件.

        Args:
            middleware: 中间件实例

        Returns:
            bool: 是否成功移除
        """
        try:
            self._middlewares.remove(middleware)
            return True
        except ValueError:
            return False

    def clear(self) -> None:
        """清空所有中间件."""
        self._middlewares.clear()

    async def execute(
        self,
        data: T,
        final_handler: Callable[[T], Awaitable[R]],
    ) -> R:
        """执行中间件链.

        Args:
            data: 输入数据
            final_handler: 最终处理器

        Returns:
            R: 处理结果
        """
        # 构建处理链
        handler = final_handler

        # 从后向前构建
        for middleware in reversed(self._middlewares):
            # 创建闭包捕获当前 handler
            handler = self._wrap_handler(middleware, handler)

        return await handler(data)

    def _wrap_handler(
        self,
        middleware: Middleware[T, R],
        next_handler: Callable[[T], Awaitable[R]],
    ) -> Callable[[T], Awaitable[R]]:
        """包装处理器.

        Args:
            middleware: 中间件
            next_handler: 下一个处理器

        Returns:
            包装后的处理器
        """

        async def wrapped(data: T) -> R:
            return await middleware.process(data, next_handler)

        return wrapped

    def __len__(self) -> int:
        """返回中间件数量."""
        return len(self._middlewares)


# ============================================================
# 预定义中间件示例
# ============================================================


class LoggingMessageMiddleware:
    """日志记录中间件示例.

    记录消息处理过程。
    """

    def __init__(self, name: str = "MessageLogger"):
        self.name = name

    async def process(
        self,
        messages: list[AgentMessage],
        next_handler: Callable[[list[AgentMessage]], Awaitable[list[AgentMessage]]],
    ) -> list[AgentMessage]:
        """记录消息处理."""
        logger.info(
            f"[{self.name}] Processing {len(messages)} messages",
            extra={"middleware": self.name, "count": len(messages)},
        )

        result = await next_handler(messages)

        logger.info(
            f"[{self.name}] Processed, result: {len(result)} messages",
            extra={"middleware": self.name, "result_count": len(result)},
        )

        return result


class TimingToolMiddleware:
    """计时中间件示例.

    记录工具执行耗时。
    """

    def __init__(self, name: str = "ToolTimer"):
        self.name = name

    async def process(
        self,
        ctx: ToolCallContext,
        next_handler: Callable[[ToolCallContext], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        """记录执行耗时."""
        import time

        start_time = time.time()

        result = await next_handler(ctx)

        duration_ms = (time.time() - start_time) * 1000
        result.duration_ms = duration_ms

        logger.info(
            f"[{self.name}] Tool {ctx.tool_name} executed in {duration_ms:.2f}ms",
            extra={
                "middleware": self.name,
                "tool_name": ctx.tool_name,
                "duration_ms": duration_ms,
            },
        )

        return result


class RetryToolMiddleware:
    """重试中间件示例.

    工具执行失败时自动重试。
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        name: str = "ToolRetry",
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.name = name

    async def process(
        self,
        ctx: ToolCallContext,
        next_handler: Callable[[ToolCallContext], Awaitable[ToolCallResult]],
    ) -> ToolCallResult:
        """失败时重试."""
        import asyncio

        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await next_handler(ctx)

                if not result.is_error:
                    return result

                last_error = result

                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"[{self.name}] Tool {ctx.tool_name} failed, "
                        f"retrying ({attempt + 1}/{self.max_retries})",
                        extra={
                            "middleware": self.name,
                            "tool_name": ctx.tool_name,
                            "attempt": attempt + 1,
                        },
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        # 所有重试都失败
        logger.error(
            f"[{self.name}] Tool {ctx.tool_name} failed after {self.max_retries} retries",
            extra={
                "middleware": self.name,
                "tool_name": ctx.tool_name,
                "attempts": self.max_retries,
            },
        )

        if isinstance(last_error, Exception):
            raise last_error

        return last_error  # type: ignore
