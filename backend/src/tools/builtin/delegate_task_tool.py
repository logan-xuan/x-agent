"""Agent 任务委派工具。

DelegateTaskTool 允许一个 Agent 将任务委派给另一个 Agent。
与 NotifyTool 的区别：
- NotifyTool: 直接推送文本消息，不经过 agent_loop
- DelegateTaskTool: 触发目标 Agent 的完整 agent_loop（加载上下文、技能、工具等）

使用场景：
1. Main Agent 需要将复杂任务分派给专业 Agent（如代码审查、天气查询）
2. Agent 之间的协作任务，需要对方执行分析并返回结果
3. 需要目标 Agent 使用其专属工具完成任务

与 notify 的关键区别：
- notify: 只是消息转发，适合提醒/告警等简单通知
- delegate_task: 完整任务执行，目标 Agent 会调用工具、分析、返回结果
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.agent_core.types import LogCategory
from src.conversation.context import AgentContext
from src.conversation.identity import AgentType, ChannelType, get_identity_manager
from src.utils.logger import get_logger

from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

logger = get_logger(__name__)


class DelegateTaskTool(BaseTool):
    """Agent 任务委派工具。

    允许一个 Agent 将任务委派给另一个 Agent 执行。
    目标 Agent 通过完整的 agent loop 处理任务（包括加载上下文、技能、工具等），
    然后将结果返回给调用方。

    Features:
    - 完整 Agent Loop 执行（区别于 notify 的直接消息转发）
    - 支持指定目标 session（可选，不传则自动解析）
    - 支持同步等待结果或异步委派
    """

    @property
    def name(self) -> str:
        return "delegate_task"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to another Agent for processing. The target Agent will execute "
            "the task through its complete agent loop, which includes loading its own context, "
            "skills, tools, and performing any necessary analysis or tool calls.\n\n"
            "This is the CORRECT way to ask another Agent to perform work (e.g., query weather, "
            "analyze code, search documents). The target Agent will process the task using its "
            "full capabilities and return the result.\n\n"
            "When to use:\n"
            "- You need another Agent to execute a task and get the result\n"
            "- The task requires the target Agent's specialized tools or knowledge\n"
            "- User says 'tell [agent] to do X' or 'ask [agent] about Y'\n"
            "- User says '发消息给 [agent] 让他 [做某事]' or '让 [agent] 帮我 [查询/分析/...]'\n\n"
            "When NOT to use (use 'notify' instead):\n"
            "- You only need to send a simple notification/alert/reminder\n"
            "- No response or task execution is needed from the target Agent\n\n"
            "Key parameters:\n"
            "- agent_id: Target Agent ID (e.g., 'product-assistant', 'code-assistant')\n"
            "- task: The task description for the target Agent to execute\n"
            "- session_id: (optional) Target session ID, auto-resolved if not provided\n"
            "- wait_for_result: (optional) Whether to wait for task completion, default true"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="agent_id",
                type=ToolParameterType.STRING,
                description=(
                    "The target Agent ID to delegate the task to. "
                    "Examples: 'product-assistant', 'code-assistant', 'research-agent'. "
                    "Use the exact agent_id from the multi-agent configuration."
                ),
                required=True,
                min_length=1,
                max_length=100,
            ),
            ToolParameter(
                name="task",
                type=ToolParameterType.STRING,
                description=(
                    "The task description to delegate to the target Agent. "
                    "Be clear and specific about what you want the Agent to do. "
                    "The target Agent will execute this through its full agent loop."
                ),
                required=True,
                min_length=1,
                max_length=8192,
            ),
            ToolParameter(
                name="session_id",
                type=ToolParameterType.STRING,
                description=(
                    "Target session ID (optional). If not provided, the system will "
                    "automatically resolve the active session for the target Agent, "
                    "or create a new one if needed."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="wait_for_result",
                type=ToolParameterType.BOOLEAN,
                description=(
                    "Whether to wait for the target Agent to complete the task and "
                    "return the result. Default is true. Set to false for fire-and-forget tasks."
                ),
                required=False,
                default=True,
            ),
            ToolParameter(
                name="timeout",
                type=ToolParameterType.NUMBER,
                description=(
                    "Maximum time in seconds to wait for the target agent to complete. "
                    "Default is 120 seconds. Set a higher value for complex tasks. "
                    "Only applies when wait_for_result is true."
                ),
                required=False,
                default=120,
            ),
        ]

    async def execute(
        self,
        agent_id: str,
        task: str,
        session_id: str | None = None,
        wait_for_result: bool = True,
        timeout: float = 120,
    ) -> ToolResult:
        """Execute task delegation to another Agent.

        Args:
            agent_id: Target Agent ID to delegate to.
            task: Task description for the target Agent.
            session_id: Target session ID (optional, auto-resolved if not provided).
            wait_for_result: Whether to wait for completion and return result.
            timeout: Maximum time in seconds to wait for the target agent.

        Returns:
            ToolResult with the delegated task's response or status.
        """
        try:
            canonical_agent_id = self._canonicalize_agent_id(agent_id)
            from src.gateway.agent_invoker import AgentInvoker, InvokeSource
            from src.agent_core.api.dev_routes import get_logger as get_agent_logger
            from src.agent_core.types import LogCategory, LogLevel
            from src.conversation.context import AgentContext, get_current_context, set_current_context
            from src.conversation.identity import AgentType, ChannelType, get_identity_manager
            from src.gateway.agent_bridge import AgentBridge
            from src.gateway.connection_registry import get_connection_registry
            from src.runtime.service import get_runtime_services
            from src.runtime.turn.finish_reason import is_budget_stop_reason
            from src.runtime.adapters import GatewayAdapter as RuntimeGatewayAdapter

            logger.info(
                "DelegateTaskTool executing",
                extra={
                    "target_agent_id": agent_id,
                    "canonical_target_agent_id": canonical_agent_id,
                    "task_length": len(task),
                    "session_id": session_id,
                    "wait_for_result": wait_for_result,
                },
            )

            # Create invoker
            invoker = AgentInvoker()
            current_context = get_current_context()
            runtime_services = get_runtime_services()
            can_use_runtime_child_flow = (
                session_id is None
                and current_context is not None
                and bool(current_context.session_id)
            )
            effective_timeout = self._resolve_sync_wait_timeout(
                requested_timeout=float(timeout),
                current_context=current_context,
                runtime_services=runtime_services,
            )
            child_trace_ref: dict[str, str] = {}
            child_abort_ref: dict[str, asyncio.Event] = {}
            parent_agent_logger = get_agent_logger()

            async def _prepare_runtime_child_flow() -> dict[str, object]:
                from src.conversation.session import SessionManager

                session_manager = SessionManager()
                delegate_budget_profile = self._resolve_delegate_budget_profile(runtime_services)

                parent = await runtime_services.orchestrator.resolve_or_create(
                    {
                        "session_id": current_context.session_id,
                        "channel": current_context.channel_type.value,
                        "user_id": current_context.user_id,
                        "channel_id": current_context.channel_id,
                    }
                )

                target_session = await self._resolve_target_session(
                    session_manager=session_manager,
                    agent_id=canonical_agent_id,
                )
                if target_session is None:
                    target_session = await session_manager.create_session(
                        title=f"{canonical_agent_id} 对话",
                        agent_id=canonical_agent_id,
                        close_existing=False,
                    )

                parent_context = current_context
                target_channel_type = (
                    parent_context.channel_type if parent_context is not None else ChannelType.WEB_CHAT
                )
                delegate_profile = runtime_services.turn_profiles.get(delegate_budget_profile)
                delegate_timeout_ms = int(
                    getattr(delegate_profile, "max_wall_time_ms", 180000) or 180000
                )
                invoker = AgentInvoker()
                _runtime_session, child_request = await invoker.prepare_runtime_turn(
                    task,
                    agent_id=canonical_agent_id,
                    session_id=target_session.id,
                    channel_type=target_channel_type,
                    source=InvokeSource.AGENT,
                    metadata={
                        "persist_user_message": False,
                        "prompt_mode": "minimal",
                        "_runtime_budget_profile": delegate_profile,
                        "_runtime_compression_profile_name": runtime_services.default_compression_profile,
                        "runtime_timeout_ms": delegate_timeout_ms,
                        "delegate_from_session_id": parent.session_id,
                        "delegate_from_trace_id": current_context.trace_id if current_context is not None else "",
                    },
                )
                child_abort_event = asyncio.Event()
                child_abort_ref["event"] = child_abort_event
                child_request.metadata["runtime_abort_event"] = child_abort_event
                child_context = self._build_child_context(
                    parent_context=parent_context,
                    child_session_id=target_session.id,
                    agent_id=canonical_agent_id,
                )
                child_trace_ref["trace_id"] = child_context.trace_id
                return {
                    "parent": parent,
                    "parent_context": parent_context,
                    "child_request": child_request,
                    "child_context": child_context,
                }

            async def _run_runtime_child_flow(prepared: dict[str, object]) -> dict[str, object]:
                bridge = AgentBridge()
                parent = prepared["parent"]
                parent_context = prepared["parent_context"]
                child_request = prepared["child_request"]
                child_context = prepared["child_context"]
                self._log_delegate_child_event(
                    parent_logger=parent_agent_logger,
                    parent_context=parent_context,
                    event="delegate_child_start",
                    message=f"Delegated child session started: {agent_id}",
                    data={
                        "target_agent_id": agent_id,
                        "child_session_id": child_request.session.session_id,
                        "child_trace_id": child_context.trace_id,
                    },
                    level=LogLevel.INFO,
                )
                set_current_context(child_context)
                try:
                    runtime_result = await bridge.run_runtime_turn(child_request)
                finally:
                    if parent_context is not None:
                        set_current_context(parent_context)
                finish_reason = runtime_result.finish_reason or "controller_abort"
                child_status = self._classify_runtime_child_status(
                    kind=runtime_result.kind,
                    finish_reason=finish_reason,
                    unresolved=list(
                        (runtime_result.updated_task_frame or child_request.task_frame).unresolved
                    ),
                    output_text=runtime_result.output_text or "",
                )
                child_summary = self._child_summary_text(
                    runtime_result.output_text or "",
                    finish_reason=finish_reason,
                    child_status=child_status,
                )
                self._log_delegate_child_event(
                    parent_logger=parent_agent_logger,
                    parent_context=parent_context,
                    event="delegate_child_finish" if child_status == "success" else "delegate_child_error",
                    message=(
                        f"Delegated child session completed: {agent_id}"
                        if child_status == "success"
                        else f"Delegated child session failed: {agent_id}"
                    ),
                    data={
                        "target_agent_id": agent_id,
                        "child_session_id": child_request.session.session_id,
                        "child_trace_id": child_context.trace_id,
                        "finish_reason": finish_reason,
                        "child_status": child_status,
                    },
                    level=LogLevel.INFO if child_status == "success" else LogLevel.ERROR,
                    error=None if child_status == "success" else child_summary,
                )
                return {
                    "session_id": child_request.session.session_id,
                    "trace_id": child_context.trace_id,
                    "status": child_status,
                    "finish_reason": finish_reason,
                    "output_text": runtime_result.output_text or "",
                    "summary": child_summary,
                    "budget": dict(runtime_result.metadata.get("budget", {})),
                    "artifact_refs": [artifact.id for artifact in runtime_result.artifact_refs],
                    "is_budget_stop": bool(is_budget_stop_reason(finish_reason)),
                    "unresolved": list((runtime_result.updated_task_frame or child_request.task_frame).unresolved),
                    "duration_ms": int(
                        runtime_result.metadata.get("runtime_diagnostics", {}).get("milestones_ms", {}).get("completed", 0)
                        or runtime_result.metadata.get("runtime_diagnostics", {}).get("milestones_ms", {}).get("timed_out", 0)
                        or 0
                    ),
                }

            async def _resume_parent_after_child(
                child_result: dict[str, object],
                *,
                parent,
                parent_context,
            ) -> None:
                resume_context = self._build_parent_resume_context(
                    parent_context=parent_context,
                    session_id=parent.session_id,
                    agent_id=parent_context.agent_id if parent_context is not None else "main-agent",
                )
                set_current_context(resume_context)
                try:
                    adapter = RuntimeGatewayAdapter(orchestrator=runtime_services.orchestrator)
                    session, request = await adapter.prepare_resumed_turn(
                        parent.session_key,
                        user_input="请根据刚完成的委托子任务结果继续当前主任务，并向用户汇报最终结果。",
                        metadata={
                            "agent_id": parent_context.agent_id if parent_context is not None else "main-agent",
                            "persist_user_message": False,
                            "source": "agent",
                            "runtime_resume_from_child": True,
                            "runtime_child_trace_id": child_result.get("trace_id", ""),
                        },
                    )
                    request = await adapter.enqueue(session, request)
                    bridge = AgentBridge()
                    result = await bridge.run_runtime_turn(request)
                finally:
                    if parent_context is not None:
                        set_current_context(parent_context)

                if not result.output_text:
                    return

                registry = get_connection_registry()
                await registry.push(
                    parent.session_id,
                    {
                        "type": "message",
                        "content": result.output_text,
                        "model": str(result.metadata.get("model", "")),
                        "is_finished": True,
                    },
                )

            async def _background_child_runner(prepared: dict[str, object]) -> None:
                try:
                    child_result = await _run_runtime_child_flow(prepared)
                    await runtime_services.orchestrator.announcement_manager.enqueue(
                        {
                            "target_session_key": prepared["parent"].session_key,
                            "child_session_key": prepared["child_request"].session.session_key,
                            "status": child_result["status"],
                            "summary": child_result["summary"],
                            "unresolved": child_result["unresolved"],
                            "artifact_refs": child_result["artifact_refs"],
                            "usage": child_result["budget"],
                            "duration_ms": child_result["duration_ms"],
                            "stats_line": f"duration={child_result['duration_ms']}ms",
                            "target_route": prepared["parent"].route.__dict__ if prepared["parent"].route is not None else None,
                            "child_route": prepared["child_request"].route.__dict__ if prepared["child_request"].route is not None else None,
                        }
                    )
                    await _resume_parent_after_child(
                        child_result,
                        parent=prepared["parent"],
                        parent_context=prepared["parent_context"],
                    )
                except Exception as exc:
                    logger.error(
                        "Delegate child background runner failed",
                        extra={
                            "target_agent_id": agent_id,
                            "parent_session_id": prepared["parent"].session_id,
                            "child_session_id": prepared["child_request"].session.session_id,
                            "error": str(exc),
                        },
                        exc_info=True,
                    )
                    self._log_delegate_child_event(
                        parent_logger=parent_agent_logger,
                        parent_context=prepared["parent_context"],
                        event="delegate_child_error",
                        message=f"Delegated child session failed before callback: {agent_id}",
                        data={
                            "target_agent_id": agent_id,
                            "child_session_id": prepared["child_request"].session.session_id,
                            "child_trace_id": prepared["child_context"].trace_id,
                        },
                        level=LogLevel.ERROR,
                        error=str(exc),
                    )
                    try:
                        registry = get_connection_registry()
                        await registry.push(
                            prepared["parent"].session_id,
                            {
                                "type": "message",
                                "content": (
                                    f"委托给 {agent_id} 的子任务执行失败，未能自动回传结果。\n"
                                    f"错误：{exc}"
                                ),
                                "model": "",
                                "is_finished": True,
                            },
                        )
                    except Exception:
                        logger.warning(
                            "Failed to push delegate child failure back to parent session",
                            extra={"parent_session_id": prepared["parent"].session_id},
                        )

            # Fire-and-forget mode: delegate without waiting for result
            if not wait_for_result:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if can_use_runtime_child_flow:
                    prepared = await _prepare_runtime_child_flow()
                    loop.create_task(
                        _background_child_runner(prepared),
                        name=f"delegate-child:{agent_id}",
                    )
                else:
                    loop.create_task(
                        invoker.invoke(
                            content=task,
                            agent_id=canonical_agent_id,
                            session_id=session_id,
                            source=InvokeSource.AGENT,
                        )
                    )

                logger.info(
                    "DelegateTaskTool: fire-and-forget task delegated",
                    extra={
                        "target_agent_id": agent_id,
                        "session_id": session_id,
                        "task_length": len(task),
                    },
                )

                return ToolResult.ok(
                    f"Task has been delegated to agent '{agent_id}' asynchronously. "
                    f"The agent will process the task in the background and the result "
                    f"will be delivered to the user directly.",
                    agent_id=agent_id,
                    async_mode=True,
                )

            if can_use_runtime_child_flow:
                prepared = await _prepare_runtime_child_flow()
                loop = asyncio.get_running_loop()
                loop.create_task(
                    _background_child_runner(prepared),
                    name=f"delegate-child:{agent_id}",
                )
                return ToolResult.ok(
                    (
                        f"Task has been delegated to agent '{agent_id}' and is running asynchronously. "
                        "Do not continue researching yourself. The delegated agent will report back automatically."
                    ),
                    agent_id=agent_id,
                    session_id=prepared["child_request"].session.session_id,
                    child_trace_id=prepared["child_context"].trace_id,
                    async_wait=True,
                    delegate_terminal=True,
                    delegate_terminal_reason="async_wait",
                )

            # Synchronous mode: wait for result with timeout protection
            try:
                result = await asyncio.wait_for(
                    invoker.invoke(
                        content=task,
                        agent_id=canonical_agent_id,
                        session_id=session_id,
                        source=InvokeSource.AGENT,
                    ),
                    timeout=effective_timeout,
                )
            except TimeoutError:
                logger.warning(
                    "DelegateTaskTool timed out",
                    extra={
                        "agent_id": agent_id,
                        "timeout": effective_timeout,
                        "task_preview": task[:100] if len(task) > 100 else task,
                    },
                )
                child_abort_event = child_abort_ref.get("event")
                if child_abort_event is not None:
                    child_abort_event.set()
                self._log_delegate_child_event(
                    parent_logger=parent_agent_logger,
                    parent_context=current_context,
                    event="delegate_child_timeout",
                    message=f"Delegated child session timed out: {agent_id}",
                    data={
                        "target_agent_id": agent_id,
                        "child_trace_id": child_trace_ref.get("trace_id", ""),
                        "timeout": effective_timeout,
                    },
                    level=LogLevel.ERROR,
                    error=f"child timed out after {effective_timeout:.0f}s",
                )
                return ToolResult.error_result(
                    f"Delegated agent '{agent_id}' did not complete within {effective_timeout:.0f} seconds. "
                    "The delegated run was stopped before a final result was returned.",
                    agent_id=agent_id,
                    child_trace_id=child_trace_ref.get("trace_id", ""),
                    delegate_terminal=True,
                    delegate_terminal_reason="timeout",
                    timed_out=True,
                    timeout=effective_timeout,
                )

            # Handle error case
            if result.error:
                logger.error(
                    "DelegateTaskTool failed",
                    extra={
                        "target_agent_id": agent_id,
                        "error": result.error,
                    },
                )
                return ToolResult.error_result(
                    f"Failed to delegate task to '{agent_id}': {result.error}",
                    agent_id=agent_id,
                    session_id=result.session_id,
                    trace_id=result.trace_id,
                    delegate_terminal=True,
                    delegate_terminal_reason="error",
                )

            # Build success response
            logger.info(
                "DelegateTaskTool completed",
                extra={
                    "target_agent_id": agent_id,
                    "session_id": result.session_id,
                    "delivered": result.delivered,
                    "response_length": len(result.response) if result.response else 0,
                },
            )

            return ToolResult.ok(
                f"Agent '{agent_id}' completed the task.\n\nResponse:\n{result.response}",
                agent_id=agent_id,
                session_id=result.session_id,
                trace_id=result.trace_id,
                delivered=result.delivered,
                delegate_terminal=True,
                delegate_terminal_reason="success",
            )

        except ValueError as exc:
            # Agent not found in configuration
            logger.warning(
                "DelegateTaskTool: Agent not found",
                extra={"agent_id": agent_id, "error": str(exc)},
            )
            return ToolResult.error_result(
                f"Agent '{agent_id}' not found. Please check the agent_id is correct. "
                f"Error: {str(exc)}",
                agent_id=agent_id,
            )

        except Exception as exc:
            logger.error(
                "DelegateTaskTool execution failed",
                extra={
                    "agent_id": agent_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return ToolResult.error_result(
                f"Failed to delegate task to '{agent_id}': {str(exc)}",
                agent_id=agent_id,
            )

    def _resolve_delegate_budget_profile(self, runtime_services) -> str:
        """Use a fuller budget profile for explicit delegated work when available."""
        if "delegate-default" in runtime_services.turn_profiles:
            return "delegate-default"
        return runtime_services.default_turn_profile

    def _canonicalize_agent_id(self, agent_id: str) -> str:
        """将传入的 Agent ID 归一化为配置中的标准 ID。"""
        from src.config.manager import get_config

        return get_config().multi_agent.resolve_agent_id(agent_id) or agent_id

    async def _resolve_target_session(
        self,
        *,
        session_manager,
        agent_id: str,
    ):
        """Prefer the currently connected target-agent session over a stale active record."""
        from src.gateway.connection_registry import get_connection_registry

        registry = get_connection_registry()
        canonical_agent_id = self._canonicalize_agent_id(agent_id)
        for connected_session_id in registry.get_all_session_ids():
            connected_session = await session_manager.get_session(connected_session_id)
            if connected_session is None:
                continue
            if self._canonicalize_agent_id(connected_session.agent_id) != canonical_agent_id:
                continue
            if connected_session.status != "active":
                continue
            return connected_session
        return await session_manager.get_active_session_by_agent(canonical_agent_id)

    def _build_child_context(
        self,
        *,
        parent_context: AgentContext | None,
        child_session_id: str,
        agent_id: str,
    ) -> AgentContext:
        """Create an isolated child request context with a fresh trace and parent linkage."""
        if parent_context is None:
            return AgentContext.for_internal(
                session_id=child_session_id,
                source="agent",
                agent_id=agent_id,
                channel_type=ChannelType.WEB_CHAT,
            )

        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            session_id=child_session_id,
            agent_id=agent_id,
            channel_id=parent_context.channel_id,
            channel_type=parent_context.channel_type,
            channel_protocol=parent_context.channel_protocol,
            user_id=parent_context.user_id,
            agent_type=AgentType.SUB,
            parent_trace_id=parent_context.trace_id,
            metadata={
                "source": "delegate_child",
                "parent_session_id": parent_context.session_id,
                "parent_trace_id": parent_context.trace_id,
            },
        )
        return AgentContext(identity=identity, metadata={"source": "delegate_child"})

    def _build_parent_resume_context(
        self,
        *,
        parent_context: AgentContext | None,
        session_id: str,
        agent_id: str,
    ) -> AgentContext:
        """Build a fresh parent follow-up context for child-result ingestion."""
        if parent_context is None:
            return AgentContext.for_internal(
                session_id=session_id,
                source="agent",
                agent_id=agent_id,
                channel_type=ChannelType.WEB_CHAT,
            )

        return AgentContext.for_internal(
            session_id=session_id,
            source="agent",
            agent_id=agent_id,
            channel_type=parent_context.channel_type,
            user_id=parent_context.user_id,
            channel_id=parent_context.channel_id,
        )

    def _log_delegate_child_event(
        self,
        *,
        parent_logger,
        parent_context: AgentContext | None,
        event: str,
        message: str,
        data: dict[str, Any],
        level,
        error: str | None = None,
    ) -> None:
        """Emit explicit child-session lifecycle events into the parent trace."""
        if parent_context is None or not parent_context.trace_id:
            return
        parent_logger.create_log_entry(
            trace_id=parent_context.trace_id,
            event=event,
            message=message,
            level=level,
            category=LogCategory.AGENT_LOOP,
            data=data,
            error=error,
        )

    def _resolve_sync_wait_timeout(
        self,
        *,
        requested_timeout: float,
        current_context,
        runtime_services,
    ) -> float:
        """Clamp delegate wait time so the parent turn still has time to respond cleanly."""
        if requested_timeout <= 0:
            requested_timeout = 120.0

        max_timeout = requested_timeout
        try:
            parent_profile = runtime_services.turn_profiles.get(runtime_services.default_turn_profile)
            if parent_profile is not None:
                elapsed_ms = float(getattr(current_context, "elapsed_ms", 0.0) or 0.0)
                remaining_sec = max((float(parent_profile.max_wall_time_ms) - elapsed_ms) / 1000.0, 0.0)
                max_timeout = min(max_timeout, max(remaining_sec - 15.0, 5.0))
        except Exception:
            pass

        return max(min(max_timeout, requested_timeout), 5.0)

    def _infer_delegate_deliverable(self, task: str) -> str:
        """Infer the real delegated deliverable instead of forcing a generic summary."""
        task_lower = task.lower()
        if "html" in task_lower:
            return "Produce the requested HTML deliverable and save it to the appropriate workspace path"
        if "markdown" in task_lower or " md " in f" {task_lower} " or "md文件" in task:
            return "Produce the requested Markdown deliverable and save it to the appropriate workspace path"
        if "报告" in task or "调研" in task or "分析" in task:
            return "Complete the delegated research/analysis task and provide a structured written deliverable"
        return "Complete the delegated task and return the requested deliverable"

    def _classify_runtime_child_status(
        self,
        *,
        kind: str,
        finish_reason: str,
        unresolved: list[str],
        output_text: str,
    ) -> str:
        """Map a runtime child result into success/error/timeout without treating budget stops as success."""
        if finish_reason == "max_wall_time":
            return "timeout"
        if kind != "final":
            return "error"
        if finish_reason == "done_definition_satisfied" and output_text.strip():
            return "success"
        if not output_text.strip() and unresolved:
            return "error"
        return "error"

    def _child_summary_text(self, output_text: str, *, finish_reason: str, child_status: str) -> str:
        """Create a stable child-result summary for parent announcement queues."""
        if output_text.strip():
            return output_text
        if child_status == "timeout":
            return f"Child session timed out before completing the delegated task (finish_reason={finish_reason})."
        return f"Child session stopped before completing the delegated task (finish_reason={finish_reason})."

    def _truncate_delegate_output(self, output_text: str, *, limit: int = 1800) -> str:
        """Trim partial delegated output for error propagation back to the parent."""
        normalized = output_text.strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit] + "\n...[truncated]..."
