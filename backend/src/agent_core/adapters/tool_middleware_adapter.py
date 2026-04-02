"""ToolMiddlewareAdapter - 工具执行中间件适配器.

将 agent_core 的 ToolMiddlewarePipeline 接入 agent_loop 的工具执行流程。
支持:
- 执行前/后处理
- 参数修改
- 执行中止（如高危工具审批）
- 结果转换
- Hook 系统集成

Example:
    from agent_core.adapters.tool_middleware_adapter import (
        ToolMiddlewareAdapter,
        create_tool_middleware_adapter,
    )
    
    # 使用工厂函数创建（带默认中间件）
    adapter = create_tool_middleware_adapter(
        enable_timing=True,
        enable_logging=True,
        high_risk_tools=["delete_file", "execute_code"],
    )
    
    # 执行工具调用
    result = await adapter.execute(
        tool_name="search_web",
        tool_call_id="call-123",
        arguments={"query": "hello"},
        tool_executor=tool_port.execute,
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from ..tool_middleware import (
    ToolMiddleware,
    ToolMiddlewarePipeline,
    ToolCallContext,
    MiddlewareAction,
)

if TYPE_CHECKING:
    from ..hooks import HookRegistry
    from ..types import ToolResult

try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# === 内置中间件实现 ===

class TimingMiddleware(ToolMiddleware):
    """计时中间件.
    
    记录工具执行时间到 metadata 中。
    """
    
    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        ctx.metadata["start_time"] = time.time()
        return ctx
    
    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        start_time = ctx.metadata.get("start_time")
        if start_time:
            duration_ms = (time.time() - start_time) * 1000
            ctx.metadata["duration_ms"] = duration_ms
            ctx.metadata["timing_recorded"] = True
        return ctx


class LoggingMiddleware(ToolMiddleware):
    """日志中间件.
    
    在执行前后记录日志。
    """
    
    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        logger.debug(
            "Tool execution starting",
            extra={
                "tool_name": ctx.tool_name,
                "tool_call_id": ctx.tool_call_id,
                "arguments": ctx.arguments,
            },
        )
        return ctx
    
    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        logger.debug(
            "Tool execution completed",
            extra={
                "tool_name": ctx.tool_name,
                "tool_call_id": ctx.tool_call_id,
                "has_error": ctx.error is not None,
                "duration_ms": ctx.metadata.get("duration_ms"),
            },
        )
        return ctx


class ApprovalMiddleware(ToolMiddleware):
    """审批中间件.
    
    对高危工具执行前进行审批检查。
    如果工具在高危列表中且未通过审批，则中止执行。
    
    Attributes:
        high_risk_tools: 高危工具名称列表
        approval_callback: 审批回调函数（可选）
        auto_approve: 自动审批（用于测试，生产环境应禁用）
    """
    
    def __init__(
        self,
        high_risk_tools: list[str] | None = None,
        approval_callback: Callable[[ToolCallContext], Awaitable[bool]] | None = None,
        auto_approve: bool = False,
    ):
        self.high_risk_tools = set(high_risk_tools or [])
        self.approval_callback = approval_callback
        self.auto_approve = auto_approve
    
    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        # 检查是否为高危工具
        if ctx.tool_name not in self.high_risk_tools:
            return ctx
        
        ctx.metadata["requires_approval"] = True
        
        # 自动审批（测试用）
        if self.auto_approve:
            ctx.metadata["approved"] = True
            ctx.metadata["approval_mode"] = "auto"
            return ctx
        
        # 调用审批回调
        if self.approval_callback:
            try:
                approved = await self.approval_callback(ctx)
                ctx.metadata["approved"] = approved
                ctx.metadata["approval_mode"] = "callback"
                
                if not approved:
                    ctx.action = MiddlewareAction.ABORT
                    ctx.abort_reason = f"High-risk tool '{ctx.tool_name}' not approved"
                    logger.warning(
                        "Tool execution blocked by approval",
                        extra={
                            "tool_name": ctx.tool_name,
                            "tool_call_id": ctx.tool_call_id,
                        },
                    )
            except Exception as e:
                # 审批失败，默认拒绝
                ctx.action = MiddlewareAction.ABORT
                ctx.abort_reason = f"Approval check failed: {e}"
                logger.error(
                    "Approval callback error",
                    extra={"tool_name": ctx.tool_name, "error": str(e)},
                )
        else:
            # 没有审批回调，高危工具默认拒绝
            ctx.action = MiddlewareAction.ABORT
            ctx.abort_reason = f"High-risk tool '{ctx.tool_name}' requires approval"
        
        return ctx


class ArgumentValidationMiddleware(ToolMiddleware):
    """参数验证中间件.
    
    在执行前验证工具参数。
    """
    
    def __init__(self, validators: dict[str, Callable[[dict], bool | str]] | None = None):
        """初始化参数验证中间件.
        
        Args:
            validators: 工具名称到验证函数的映射
                        验证函数返回 True 或 str（错误消息）
        """
        self.validators = validators or {}
    
    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        validator = self.validators.get(ctx.tool_name)
        if not validator:
            return ctx
        
        try:
            result = validator(ctx.arguments)
            if result is True:
                return ctx
            
            # 验证失败
            error_msg = result if isinstance(result, str) else "Invalid arguments"
            ctx.action = MiddlewareAction.ABORT
            ctx.abort_reason = error_msg
            
        except Exception as e:
            ctx.action = MiddlewareAction.ABORT
            ctx.abort_reason = f"Argument validation failed: {e}"
        
        return ctx


class RetryMiddleware(ToolMiddleware):
    """重试中间件.
    
    在工具执行失败时自动重试。
    注意: 此中间件需要配合外部重试逻辑使用。
    """
    
    def __init__(self, max_retries: int = 2, retry_delay_seconds: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
    
    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        # 初始化重试计数
        if "retry_count" not in ctx.metadata:
            ctx.metadata["retry_count"] = 0
            ctx.metadata["max_retries"] = self.max_retries
        return ctx
    
    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        # 记录重试状态
        if ctx.error and ctx.metadata.get("retry_count", 0) < self.max_retries:
            ctx.metadata["should_retry"] = True
            ctx.metadata["retry_delay"] = self.retry_delay_seconds
        else:
            ctx.metadata["should_retry"] = False
        return ctx


# === ToolMiddlewareAdapter ===

class ToolMiddlewareAdapter:
    """工具中间件适配器.
    
    包装 ToolMiddlewarePipeline，提供便捷的接口和 Hook 集成。
    
    职责:
    1. 管理 ToolMiddlewarePipeline 实例
    2. 提供便捷的中间件注册接口
    3. 将 Hook 系统与中间件管道桥接
    4. 封装完整的执行流程
    
    Attributes:
        _pipeline: 内部的 ToolMiddlewarePipeline 实例
        _hooks: 可选的 HookRegistry 引用
    """
    
    def __init__(
        self,
        pipeline: ToolMiddlewarePipeline | None = None,
        hooks: HookRegistry | None = None,
    ) -> None:
        """初始化适配器.
        
        Args:
            pipeline: ToolMiddlewarePipeline 实例，为 None 时自动创建
            hooks: Hook 注册中心（可选）
        """
        self._pipeline = pipeline or ToolMiddlewarePipeline()
        self._hooks = hooks
    
    @property
    def pipeline(self) -> ToolMiddlewarePipeline:
        """获取内部的 ToolMiddlewarePipeline 实例."""
        return self._pipeline
    
    def use(self, middleware: ToolMiddleware) -> ToolMiddlewareAdapter:
        """添加中间件（链式调用）.
        
        Args:
            middleware: 中间件实例
            
        Returns:
            self，支持链式调用
        """
        self._pipeline.use(middleware)
        return self
    
    def remove(self, middleware_type: type) -> bool:
        """按类型移除中间件.
        
        Args:
            middleware_type: 中间件类类型
            
        Returns:
            是否成功移除
        """
        return self._pipeline.remove(middleware_type)
    
    def list_middlewares(self) -> list[str]:
        """列出所有中间件名称.
        
        Returns:
            中间件类名列表
        """
        return self._pipeline.list_middlewares()
    
    async def execute(
        self,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]],
    ) -> tuple[Any, bool, dict[str, Any]]:
        """执行工具调用（通过中间件管道）.
        
        完整流程:
        1. 创建 ToolCallContext
        2. 触发 BEFORE_TOOL_EXEC Hook
        3. 执行 before_execute 中间件链
        4. 如果未中止，执行工具
        5. 执行 after_execute 中间件链
        6. 触发 AFTER_TOOL_EXEC Hook
        7. 返回结果
        
        Args:
            tool_name: 工具名称
            tool_call_id: 工具调用 ID
            arguments: 调用参数
            tool_executor: 工具执行函数
            
        Returns:
            (result, is_error, metadata) 元组
        """
        # 创建上下文
        ctx = ToolCallContext(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=arguments,
        )
        
        # 触发 BEFORE_TOOL_EXEC Hook
        if self._hooks:
            await self._trigger_before_hook(ctx)
        
        # 执行 before 中间件链
        ctx = await self._pipeline.execute_before(ctx)
        
        # 检查是否中止
        if ctx.action == MiddlewareAction.ABORT:
            logger.info(
                "Tool execution aborted by middleware",
                extra={
                    "tool_name": tool_name,
                    "abort_reason": ctx.abort_reason,
                },
            )
            return (
                {"error": ctx.abort_reason or "Execution aborted"},
                True,
                ctx.metadata,
            )
        
        # 执行工具
        try:
            # 使用可能被中间件修改过的参数
            result = await tool_executor(ctx.tool_name, ctx.arguments)
            ctx.result = result
        except Exception as e:
            ctx.error = str(e)
            logger.error(
                "Tool execution error",
                extra={
                    "tool_name": tool_name,
                    "error": str(e),
                },
            )
        
        # 执行 after 中间件链
        ctx = await self._pipeline.execute_after(ctx)
        
        # 触发 AFTER_TOOL_EXEC Hook
        if self._hooks:
            await self._trigger_after_hook(ctx)
        
        # 返回结果
        is_error = ctx.error is not None
        result = ctx.error if is_error else ctx.result
        
        return (result, is_error, ctx.metadata)
    
    async def _trigger_before_hook(self, ctx: ToolCallContext) -> None:
        """触发 BEFORE_TOOL_EXEC Hook."""
        from ..hooks import HookContext, HookPoint
        
        if self._hooks is None:
            return
        
        hook_ctx = HookContext(
            point=HookPoint.BEFORE_TOOL_EXEC,
            tool_name=ctx.tool_name,
            tool_arguments=ctx.arguments,
            data={
                "tool_call_id": ctx.tool_call_id,
            },
        )
        await self._hooks.trigger(hook_ctx)
    
    async def _trigger_after_hook(self, ctx: ToolCallContext) -> None:
        """触发 AFTER_TOOL_EXEC Hook."""
        from ..hooks import HookContext, HookPoint
        
        if self._hooks is None:
            return
        
        hook_ctx = HookContext(
            point=HookPoint.AFTER_TOOL_EXEC,
            tool_name=ctx.tool_name,
            tool_arguments=ctx.arguments,
            tool_result=ctx.result,
            data={
                "tool_call_id": ctx.tool_call_id,
                "error": ctx.error,
                "duration_ms": ctx.metadata.get("duration_ms"),
            },
        )
        await self._hooks.trigger(hook_ctx)


# === 工厂函数 ===

def create_tool_middleware_adapter(
    hooks: HookRegistry | None = None,
    enable_timing: bool = True,
    enable_logging: bool = True,
    high_risk_tools: list[str] | None = None,
    approval_callback: Callable[[ToolCallContext], Awaitable[bool]] | None = None,
    auto_approve_high_risk: bool = False,
) -> ToolMiddlewareAdapter:
    """创建 ToolMiddlewareAdapter 的工厂函数.
    
    自动注册默认的中间件并返回配置好的适配器。
    
    Args:
        hooks: Hook 注册中心（可选）
        enable_timing: 是否启用计时中间件
        enable_logging: 是否启用日志中间件
        high_risk_tools: 高危工具列表（需要审批）
        approval_callback: 审批回调函数
        auto_approve_high_risk: 是否自动审批高危工具（仅测试用）
        
    Returns:
        ToolMiddlewareAdapter 实例
    """
    adapter = ToolMiddlewareAdapter(hooks=hooks)
    
    # 注册默认中间件（按执行顺序）
    
    # 1. 计时中间件（最外层，记录总时间）
    if enable_timing:
        adapter.use(TimingMiddleware())
    
    # 2. 日志中间件
    if enable_logging:
        adapter.use(LoggingMiddleware())
    
    # 3. 审批中间件（在执行前检查）
    if high_risk_tools:
        adapter.use(ApprovalMiddleware(
            high_risk_tools=high_risk_tools,
            approval_callback=approval_callback,
            auto_approve=auto_approve_high_risk,
        ))
    
    logger.info(
        "ToolMiddlewareAdapter created",
        extra={
            "middleware_count": len(adapter.pipeline),
            "middlewares": adapter.list_middlewares(),
            "high_risk_tools": high_risk_tools or [],
        },
    )
    
    return adapter
