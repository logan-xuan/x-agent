"""工具执行器.

提供工具调用的执行逻辑，包括并行执行、错误处理和 steering 支持。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ports.tool_port import ToolPort
    from .tool_middleware import ToolMiddlewarePipeline
    from .types import (
        AgentMessage,
        AgentTool,
        ToolCallContent,
        ToolExecutionEndEvent,
        ToolExecutionStartEvent,
        ToolExecutionUpdateEvent,
        ToolResult,
    )


async def execute_tool_calls(
    trace_id: str,
    llm_call_id: str,
    tool_port: ToolPort | None,
    tools: list[AgentTool],
    tool_calls: list[ToolCallContent],
    abort_event: asyncio.Event | None = None,
    get_steering: Callable[[], asyncio.Coroutine[Any, Any, list[AgentMessage]]] | None = None,
    middleware_pipeline: ToolMiddlewarePipeline | None = None,
) -> AsyncGenerator[ToolExecutionStartEvent | ToolExecutionUpdateEvent | ToolExecutionEndEvent, None]:
    """执行工具调用.
    
    顺序执行工具调用，支持 abort、steering 和中间件机制。
    
    Args:
        trace_id: 追踪 ID
        llm_call_id: LLM 调用 ID
        tool_port: 工具执行端口
        tools: 可用工具列表
        tool_calls: 要执行的工具调用列表
        abort_event: 中止事件
        get_steering: 获取 steering 消息的回调
        middleware_pipeline: 工具中间件管道（可选）
    
    Yields:
        ToolExecutionStartEvent | ToolExecutionUpdateEvent | ToolExecutionEndEvent
    """
    from .types import (
        TextContent,
        ToolExecutionEndEvent,
        ToolExecutionStartEvent,
        ToolResult,
    )

    for i, tc in enumerate(tool_calls):
        # 检查是否中止
        if abort_event and abort_event.is_set():
            yield _create_skipped_event(tc, "Aborted by user")
            continue

        # 查找工具定义
        tool = next((t for t in tools if t.name == tc.name), None)

        # 发送开始事件
        yield ToolExecutionStartEvent(
            tool_call_id=tc.id,
            tool_name=tc.name,
            arguments=tc.arguments,
        )

        start_time = time.time()
        result: ToolResult | None = None
        is_error = False
        error_msg: str | None = None

        try:
            if tool is None:
                raise ValueError(f"Tool not found: {tc.name}")

            if tool_port is None:
                raise ValueError("ToolPort is not configured")

            # 使用中间件管道执行工具（如果配置了）
            if middleware_pipeline is not None:
                from .tool_middleware import ToolCallContext, MiddlewareAction
                
                # 创建中间件上下文
                ctx = ToolCallContext(
                    tool_name=tc.name,
                    tool_call_id=tc.id,
                    arguments=tc.arguments,
                )
                
                # 执行 before 中间件
                ctx = await middleware_pipeline.execute_before(ctx)
                
                # 检查是否中止
                if ctx.action == MiddlewareAction.ABORT:
                    result = ToolResult(
                        content=[TextContent(text=ctx.abort_reason or "Execution aborted by middleware")],
                        details={
                            "aborted": True,
                            "reason": ctx.abort_reason,
                            **{
                                key: value
                                for key, value in ctx.metadata.items()
                                if not str(key).startswith("_")
                            },
                        },
                    )
                    is_error = True
                else:
                    # 执行工具（可能使用中间件修改后的参数）
                    result = await tool_port.execute(
                        tool_name=ctx.tool_name,
                        arguments=ctx.arguments,
                        abort_event=abort_event,
                    )
                    ctx.result = result
                    
                    # 执行 after 中间件
                    ctx = await middleware_pipeline.execute_after(ctx)
                    
                    # 使用中间件可能修改的结果
                    if ctx.result is not None:
                        result = ctx.result
                        if hasattr(result, "details") and isinstance(result.details, dict):
                            result.details = {
                                **result.details,
                                **{
                                    key: value
                                    for key, value in ctx.metadata.items()
                                    if not str(key).startswith("_")
                                },
                            }
                        if isinstance(result.details, dict) and result.details.get("error"):
                            is_error = True
            else:
                # 直接执行工具
                result = await tool_port.execute(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    abort_event=abort_event,
                )
                if (
                    result is not None
                    and hasattr(result, "details")
                    and isinstance(result.details, dict)
                    and result.details.get("error")
                ):
                    is_error = True

        except Exception as e:
            is_error = True
            error_msg = str(e)
            result = ToolResult(
                content=[TextContent(text=f"Error: {error_msg}")],
                details={"error": error_msg, "error_type": type(e).__name__},
            )

        duration_ms = (time.time() - start_time) * 1000

        # 发送结束事件
        yield ToolExecutionEndEvent(
            tool_call_id=tc.id,
            tool_name=tc.name,
            result=result,
            is_error=is_error,
            duration_ms=duration_ms,
        )

        if (
            result is not None
            and isinstance(getattr(result, "details", None), dict)
            and result.details.get("force_finalize")
        ):
            for remaining in tool_calls[i + 1:]:
                yield _create_skipped_event(remaining, "Skipped due to tool budget exhaustion")
            break

        # 检查 steering 消息
        if get_steering:
            try:
                steering = await get_steering()
                if steering:
                    # 跳过剩余工具
                    for remaining in tool_calls[i + 1:]:
                        yield _create_skipped_event(remaining, "Skipped due to steering")
                    break
            except Exception:
                pass


def _create_skipped_event(
    tc: ToolCallContent,
    reason: str
) -> ToolExecutionEndEvent:
    """创建跳过事件.
    
    Args:
        tc: 工具调用内容
        reason: 跳过原因
    
    Returns:
        ToolExecutionEndEvent
    """
    from .types import TextContent, ToolExecutionEndEvent, ToolResult

    return ToolExecutionEndEvent(
        tool_call_id=tc.id,
        tool_name=tc.name,
        result=ToolResult(
            content=[TextContent(text=reason)],
            details={"skipped": True, "reason": reason},
        ),
        is_error=True,
        duration_ms=0,
    )


async def execute_tool_calls_parallel(
    trace_id: str,
    llm_call_id: str,
    tool_port: ToolPort | None,
    tools: list[AgentTool],
    tool_calls: list[ToolCallContent],
    abort_event: asyncio.Event | None = None,
    max_concurrent: int = 5,
) -> list[tuple[ToolCallContent, ToolResult, bool, float]]:
    """并行执行工具调用.
    
    Args:
        trace_id: 追踪 ID
        llm_call_id: LLM 调用 ID
        tool_port: 工具执行端口
        tools: 可用工具列表
        tool_calls: 要执行的工具调用列表
        abort_event: 中止事件
        max_concurrent: 最大并发数
    
    Returns:
        list[tuple[ToolCallContent, ToolResult, is_error, duration_ms]]
    """
    from .types import TextContent, ToolResult

    semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_single(tc: ToolCallContent) -> tuple[ToolCallContent, ToolResult, bool, float]:
        async with semaphore:
            if abort_event and abort_event.is_set():
                return (
                    tc,
                    ToolResult(
                        content=[TextContent(text="Aborted by user")],
                        details={"skipped": True},
                    ),
                    True,
                    0,
                )

            tool = next((t for t in tools if t.name == tc.name), None)
            start_time = time.time()

            try:
                if tool is None:
                    raise ValueError(f"Tool not found: {tc.name}")

                if tool_port is None:
                    raise ValueError("ToolPort is not configured")

                result = await tool_port.execute(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    abort_event=abort_event,
                )
                is_error = bool(
                    result is not None
                    and hasattr(result, "details")
                    and isinstance(result.details, dict)
                    and result.details.get("error")
                )
                return (tc, result, is_error, (time.time() - start_time) * 1000)

            except Exception as e:
                return (
                    tc,
                    ToolResult(
                        content=[TextContent(text=f"Error: {str(e)}")],
                        details={"error": str(e)},
                    ),
                    True,
                    (time.time() - start_time) * 1000,
                )

    tasks = [execute_single(tc) for tc in tool_calls]
    results = await asyncio.gather(*tasks)

    return list(results)
