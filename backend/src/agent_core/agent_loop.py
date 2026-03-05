"""Agent Loop 核心实现.

实现 pi-agent 风格的双层循环架构:
- 外层循环: 处理 follow-up 消息
- 内层循环: 处理 tool calls + steering 消息

设计原则:
- AsyncGenerator 返回事件流
- 支持 abort 中断机制
- 支持 steering 和 follow-up 消息注入
- 通过 Port 接口调用外部系统

内部使用 _AgentLoopRunner 类封装循环状态和逻辑,
公共 API agent_loop() 保持为薄包装函数.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from .types import (
    AgentContext,
    AgentMessage,
    AgentEvent,
    AgentStartEvent,
    AgentEndEvent,
    TurnStartEvent,
    TurnEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    MessageEndEvent,
    AssistantMessage,
    ToolResultMessage,
    ToolCallContent,
    TextContent,
    ThinkingContent,
    StreamChunkType,
    ToolExecutionEndEvent,
    LogLevel,
    LogCategory,
    LLMCallLog,
    ToolCallLog,
)
from .context_transform import convert_messages_to_llm, estimate_tokens, content_to_dict
from .tool_executor import execute_tool_calls

if TYPE_CHECKING:
    from .config import AgentCoreConfig
    from .ports.llm_port import LLMPort
    from .logger import AgentLogger


# ============================================================
# 公共 API（签名不变）
# ============================================================

async def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: "AgentCoreConfig",
    abort_event: asyncio.Event | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Agent Loop 主入口.

    实现双层循环架构:
    - 外层循环: 处理 follow-up 消息
    - 内层循环: 处理 tool calls + steering 消息

    Args:
        prompts: 初始用户消息
        context: Agent 上下文 (system_prompt, messages, tools)
        config: Agent Core 配置
        abort_event: 中止事件

    Yields:
        AgentEvent: 各类事件

    Example:
        async for event in agent_loop(
            prompts=[UserMessage.from_text("Hello")],
            context=AgentContext(system_prompt="You are helpful."),
            config=config,
        ):
            print(event.type)
    """
    runner = _AgentLoopRunner(prompts, context, config, abort_event)
    async for event in runner.run():
        yield event


# ============================================================
# 内部执行器
# ============================================================

