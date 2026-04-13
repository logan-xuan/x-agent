"""内置工具中间件示例.

提供常用的工具中间件实现：
- TimingMiddleware: 记录执行耗时
- RetryMiddleware: 失败时自动重试
- ApprovalMiddleware: 高危工具审批
- LoggingMiddleware: 执行日志记录
- ValidationMiddleware: 参数验证

Example:
    from agent_core.builtin_middlewares import TimingMiddleware, RetryMiddleware

    pipeline = ToolMiddlewarePipeline()
    pipeline.use(TimingMiddleware()).use(RetryMiddleware(max_retries=3))
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .tool_middleware import MiddlewareAction, ToolCallContext, ToolMiddleware

logger = logging.getLogger(__name__)


class TimingMiddleware(ToolMiddleware):
    """记录工具执行耗时.

    在 before_execute 中记录开始时间，
    在 after_execute 中计算并记录耗时。

    Example:
        pipeline.use(TimingMiddleware())

        # 执行后，ctx.metadata 中将包含:
        # {
        #     "execution_time_ms": 123.45,
        #     "_start_time": 1234567890.123
        # }
    """

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """记录开始时间."""
        ctx.metadata["_start_time"] = time.time()
        return ctx

    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """计算并记录耗时."""
        start_time = ctx.metadata.get("_start_time")
        if start_time:
            elapsed = time.time() - start_time
            ctx.metadata["execution_time_ms"] = round(elapsed * 1000, 2)

            logger.debug(
                f"Tool '{ctx.tool_name}' executed in {ctx.metadata['execution_time_ms']}ms",
                extra={
                    "tool_name": ctx.tool_name,
                    "tool_call_id": ctx.tool_call_id,
                    "execution_time_ms": ctx.metadata["execution_time_ms"],
                },
            )
        return ctx


class RetryMiddleware(ToolMiddleware):
    """工具执行失败时自动重试.

    通过检查 ctx.error 来判断是否需要重试。
    注意：此中间件需要在实际执行工具前被调用，
    它会包装工具执行逻辑。

    Example:
        pipeline.use(RetryMiddleware(max_retries=3, retry_delay=1.0))
    """

    def __init__(
        self,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True,
        retry_on_error_types: list[type] | None = None,
    ):
        """初始化重试中间件.

        Args:
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            exponential_backoff: 是否使用指数退避
            retry_on_error_types: 指定需要重试的错误类型，None 表示所有错误
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.exponential_backoff = exponential_backoff
        self.retry_on_error_types = retry_on_error_types
        self._retry_count: dict[str, int] = {}

    def _should_retry(self, error: str | None) -> bool:
        """判断是否应该重试.

        Args:
            error: 错误信息

        Returns:
            bool: 是否应该重试
        """
        return error is not None

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """初始化重试计数."""
        ctx.metadata["_retry_count"] = 0
        ctx.metadata["_max_retries"] = self.max_retries
        return ctx

    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """检查是否需要重试.

        注意：此中间件只是记录重试信息，
        实际的重试逻辑需要在调用方实现。

        Args:
            ctx: 工具调用上下文

        Returns:
            ToolCallContext: 处理后的上下文
        """
        if ctx.error and self._should_retry(ctx.error):
            retry_count = ctx.metadata.get("_retry_count", 0)

            if retry_count < self.max_retries:
                # 计算延迟时间
                if self.exponential_backoff:
                    delay = self.retry_delay * (2**retry_count)
                else:
                    delay = self.retry_delay

                ctx.metadata["_retry_count"] = retry_count + 1
                ctx.metadata["_should_retry"] = True
                ctx.metadata["_retry_delay"] = delay

                logger.warning(
                    f"Tool '{ctx.tool_name}' failed, will retry "
                    f"({retry_count + 1}/{self.max_retries}) after {delay}s",
                    extra={
                        "tool_name": ctx.tool_name,
                        "tool_call_id": ctx.tool_call_id,
                        "retry_count": retry_count + 1,
                        "max_retries": self.max_retries,
                        "retry_delay": delay,
                        "error": ctx.error,
                    },
                )
            else:
                ctx.metadata["_should_retry"] = False
                logger.error(
                    f"Tool '{ctx.tool_name}' failed after {self.max_retries} retries",
                    extra={
                        "tool_name": ctx.tool_name,
                        "tool_call_id": ctx.tool_call_id,
                        "max_retries": self.max_retries,
                        "error": ctx.error,
                    },
                )
        else:
            ctx.metadata["_should_retry"] = False

        return ctx


