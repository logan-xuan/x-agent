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
from typing import Any, TYPE_CHECKING

from ..services.compression.token_counter import TokenCounter
from .context_transform import content_to_dict, convert_messages_to_llm
from .experience_learning import ExperienceLearner, format_experience_for_prompt
from .tool_executor import execute_tool_calls
from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentMessage,
    AgentStartEvent,
    AssistantMessage,
    LLMCallLog,
    LogCategory,
    LogLevel,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    StreamChunkType,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolCallLog,
    ToolExecutionEndEvent,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
)

if TYPE_CHECKING:
    from .config import AgentCoreConfig
    from .logger import AgentLogger
    from .ports.llm_port import LLMPort


_TOKEN_COUNTER = TokenCounter()


# ============================================================
# 公共 API（签名不变）
# ============================================================

async def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentCoreConfig,
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
        config: AgentCoreConfig,
        abort_event: asyncio.Event | None,
    ) -> None:
        if config.llm is None:
            raise ValueError("LLMPort is required")

        self.config = config
        self.abort_event = abort_event
        self.prompts = prompts

        # 追踪 - 从请求上下文的 Identity 获取 trace_id 和 session_id
        # Identity 是全局唯一身份信息的单一来源
        try:
            from src.conversation.context import get_current_context
        except ImportError:  # 兼容不同运行入口
            from backend.src.conversation.context import get_current_context  # type: ignore
        req_ctx = get_current_context()
        if req_ctx and req_ctx.trace_id:
            self.trace_id = req_ctx.trace_id
        else:
            self.trace_id = str(uuid.uuid4())[:12]
        # session_id 从 Identity 获取，确保与全局一致
        self.session_id: str = (req_ctx.session_id if req_ctx and req_ctx.session_id else self.trace_id)
        # agent_id 从 Identity 获取
        self.agent_id: str = req_ctx.agent_id if req_ctx else self.trace_id
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
        self._stateful_mode_detector: Any | None = None
        self._stateful_updater: Any | None = None
        self._tool_result_archiver: Any | None = None

        # 经验学习
        self._experience_learner: ExperienceLearner | None = None
        self._tool_call_logs: list[dict] = []
        if config.enable_experience_learning and config.memory is not None:
            self._experience_learner = ExperienceLearner(
                memory=config.memory,
                search_timeout_ms=config.experience_search_timeout_ms,
            )

        try:
            from ..services.context import (
                get_mode_detector,
                get_session_state_updater,
                get_tool_result_archiver,
            )

            self._stateful_mode_detector = get_mode_detector()
            self._stateful_updater = get_session_state_updater()
            self._tool_result_archiver = get_tool_result_archiver()
        except Exception:
            self._stateful_mode_detector = None
            self._stateful_updater = None
            self._tool_result_archiver = None

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
            from src.conversation.context import AgentContext as ReqContext
            from src.conversation.context import get_current_context, set_current_context
        except ImportError:
            from backend.src.conversation.context import AgentContext as ReqContext
            from backend.src.conversation.context import (  # type: ignore
                get_current_context,
                set_current_context,
            )
        req_ctx = get_current_context()
        if not req_ctx:
            # 如果没有上下文（如 CLI 或测试入口），创建一个带 Identity 的新上下文
            req_ctx = ReqContext.for_cli()
            req_ctx.trace_id = self.trace_id
            set_current_context(req_ctx)
        elif not req_ctx.trace_id:
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

                    await self._persist_stateful_turn_snapshot(msg, self._last_tool_results)

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
        """执行一次 LLM 调用: 消息转换 → 上下文压缩 → 日志 → 流式响应 → 日志.

        结果存入 self._last_assistant_msg.
        """
        self._last_assistant_msg = None
        llm_call_id = str(uuid.uuid4())[:8]
        self._last_llm_call_id = llm_call_id

        # 转换消息为 LLM 格式
        llm_messages = convert_messages_to_llm(self.current_context.messages)
        effective_system_prompt = self.current_context.system_prompt or ""

        # 经验检索: 将经验提示词纳入本轮有效 system prompt，避免绕过压缩预算。
        if self._experience_learner is not None:
            experience_prompt = await self._retrieve_and_format_experience()
            if experience_prompt:
                effective_system_prompt = (
                    f"{effective_system_prompt}\n\n{experience_prompt}"
                    if effective_system_prompt
                    else experience_prompt
                )

        # 上下文压缩 (通过 ContextPort，如果已配置)
        llm_tools = [t.to_llm_tool() for t in self.current_context.tools] if self.current_context.tools else None
        if (
            self.config.context is not None
            and self.config.enable_context_compression
        ):
            prepared = await self.config.context.prepare_context(
                session_id=self.session_id,
                messages=llm_messages,
                system_prompt=effective_system_prompt,
                tools=llm_tools,
            )
            llm_messages = prepared.messages
            if self.logger and getattr(prepared, "metadata", None):
                self.logger.create_log_entry(
                    trace_id=self.trace_id,
                    event="context_prepared",
                    message="Context prepared for LLM call",
                    category=LogCategory.AGENT_LOOP,
                    data={
                        "context_mode": prepared.metadata.get("context_mode"),
                        "was_compressed": prepared.was_compressed,
                        "original_tokens": prepared.original_tokens,
                        "final_tokens": prepared.final_tokens,
                        "quality_rejected": prepared.metadata.get("quality_rejected", False),
                        "used_fallback": prepared.metadata.get("used_fallback", False),
                        "token_breakdown": prepared.metadata.get("token_breakdown", {}),
                        },
                    )

        estimated_prompt_tokens = _estimate_request_tokens(
            system_prompt=effective_system_prompt,
            messages=llm_messages,
            tools=llm_tools,
        )

        # 日志: LLM 调用开始
        if self.logger:
            self.logger.log_llm_call_start(LLMCallLog(
                call_id=llm_call_id,
                trace_id=self.trace_id,
                model=self.config.model,
                provider=self.config.provider,
                system_prompt=effective_system_prompt,
                messages=llm_messages,
                message_count=len(llm_messages),
                estimated_tokens=estimated_prompt_tokens,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                thinking_level=self.config.thinking_level,
                tools=llm_tools,
            ))

        llm_call_start_time = time.time()

        # 流式获取响应
        async for event in _stream_assistant_response(
            llm=self.config.llm,
            llm_call_id=llm_call_id,
            system_prompt=effective_system_prompt,
            messages=llm_messages,
            tools=self.current_context.tools,
            model=self.config.model,
            provider=self.config.provider,
            max_tokens=self.config.max_tokens,
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
            middleware_pipeline=self.config.tool_middleware_pipeline,  # 传递中间件管道
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

                # 收集工具调用日志用于经验提取
                if self._experience_learner is not None:
                    result_text = ""
                    if event.result and event.result.content:
                        text_parts: list[str] = []
                        for content_item in event.result.content:
                            if isinstance(content_item, TextContent):
                                text_parts.append(content_item.text)
                        result_text = " ".join(text_parts)[:200]

                    self._tool_call_logs.append({
                        "tool_name": event.tool_name,
                        "arguments": {},
                        "is_error": event.is_error,
                        "duration_ms": event.duration_ms,
                        "result_summary": result_text,
                    })

                result_msg = ToolResultMessage(
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    content=event.result.content if event.result else [],
                    is_error=event.is_error,
                    details={
                        **(event.result.details if event.result else {}),
                        "duration_ms": event.duration_ms,
                        "tool_status": "error" if event.is_error else "completed",
                    },
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

    async def _persist_stateful_turn_snapshot(
        self,
        assistant_msg: AssistantMessage,
        tool_results: list[ToolResultMessage],
    ) -> None:
        """Persist a lightweight structured state snapshot after each turn."""
        if self._stateful_updater is None or self._stateful_mode_detector is None:
            return

        latest_user = self._find_latest_user_message()
        new_messages: list[dict[str, Any]] = []
        if latest_user is not None:
            new_messages.append(
                {
                    "role": "user",
                    "content": self._message_to_text(latest_user),
                }
            )
        new_messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get_text(),
            }
        )

        tool_payloads = []
        for result in tool_results:
            details = dict(result.details)
            if self._tool_result_archiver is not None:
                try:
                    details = await self._tool_result_archiver.archive(
                        session_id=self.session_id,
                        tool_name=result.tool_name,
                        result_text=self._tool_result_to_text(result),
                        details=details,
                    )
                except Exception as exc:
                    if self.logger:
                        self.logger.create_log_entry(
                            trace_id=self.trace_id,
                            event="tool_result_archive_failed",
                            message=f"Tool result archive failed: {str(exc)}",
                            level=LogLevel.WARNING,
                            category=LogCategory.AGENT_LOOP,
                            data={"tool_name": result.tool_name, "error_type": type(exc).__name__},
                        )

            tool_payloads.append(
                {
                    "tool_name": result.tool_name,
                    "error": details.get("error") if result.is_error else "",
                    "artifact_ref": details.get("artifact_ref"),
                    "details": details,
                    "evidence_count": details.get("evidence_count", 0),
                }
            )

        try:
            mode = self._stateful_mode_detector.detect(
                messages=new_messages,
                tools=self.current_context.tools,
            )
            await self._stateful_updater.update_after_turn(
                session_id=self.session_id,
                agent_id=self.agent_id,
                mode=mode,
                new_messages=new_messages,
                tool_results=tool_payloads,
                delegate_results=[],
            )
        except Exception as exc:
            if self.logger:
                self.logger.create_log_entry(
                    trace_id=self.trace_id,
                    event="session_state_update_failed",
                    message=f"Session state update failed: {str(exc)}",
                    level=LogLevel.WARNING,
                    category=LogCategory.AGENT_LOOP,
                    data={"error_type": type(exc).__name__},
                )

    def _find_latest_user_message(self) -> AgentMessage | None:
        for message in reversed(self.current_context.messages):
            if getattr(message, "role", None) == "user":
                return message
        return None

    @staticmethod
    def _message_to_text(message: AgentMessage) -> str:
        content = getattr(message, "content", [])
        parts: list[str] = []
        for item in content:
            if hasattr(item, "text") and item.text:
                parts.append(item.text)
        return " ".join(parts)

    @staticmethod
    def _tool_result_to_text(message: ToolResultMessage) -> str:
        parts: list[str] = []
        for item in message.content:
            if hasattr(item, "text") and item.text:
                parts.append(item.text)
        return " ".join(parts)

    async def _retrieve_and_format_experience(self) -> str:
        """检索相关经验并格式化为 prompt 文本.

        从用户消息中提取查询文本，检索历史经验，
        返回格式化后的经验文本用于注入 system prompt。

        Returns:
            格式化后的经验文本，空字符串表示无相关经验
        """
        if self._experience_learner is None:
            return ""

        # 从最近的用户消息中提取查询文本
        query_parts = []
        for msg in reversed(self.current_context.messages):
            if hasattr(msg, "role") and getattr(msg, "role", None) == "user":
                for content_item in getattr(msg, "content", []):
                    if hasattr(content_item, "text") and content_item.text:
                        query_parts.append(content_item.text[:200])
                        break
                if query_parts:
                    break

        if not query_parts:
            return ""

        query = " ".join(query_parts)
        experiences = await self._experience_learner.retrieve_experience(query)
        return format_experience_for_prompt(experiences)

    async def _emit_end_event(self) -> AsyncGenerator[AgentEvent, None]:
        """发送 Agent 结束事件和日志."""
        total_duration = (time.time() - self.start_time) * 1000

        # 经验提取: 对话结束后异步分析工具调用序列，提取经验模式
        if (
            self._experience_learner is not None
            and self._tool_call_logs
        ):
            asyncio.create_task(
                self._experience_learner.extract_experience(
                    trace_id=self.trace_id,
                    tool_call_logs=self._tool_call_logs,
                ),
                name=f"extract-experience-{self.trace_id[:8]}",
            )

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


def _estimate_request_tokens(
    *,
    system_prompt: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> int:
    """Estimate tokens for the final request payload sent to the provider."""
    return (
        _TOKEN_COUNTER.count_text(system_prompt)
        + _TOKEN_COUNTER.count_messages(messages)
        + _TOKEN_COUNTER.count_tool_definitions(tools)
    )


async def _stream_assistant_response(
    llm: LLMPort,
    llm_call_id: str,
    system_prompt: str,
    messages: list[dict],
    tools: list,
    model: str,
    provider: str,
    max_tokens: int | None,
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
            provider_name=provider or None,
            max_tokens=max_tokens,
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
