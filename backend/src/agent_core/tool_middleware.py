"""Tool 中间件管道实现.

提供工具调用生命周期的中间件管道模式，支持：
- 执行前/后处理
- 参数修改
- 执行中止
- 结果转换

Example:
    # 创建管道
    pipeline = ToolMiddlewarePipeline()
    
    # 添加中间件（链式调用）
    pipeline.use(TimingMiddleware()).use(ApprovalMiddleware())
    
    # 执行前处理
    ctx = await pipeline.execute_before(ctx)
    if ctx.action == MiddlewareAction.ABORT:
        # 处理中止
        pass
    
    # 执行工具...
    
    # 执行后处理
    ctx = await pipeline.execute_after(ctx)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MiddlewareAction(str, Enum):
    """中间件控制动作."""

    PROCEED = "proceed"    # 继续执行
    ABORT = "abort"        # 中止执行
    MODIFY = "modify"      # 修改参数后继续


@dataclass
class ToolCallContext:
    """工具调用的上下文，在中间件链中传递.
    
    Attributes:
        tool_name: 工具名称
        tool_call_id: 工具调用 ID（LLM 返回的 ID）
        arguments: 调用参数
        metadata: 中间件可附加的元数据
        result: 执行结果（在 AFTER 阶段可用）
        error: 错误信息（在 AFTER 阶段可用）
        action: 控制流动作
        abort_reason: 中止原因
    """

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # 执行结果（在 AFTER 阶段可用）
    result: Any = None
    error: str | None = None

    # 控制流
    action: MiddlewareAction = field(default=MiddlewareAction.PROCEED)
    abort_reason: str | None = None


class ToolMiddleware:
    """工具中间件基类.
    
    子类应重写 before_execute 和/或 after_execute 方法。
    
    Example:
        class LoggingMiddleware(ToolMiddleware):
            async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
                print(f"Executing: {ctx.tool_name}")
                return ctx
            
            async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
                print(f"Completed: {ctx.tool_name}")
                return ctx
    """

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """执行前处理，可修改参数或中止执行.
        
        Args:
            ctx: 工具调用上下文
        
        Returns:
            ToolCallContext: 处理后的上下文
        """
        return ctx

    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """执行后处理，可转换结果.
        
        Args:
            ctx: 工具调用上下文
        
        Returns:
            ToolCallContext: 处理后的上下文
        """
        return ctx


class ToolMiddlewarePipeline:
    """工具中间件管道.
    
    管理和执行工具中间件链。
    
    Example:
        pipeline = ToolMiddlewarePipeline()
        
        # 链式添加中间件
        pipeline.use(TimingMiddleware()).use(RetryMiddleware())
        
        # 执行前处理
        ctx = await pipeline.execute_before(ctx)
        
        # 如果未中止，执行工具
        if ctx.action != MiddlewareAction.ABORT:
            ctx.result = await execute_tool(ctx.tool_name, ctx.arguments)
        
        # 执行后处理
        ctx = await pipeline.execute_after(ctx)
    """

    def __init__(self):
        """初始化管道."""
        self._middlewares: list[ToolMiddleware] = []

    def use(self, middleware: ToolMiddleware) -> ToolMiddlewarePipeline:
        """添加中间件（链式调用）.
        
        Args:
            middleware: 中间件实例
        
        Returns:
            ToolMiddlewarePipeline: self，支持链式调用
        """
        self._middlewares.append(middleware)
        return self

    def remove(self, middleware_type: type) -> bool:
        """按类型移除中间件.
        
        Args:
            middleware_type: 中间件类类型
        
        Returns:
            bool: 是否成功移除
        """
        for i, mw in enumerate(self._middlewares):
            if isinstance(mw, middleware_type):
                self._middlewares.pop(i)
                return True
        return False

    def remove_all(self, middleware_type: type) -> int:
        """按类型移除所有匹配的中间件.
        
        Args:
            middleware_type: 中间件类类型
        
        Returns:
            int: 移除的数量
        """
        original_count = len(self._middlewares)
        self._middlewares = [
            mw for mw in self._middlewares
            if not isinstance(mw, middleware_type)
        ]
        return original_count - len(self._middlewares)

    def clear(self) -> None:
        """清空所有中间件."""
        self._middlewares.clear()

    def list_middlewares(self) -> list[str]:
        """列出所有中间件名称.
        
        Returns:
            list[str]: 中间件类名列表
        """
        return [type(mw).__name__ for mw in self._middlewares]

    def __len__(self) -> int:
        """返回中间件数量."""
        return len(self._middlewares)

    async def execute_before(self, ctx: ToolCallContext) -> ToolCallContext:
        """依次执行所有中间件的 before_execute.
        
        按注册顺序执行，如果某个中间件返回 ABORT 动作，
        则停止后续中间件的执行。
        
        Args:
            ctx: 工具调用上下文
        
        Returns:
            ToolCallContext: 处理后的上下文
        """
        for mw in self._middlewares:
            ctx = await mw.before_execute(ctx)
            if ctx.action == MiddlewareAction.ABORT:
                break
        return ctx

    async def execute_after(self, ctx: ToolCallContext) -> ToolCallContext:
        """反序执行所有中间件的 after_execute.
        
        按注册顺序的逆序执行，形成洋葱模型。
        
        Args:
            ctx: 工具调用上下文
        
        Returns:
            ToolCallContext: 处理后的上下文
        """
        for mw in reversed(self._middlewares):
            ctx = await mw.after_execute(ctx)
        return ctx

    async def execute(
        self,
        ctx: ToolCallContext,
        tool_executor: Callable[[ToolCallContext], Awaitable[Any]],
    ) -> ToolCallContext:
        """完整执行管道（before + tool + after）.
        
        这是一个便捷方法，封装了完整的执行流程。
        
        Args:
            ctx: 工具调用上下文
            tool_executor: 工具执行函数
        
        Returns:
            ToolCallContext: 处理后的上下文
        """
        # 执行前处理
        ctx = await self.execute_before(ctx)

        # 如果未中止，执行工具
        if ctx.action != MiddlewareAction.ABORT:
            try:
                ctx.result = await tool_executor(ctx)
            except Exception as e:
                ctx.error = str(e)

        # 执行后处理
        ctx = await self.execute_after(ctx)

        return ctx