class ApprovalMiddleware(ToolMiddleware):
    """高危工具审批中间件.

    对指定的高危工具进行审批检查，可以阻断执行。

    Example:
        # 使用默认审批函数
        pipeline.use(ApprovalMiddleware(
            high_risk_tools=["file_delete", "database_drop"]
        ))

        # 使用自定义审批函数
        async def my_approval(ctx: ToolCallContext) -> bool:
            # 调用外部审批服务或显示 UI 确认对话框
            return await show_confirmation_dialog(ctx.tool_name, ctx.arguments)

        pipeline.use(ApprovalMiddleware(
            high_risk_tools=["file_delete"],
            approval_fn=my_approval
        ))
    """

    def __init__(
        self,
        high_risk_tools: list[str] | None = None,
        approval_fn: Callable[[ToolCallContext], Awaitable[bool]] | None = None,
        default_approved: bool = False,
    ):
        """初始化审批中间件.

        Args:
            high_risk_tools: 高危工具名称列表
            approval_fn: 外部审批函数，接收上下文返回是否批准
            default_approved: 没有审批函数时的默认行为（True=放行，False=阻断）
        """
        self.high_risk_tools = set(high_risk_tools or [])
        self.approval_fn = approval_fn
        self.default_approved = default_approved

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """检查是否需要审批.

        Args:
            ctx: 工具调用上下文

        Returns:
            ToolCallContext: 处理后的上下文，可能被标记为 ABORT
        """
        if ctx.tool_name not in self.high_risk_tools:
            # 非高危工具，直接放行
            return ctx

        # 标记需要审批
        ctx.metadata["requires_approval"] = True
        ctx.metadata["approval_tool_name"] = ctx.tool_name

        if self.approval_fn:
            # 调用外部审批函数
            try:
                approved = await self.approval_fn(ctx)
                ctx.metadata["approved"] = approved

                if not approved:
                    ctx.action = MiddlewareAction.ABORT
                    ctx.abort_reason = f"Tool '{ctx.tool_name}' requires approval and was denied"
                    logger.warning(
                        f"Tool '{ctx.tool_name}' execution denied by approval check",
                        extra={
                            "tool_name": ctx.tool_name,
                            "tool_call_id": ctx.tool_call_id,
                            "arguments": ctx.arguments,
                        },
                    )
                else:
                    logger.info(
                        f"Tool '{ctx.tool_name}' approved for execution",
                        extra={
                            "tool_name": ctx.tool_name,
                            "tool_call_id": ctx.tool_call_id,
                        },
                    )
            except Exception as e:
                # 审批函数异常，根据 default_approved 决定
                ctx.metadata["approval_error"] = str(e)
                if not self.default_approved:
                    ctx.action = MiddlewareAction.ABORT
                    ctx.abort_reason = f"Approval check failed: {e}"
                logger.error(
                    f"Approval check failed for tool '{ctx.tool_name}': {e}",
                    extra={
                        "tool_name": ctx.tool_name,
                        "tool_call_id": ctx.tool_call_id,
                        "error": str(e),
                    },
                )
        else:
            # 没有审批函数，使用默认行为
            ctx.metadata["approved"] = self.default_approved

            if not self.default_approved:
                ctx.action = MiddlewareAction.ABORT
                ctx.abort_reason = (
                    f"Tool '{ctx.tool_name}' requires approval but no approval function configured"
                )
                logger.warning(
                    f"Tool '{ctx.tool_name}' blocked: no approval function configured",
                    extra={
                        "tool_name": ctx.tool_name,
                        "tool_call_id": ctx.tool_call_id,
                    },
                )

        return ctx

    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """记录审批执行结果."""
        if ctx.metadata.get("requires_approval"):
            ctx.metadata["approval_executed"] = True
            ctx.metadata["approval_success"] = ctx.error is None
        return ctx