class _AgentLoopRunner:
    """Agent Loop 内部执行器.

    封装双层循环的状态和逻辑, 通过实例属性管理共享状态,
    每个方法专注单一职责.
    """

    def __init__(
        self,
        prompts: list[AgentMessage],
        context: AgentContext,
        config: "AgentCoreConfig",
        abort_event: asyncio.Event | None,
    ) -> None:
        if config.llm is None:
            raise ValueError("LLMPort is required")

        self.config = config
        self.abort_event = abort_event
        self.prompts = prompts

        # 追踪 - 复用或生成 trace_id
        # 优先从请求上下文获取 trace_id，确保整个请求链路一致
        try:
            from src.conversation.context import get_current_context
        except ImportError:  # 兼容不同运行入口
            from backend.src.conversation.context import get_current_context  # type: ignore
        req_ctx = get_current_context()
        if req_ctx and req_ctx.trace_id:
            self.trace_id = req_ctx.trace_id
        else:
            self.trace_id = str(uuid.uuid4())[:12]
        self.start_time = time.time()

        # 日志器（可选）
        self.logger: AgentLogger | None = getattr(config, 'logger', None)

        # 上下文和消息
        self.new_messages: list[AgentMessage] = list(prompts)
        self.current_context = AgentContext(
            system_prompt=context.system_prompt or config.system_prompt,
            messages=[*context.messages, *prompts],
            tools=context.tools,
        )

        # 循环状态
        self.turn_index = 0
        self.pending_messages: list[AgentMessage] = []

        # 跨 yield 传递结果（async generator 无法 return 值）
        self._last_assistant_msg: AssistantMessage | None = None
        self._last_tool_results: list[ToolResultMessage] = []
        self._last_llm_call_id: str = ""

        # 日志: agent loop 开始
        if self.logger:
            self.logger.create_log_entry(
                trace_id=self.trace_id,
                event="agent_loop_start",
                message=f"Agent loop started with {len(prompts)} prompt(s)",
                category=LogCategory.AGENT_LOOP,
                data={
                    "prompt_count": len(prompts),
                    "system_prompt_length": len(self.current_context.system_prompt),
                    "tool_count": len(self.current_context.tools),
                    "model": config.model,
                    "provider": config.provider,
                },
            )

    # ----------------------------------------------------------
    # 主循环
    # ----------------------------------------------------------

    async def run(self) -> AsyncGenerator[AgentEvent, None]:
        """主循环: 协调双层循环."""
        try:
            from src.conversation.context import get_current_context, set_current_context, AgentContext as ReqContext, ContextSource
        except ImportError:
            from backend.src.conversation.context import get_current_context, set_current_context, AgentContext as ReqContext, ContextSource  # type: ignore
        req_ctx = get_current_context()
        if not req_ctx:
            # 如果没有上下文，创建一个新的
            req_ctx = ReqContext(
                trace_id=self.trace_id,
                source=ContextSource.INTERNAL
            )
            set_current_context(req_ctx)
        elif not req_ctx.trace_id:
            # 如果上下文没有 trace_id，设置它
            req_ctx.trace_id = self.trace_id

        async for ev in self._emit_start_events():
            yield ev

        try:
            # === 外层循环: 处理 follow-up ===
            while True:
                if self._is_aborted():
                    break

                has_more_tool_calls = True

                # === 内层循环: 处理 tool calls + steering ===
                while has_more_tool_calls or self.pending_messages:
                    if self._is_aborted():
                        break

                    async for ev in self._process_pending_messages():
                        yield ev

                    async for ev in self._call_llm():
                        yield ev

                    msg = self._last_assistant_msg
                    if msg is None:
                        break

                    if msg.stop_reason in ("error", "aborted"):
                        yield TurnEndEvent(
                            turn_index=self.turn_index,
                            message=msg,
                            tool_results=[],
                        )
                        break

                    tool_calls = msg.get_tool_calls()
                    has_more_tool_calls = len(tool_calls) > 0
                    self._last_tool_results = []

                    if has_more_tool_calls:
                        async for ev in self._execute_tools(tool_calls):
                            yield ev

                    yield TurnEndEvent(
                        turn_index=self.turn_index,
                        message=msg,
                        tool_results=self._last_tool_results,
                    )

                    self.turn_index += 1
                    if has_more_tool_calls or self.pending_messages:
                        yield TurnStartEvent(turn_index=self.turn_index)

                # === 检查 follow-up messages ===
                # TODO: 支持 get_follow_up_messages 回调
                break

        except Exception as e:
            async for ev in self._handle_error(e):
                yield ev

        async for ev in self._emit_end_event():
            yield ev

    # ----------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------

    def _is_aborted(self) -> bool:
        """检查是否已中止."""
        return bool(self.abort_event and self.abort_event.is_set())

    async def _emit_start_events(self) -> AsyncGenerator[AgentEvent, None]:
        """发送 Agent 开始事件和初始 prompt 消息事件."""
        yield AgentStartEvent(trace_id=self.trace_id)
        yield TurnStartEvent(turn_index=self.turn_index)

        for prompt in self.prompts:
            yield MessageStartEvent(message=prompt)
            yield MessageEndEvent(message=prompt)

    async def _process_pending_messages(self) -> AsyncGenerator[AgentEvent, None]:
        """处理 pending messages (steering 或 follow-up)."""
        if not self.pending_messages:
            return

        for msg in self.pending_messages:
            yield MessageStartEvent(message=msg)
            yield MessageEndEvent(message=msg)
            self.current_context.messages.append(msg)
            self.new_messages.append(msg)

        self.pending_messages = []

    async def _call_llm(self) -> AsyncGenerator[AgentEvent, None]:
        """执行一次 LLM 调用: 消息转换 → 日志 → 流式响应 → 日志.

        结果存入 self._last_assistant_msg.
        """
        self._last_assistant_msg = None
        llm_call_id = str(uuid.uuid4())[:8]
        self._last_llm_call_id = llm_call_id

        # 转换消息为 LLM 格式
        llm_messages = convert_messages_to_llm(self.current_context.messages)

        # 日志: LLM 调用开始
        if self.logger:
            self.logger.log_llm_call_start(LLMCallLog(
                call_id=llm_call_id,
                trace_id=self.trace_id,
                model=self.config.model,
                provider=self.config.provider,
                system_prompt=self.current_context.system_prompt,
                messages=llm_messages,
                message_count=len(llm_messages),
                estimated_tokens=estimate_tokens(self.current_context.messages),
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                thinking_level=self.config.thinking_level,
                tools=[t.to_llm_tool() for t in self.current_context.tools] if self.current_context.tools else None,
            ))

        llm_call_start_time = time.time()

        # 流式获取响应
        async for event in _stream_assistant_response(
            llm=self.config.llm,
            llm_call_id=llm_call_id,
            system_prompt=self.current_context.system_prompt,
            messages=llm_messages,
            tools=self.current_context.tools,
            model=self.config.model,
            provider=self.config.provider,
            abort_event=self.abort_event,
        ):
            yield event

            if isinstance(event, MessageEndEvent) and event.message:
                if isinstance(event.message, AssistantMessage):
                    self._last_assistant_msg = event.message

        if self._last_assistant_msg is None:
            return

        # 日志: LLM 调用结束
        if self.logger:
            llm_duration = (time.time() - llm_call_start_time) * 1000
            self.logger.log_llm_call_end(
                call_id=llm_call_id,
                response={
                    "content": [content_to_dict(c) for c in self._last_assistant_msg.content],
                    "stop_reason": self._last_assistant_msg.stop_reason,
                },
                usage=self._last_assistant_msg.usage,
                duration_ms=llm_duration,
                error=self._last_assistant_msg.error_message,
            )

        self.current_context.messages.append(self._last_assistant_msg)
        self.new_messages.append(self._last_assistant_msg)

    async def _execute_tools(
        self,
        tool_calls: list[ToolCallContent],
    ) -> AsyncGenerator[AgentEvent, None]:
        """执行工具调用: 日志 → 执行 → 收集结果 → 日志.

        结果存入 self._last_tool_results.
        """
        self._last_tool_results = []
        llm_call_id = self._last_llm_call_id

        # 日志: 工具调用开始
        if self.logger:
            for tc in tool_calls:
                self.logger.log_tool_call_start(ToolCallLog(
                    call_id=tc.id,
                    trace_id=self.trace_id,
                    llm_call_id=llm_call_id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                ))

        # 执行工具调用
        async for event in execute_tool_calls(
            trace_id=self.trace_id,
            llm_call_id=llm_call_id,
            tool_port=self.config.tools,
            tools=self.current_context.tools,
            tool_calls=tool_calls,
            abort_event=self.abort_event,
            get_steering=None,  # TODO: 支持 steering
        ):
            yield event

            if isinstance(event, ToolExecutionEndEvent):
                # 日志: 工具调用结束
                if self.logger:
                    self.logger.log_tool_call_end(
                        call_id=event.tool_call_id,
                        result=event.result,
                        duration_ms=event.duration_ms,
                        is_error=event.is_error,
                        error=str(event.result.details.get("error", "")) if event.is_error and event.result else None,
                    )

                result_msg = ToolResultMessage(
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    content=event.result.content if event.result else [],
                    is_error=event.is_error,
                    details=event.result.details if event.result else {},
                )
                self._last_tool_results.append(result_msg)
                self.current_context.messages.append(result_msg)
                self.new_messages.append(result_msg)

                yield MessageStartEvent(message=result_msg)
                yield MessageEndEvent(message=result_msg)

    async def _handle_error(self, error: Exception) -> AsyncGenerator[AgentEvent, None]:
        """处理异常: 日志 → 错误消息事件."""
        if self.logger:
            self.logger.create_log_entry(
                trace_id=self.trace_id,
                event="agent_loop_error",
                message=f"Agent loop error: {str(error)}",
                level=LogLevel.ERROR,
                category=LogCategory.AGENT_LOOP,
                error=str(error),
                data={
                    "error_type": type(error).__name__,
                    "stack_trace": traceback.format_exc(),
                },
            )

        error_msg = AssistantMessage(
            content=[TextContent(text=f"Error: {str(error)}")],
            model=self.config.model,
            provider=self.config.provider,
            stop_reason="error",
            error_message=str(error),
        )
        yield MessageStartEvent(message=error_msg)
        yield MessageEndEvent(message=error_msg)
        self.new_messages.append(error_msg)

    async def _emit_end_event(self) -> AsyncGenerator[AgentEvent, None]:
        """发送 Agent 结束事件和日志."""
        total_duration = (time.time() - self.start_time) * 1000

        if self.logger:
            was_aborted = self._is_aborted()
            self.logger.create_log_entry(
                trace_id=self.trace_id,
                event="agent_loop_aborted" if was_aborted else "agent_loop_end",
                message=f"Agent loop {'aborted' if was_aborted else 'completed'} in {total_duration:.0f}ms",
                category=LogCategory.AGENT_LOOP,
                duration_ms=total_duration,
                data={
                    "total_messages": len(self.new_messages),
                    "total_turns": self.turn_index + 1,
                    "aborted": bool(was_aborted),
                },
            )

        yield AgentEndEvent(
            messages=self.new_messages,
            trace_id=self.trace_id,
            total_duration_ms=total_duration,
        )


