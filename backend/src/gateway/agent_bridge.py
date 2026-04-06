"""Agent Core 桥接器。

AgentBridge 是 Gateway 与 Agent Core 之间的唯一连接点。
封装 AgentCoreConfig 的创建、Agent 实例管理、技能调度和 agent_loop 的调用。

从 agent_core/api/websocket.py 中的以下逻辑迁移而来：
- create_agent_config(): 创建 AgentCoreConfig
- _get_llm_router() / _get_tool_manager(): 依赖获取
- _get_skill_adapter() / _get_skill_command_resolver(): 技能系统初始化
- _match_and_load_skill_prompt(): 技能匹配和 prompt 注入
- _handle_message(): 消息处理和事件流转换
- _persist_assistant_message(): assistant 消息持久化
- _load_session_history(): 会话历史加载

设计原则：
- 协议无关：不依赖 WebSocket/HTTP 等具体协议
- 输入 Envelope，输出 AsyncGenerator[GatewayEvent]
- 通过 AgentInfo 支持多 Agent 配置
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional

from .agent_info import AgentInfo
from .response import GatewayEvent, GatewayEventType
from .errors import DispatchError

from ..agent_core.agent import Agent
from ..agent_core.config import AgentCoreConfig
from ..agent_core.adapters.llm_adapter import XAgentLLMAdapter
from ..agent_core.adapters.tool_adapter import XAgentToolAdapter
from ..agent_core.adapters.system_prompt_adapter import create_system_prompt_adapter
# 新增 Adapter 导入
from ..agent_core.adapters.tool_middleware_adapter import create_tool_middleware_adapter
from ..runtime.session import DefaultSessionOrchestrator
from ..agent_core.types import (
    AgentEndEvent,
    AgentStartEvent,
    AssistantMessage,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionUpdateEvent,
    TextContent,
)
from ..agent_core.skill_dispatcher import (
    SkillCommandResolver,
    SkillPromptRewriter,
    SkillInvocation,
    build_skill_command_specs,
)
from ..runtime.turn import DefaultTurnController
from ..runtime.types import TurnRequest, TurnResult
from ..conversation.dao.models import Agent as AgentORM

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


_RUNTIME_FAST_SYSTEM_PROMPT = (
    "你正在执行 runtime debug fast mode。"
    "请使用中文，直接、简短回答用户当前请求。"
    "不要调用工具，不要展开额外计划，不要读取长期上下文。"
    "优先在一小段文本内给出结论。"
)
_RUNTIME_FAST_MAX_TOKENS = 64


# ============================================================================
# 全局缓存（与原 websocket.py 保持一致的单例模式）
# ============================================================================

_skill_adapter_cache = None
_skill_command_resolver_cache: Optional[SkillCommandResolver] = None
_skill_prompt_rewriter = SkillPromptRewriter()


# ============================================================================
# 依赖获取函数
# ============================================================================

def _get_llm_router():
    """获取 LLMRouter 实例。"""
    from ..main import get_llm_router
    return get_llm_router()


def _get_tool_manager():
    """获取 ToolManager 实例（带内置工具）。"""
    from ..tools.manager import get_tool_manager
    from ..tools.builtin import get_builtin_tools

    manager = get_tool_manager()

    if len(manager.get_all_tools()) == 0:
        for tool in get_builtin_tools():
            manager.register(tool)

    return manager


def _get_session_manager():
    """获取 SessionManager 实例。"""
    from ..conversation.session import SessionManager
    return SessionManager()


def _get_skill_adapter():
    """获取技能适配器实例（带缓存）。"""
    global _skill_adapter_cache

    if _skill_adapter_cache is not None:
        return _skill_adapter_cache

    try:
        from ..agent_core.adapters.skill_adapter import create_skill_adapter
        _skill_adapter_cache = create_skill_adapter()
        if _skill_adapter_cache:
            logger.info("Skill adapter initialized successfully")
        return _skill_adapter_cache
    except Exception as exc:
        logger.warning("Failed to initialize skill adapter", extra={"error": str(exc)})
        return None


def _get_skill_command_resolver() -> Optional[SkillCommandResolver]:
    """获取技能命令解析器实例（带缓存）。"""
    global _skill_command_resolver_cache

    if _skill_command_resolver_cache is not None:
        return _skill_command_resolver_cache

    skill_adapter = _get_skill_adapter()
    if not skill_adapter:
        return None

    try:
        manifests = skill_adapter._registry.list_skills()
        if not manifests:
            return None

        command_specs = build_skill_command_specs(manifests)
        _skill_command_resolver_cache = SkillCommandResolver(command_specs)

        logger.info(
            "Skill command resolver initialized",
            extra={"command_count": len(command_specs)},
        )
        return _skill_command_resolver_cache
    except Exception as exc:
        logger.warning(
            "Failed to initialize skill command resolver",
            extra={"error": str(exc)},
        )
        return None


def _get_agent_logger():
    """获取共享的 AgentLogger 实例。"""
    from ..agent_core.api.dev_routes import get_logger as get_agent_logger_fn
    return get_agent_logger_fn()


# ============================================================================
# 技能匹配
# ============================================================================

def _match_and_load_skill_prompt(user_input: str) -> tuple[str, Optional[SkillInvocation]]:
    """根据用户输入匹配技能并生成技能指令。

    三种模式：
    1. 显式命令 (/skill_name args): 使用命令解析器，Prompt Rewrite 调度
    2. 显式命令 (Tool Dispatch): 直接返回调用信息
    3. 意图匹配: 注入 XML 技能列表，让 LLM 自己选择

    Args:
        user_input: 用户输入内容。

    Returns:
        (技能指令 prompt, 技能调用信息 或 None)
    """
    skill_adapter = _get_skill_adapter()
    if not skill_adapter:
        return "", None

    try:
        # 模式 1: 显式命令解析 (/skill_name args)
        if user_input.startswith("/"):
            resolver = _get_skill_command_resolver()
            if resolver:
                invocation = resolver.resolve(user_input)
                if invocation:
                    logger.info(
                        "Skill command resolved",
                        extra={
                            "skill_name": invocation.skill_name,
                            "command_name": invocation.command_name,
                            "dispatch_mode": invocation.dispatch_mode,
                        },
                    )

                    content = skill_adapter.load_skill_content(invocation.skill_name)
                    if content:
                        rewritten = _skill_prompt_rewriter.rewrite(invocation)
                        skill_prompt = (
                            f"\n# 技能指令 (/{invocation.skill_name})\n\n"
                            f"⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。\n\n"
                            f"{content}\n\n---\n\n{rewritten}\n"
                        )
                        return skill_prompt, invocation

            # 回退: 直接用 skill_id 匹配
            command = user_input.split()[0][1:]
            content = skill_adapter.load_skill_content(command)
            if content:
                logger.info("Skill matched by direct command", extra={"skill_id": command})
                return (
                    f"\n\n# 技能指令 (/{command})\n\n"
                    f"⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。\n\n"
                    f"{content}"
                ), None

        # 模式 3: 意图匹配
        skills_prompt = skill_adapter.build_skills_xml_prompt()
        if skills_prompt:
            logger.debug(
                "Skills XML prompt generated",
                extra={
                    "user_input": user_input[:50],
                    "prompt_length": len(skills_prompt),
                },
            )
            return f"\n\n{skills_prompt}", None

        return "", None

    except Exception as exc:
        logger.warning("Failed to generate skill prompt", extra={"error": str(exc)})
        return "", None


# ============================================================================
# AgentBridge
# ============================================================================

class AgentBridge:
    """Agent Core 桥接器。

    封装 AgentCoreConfig 的创建和 agent_loop 的调用，
    是 Gateway 与 Agent Core 之间的唯一连接点。

    职责：
    1. 创建 AgentCoreConfig（注入 LLM、Tool、Context、SystemPrompt 适配器）
    2. 管理 Agent 实例（创建、加载历史）
    3. 技能匹配和 prompt 注入
    4. 执行 agent_loop 并将 AgentEvent 转换为 GatewayEvent
    5. 持久化用户消息和 assistant 消息
    """

    def __init__(self) -> None:
        self.runtime_session_orchestrator = DefaultSessionOrchestrator()
        self.runtime_turn_controller = DefaultTurnController()

    def create_config(
        self,
        agent_info: AgentInfo | None = None,
        *,
        disable_tools: bool = False,
    ) -> AgentCoreConfig:
        """创建 Agent 配置。

        注入 LLM、Tool、SystemPrompt、Context 适配器。
        如果提供了 agent_info，会将 Agent 的 persona 注入到 system_prompt 中。

        Args:
            agent_info: Agent 信息值对象，用于注入 persona。

        Returns:
            配置好的 AgentCoreConfig 实例。
        """
        llm_router = _get_llm_router()

        llm_adapter = XAgentLLMAdapter(llm_router)
        tool_adapter = None if disable_tools else XAgentToolAdapter(_get_tool_manager())
        agent_logger = _get_agent_logger()

        # 解析 agent 对应的 workspace 路径，多 Agent 场景下各 agent 有独立 workspace
        workspace_path = self._resolve_agent_workspace(agent_info)

        system_prompt_adapter = create_system_prompt_adapter(workspace_path=workspace_path)
        system_prompt = system_prompt_adapter.build_system_prompt()

        context_adapter = self._create_context_adapter(llm_router, agent_info, workspace_path=workspace_path)

        # 创建工具中间件管道（可选，默认启用计时和日志中间件）
        tool_middleware_adapter = None if disable_tools else self._create_tool_middleware_adapter()

        return AgentCoreConfig(
            llm=llm_adapter,
            tools=tool_adapter,
            logger=agent_logger,
            context=context_adapter,
            system_prompt=system_prompt,
            system_prompt_port=system_prompt_adapter,
            tool_middleware_pipeline=tool_middleware_adapter.pipeline if tool_middleware_adapter else None,
        )

    def create_agent(
        self,
        config: AgentCoreConfig | None = None,
        agent_info: AgentInfo | None = None,
    ) -> Agent:
        """创建 Agent 实例。

        Args:
            config: AgentCoreConfig，为 None 时自动创建。
            agent_info: Agent 信息，用于注入 persona。

        Returns:
            配置好的 Agent 实例。
        """
        if config is None:
            config = self.create_config(agent_info)
        return Agent(config)

    async def load_session_history(self, agent: Agent, session_id: str) -> None:
        """从数据库加载会话历史消息到 Agent 内存。

        WebSocket 每次连接或 CLI 每次启动会创建新的 Agent 实例，
        内存中没有历史消息。通过 MemoryManager 从数据库恢复历史，
        确保 LLM 调用时能看到完整的对话上下文。

        Args:
            agent: Agent 实例。
            session_id: 会话 ID。
        """
        try:
            from ..memory.manager import get_memory_manager
            memory_manager = get_memory_manager()
            agent_messages = await memory_manager.get_session_history_as_agent_messages(
                session_id, limit=200,
            )

            if not agent_messages:
                return

            for msg in agent_messages:
                agent.add_message(msg)

            logger.info(
                "Session history loaded into Agent via MemoryManager",
                extra={
                    "session_id": session_id,
                    "loaded_message_count": len(agent_messages),
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to load session history, starting with empty context",
                extra={
                    "session_id": session_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

    async def run(
        self,
        agent: Agent,
        content: str,
        session_id: str,
        *,
        agent_info: AgentInfo | None = None,
        images: list[tuple[str, str]] | None = None,
        abort_event: asyncio.Event | None = None,
        persist_user_message: bool = True,
        disable_skills: bool = False,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """执行 Agent Loop 并产出 GatewayEvent。

        完整流程：
        1. 持久化用户消息（仅用户主动发起时）
        2. 匹配技能并注入 prompt
        3. 调用 agent.prompt() 获取事件流
        4. 将 AgentEvent 转换为 GatewayEvent
        5. 持久化 assistant 消息

        Args:
            agent: Agent 实例。
            content: 用户消息文本。
            session_id: 会话 ID。
            agent_info: Agent 信息（用于 GatewayEvent 的 agent_id/agent_name）。
            images: 附带的图片列表。
            abort_event: 中止事件。
            persist_user_message: 是否持久化用户消息。AgentInvoker 等内部
                触发场景应设为 False，因为 prompt 不是用户主动发送的。
            disable_skills: 是否跳过技能匹配与 prompt 注入。

        Yields:
            GatewayEvent 事件流。
        """
        event_agent_id = agent_info.agent_id if agent_info else None
        event_agent_name = agent_info.agent_name if agent_info else None
        user_msg_id: str | None = None
        assistant_content: list[str] = []
        abort_forwarder: asyncio.Task[None] | None = None

        async def forward_abort() -> None:
            await abort_event.wait()
            while getattr(agent, "_abort_event", None) is None:
                await asyncio.sleep(0)
            agent.abort()

        try:
            # 1. 持久化用户消息（仅用户主动发起时）
            if persist_user_message:
                user_msg_id = await self._persist_user_message(session_id, content)

            # 2. 技能匹配和 prompt 注入
            if not disable_skills:
                self._inject_skill_prompt(agent, content)

            # 3. 调用 agent.prompt() 并转换事件
            if abort_event is not None:
                abort_forwarder = asyncio.create_task(forward_abort())
            async for event in agent.prompt(content, images):
                gateway_event = self._convert_agent_event(
                    event,
                    agent_id=event_agent_id,
                    agent_name=event_agent_name,
                )

                # 收集 assistant 响应内容
                if isinstance(event, MessageUpdateEvent) and event.delta_type == "text":
                    assistant_content.append(event.delta)

                # 持久化 assistant 消息
                if isinstance(event, AgentEndEvent):
                    await self._persist_assistant_messages(
                        session_id, event, user_msg_id,
                    )

                if gateway_event is not None:
                    yield gateway_event

            # 4. 恢复原始 system prompt
            self._restore_system_prompt(agent)

        except Exception as exc:
            logger.exception(
                "Error in AgentBridge.run",
                extra={"session_id": session_id, "error": str(exc)},
            )

            # 即使出错也尝试保存部分响应
            if assistant_content:
                await self._persist_partial_response(
                    session_id, assistant_content, str(exc),
                )

            yield GatewayEvent.error(
                message=str(exc),
                error_type=type(exc).__name__,
                agent_id=event_agent_id,
                agent_name=event_agent_name,
            )
        finally:
            if abort_forwarder is not None:
                abort_forwarder.cancel()
            self._restore_system_prompt(agent)

    async def run_runtime_turn(
        self,
        request: TurnRequest,
        *,
        controller=None,
    ) -> TurnResult:
        """Execute a prepared runtime turn through the bounded runtime controller."""
        runtime_controller = controller
        if runtime_controller is None:
            return await self._run_runtime_turn_via_legacy_bridge(request)
        return await runtime_controller.run(request)

    async def _run_runtime_turn_via_legacy_bridge(self, request: TurnRequest) -> TurnResult:
        """Fallback runtime execution path that reuses the legacy AgentBridge event stream."""
        started_at = time.monotonic()
        response_parts: list[str] = []
        final_content: str | None = None
        error_payload: dict[str, object] | None = None
        persist_user_message = bool(request.metadata.get("persist_user_message", True))
        disable_skills = bool(request.metadata.get("runtime_disable_skills", False))
        timeout_ms = self._normalize_runtime_timeout_ms(request.metadata.get("runtime_timeout_ms"))
        diagnostics: dict[str, Any] = {
            "path": "legacy_bridge",
            "phase": "resolve_agent",
            "timeout_ms": timeout_ms,
            "agent_id": None,
            "fast_mode": bool(request.metadata.get("runtime_disable_tools"))
            or bool(request.metadata.get("runtime_disable_skills")),
            "events_seen": 0,
            "text_chunks": 0,
            "text_chars": 0,
            "event_counts": {},
            "last_event_type": None,
            "last_progress": "resolving_agent",
            "milestones_ms": {"started": 0},
        }

        def elapsed_ms() -> int:
            return int((time.monotonic() - started_at) * 1000)

        def mark_milestone(name: str, *, phase: str | None = None, progress: str | None = None) -> None:
            diagnostics["milestones_ms"][name] = elapsed_ms()
            if phase is not None:
                diagnostics["phase"] = phase
            if progress is not None:
                diagnostics["last_progress"] = progress

        async def consume_events() -> None:
            nonlocal final_content, error_payload

            mark_milestone(
                "event_stream_started",
                phase="stream_events",
                progress="waiting_for_gateway_events",
            )

            async for event in self.run(
                agent=agent,
                content=request.user_input,
                session_id=request.session.session_id,
                agent_info=agent_info,
                persist_user_message=persist_user_message,
                disable_skills=disable_skills,
            ):
                event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
                diagnostics["events_seen"] += 1
                diagnostics["event_counts"][event_type] = diagnostics["event_counts"].get(event_type, 0) + 1
                diagnostics["last_event_type"] = event_type

                if diagnostics["events_seen"] == 1:
                    mark_milestone("first_event", progress="received_first_gateway_event")
                    logger.info(
                        "Runtime turn via legacy bridge received first event",
                        extra={
                            "session_id": request.session.session_id,
                            "agent_id": agent_info.agent_id,
                            "event_type": event_type,
                            "elapsed_ms": diagnostics["milestones_ms"]["first_event"],
                        },
                    )

                if event.type == GatewayEventType.TEXT_CHUNK:
                    chunk = event.data.get("content", "")
                    if chunk:
                        response_parts.append(chunk)
                        diagnostics["text_chunks"] += 1
                        diagnostics["text_chars"] += len(chunk)
                        if diagnostics["text_chunks"] == 1:
                            mark_milestone("first_text_chunk", progress="streaming_text")
                elif event.type == GatewayEventType.MESSAGE_END:
                    content = event.data.get("content", "")
                    if content:
                        final_content = content
                    mark_milestone(
                        "message_end",
                        phase="message_end",
                        progress="received_message_end",
                    )
                elif event.type == GatewayEventType.ERROR:
                    error_payload = dict(event.data)
                    mark_milestone(
                        "error_event",
                        phase="error",
                        progress="received_error_event",
                    )

        try:
            agent_info = self._resolve_runtime_agent_info(request)
            diagnostics["agent_id"] = agent_info.agent_id
            mark_milestone("agent_resolved", phase="create_agent", progress="agent_resolved")

            runtime_config = self._build_runtime_agent_config(request, agent_info)
            agent = self.create_agent(config=runtime_config, agent_info=agent_info)
            mark_milestone("agent_created", phase="load_history", progress="agent_created")

            logger.info(
                "Runtime turn via legacy bridge started",
                extra={
                    "session_id": request.session.session_id,
                    "agent_id": agent_info.agent_id,
                    "timeout_ms": timeout_ms,
                },
            )

            if bool(request.metadata.get("runtime_skip_history_load")):
                mark_milestone(
                    "history_skipped",
                    phase="stream_events",
                    progress="session_history_skipped",
                )
            else:
                await self.load_session_history(agent, request.session.session_id)
                mark_milestone("history_loaded", phase="stream_events", progress="session_history_loaded")

            if timeout_ms is not None:
                await asyncio.wait_for(consume_events(), timeout=float(timeout_ms) / 1000.0)
            else:
                await consume_events()
        except asyncio.TimeoutError:
            mark_milestone("timed_out", phase="timeout", progress="timed_out")
            logger.warning(
                "Runtime turn via legacy bridge timed out",
                extra={
                    "session_id": request.session.session_id,
                    "agent_id": diagnostics.get("agent_id"),
                    "timeout_ms": timeout_ms,
                    "phase": diagnostics["phase"],
                    "last_event_type": diagnostics["last_event_type"],
                    "events_seen": diagnostics["events_seen"],
                },
            )
            return TurnResult(
                kind="abort",
                finish_reason="max_wall_time",
                output_text=self._resolve_runtime_output_text(
                    final_content,
                    response_parts,
                    diagnostics=diagnostics,
                    finish_reason="max_wall_time",
                    user_input=request.user_input,
                ),
                updated_task_frame=request.task_frame,
                metadata={
                    "legacy_bridge": True,
                    "agent_id": diagnostics.get("agent_id"),
                    "timeout_ms": timeout_ms,
                    "runtime_diagnostics": diagnostics,
                },
            )
        except Exception as exc:
            mark_milestone("failed", phase="error", progress="runtime_bridge_failed")
            logger.exception(
                "Runtime turn via legacy bridge failed",
                extra={
                    "session_id": request.session.session_id,
                    "agent_id": diagnostics.get("agent_id"),
                    "phase": diagnostics["phase"],
                    "events_seen": diagnostics["events_seen"],
                    "error": str(exc),
                },
            )
            return TurnResult(
                kind="abort",
                finish_reason="controller_abort",
                output_text=self._resolve_runtime_output_text(
                    final_content,
                    response_parts,
                    diagnostics=diagnostics,
                    finish_reason="controller_abort",
                    error_payload={
                        "message": str(exc),
                        "error_type": type(exc).__name__,
                    },
                    user_input=request.user_input,
                ),
                updated_task_frame=request.task_frame,
                metadata={
                    "legacy_bridge": True,
                    "agent_id": diagnostics.get("agent_id"),
                    "error": {
                        "message": str(exc),
                        "error_type": type(exc).__name__,
                    },
                    "runtime_diagnostics": diagnostics,
                },
            )

        if error_payload is not None:
            mark_milestone("completed", phase="error", progress="completed_with_error_event")
            logger.warning(
                "Runtime turn via legacy bridge completed with error event",
                extra={
                    "session_id": request.session.session_id,
                    "agent_id": diagnostics.get("agent_id"),
                    "events_seen": diagnostics["events_seen"],
                    "last_event_type": diagnostics["last_event_type"],
                },
            )
            return TurnResult(
                kind="abort",
                finish_reason="controller_abort",
                output_text=self._resolve_runtime_output_text(
                    final_content,
                    response_parts,
                    diagnostics=diagnostics,
                    finish_reason="controller_abort",
                    error_payload=error_payload,
                    user_input=request.user_input,
                ),
                updated_task_frame=request.task_frame,
                metadata={
                    "legacy_bridge": True,
                    "agent_id": diagnostics.get("agent_id"),
                    "error": error_payload,
                    "runtime_diagnostics": diagnostics,
                },
            )

        mark_milestone("completed", phase="completed", progress="completed_successfully")
        logger.info(
            "Runtime turn via legacy bridge completed",
            extra={
                "session_id": request.session.session_id,
                "agent_id": diagnostics.get("agent_id"),
                "events_seen": diagnostics["events_seen"],
                "text_chunks": diagnostics["text_chunks"],
                "elapsed_ms": diagnostics["milestones_ms"]["completed"],
            },
        )
        return TurnResult(
            kind="final",
            finish_reason="done_definition_satisfied",
            output_text=final_content or "".join(response_parts) or None,
            updated_task_frame=request.task_frame,
            metadata={
                "legacy_bridge": True,
                "agent_id": diagnostics.get("agent_id"),
                "runtime_diagnostics": diagnostics,
            },
        )

    def _resolve_runtime_agent_info(self, request: TurnRequest) -> AgentInfo:
        """Resolve AgentInfo for runtime execution using request metadata when available."""
        agent_id = request.metadata.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            agent = AgentORM.from_config(agent_id)
            if agent is not None:
                return AgentInfo.from_orm(agent)
        return AgentInfo.default()

    def _normalize_runtime_timeout_ms(self, value: object) -> int | None:
        """Normalize per-request wall-time timeout metadata for runtime debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        return None

    def _normalize_runtime_max_tokens(self, value: object) -> int | None:
        """Normalize optional runtime max_tokens override for debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        return None

    def _normalize_runtime_temperature(self, value: object) -> float | None:
        """Normalize optional runtime temperature override for debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and 0.0 <= float(value) <= 2.0:
            return float(value)
        return None

    def _build_runtime_agent_config(
        self,
        request: TurnRequest,
        agent_info: AgentInfo,
    ) -> AgentCoreConfig | None:
        """Build an optional runtime-specific agent config for debug execution."""
        disable_tools = bool(request.metadata.get("runtime_disable_tools"))
        disable_skills = bool(request.metadata.get("runtime_disable_skills"))
        if not disable_tools and not disable_skills:
            return None

        if disable_tools:
            llm_router = _get_llm_router()
            force_non_streaming = bool(request.metadata.get("runtime_force_non_streaming"))
            runtime_max_tokens = self._normalize_runtime_max_tokens(
                request.metadata.get("runtime_max_tokens")
            )
            runtime_temperature = self._normalize_runtime_temperature(
                request.metadata.get("runtime_temperature")
            )
            return AgentCoreConfig(
                llm=XAgentLLMAdapter(llm_router, force_non_streaming=force_non_streaming),
                tools=None,
                logger=_get_agent_logger(),
                context=None,
                system_prompt=_RUNTIME_FAST_SYSTEM_PROMPT,
                system_prompt_port=None,
                enable_context_compression=False,
                enable_experience_learning=False,
                temperature=runtime_temperature if runtime_temperature is not None else 0.0,
                thinking_level="off",
                max_tokens=runtime_max_tokens or _RUNTIME_FAST_MAX_TOKENS,
                tool_middleware_pipeline=None,
            )

        return self.create_config(agent_info, disable_tools=False)

    def _resolve_runtime_output_text(
        self,
        final_content: str | None,
        response_parts: list[str],
        *,
        diagnostics: dict[str, Any],
        finish_reason: str,
        error_payload: dict[str, object] | None = None,
        user_input: str = "",
    ) -> str | None:
        """Return streamed output when available, otherwise synthesize a compact debug summary."""
        streamed = final_content or "".join(response_parts) or None
        if streamed:
            return streamed

        phase = diagnostics.get("phase") or "unknown"
        last_event = diagnostics.get("last_event_type") or "none"
        events_seen = diagnostics.get("events_seen", 0)
        timeout_ms = diagnostics.get("timeout_ms")
        fast_mode = bool(diagnostics.get("fast_mode"))

        if finish_reason == "max_wall_time":
            timeout_suffix = f" after {timeout_ms}ms" if timeout_ms else ""
            if fast_mode and not streamed:
                request_preview = " ".join(user_input.split())[:48] or "(empty)"
                if last_event == "agent_start":
                    return (
                        f"[runtime fast mode timeout{timeout_suffix}] "
                        f"request=\"{request_preview}\". "
                        "provider emitted no content chunk before timeout. "
                        "Try /api/v1/dev/llm-stream-probe or increase runtime_timeout_ms. "
                        f"phase={phase}, last_event={last_event}, events_seen={events_seen}"
                    )
                return (
                    f"[runtime fast mode timeout{timeout_suffix}] "
                    f"request=\"{request_preview}\". bridge ok, waiting for provider content. "
                    f"phase={phase}, last_event={last_event}, events_seen={events_seen}"
                )
            return (
                f"[runtime-turn timeout{timeout_suffix}] "
                f"phase={phase}, last_event={last_event}, events_seen={events_seen}"
            )

        if error_payload:
            error_type = error_payload.get("error_type") or "RuntimeError"
            message = error_payload.get("message") or "runtime turn aborted"
            return (
                f"[runtime-turn abort] phase={phase}, last_event={last_event}, "
                f"error={error_type}: {message}"
            )

        return f"[runtime-turn abort] phase={phase}, last_event={last_event}, events_seen={events_seen}"

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _resolve_agent_workspace(self, agent_info: AgentInfo | None) -> str | None:
        """解析 Agent 对应的 workspace 路径。

        多 Agent 场景下，每个 agent 有独立的 workspace 目录。

        解析优先级：
        1. MultiAgentContextLoader 中已初始化的 agent workspace（最可靠）
        2. AgentInfo.workspace 字段（从配置加载，作为 fallback）
        3. 返回 None，由调用方 fallback 到全局默认 workspace

        Args:
            agent_info: Agent 信息，包含 agent_id 和 workspace。

        Returns:
            agent 对应的 workspace 路径字符串，无法解析时返回 None。
        """
        if agent_info is None:
            logger.info("[workspace-debug] _resolve_agent_workspace: agent_info is None, skip")
            return None

        logger.info(
            "[workspace-debug] _resolve_agent_workspace: start",
            extra={
                "agent_id": agent_info.agent_id,
                "agent_info_workspace": agent_info.workspace,
            },
        )

        # 优先级 1: 从 MultiAgentContextLoader 获取（已初始化、路径已解析）
        try:
            from ..config.manager import get_config
            config = get_config()

            has_multi_agent = hasattr(config, 'multi_agent') and config.multi_agent and config.multi_agent.agents
            if has_multi_agent:
                from ..conversation.multi_agent_context_loader import get_multi_agent_context_loader
                multi_agent_context_loader = get_multi_agent_context_loader()

                if multi_agent_context_loader is not None:
                    agent_context = multi_agent_context_loader.get_agent_context(agent_info.agent_id)

                    if agent_context is not None:
                        workspace_path = str(agent_context.workspace_path)
                        logger.info(
                            "[workspace-debug] Resolved from MultiAgentContextLoader",
                            extra={
                                "agent_id": agent_info.agent_id,
                                "workspace_path": workspace_path,
                            },
                        )
                        return workspace_path

                    logger.info(
                        "[workspace-debug] Agent not found in MultiAgentContextLoader",
                        extra={
                            "agent_id": agent_info.agent_id,
                            "available_agent_ids": str(list(multi_agent_context_loader.agent_contexts.keys())),
                        },
                    )

        except Exception as exc:
            logger.warning(
                "[workspace-debug] MultiAgentContextLoader lookup failed",
                extra={"agent_id": agent_info.agent_id, "error": str(exc)},
            )

        # 优先级 2: 使用 AgentInfo 自身携带的 workspace 字段（从配置加载）
        if agent_info.workspace:
            from pathlib import Path
            workspace_path = str(Path(agent_info.workspace).expanduser())
            logger.info(
                "[workspace-debug] Fallback to AgentInfo.workspace",
                extra={
                    "agent_id": agent_info.agent_id,
                    "workspace_path": workspace_path,
                },
            )
            return workspace_path

        logger.info(
            "[workspace-debug] No workspace resolved, will use global default",
            extra={"agent_id": agent_info.agent_id},
        )
        return None

    def _create_context_adapter(
        self,
        llm_router,
        agent_info: AgentInfo | None = None,
        workspace_path: str | None = None,
    ):
        """创建 ContextPort adapter（上下文压缩）。

        Args:
            llm_router: LLMRouter 实例。
            agent_info: Agent 信息（已废弃，workspace 解析由调用方完成）。
            workspace_path: 已解析好的 workspace 路径。为 None 时 fallback 到全局默认。

        Returns:
            XAgentContextAdapter 实例，或 None（创建失败时）。
        """
        try:
            from ..agent_core.adapters.context_adapter import create_context_adapter
            from ..config.manager import get_config

            config = get_config()

            # 优先使用外部传入的 workspace_path（由 create_config 统一解析）
            resolved_workspace = workspace_path or config.workspace.path

            return create_context_adapter(
                llm_router=llm_router,
                compression_config=config.compression,
                workspace_path=resolved_workspace,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create context adapter, compression disabled",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            return None

    def _create_tool_middleware_adapter(self):
        """创建工具中间件适配器（可选）。

        默认启用计时和日志中间件。
        可通过配置添加高危工具审批中间件。

        Returns:
            ToolMiddlewareAdapter 实例，或 None。
        """
        try:
            from ..config.manager import get_config

            config = get_config()

            # 检查是否有配置高危工具列表
            high_risk_tools = None
            if hasattr(config, 'tools') and hasattr(config.tools, 'high_risk_tools'):
                high_risk_tools = config.tools.high_risk_tools

            return create_tool_middleware_adapter(
                enable_timing=True,
                enable_logging=True,
                high_risk_tools=high_risk_tools,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create tool middleware adapter",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            return None

    async def _persist_user_message(self, session_id: str, content: str) -> str | None:
        """持久化用户消息（在发送到 LLM 之前）。

        Args:
            session_id: 会话 ID。
            content: 用户消息文本。

        Returns:
            用户消息 ID，失败时返回 None。
        """
        try:
            session_manager = _get_session_manager()
            user_msg = await session_manager.add_message(
                session_id=session_id,
                role="user",
                content=content,
            )
            logger.info(
                "User message persisted before LLM call",
                extra={
                    "session_id": session_id,
                    "message_id": user_msg.id,
                    "content_length": len(content),
                },
            )
            return user_msg.id
        except Exception as exc:
            logger.exception(
                "Failed to persist user message before LLM call",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return None

    def _inject_skill_prompt(self, agent: Agent, content: str) -> None:
        """匹配技能并注入 prompt 到 Agent 的 system_prompt。

        使用原始 prompt（含 SKILLS_INJECTION_MARKER）作为基准，
        避免多轮对话中重复追加 skills 段落。

        Args:
            agent: Agent 实例。
            content: 用户消息文本。
        """
        skill_prompt, _invocation = _match_and_load_skill_prompt(content)

        from ..conversation.system_prompt_builder import SKILLS_INJECTION_MARKER
        base_prompt = agent._original_system_prompt

        if skill_prompt:
            if SKILLS_INJECTION_MARKER in base_prompt:
                agent._system_prompt = base_prompt.replace(
                    SKILLS_INJECTION_MARKER, skill_prompt.strip(),
                )
            else:
                agent._system_prompt = base_prompt + skill_prompt
            logger.debug(
                "Skill prompt injected",
                extra={"skill_prompt_length": len(skill_prompt)},
            )
        elif SKILLS_INJECTION_MARKER in base_prompt:
            agent._system_prompt = base_prompt.replace(SKILLS_INJECTION_MARKER, "")

    def _restore_system_prompt(self, agent: Agent) -> None:
        """恢复 Agent 的原始 system prompt。

        Args:
            agent: Agent 实例。
        """
        agent._system_prompt = agent._original_system_prompt

    def _convert_agent_event(
        self,
        event,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent | None:
        """将 AgentEvent 转换为 GatewayEvent。

        Args:
            event: agent_core 的事件对象。
            agent_id: 来源 Agent ID。
            agent_name: 来源 Agent 名称。

        Returns:
            GatewayEvent 或 None（内部事件不转换）。
        """
        if isinstance(event, AgentStartEvent):
            return GatewayEvent.agent_start(
                trace_id=event.trace_id,
                agent_id=agent_id,
                agent_name=agent_name,
            )

        if isinstance(event, MessageUpdateEvent):
            if not event.delta:
                return None
            if event.delta_type == "text":
                return GatewayEvent.text_chunk(
                    content=event.delta,
                    agent_id=agent_id,
                    agent_name=agent_name,
                )
            if event.delta_type == "thinking":
                return GatewayEvent.thinking_chunk(
                    content=event.delta,
                    agent_id=agent_id,
                    agent_name=agent_name,
                )
            return None

        if isinstance(event, MessageEndEvent):
            if not event.message or not isinstance(event.message, AssistantMessage):
                return None
            msg = event.message
            if msg.stop_reason == "tool_use":
                return None
            text_parts = [c.text for c in msg.content if isinstance(c, TextContent)]
            return GatewayEvent.message_end(
                content="".join(text_parts),
                model=msg.model,
                usage=msg.usage,
                stop_reason=msg.stop_reason,
                agent_id=agent_id,
                agent_name=agent_name,
            )

        if isinstance(event, ToolExecutionStartEvent):
            return GatewayEvent.tool_call(
                tool_call_id=event.tool_call_id,
                name=event.tool_name,
                arguments=event.arguments,
                agent_id=agent_id,
                agent_name=agent_name,
            )

        if isinstance(event, ToolExecutionEndEvent):
            result_content = ""
            if event.result:
                text_parts = [
                    c.text for c in event.result.content if isinstance(c, TextContent)
                ]
                result_content = "".join(text_parts)
            return GatewayEvent.tool_result(
                tool_call_id=event.tool_call_id,
                name=event.tool_name,
                result=result_content,
                is_error=event.is_error,
                agent_id=agent_id,
                agent_name=agent_name,
            )

        if isinstance(event, AgentEndEvent):
            return GatewayEvent.agent_end(
                trace_id=event.trace_id,
                total_duration_ms=event.total_duration_ms,
                message_count=len(event.messages),
                agent_id=agent_id,
                agent_name=agent_name,
            )

        # 其他内部事件（TurnStart/TurnEnd/MessageStart/ToolUpdate）不转换
        return None

    async def _persist_assistant_messages(
        self,
        session_id: str,
        event: AgentEndEvent,
        user_msg_id: str | None = None,
    ) -> None:
        """持久化 assistant 消息到会话。

        Args:
            session_id: 会话 ID。
            event: AgentEndEvent 包含新消息。
            user_msg_id: 关联的用户消息 ID。
        """
        try:
            session_manager = _get_session_manager()

            for msg in event.messages:
                if isinstance(msg, AssistantMessage):
                    await session_manager.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=msg.get_text(),
                        metadata={
                            "model": msg.model,
                            "provider": msg.provider,
                            "stop_reason": msg.stop_reason,
                            "usage": msg.usage,
                            "user_msg_id": user_msg_id,
                        },
                    )

            logger.info(
                "Assistant message persisted",
                extra={"session_id": session_id, "user_msg_id": user_msg_id},
            )
        except Exception as exc:
            logger.exception(
                "Failed to persist assistant message",
                extra={"session_id": session_id, "error": str(exc)},
            )

    async def _persist_partial_response(
        self,
        session_id: str,
        assistant_content: list[str],
        error_message: str,
    ) -> None:
        """即使出错也尝试保存部分响应。

        Args:
            session_id: 会话 ID。
            assistant_content: 已收集的 assistant 响应片段。
            error_message: 错误描述。
        """
        try:
            session_manager = _get_session_manager()
            await session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content="".join(assistant_content),
                metadata={
                    "status": "error_interrupted",
                    "error": error_message,
                },
            )
            logger.info(
                "Partial assistant message saved after error",
                extra={"session_id": session_id},
            )
        except Exception:
            pass