class LoggingMiddleware(ToolMiddleware):
    """工具执行日志记录中间件.

    记录工具调用的开始、参数、结果和错误。

    Example:
        pipeline.use(LoggingMiddleware(log_level=logging.INFO))
    """

    def __init__(self, log_level: int = logging.INFO, log_arguments: bool = True):
        """初始化日志中间件.

        Args:
            log_level: 日志级别
            log_arguments: 是否记录参数
        """
        self.log_level = log_level
        self.log_arguments = log_arguments

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """记录工具调用开始."""
        extra = {
            "tool_name": ctx.tool_name,
            "tool_call_id": ctx.tool_call_id,
        }
        if self.log_arguments:
            extra["arguments"] = ctx.arguments

        logger.log(
            self.log_level,
            f"Executing tool: {ctx.tool_name}",
            extra=extra,
        )
        return ctx

    async def after_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """记录工具调用结果."""
        if ctx.error:
            logger.error(
                f"Tool '{ctx.tool_name}' failed: {ctx.error}",
                extra={
                    "tool_name": ctx.tool_name,
                    "tool_call_id": ctx.tool_call_id,
                    "error": ctx.error,
                },
            )
        else:
            logger.log(
                self.log_level,
                f"Tool '{ctx.tool_name}' completed successfully",
                extra={
                    "tool_name": ctx.tool_name,
                    "tool_call_id": ctx.tool_call_id,
                    "has_result": ctx.result is not None,
                },
            )
        return ctx


class ValidationMiddleware(ToolMiddleware):
    """工具参数验证中间件.

    验证工具调用的参数是否符合要求。

    Example:
        # 验证所有工具
        pipeline.use(ValidationMiddleware())

        # 只验证特定工具
        pipeline.use(ValidationMiddleware(
            tool_validators={
                "web_search": lambda args: "query" in args and len(args["query"]) > 0
            }
        ))
    """

    def __init__(
        self,
        tool_validators: dict[str, Callable[[dict[str, Any]], bool]] | None = None,
        require_all_params: bool = False,
    ):
        """初始化验证中间件.

        Args:
            tool_validators: 工具特定的验证函数字典
            require_all_params: 是否要求所有必需参数都存在
        """
        self.tool_validators = tool_validators or {}
        self.require_all_params = require_all_params

    def _validate(self, ctx: ToolCallContext) -> tuple[bool, str | None]:
        """验证参数.

        Args:
            ctx: 工具调用上下文

        Returns:
            tuple[bool, str | None]: (是否通过, 错误信息)
        """
        # 检查是否有工具特定的验证器
        if ctx.tool_name in self.tool_validators:
            validator = self.tool_validators[ctx.tool_name]
            try:
                if not validator(ctx.arguments):
                    return False, f"Validation failed for tool '{ctx.tool_name}'"
            except Exception as e:
                return False, f"Validation error: {e}"

        # 基本验证：参数不能为空（如果 require_all_params 为 True）
        if self.require_all_params and not ctx.arguments:
            return False, f"Tool '{ctx.tool_name}' requires parameters but none provided"

        return True, None

    async def before_execute(self, ctx: ToolCallContext) -> ToolCallContext:
        """验证参数."""
        is_valid, error_msg = self._validate(ctx)

        ctx.metadata["validation_passed"] = is_valid

        if not is_valid:
            ctx.action = MiddlewareAction.ABORT
            ctx.abort_reason = error_msg
            logger.warning(
                f"Tool '{ctx.tool_name}' validation failed: {error_msg}",
                extra={
                    "tool_name": ctx.tool_name,
                    "tool_call_id": ctx.tool_call_id,
                    "arguments": ctx.arguments,
                    "error": error_msg,
                },
            )
        else:
            logger.debug(
                f"Tool '{ctx.tool_name}' validation passed",
                extra={
                    "tool_name": ctx.tool_name,
                    "tool_call_id": ctx.tool_call_id,
                },
            )

        return ctx