# ============================================================
# 模块级辅助函数（不依赖 runner 状态）
# ============================================================

async def _stream_assistant_response(
    llm: "LLMPort",
    llm_call_id: str,
    system_prompt: str,
    messages: list[dict],
    tools: list,
    model: str,
    provider: str,
    abort_event: asyncio.Event | None,
) -> AsyncGenerator[AgentEvent, None]:
    """流式获取 Assistant 响应.

    Args:
        llm: LLM 端口
        llm_call_id: LLM 调用 ID
        system_prompt: 系统提示词
        messages: LLM 格式的消息列表
        tools: 工具列表
        model: 模型名称
        provider: 提供商名称
        abort_event: 中止事件

    Yields:
        MessageStartEvent | MessageUpdateEvent | MessageEndEvent
    """
    # 初始化 partial message
    partial_message = AssistantMessage(
        model=model,
        provider=provider,
    )

    yield MessageStartEvent(message=partial_message)

    try:
        async for chunk in llm.stream(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools if tools else None,
        ):
            if abort_event and abort_event.is_set():
                partial_message.stop_reason = "aborted"
                break

            if chunk.type == StreamChunkType.TEXT_DELTA:
                _append_text_content(partial_message, chunk.delta)
                yield MessageUpdateEvent(
                    message=partial_message,
                    delta=chunk.delta,
                    delta_type="text",
                )

            elif chunk.type == StreamChunkType.THINKING_DELTA:
                _append_thinking_content(partial_message, chunk.delta)
                yield MessageUpdateEvent(
                    message=partial_message,
                    delta=chunk.delta,
                    delta_type="thinking",
                )

            elif chunk.type == StreamChunkType.TOOL_CALL:
                partial_message.content.append(ToolCallContent(
                    id=chunk.tool_call_id,
                    name=chunk.tool_name,
                    arguments=chunk.arguments,
                ))
                yield MessageUpdateEvent(
                    message=partial_message,
                    delta="",
                    delta_type="tool_call",
                )

            elif chunk.type == StreamChunkType.DONE:
                partial_message.stop_reason = chunk.stop_reason
                partial_message.usage = chunk.usage or {}

            elif chunk.type == StreamChunkType.ERROR:
                partial_message.stop_reason = "error"
                partial_message.error_message = chunk.error
                break

    except Exception as e:
        partial_message.stop_reason = "error"
        partial_message.error_message = str(e)

    yield MessageEndEvent(message=partial_message)


def _append_text_content(msg: AssistantMessage, delta: str) -> None:
    """追加文本内容到消息."""
    if msg.content and isinstance(msg.content[-1], TextContent):
        msg.content[-1].text += delta
    else:
        msg.content.append(TextContent(text=delta))


def _append_thinking_content(msg: AssistantMessage, delta: str) -> None:
    """追加思考内容到消息."""
    if msg.content and isinstance(msg.content[-1], ThinkingContent):
        msg.content[-1].thinking += delta
    else:
        msg.content.append(ThinkingContent(thinking=delta))
