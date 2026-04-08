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
import re
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional
from uuid import uuid4

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
from ..agent_core.types import (
    AgentEndEvent,
    AgentStartEvent,
    AssistantMessage,
    LLMCallLog,
    LogCategory,
    LogLevel,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolCallLog,
    ToolCallContent,
    ToolExecutionStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionUpdateEvent,
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from ..agent_core.skill_dispatcher import (
    SkillCommandResolver,
    SkillPromptRewriter,
    SkillInvocation,
    build_skill_command_specs,
)
from ..runtime.turn import DefaultToolGovernor, DefaultTurnController
from ..runtime.service import get_runtime_services
from ..runtime.repositories import StateSnapshotRecord, SummaryRecord, TranscriptEntry
from ..runtime.types import ToolCallSpec, ToolExecutionPlan, ToolExecutionResult, TurnRequest, TurnResult
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
        self._runtime_services = get_runtime_services()
        self.runtime_session_orchestrator = self._runtime_services.orchestrator
        from ..runtime.context import DefaultCompressionPipeline, DefaultContextBuilder

        self._runtime_context_builder = DefaultContextBuilder()
        self._runtime_compression_pipeline = DefaultCompressionPipeline()
        self.runtime_turn_controller = self._create_runtime_turn_controller()

    def create_config(
        self,
        agent_info: AgentInfo | None = None,
        *,
        disable_tools: bool = False,
        use_legacy_context: bool = True,
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
        model_name = getattr(getattr(llm_router, "_primary", None), "model_id", "")
        provider_name = getattr(getattr(llm_router, "_primary", None), "name", "")
        turn_profile = self._runtime_services.turn_profiles[self._runtime_services.default_turn_profile]
        tool_policies = {
            name: policy
            for name, policy in self._runtime_services.tool_policies.items()
            if name != "__default__"
        }
        if not tool_policies:
            from ..runtime.types import ToolPolicy

            tool_policies = {
                "web_search": ToolPolicy(max_uses_per_turn=3, repeat_signature_limit=1),
                "fetch_web_content": ToolPolicy(max_uses_per_turn=2, repeat_signature_limit=1),
                "run_in_terminal": ToolPolicy(max_uses_per_turn=4, repeat_signature_limit=2),
                "read_file": ToolPolicy(max_uses_per_turn=8, repeat_signature_limit=2),
            }

        # 解析 agent 对应的 workspace 路径，多 Agent 场景下各 agent 有独立 workspace
        workspace_path = self._resolve_agent_workspace(agent_info)

        system_prompt_adapter = create_system_prompt_adapter(workspace_path=workspace_path)
        system_prompt = system_prompt_adapter.build_system_prompt()

        context_adapter = (
            self._create_context_adapter(llm_router, agent_info, workspace_path=workspace_path)
            if use_legacy_context
            else None
        )

        # 创建工具中间件管道（可选，默认启用计时和日志中间件）
        tool_middleware_adapter = None if disable_tools else self._create_tool_middleware_adapter(
            turn_profile=turn_profile,
            tool_policies=tool_policies,
        )

        return AgentCoreConfig(
            llm=llm_adapter,
            tools=tool_adapter,
            logger=agent_logger,
            context=context_adapter,
            system_prompt=system_prompt,
            system_prompt_port=system_prompt_adapter,
            tool_middleware_pipeline=tool_middleware_adapter.pipeline if tool_middleware_adapter else None,
            max_turns=turn_profile.max_turns,
            model=model_name,
            provider=provider_name,
            enable_context_compression=use_legacy_context,
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
        allow_auto_resume: bool = False,
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
            allow_auto_resume: 是否在状态类回复后自动触发主任务继续执行。

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

            if allow_auto_resume:
                try:
                    from ..services.context.session_state_store import SessionContextStateStore
                    from ..services.storage import get_storage_service
                    from .agent_invoker import AgentInvoker

                    state = await SessionContextStateStore(get_storage_service()).get(session_id)
                    if state is not None:
                        payload = state.to_dict()
                        goal = payload.get("current_goal", {})
                        primary_goal = goal.get("primary_goal", "")
                        if goal.get("is_progress_query") and primary_goal:
                            await AgentInvoker(self).invoke(
                                agent_id=event_agent_id or "",
                                session_id=session_id,
                                content=f"继续执行当前主任务：{primary_goal}",
                            )
                except Exception as exc:
                    logger.warning(
                        "Failed to schedule auto-resume",
                        extra={"session_id": session_id, "error": str(exc)},
                    )

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

    def _create_runtime_turn_controller(self) -> DefaultTurnController:
        """Create the default runtime controller backed by the shared runtime service."""
        default_tool_policy = self._runtime_services.tool_policies.get("__default__")
        governed_policies = dict(self._runtime_services.tool_policies)
        if default_tool_policy is None:
            from ..runtime.types import ToolPolicy

            default_tool_policy = ToolPolicy()
        if len(governed_policies) <= 1:
            from ..runtime.types import ToolPolicy

            governed_policies.update(
                {
                    "web_search": ToolPolicy(max_uses_per_turn=3, repeat_signature_limit=1),
                    "fetch_web_content": ToolPolicy(max_uses_per_turn=2, repeat_signature_limit=1),
                    "read_file": ToolPolicy(max_uses_per_turn=8, repeat_signature_limit=2),
                    "write_file": ToolPolicy(max_uses_per_turn=4, repeat_signature_limit=2),
                    "run_in_terminal": ToolPolicy(max_uses_per_turn=4, repeat_signature_limit=2),
                }
            )
        governed_policies.setdefault(
            "runtime_legacy_bridge",
            default_tool_policy,
        )
        return DefaultTurnController(
            tool_governor=DefaultToolGovernor(
                default_policy=default_tool_policy,
                policies_by_name=governed_policies,
            ),
            planner=self._runtime_controller_planner,
            executor=self._runtime_controller_executor,
            compact_fn=self._runtime_controller_compact,
        )

    async def _runtime_controller_planner(self, state) -> ToolExecutionPlan | None:
        """Plan the next bounded runtime step by calling the model directly."""
        if state.request.metadata.get("runtime_force_legacy_bridge"):
            if state.metadata.get("runtime_legacy_bridge_executed"):
                return ToolExecutionPlan()
            return ToolExecutionPlan(
                calls=[
                    ToolCallSpec(
                        tool_name="runtime_legacy_bridge",
                        arguments={"session_id": state.request.session.session_id},
                    )
                ]
            )

        await self._ensure_runtime_turn_bootstrap(state)
        forced_delegate_plan = self._runtime_maybe_force_delegate_plan(state)
        if forced_delegate_plan is not None:
            return forced_delegate_plan
        self._runtime_log_entry(
            state,
            event="runtime_turn_plan",
            message=f"Runtime planner starting for turn {state.turn_index}",
            category=LogCategory.AGENT_LOOP,
            data={"turn_index": state.turn_index},
        )
        assistant_message = await self._runtime_invoke_model_once(state)
        state.metadata["last_assistant_message"] = assistant_message
        state.active_messages.append(assistant_message)
        state.metadata["model"] = assistant_message.model or state.metadata.get("model", "")
        state.metadata["provider"] = assistant_message.provider or state.metadata.get("provider", "")

        usage = assistant_message.usage or {}
        state.record_token_usage(
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
        )

        tool_calls = assistant_message.get_tool_calls()
        text_output = assistant_message.get_text().strip()
        if assistant_message.stop_reason in {"error", "aborted"}:
            state.metadata["final_output_text"] = text_output or self._runtime_best_effort_output(
                state,
                error_message=assistant_message.error_message or assistant_message.stop_reason,
            )
            state.metadata["final_candidate_ready"] = True
            state.metadata["best_effort_reason"] = assistant_message.stop_reason
            return ToolExecutionPlan()

        if not tool_calls:
            state.metadata["final_output_text"] = text_output or self._runtime_best_effort_output(state)
            state.metadata["final_candidate_ready"] = True
            return ToolExecutionPlan()

        state.metadata["final_candidate_ready"] = False
        self._runtime_log_entry(
            state,
            event="runtime_turn_plan_ready",
            message="Runtime planner produced tool plan",
            category=LogCategory.AGENT_LOOP,
            data={
                "turn_index": state.turn_index,
                "tool_call_count": len(tool_calls),
                "stop_reason": assistant_message.stop_reason,
                "output_chars": len(text_output),
            },
        )
        return ToolExecutionPlan(
            calls=[
                ToolCallSpec(
                    tool_name=tool_call.name,
                    arguments=dict(tool_call.arguments),
                )
                for tool_call in tool_calls
            ],
            allow_parallel=len(tool_calls) > 1,
        )

    def _runtime_maybe_force_delegate_plan(self, state) -> ToolExecutionPlan | None:
        """Convert explicit delegation requests into a deterministic delegate_task plan."""
        if state.turn_index != 0:
            return None
        if state.request.metadata.get("runtime_resume_from_child"):
            return None

        available_tool_names = {tool.name for tool in self._runtime_available_tools(state)}
        if "delegate_task" not in available_tool_names:
            return None

        current_agent_id = ""
        runtime_agent_info = state.metadata.get("runtime_agent_info")
        if runtime_agent_info is not None:
            current_agent_id = getattr(runtime_agent_info, "agent_id", "") or ""

        parsed = self._runtime_parse_delegate_intent(
            state.request.user_input,
            current_agent_id=current_agent_id,
        )
        if parsed is None:
            return None

        target_agent_id, delegated_task = parsed
        self._runtime_log_entry(
            state,
            event="runtime_forced_delegate_plan",
            message=f"Forced delegate_task plan for {target_agent_id}",
            category=LogCategory.AGENT_LOOP,
            data={
                "target_agent_id": target_agent_id,
                "task_preview": delegated_task[:200],
            },
        )
        return ToolExecutionPlan(
            calls=[
                ToolCallSpec(
                    tool_name="delegate_task",
                    arguments={
                        "agent_id": target_agent_id,
                        "task": delegated_task,
                    },
                )
            ]
        )

    def _runtime_parse_delegate_intent(
        self,
        user_input: str,
        *,
        current_agent_id: str = "",
    ) -> tuple[str, str] | None:
        """Parse explicit '让某个 agent 去做事' requests before they hit the model."""
        text = (user_input or "").strip()
        if not text:
            return None

        agents = AgentORM.list_all()
        if not agents:
            return None

        alias_to_agent_id: dict[str, str] = {}
        for agent in agents:
            agent_id = getattr(agent, "agent_id", "") or ""
            agent_name = getattr(agent, "agent_name", "") or ""
            if not agent_id or agent_id == current_agent_id:
                continue

            aliases = {
                agent_id,
                agent_name,
                agent_name.replace("助手", "").strip(),
                agent_name.replace("分析员", "").strip(),
                agent_name.replace("评估员", "").strip(),
            }
            for alias in aliases:
                normalized = alias.strip()
                if normalized:
                    alias_to_agent_id[normalized] = agent_id

        if not alias_to_agent_id:
            return None

        alias_pattern = "|".join(
            sorted((re.escape(alias) for alias in alias_to_agent_id.keys()), key=len, reverse=True)
        )
        pattern = re.compile(
            rf"^\s*(?:请|麻烦|请你|帮我)?\s*(?:委托|让|叫)?\s*(?P<agent>{alias_pattern})\s*(?P<task>.+)$"
        )
        match = pattern.match(text)
        if match is None:
            return None

        target_agent_id = alias_to_agent_id.get(match.group("agent"), "")
        delegated_task = match.group("task").lstrip(" ，,:：")
        for prefix in ("帮我", "帮忙", "给我", "为我", "去", "来", "帮我去", "帮忙去"):
            if delegated_task.startswith(prefix) and len(delegated_task) > len(prefix):
                delegated_task = delegated_task[len(prefix):].lstrip(" ，,:：")
                break
        delegated_task = delegated_task.strip()
        if not target_agent_id or not delegated_task:
            return None
        return target_agent_id, delegated_task

    async def _runtime_controller_executor(
        self,
        plan,
        state,
    ) -> list[ToolExecutionResult]:
        """Execute governed runtime tools directly, with legacy fallback only when requested."""
        observed: list[ToolExecutionResult] = []
        runtime_abort_event = (
            state.request.metadata.get("runtime_abort_event")
            if isinstance(state.request.metadata.get("runtime_abort_event"), asyncio.Event)
            else None
        )
        if state.request.metadata.get("runtime_force_legacy_bridge"):
            for call in plan.calls:
                if call.tool_name != "runtime_legacy_bridge":
                    observed.append(
                        ToolExecutionResult(
                            tool_name=call.tool_name,
                            success=False,
                            error=f"unsupported runtime controller tool: {call.tool_name}",
                        )
                    )
                    continue

                state.metadata["runtime_legacy_bridge_executed"] = True
                result = await self._run_runtime_turn_via_legacy_bridge(state.request)
                await self._persist_runtime_turn_result(state.request, result)
                result.metadata["runtime_persisted"] = True
                observed.append(
                    ToolExecutionResult(
                        tool_name=call.tool_name,
                        success=result.kind != "abort",
                        output=result.output_text or "",
                        error=None if result.kind != "abort" else result.finish_reason,
                        metadata={"turn_result": result},
                    )
                )
            return observed

        await self._ensure_runtime_turn_bootstrap(state)
        config = state.metadata["runtime_config"]
        available_tools = self._runtime_available_tools(state)
        tool_port = config.tools

        for call in plan.calls:
            if tool_port is None:
                observed.append(
                    ToolExecutionResult(
                        tool_name=call.tool_name,
                        success=False,
                        error="tool execution is disabled for this runtime request",
                    )
                )
                continue

        from ..agent_core.tool_executor import execute_tool_calls
        from ..agent_core.types import TextContent, ToolCallContent

        runtime_tool_calls = [
            ToolCallContent(
                id=f"runtime-tool-{uuid4().hex[:8]}",
                name=call.tool_name,
                arguments=dict(call.arguments),
            )
            for call in plan.calls
        ]
        self._runtime_log_entry(
            state,
            event="runtime_tool_batch_start",
            message=f"Executing {len(runtime_tool_calls)} runtime tool call(s)",
            category=LogCategory.TOOL_EXEC,
            data={
                "turn_index": state.turn_index,
                "tool_names": [call.name for call in runtime_tool_calls],
            },
        )
        for tool_call in runtime_tool_calls:
            self._runtime_log_tool_call_start(
                state,
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
            )
            self._runtime_record_gateway_event(
                state,
                event_type="tool_call",
                payload={
                    "tool_call_id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                },
            )

        async for event in execute_tool_calls(
            trace_id=getattr(self._runtime_request_context(state.request), "trace_id", ""),
            llm_call_id=f"runtime-turn-{uuid4().hex[:8]}",
            tool_port=tool_port,
            tools=available_tools,
            tool_calls=runtime_tool_calls,
            abort_event=runtime_abort_event,
            middleware_pipeline=config.tool_middleware_pipeline,
        ):
            if not isinstance(event, ToolExecutionEndEvent):
                continue

            output_text = ""
            details: dict[str, Any] = {}
            if event.result is not None:
                details = dict(event.result.details)
                output_text = "".join(
                    content.text
                    for content in event.result.content
                    if isinstance(content, TextContent)
                )
            artifact_ref = await self._runtime_maybe_archive_tool_output(
                state,
                tool_name=event.tool_name,
                output_text=output_text,
                details=details,
            )
            if artifact_ref is not None:
                details["artifact_ref"] = artifact_ref.id
                output_text = (
                    f"[Stored large result: {artifact_ref.id}]\n"
                    f"Preview:\n{artifact_ref.preview}"
                )

            result_message = ToolResultMessage.from_text(
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                text=output_text or (event.result.details.get("error", "") if event.result else ""),
                is_error=event.is_error,
                details=details,
            )
            state.active_messages.append(result_message)
            result_text = "".join(
                content.text
                for content in result_message.content
                if isinstance(content, TextContent)
            )
            self._runtime_log_tool_call_end(
                state,
                tool_call_id=event.tool_call_id,
                result=event.result,
                duration_ms=event.duration_ms,
                is_error=event.is_error,
                error=str(details.get("error") or output_text) if event.is_error else None,
            )
            self._runtime_record_gateway_event(
                state,
                event_type="tool_result",
                payload={
                    "tool_call_id": event.tool_call_id,
                    "name": event.tool_name,
                    "result": result_text,
                    "is_error": event.is_error,
                    "details": dict(details),
                    "duration_ms": event.duration_ms,
                },
            )
            await self.runtime_session_orchestrator.append_transcript_entry(
                TranscriptEntry(
                    entry_id=f"runtime-tool-result:{uuid4().hex}",
                    session_id=state.request.session.session_id,
                    turn_index=state.turn_index,
                    kind="tool_result",
                    role="tool",
                    text=result_text,
                    payload_json={
                        "tool_call_id": event.tool_call_id,
                        "tool_name": event.tool_name,
                        "is_error": event.is_error,
                        "details": dict(details),
                    },
                    created_at=time.time(),
                )
            )
            await self._runtime_record_tool_side_effects(state, result_message)

            if details.get("force_finalize"):
                exhausted = list(details.get("exhausted_tool_names", []))
                disabled = state.metadata.setdefault("disabled_tool_names", set())
                disabled.update(exhausted or [event.tool_name])
                state.metadata["force_finalize"] = True

            if event.tool_name == "delegate_task" and details.get("delegate_terminal"):
                state.metadata["runtime_synthesis_instruction"] = self._runtime_delegate_synthesis_instruction(
                    tool_name=event.tool_name,
                    details=details,
                    result_text=result_text,
                )
                disabled = state.metadata.setdefault("disabled_tool_names", set())
                disabled.update(tool.name for tool in self._runtime_available_tools(state))
                self._runtime_log_entry(
                    state,
                    event="delegate_terminal_result",
                    message="Delegate task returned terminal child result; forcing synthesis without more tool calls",
                    category=LogCategory.AGENT_LOOP,
                    data={
                        "delegate_terminal_reason": details.get("delegate_terminal_reason", ""),
                        "child_trace_id": details.get("child_trace_id", ""),
                    },
                    level=LogLevel.INFO,
                )

            observed.append(
                ToolExecutionResult(
                    tool_name=event.tool_name,
                    success=not event.is_error,
                    output=output_text,
                    error=str(details.get("error") or output_text) if event.is_error else None,
                    metadata=details,
                )
            )
        return observed

    def _runtime_delegate_synthesis_instruction(
        self,
        *,
        tool_name: str,
        details: dict[str, Any],
        result_text: str,
    ) -> str:
        """Force the parent runtime to summarize delegated output instead of continuing tool search."""
        child_trace_id = details.get("child_trace_id", "")
        reason = details.get("delegate_terminal_reason", "")
        if reason == "async_wait":
            lines = [
                f"委托工具 {tool_name} 已成功发起异步子任务。",
                "不要继续调用任何工具，也不要自己继续搜索或扩展调研。",
                "请向用户明确说明：子任务已委托给目标 agent，完成后会自动回传结果。",
            ]
        else:
            lines = [
                f"委托工具 {tool_name} 已返回最终子任务结果。",
                "不要继续调用任何工具，也不要自己继续搜索或扩展调研。",
                "请仅基于当前委托结果向用户给出最终答复。",
            ]
        if child_trace_id:
            lines.append(f"子任务 trace_id: {child_trace_id}")
        if reason:
            lines.append(f"委托结果状态: {reason}")
        if result_text.strip() and reason != "async_wait":
            lines.append("委托结果如下：")
            lines.append(result_text.strip())
        return "\n".join(lines)

    async def _persist_runtime_turn_result(self, request: TurnRequest, result: TurnResult) -> None:
        """Persist minimal runtime replay state for resume/reconnect and child-session flows."""
        try:
            if result.metadata.get("legacy_bridge"):
                user_entry_id = f"runtime-user:{uuid4().hex}"
                await self.runtime_session_orchestrator.append_transcript_entry(
                    TranscriptEntry(
                        entry_id=user_entry_id,
                        session_id=request.session.session_id,
                        turn_index=0,
                        kind="user_message",
                        role="user",
                        text=request.user_input,
                        created_at=time.time(),
                    )
                )
                if result.output_text:
                    await self.runtime_session_orchestrator.append_transcript_entry(
                        TranscriptEntry(
                            entry_id=f"runtime-assistant:{uuid4().hex}",
                            session_id=request.session.session_id,
                            turn_index=0,
                            kind="assistant_message",
                            role="assistant",
                            text=result.output_text,
                            created_at=time.time(),
                        )
                    )
            await self.runtime_session_orchestrator.record_state_snapshot(
                StateSnapshotRecord(
                    snapshot_id=f"snapshot:{uuid4().hex}",
                    session_id=request.session.session_id,
                    task_frame=result.updated_task_frame or request.task_frame,
                    turn_index=int(result.metadata.get("turn_index", 0) or 0),
                    unresolved=list((result.updated_task_frame or request.task_frame).unresolved),
                    active_artifact_refs=[artifact.id for artifact in result.artifact_refs],
                    budget_snapshot=dict(result.metadata.get("budget", {}) or {}),
                    tool_usage_json=dict(
                        result.metadata.get("budget", {}).get("per_tool_calls", {})
                        if isinstance(result.metadata.get("budget"), dict)
                        else {}
                    ),
                    last_finish_reason=result.finish_reason,
                    metadata={"kind": result.kind},
                    created_at=time.time(),
                )
            )
            if result.output_text:
                await self.runtime_session_orchestrator.record_summary(
                    SummaryRecord(
                        summary_id=f"summary:{uuid4().hex}",
                        session_id=request.session.session_id,
                        summary_type="child_result"
                        if request.session.parent_session_key
                        else "collapse",
                        summary=result.output_text,
                        objective=(result.updated_task_frame or request.task_frame).objective,
                        artifact_refs=[artifact.id for artifact in result.artifact_refs],
                        created_at=time.time(),
                    )
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist runtime replay state",
                extra={
                    "session_id": request.session.session_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

    async def _runtime_controller_compact(self, state, reason: str):
        """Mark runtime compaction decisions while letting runtime compression produce the final payload."""
        from ..agent_core.context_transform import convert_messages_to_llm
        from ..runtime.context import CompressionContext
        from ..runtime.types import CompactResult

        state.metadata["last_compaction_reason"] = reason
        state.metadata["compaction_count"] = state.metadata.get("compaction_count", 0) + 1
        state.metadata["request_compact"] = False

        profile_name = str(
            state.request.metadata.get("_runtime_compression_profile_name")
            or self._runtime_services.default_compression_profile
        )
        profile = self._runtime_services.compression_profiles.get(profile_name)
        if profile is None:
            profile = self._runtime_services.compression_profiles.get(
                self._runtime_services.default_compression_profile
            )

        raw_messages = (
            [dict(message) for message in state.active_messages]
            if state.active_messages and all(isinstance(message, dict) for message in state.active_messages)
            else convert_messages_to_llm(state.active_messages)
        )
        estimated_input_tokens = max(
            sum(len(str(message.get("content", ""))) for message in raw_messages) // 4,
            1,
        )
        model_context_window = state.budget.profile.max_total_tokens or estimated_input_tokens

        if profile is None:
            return CompactResult(
                active_messages=list(raw_messages),
                active_artifact_refs=list(state.active_artifact_refs),
                task_frame=state.task_frame,
                metadata={"compaction_source": "passthrough"},
            )

        result = await self._runtime_compression_pipeline.run(
            CompressionContext(
                session_key=state.request.session.session_key,
                turn=state.turn_index,
                task_frame=state.task_frame,
                profile=profile,
                model_context_window=model_context_window,
                estimated_input_tokens=estimated_input_tokens,
                messages=[dict(message) for message in raw_messages],
                active_artifacts=list(state.active_artifact_refs),
                budget=state.budget,
                metadata={
                    "now_ms": int(time.time() * 1000),
                    "recent_failures": list(state.metadata.get("runtime_recent_failures", [])),
                    "compaction_reason": reason,
                },
            )
        )
        if isinstance(result, CompactResult):
            return result
        return CompactResult(
            active_messages=list(result.messages),
            active_artifact_refs=list(result.active_artifacts),
            task_frame=state.task_frame,
            metadata={
                "compaction_source": "pipeline",
                "compression_operations": list(result.operations),
                **dict(result.metadata),
            },
        )

    async def _ensure_runtime_turn_bootstrap(self, state) -> None:
        """Load runtime dependencies and session history once per turn request."""
        if state.metadata.get("runtime_bootstrapped"):
            return

        request = state.request
        agent_info = self._resolve_runtime_agent_info(request)
        runtime_config = self._build_runtime_agent_config(request, agent_info) or self.create_config(
            agent_info,
            use_legacy_context=False,
        )
        state.metadata["runtime_agent_info"] = agent_info
        state.metadata["runtime_config"] = runtime_config
        state.metadata["model"] = runtime_config.model
        state.metadata["provider"] = runtime_config.provider
        state.metadata.setdefault("disabled_tool_names", set())
        state.metadata.setdefault("runtime_event_timeline", [])
        state.metadata["runtime_prompt_mode"] = request.metadata.get("prompt_mode") or (
            "minimal" if request.session.lane == "subagent" else "full"
        )

        resume_state = None
        if not bool(request.metadata.get("runtime_skip_history_load")):
            resume_state = await self.runtime_session_orchestrator.resume_session(
                request.session.session_key,
                recent_entries_limit=48,
            )
        state.metadata["runtime_resume_state"] = resume_state
        state.metadata["runtime_summary_chain_messages"] = self._runtime_summary_chain_messages(resume_state)
        state.metadata["runtime_recent_failures"] = self._runtime_recent_failures_from_resume(resume_state)

        history_messages = self._runtime_messages_from_resume(resume_state)
        if history_messages:
            state.active_messages.extend(history_messages)
        elif not bool(request.metadata.get("runtime_skip_history_load")):
            fallback_messages = await self._runtime_load_legacy_history_messages(request.session.session_id)
            state.active_messages.extend(fallback_messages)
            if fallback_messages:
                await self._runtime_seed_transcript_from_agent_messages(
                    request.session.session_id,
                    fallback_messages,
                )
                state.metadata["runtime_history_source"] = "legacy_memory_imported"
            else:
                state.metadata["runtime_history_source"] = "empty"
        else:
            state.metadata["runtime_history_source"] = "empty"

        state.active_artifact_refs = await self._runtime_artifact_refs_from_resume(resume_state)
        if resume_state is not None and resume_state.latest_snapshot is not None:
            state.session_tool_usage = dict(resume_state.latest_snapshot.tool_usage_json or {})

        if bool(request.metadata.get("persist_user_message", True)) and request.user_input.strip():
            state.metadata["runtime_user_msg_id"] = await self._persist_user_message(
                request.session.session_id,
                request.user_input,
            )

        current_user_message = UserMessage.from_text(request.user_input)
        state.active_messages.append(current_user_message)
        if request.user_input.strip():
            await self.runtime_session_orchestrator.append_transcript_entry(
                TranscriptEntry(
                    entry_id=f"runtime-user:{uuid4().hex}",
                    session_id=request.session.session_id,
                    turn_index=state.turn_index,
                    kind="user_message",
                    role="user",
                    text=request.user_input,
                    created_at=time.time(),
                )
            )
        state.metadata["runtime_system_prompt"] = self._runtime_system_prompt(request, runtime_config)
        self._runtime_log_entry(
            state,
            event="runtime_turn_start",
            message="Runtime turn bootstrapped",
            category=LogCategory.AGENT_LOOP,
            data={
                "session_id": request.session.session_id,
                "turn_index": state.turn_index,
                "history_source": state.metadata.get("runtime_history_source", "runtime_store"),
                "prompt_mode": state.metadata.get("runtime_prompt_mode", "full"),
            },
        )
        state.metadata["runtime_bootstrapped"] = True

    async def _runtime_load_legacy_history_messages(self, session_id: str) -> list[Any]:
        """Fallback loader for older sessions that have not been replayed into runtime stores yet."""
        try:
            from ..memory.manager import get_memory_manager

            memory_manager = get_memory_manager()
            return await memory_manager.get_session_history_as_agent_messages(session_id, limit=200)
        except Exception as exc:
            logger.warning(
                "Failed to load legacy session history for runtime fallback",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return []

    def _runtime_messages_from_resume(self, resume_state) -> list[Any]:
        """Convert persisted runtime transcript entries back into agent-core messages."""
        if resume_state is None:
            return []

        messages: list[Any] = []
        for entry in resume_state.recent_entries:
            message = self._runtime_entry_to_message(entry)
            if message is not None:
                messages.append(message)
        return messages

    def _runtime_entry_to_message(self, entry: TranscriptEntry) -> Any | None:
        """Map one runtime transcript entry into an agent-core message."""
        payload = entry.payload_json or {}
        if entry.kind == "user_message":
            return UserMessage.from_text(entry.text or "")
        if entry.kind == "assistant_message":
            content: list[Any] = []
            if entry.text:
                content.append(TextContent(text=entry.text))
            for tool_call in payload.get("tool_calls", []) if isinstance(payload, dict) else []:
                if not isinstance(tool_call, dict):
                    continue
                content.append(
                    ToolCallContent(
                        id=str(tool_call.get("id", "")),
                        name=str(tool_call.get("name", "")),
                        arguments=(
                            dict(tool_call.get("arguments", {}) or {})
                            if isinstance(tool_call.get("arguments"), dict)
                            else {"raw": tool_call.get("arguments")}
                        ),
                    )
                )
            return AssistantMessage(
                content=content,
                model=str(payload.get("model", "")),
                provider=str(payload.get("provider", "")),
                stop_reason=str(payload.get("stop_reason", "")),
                usage=dict(payload.get("usage", {}) or {}),
            )
        if entry.kind == "tool_result":
            return ToolResultMessage.from_text(
                tool_call_id=str(payload.get("tool_call_id", "")),
                tool_name=str(payload.get("tool_name", entry.role or "")),
                text=entry.text or "",
                is_error=bool(payload.get("is_error", False)),
                details=dict(payload.get("details", {}) or {}),
            )
        if entry.kind == "tool_call":
            payload_calls = payload.get("tool_calls")
            if isinstance(payload_calls, list) and payload_calls:
                tool_contents = [
                    ToolCallContent(
                        id=str(call.get("id", "")),
                        name=str(call.get("name", "")),
                        arguments=(
                            dict(call.get("arguments", {}) or {})
                            if isinstance(call.get("arguments"), dict)
                            else {"raw": call.get("arguments")}
                        ),
                    )
                    for call in payload_calls
                    if isinstance(call, dict)
                ]
                return AssistantMessage(
                    content=tool_contents,
                    model=str(payload.get("model", "")),
                    provider=str(payload.get("provider", "")),
                    stop_reason="tool_use",
                    usage=dict(payload.get("usage", {}) or {}),
                )
        return None

    def _runtime_summary_chain_messages(self, resume_state) -> list[dict[str, str]]:
        """Convert persisted summary chain into compact system summary messages."""
        if resume_state is None:
            return []

        messages: list[dict[str, str]] = []
        for summary in resume_state.summary_chain:
            lines = [f"[{summary.summary_type} summary]"]
            if summary.objective:
                lines.append(f"Objective: {summary.objective}")
            if summary.summary:
                lines.append(summary.summary)
            if summary.open_questions:
                lines.append("Open questions: " + "; ".join(summary.open_questions))
            if summary.recent_failures:
                lines.append("Recent failures: " + "; ".join(summary.recent_failures))
            if summary.artifact_refs:
                lines.append("Artifacts: " + ", ".join(summary.artifact_refs))
            messages.append({"role": "system", "content": "\n".join(lines)})
        return messages

    def _runtime_recent_failures_from_resume(self, resume_state) -> list[str]:
        """Recover persisted failure summaries for compression invariants and assessment context."""
        if resume_state is None:
            return []

        failures: list[str] = []
        for summary in resume_state.summary_chain:
            failures.extend(summary.recent_failures)
        return failures[-6:]

    async def _runtime_artifact_refs_from_resume(self, resume_state) -> list[Any]:
        """Resolve active artifact refs from the latest runtime snapshot when available."""
        if resume_state is None or resume_state.latest_snapshot is None:
            return []

        refs: list[Any] = []
        seen: set[str] = set()
        for artifact_id in resume_state.latest_snapshot.active_artifact_refs:
            if artifact_id in seen:
                continue
            seen.add(artifact_id)
            try:
                stored = await self.runtime_session_orchestrator.artifact_repository.get(artifact_id)
            except Exception as exc:
                logger.warning(
                    "Failed to resolve runtime artifact reference",
                    extra={"session_id": resume_state.session.session_id, "artifact_id": artifact_id, "error": str(exc)},
                )
                continue
            if stored is None:
                continue
            artifact_ref, _content = stored
            refs.append(artifact_ref)
        return refs

    async def _runtime_seed_transcript_from_agent_messages(
        self,
        session_id: str,
        messages: list[Any],
    ) -> None:
        """Import legacy agent messages into runtime transcript storage once, for compatibility migration."""
        for index, message in enumerate(messages):
            entry = self._runtime_message_to_transcript_entry(
                session_id=session_id,
                turn_index=index,
                message=message,
            )
            if entry is None:
                continue
            await self.runtime_session_orchestrator.append_transcript_entry(entry)

    def _runtime_message_to_transcript_entry(
        self,
        *,
        session_id: str,
        turn_index: int,
        message: Any,
    ) -> TranscriptEntry | None:
        """Convert an agent-core message into a runtime transcript entry."""
        if isinstance(message, UserMessage):
            text = "".join(content.text for content in message.content if isinstance(content, TextContent))
            return TranscriptEntry(
                entry_id=f"runtime-import-user:{uuid4().hex}",
                session_id=session_id,
                turn_index=turn_index,
                kind="user_message",
                role="user",
                text=text,
                created_at=float(getattr(message, "timestamp", 0) or 0) / 1000.0,
            )

        if isinstance(message, AssistantMessage):
            text = message.get_text()
            tool_calls = [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                }
                for tool_call in message.get_tool_calls()
            ]
            return TranscriptEntry(
                entry_id=f"runtime-import-assistant:{uuid4().hex}",
                session_id=session_id,
                turn_index=turn_index,
                kind="assistant_message" if text else "tool_call",
                role="assistant",
                text=text or None,
                payload_json={
                    "model": message.model,
                    "provider": message.provider,
                    "stop_reason": message.stop_reason,
                    "usage": dict(message.usage or {}),
                    "tool_calls": tool_calls,
                },
                created_at=float(getattr(message, "timestamp", 0) or 0) / 1000.0,
            )

        if isinstance(message, ToolResultMessage):
            text = "".join(content.text for content in message.content if isinstance(content, TextContent))
            return TranscriptEntry(
                entry_id=f"runtime-import-tool:{uuid4().hex}",
                session_id=session_id,
                turn_index=turn_index,
                kind="tool_result",
                role="tool",
                text=text,
                payload_json={
                    "tool_call_id": message.tool_call_id,
                    "tool_name": message.tool_name,
                    "is_error": message.is_error,
                    "details": dict(message.details),
                },
                created_at=float(getattr(message, "timestamp", 0) or 0) / 1000.0,
            )
        return None

    def _runtime_system_prompt(self, request: TurnRequest, config: AgentCoreConfig) -> str:
        """Build the runtime system prompt without creating an Agent instance."""
        system_prompt = config.system_prompt

        if not bool(request.metadata.get("runtime_disable_skills")):
            skill_prompt, _ = _match_and_load_skill_prompt(request.user_input)
            if skill_prompt:
                system_prompt = f"{system_prompt}\n{skill_prompt}".strip()

        announcement_block = self._render_runtime_announcements(request)
        if announcement_block:
            system_prompt = f"{system_prompt}\n\n{announcement_block}".strip()

        return system_prompt

    async def _runtime_invoke_model_once(self, state) -> AssistantMessage:
        """Run one LLM round for the runtime controller."""
        from ..agent_core.agent_loop import _stream_assistant_response

        config: AgentCoreConfig = state.metadata["runtime_config"]
        available_tools = self._runtime_available_tools(state)
        runtime_abort_event = (
            state.request.metadata.get("runtime_abort_event")
            if isinstance(state.request.metadata.get("runtime_abort_event"), asyncio.Event)
            else None
        )
        system_prompt, llm_messages = await self._runtime_prepare_model_input(
            state,
            system_prompt=state.metadata["runtime_system_prompt"],
            available_tools=available_tools,
        )
        synthesis_instruction = state.metadata.get("runtime_synthesis_instruction")
        if isinstance(synthesis_instruction, str) and synthesis_instruction.strip():
            system_prompt = f"{system_prompt}\n\n[Runtime Synthesis Directive]\n{synthesis_instruction}".strip()
        llm_call_id = self._runtime_log_llm_call_start(
            state,
            system_prompt=system_prompt,
            messages=llm_messages,
            tools=available_tools,
        )
        llm_started_at = time.time()

        assistant_message: AssistantMessage | None = None
        async for event in _stream_assistant_response(
            llm=config.llm,
            llm_call_id=llm_call_id,
            system_prompt=system_prompt,
            messages=llm_messages,
            tools=available_tools,
            model=config.model,
            provider=config.provider,
            abort_event=runtime_abort_event,
        ):
            if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
                assistant_message = event.message

        if assistant_message is None:
            assistant_message = AssistantMessage(
                content=[TextContent(text=self._runtime_best_effort_output(state))],
                model=config.model,
                provider=config.provider,
                stop_reason="error",
                error_message="runtime model invocation produced no assistant message",
            )

        if assistant_message.stop_reason in {"error", "aborted"} and not assistant_message.get_text().strip():
            assistant_message.content = [
                TextContent(
                    text=self._runtime_best_effort_output(
                        state,
                        error_message=assistant_message.error_message or assistant_message.stop_reason,
                    )
                )
            ]
        self._runtime_log_llm_call_end(
            state,
            call_id=llm_call_id,
            assistant_message=assistant_message,
            duration_ms=(time.time() - llm_started_at) * 1000,
        )
        await self._runtime_record_assistant_observation(state, assistant_message)
        return assistant_message

    async def _runtime_prepare_model_input(
        self,
        state,
        *,
        system_prompt: str,
        available_tools: list[Any],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Build runtime model input directly from transcript, summaries, artifacts, and compression."""
        from ..agent_core.context_transform import convert_messages_to_llm
        from ..runtime.context import CompressionContext, ContextBuildRequest

        raw_messages = convert_messages_to_llm(state.active_messages)
        profile_name = str(
            state.request.metadata.get("_runtime_compression_profile_name")
            or self._runtime_services.default_compression_profile
        )
        profile = self._runtime_services.compression_profiles.get(profile_name)
        if profile is None:
            profile = self._runtime_services.compression_profiles.get(
                self._runtime_services.default_compression_profile
            )

        build_result = await self._runtime_context_builder.build(
            ContextBuildRequest(
                session=state.request.session,
                task_frame=state.task_frame,
                raw_messages=raw_messages,
                prompt_mode=state.metadata.get("runtime_prompt_mode", "full"),
                metadata={
                    "stable_prefix": system_prompt,
                    "artifact_refs": list(state.active_artifact_refs),
                    "budget": state.budget,
                    "summary_chain": list(state.metadata.get("runtime_summary_chain_messages", [])),
                },
            )
        )

        if profile is None:
            return build_result.system_prompt or system_prompt, list(build_result.active_messages)

        model_context_window = state.budget.profile.max_total_tokens or max(
            build_result.estimated_input_tokens,
            1,
        )
        compression_ctx = CompressionContext(
            session_key=state.request.session.session_key,
            turn=state.turn_index,
            task_frame=state.task_frame,
            profile=profile,
            model_context_window=model_context_window,
            estimated_input_tokens=build_result.estimated_input_tokens,
            messages=[dict(message) for message in build_result.active_messages],
            active_artifacts=list(state.active_artifact_refs),
            budget=state.budget,
            metadata={
                "now_ms": int(time.time() * 1000),
                "recent_failures": list(state.metadata.get("runtime_recent_failures", [])),
                "available_tool_count": len(available_tools),
            },
        )
        compression_result = await self._runtime_compression_pipeline.run(compression_ctx)
        if (
            model_context_window > 0
            and compression_result.estimated_input_tokens >= model_context_window
        ):
            emergency_ctx = CompressionContext(
                session_key=compression_ctx.session_key,
                turn=compression_ctx.turn,
                task_frame=compression_ctx.task_frame,
                profile=compression_ctx.profile,
                model_context_window=compression_ctx.model_context_window,
                estimated_input_tokens=compression_result.estimated_input_tokens,
                messages=[dict(message) for message in compression_result.messages],
                active_artifacts=list(compression_result.active_artifacts),
                budget=compression_ctx.budget,
                metadata=dict(compression_ctx.metadata),
            )
            compression_result = await self._runtime_compression_pipeline.run_emergency(emergency_ctx)

        state.active_artifact_refs = list(compression_result.active_artifacts)
        await self._runtime_record_compression_events(
            state,
            tokens_before=build_result.estimated_input_tokens,
            result=compression_result,
        )
        state.metadata["runtime_context_summary"] = ", ".join(compression_result.operations)
        self._runtime_log_entry(
            state,
            event="runtime_context_prepared",
            message="Runtime context prepared for model call",
            category=LogCategory.CONTEXT,
            data={
                "turn_index": state.turn_index,
                "message_count": len(compression_result.messages),
                "estimated_tokens": compression_result.estimated_input_tokens,
                "operations": list(compression_result.operations),
                "artifact_count": len(compression_result.active_artifacts),
            },
        )
        return build_result.system_prompt or system_prompt, list(compression_result.messages)

    async def _runtime_record_compression_events(
        self,
        state,
        *,
        tokens_before: int,
        result,
    ) -> None:
        """Persist runtime compression telemetry for this turn."""
        from ..runtime.repositories import CompressionEventRecord

        if not getattr(result, "operations", None):
            return

        tokens_after = int(getattr(result, "estimated_input_tokens", tokens_before) or 0)
        freed_tokens = max(tokens_before - tokens_after, 0)
        affected_artifacts = [
            artifact.id
            for artifact in getattr(result, "active_artifacts", [])
            if hasattr(artifact, "id")
        ]
        for stage in result.operations:
            normalized_stage = "emergency" if stage == "emergency_compact" else stage
            if normalized_stage not in {
                "persist",
                "aggregate_budget",
                "ttl_prune",
                "microcompact",
                "collapse",
                "autocompact",
                "memory_flush",
                "emergency",
            }:
                continue
            try:
                await self.runtime_session_orchestrator.append_compression_event(
                    CompressionEventRecord(
                        event_id=f"compression:{uuid4().hex}",
                        session_id=state.request.session.session_id,
                        turn_index=state.turn_index,
                        stage=normalized_stage,
                        tokens_before=tokens_before,
                        tokens_after=tokens_after,
                        freed_tokens=freed_tokens,
                        affected_artifact_ids=affected_artifacts,
                        fallback_used=normalized_stage == "emergency",
                        metadata={
                            "operations": list(result.operations),
                            "rollback_applied": bool(getattr(result, "rollback_applied", False)),
                            "rollback_reason": getattr(result, "rollback_reason", None),
                        },
                        created_at=time.time(),
                    )
                )
                self._runtime_log_entry(
                    state,
                    event=f"runtime_compression_{normalized_stage}",
                    message=f"Runtime compression stage applied: {normalized_stage}",
                    category=LogCategory.CONTEXT,
                    data={
                        "turn_index": state.turn_index,
                        "tokens_before": tokens_before,
                        "tokens_after": tokens_after,
                        "freed_tokens": freed_tokens,
                        "affected_artifact_ids": affected_artifacts,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist runtime compression event",
                    extra={
                        "session_id": state.request.session.session_id,
                        "stage": stage,
                        "error": str(exc),
                    },
                )

    async def _runtime_record_assistant_observation(self, state, assistant_message: AssistantMessage) -> None:
        """Persist runtime transcript entries for assistant text and tool-call planning."""
        text_output = assistant_message.get_text().strip()
        tool_calls = assistant_message.get_tool_calls()

        payload = {
            "model": assistant_message.model,
            "provider": assistant_message.provider,
            "stop_reason": assistant_message.stop_reason,
            "usage": dict(assistant_message.usage or {}),
        }
        if tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                }
                for tool_call in tool_calls
            ]

        if text_output or tool_calls:
            await self.runtime_session_orchestrator.append_transcript_entry(
                TranscriptEntry(
                    entry_id=f"runtime-assistant:{uuid4().hex}",
                    session_id=state.request.session.session_id,
                    turn_index=state.turn_index,
                    kind="assistant_message" if text_output else "tool_call",
                    role="assistant",
                    text=text_output or None,
                    payload_json=payload,
                    created_at=time.time(),
                )
            )

        if assistant_message.stop_reason in {"error", "aborted"} and assistant_message.error_message:
            recent_failures = state.metadata.setdefault("runtime_recent_failures", [])
            recent_failures.append(assistant_message.error_message)
            del recent_failures[:-6]

    def _runtime_available_tools(self, state) -> list[Any]:
        """Return tools still available for the runtime turn."""
        config: AgentCoreConfig = state.metadata["runtime_config"]
        if config.tools is None:
            return []
        available_tools = config.tools.get_tools()
        disabled = state.metadata.get("disabled_tool_names") or set()
        if not disabled:
            return available_tools
        return [tool for tool in available_tools if tool.name not in disabled]

    async def _runtime_maybe_archive_tool_output(
        self,
        state,
        *,
        tool_name: str,
        output_text: str,
        details: dict[str, Any],
    ):
        """Persist very large tool output out of the active runtime context."""
        if not output_text:
            return None
        if len(output_text) <= state.budget.profile.tool_result_single_chars:
            return None

        from ..runtime.types import ArtifactRef

        artifact_id = f"artifact:{uuid4().hex[:8]}"
        preview = output_text[:900]
        artifact = ArtifactRef(
            id=artifact_id,
            kind="tool",
            title=tool_name,
            preview=preview,
            created_at=time.time(),
            metadata=dict(details),
        )
        await self.runtime_session_orchestrator.store_artifact(artifact, output_text)
        state.active_artifact_refs.append(artifact)
        return artifact

    async def _runtime_record_tool_side_effects(self, state, result_message: ToolResultMessage) -> None:
        """Record lightweight stateful side effects after one tool result."""
        details = result_message.details
        try:
            from ..services.context import get_session_state_updater, get_tool_result_archiver

            archiver = get_tool_result_archiver()
            updater = get_session_state_updater()
            archived = {}
            result_text = result_message.get_text() if hasattr(result_message, "get_text") else "".join(
                content.text for content in result_message.content if isinstance(content, TextContent)
            )

            if archiver is not None:
                archived = await archiver.archive(
                    session_id=state.request.session.session_id,
                    tool_name=result_message.tool_name,
                    result_text=result_text,
                    details=details,
                )

            if updater is not None:
                await updater.update_after_turn(
                    session_id=state.request.session.session_id,
                    agent_id=state.metadata["runtime_agent_info"].agent_id,
                    mode="research",
                    new_messages=[{"role": "user", "content": state.request.user_input}],
                    tool_results=[{"tool_name": result_message.tool_name, **archived}],
                    delegate_results=[],
                )
        except Exception as exc:
            logger.warning(
                "Runtime tool side effects failed",
                extra={
                    "session_id": state.request.session.session_id,
                    "tool_name": result_message.tool_name,
                    "error": str(exc),
                },
            )

    def _runtime_best_effort_output(self, state, error_message: str | None = None) -> str:
        """Build a compact best-effort answer from current tool evidence."""
        snippets: list[str] = []
        for result in state.tool_results[-4:]:
            if result.output:
                snippets.append(f"[{result.tool_name}] {result.output[:280]}")
        if snippets:
            body = "\n\n".join(snippets)
            if error_message:
                return (
                    f"基于当前已获取的信息，先给出最佳努力结果。\n\n{body}\n\n"
                    f"说明：后续总结阶段失败，错误为：{error_message}"
                )
            return f"基于当前已获取的信息，先给出最佳努力结果。\n\n{body}"
        if error_message:
            return f"未能完成最终总结，但已停止继续调用工具。错误：{error_message}"
        return "未能生成最终答案，但已停止继续调用工具。"

    def _runtime_request_context(self, request: TurnRequest):
        try:
            from ..conversation.context import get_current_context

            return get_current_context()
        except Exception:
            return None

    def _runtime_trace_id(self, request: TurnRequest) -> str:
        """Resolve the active trace id for runtime telemetry."""
        current_context = self._runtime_request_context(request)
        if current_context is not None and getattr(current_context, "trace_id", ""):
            return str(current_context.trace_id)
        trace_id = request.metadata.get("trace_id")
        return str(trace_id) if isinstance(trace_id, str) else ""

    def _runtime_log_request(
        self,
        request: TurnRequest,
        *,
        event: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        category: LogCategory = LogCategory.AGENT_LOOP,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        """Write one runtime log entry into AgentLogger for developer-mode inspection."""
        trace_id = self._runtime_trace_id(request)
        if not trace_id:
            return
        _get_agent_logger().create_log_entry(
            trace_id=trace_id,
            event=event,
            message=message,
            level=level,
            category=category,
            data=data or {},
            duration_ms=duration_ms,
            error=error,
        )

    def _runtime_log_entry(
        self,
        state,
        *,
        event: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        category: LogCategory = LogCategory.AGENT_LOOP,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        """State-aware wrapper around runtime request logging."""
        self._runtime_log_request(
            state.request,
            event=event,
            message=message,
            level=level,
            category=category,
            data=data,
            duration_ms=duration_ms,
            error=error,
        )

    def _runtime_log_llm_call_start(
        self,
        state,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
    ) -> str:
        """Create one runtime LLM call entry in AgentLogger and return the call id."""
        from ..agent_core.context_transform import estimate_tokens

        trace_id = self._runtime_trace_id(state.request)
        call_id = f"runtime-{uuid4().hex[:8]}"
        state.metadata["runtime_last_llm_call_id"] = call_id
        if not trace_id:
            return call_id

        _get_agent_logger().log_llm_call_start(
            LLMCallLog(
                call_id=call_id,
                trace_id=trace_id,
                model=str(state.metadata.get("model") or state.metadata["runtime_config"].model or ""),
                provider=str(state.metadata.get("provider") or state.metadata["runtime_config"].provider or ""),
                system_prompt=system_prompt,
                messages=list(messages),
                message_count=len(messages),
                estimated_tokens=estimate_tokens(messages),
                temperature=state.metadata["runtime_config"].temperature,
                max_tokens=state.metadata["runtime_config"].max_tokens,
                thinking_level=state.metadata["runtime_config"].thinking_level,
                tools=[tool.to_llm_tool() for tool in tools] if tools else None,
            )
        )
        return call_id

    def _runtime_log_llm_call_end(
        self,
        state,
        *,
        call_id: str,
        assistant_message: AssistantMessage,
        duration_ms: float,
    ) -> None:
        """Close one runtime LLM call entry in AgentLogger."""
        from ..agent_core.context_transform import content_to_dict

        if not self._runtime_trace_id(state.request):
            return
        _get_agent_logger().log_llm_call_end(
            call_id=call_id,
            response={
                "content": [content_to_dict(item) for item in assistant_message.content],
                "stop_reason": assistant_message.stop_reason,
            },
            usage=dict(assistant_message.usage or {}),
            duration_ms=duration_ms,
            error=assistant_message.error_message,
        )

    def _runtime_log_tool_call_start(
        self,
        state,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Create one runtime tool-call entry in AgentLogger."""
        trace_id = self._runtime_trace_id(state.request)
        if not trace_id:
            return
        _get_agent_logger().log_tool_call_start(
            ToolCallLog(
                call_id=tool_call_id,
                trace_id=trace_id,
                llm_call_id=str(state.metadata.get("runtime_last_llm_call_id", "")),
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
            )
        )

    def _runtime_log_tool_call_end(
        self,
        state,
        *,
        tool_call_id: str,
        result: Any,
        duration_ms: float,
        is_error: bool,
        error: str | None,
    ) -> None:
        """Close one runtime tool-call entry in AgentLogger."""
        if not self._runtime_trace_id(state.request):
            return
        _get_agent_logger().log_tool_call_end(
            call_id=tool_call_id,
            result=result,
            duration_ms=duration_ms,
            is_error=is_error,
            error=error,
        )

    def _runtime_record_gateway_event(
        self,
        state,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Record runtime events that should be replayed to gateway clients."""
        timeline = state.metadata.setdefault("runtime_event_timeline", [])
        timeline.append(
            {
                "type": event_type,
                "payload": dict(payload),
                "timestamp_ms": int(time.time() * 1000),
            }
        )

    async def _persist_runtime_assistant_message(self, request: TurnRequest, result: TurnResult) -> None:
        """Persist the final assistant answer into the legacy session store for UI history."""
        if not result.output_text:
            return
        try:
            session_manager = _get_session_manager()
            await session_manager.add_message(
                session_id=request.session.session_id,
                role="assistant",
                content=result.output_text,
                metadata={
                    "model": result.metadata.get("model", ""),
                    "provider": result.metadata.get("provider", ""),
                    "stop_reason": result.finish_reason,
                    "usage": result.metadata.get("budget", {}),
                    "user_msg_id": request.metadata.get("runtime_user_msg_id"),
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist runtime assistant message",
                extra={"session_id": request.session.session_id, "error": str(exc)},
            )

    async def run_runtime_turn(
        self,
        request: TurnRequest,
        *,
        controller=None,
    ) -> TurnResult:
        """Execute a prepared runtime turn through the bounded runtime controller."""
        runtime_controller = controller or self.runtime_turn_controller
        try:
            result = await runtime_controller.run(request)
        except Exception as exc:
            self._runtime_log_request(
                request,
                event="runtime_turn_error",
                message="Runtime turn execution failed",
                level=LogLevel.ERROR,
                category=LogCategory.AGENT_LOOP,
                data={"session_id": request.session.session_id},
                error=str(exc),
            )
            raise
        if not result.metadata.get("runtime_persisted"):
            await self._persist_runtime_turn_result(request, result)
            await self._persist_runtime_assistant_message(request, result)
            result.metadata["runtime_persisted"] = True
        self._runtime_log_request(
            request,
            event="runtime_turn_finish",
            message=f"Runtime turn finished with {result.finish_reason or result.kind}",
            category=LogCategory.AGENT_LOOP,
            data={
                "kind": result.kind,
                "finish_reason": result.finish_reason,
                "model": result.metadata.get("model", ""),
                "provider": result.metadata.get("provider", ""),
                "budget": result.metadata.get("budget", {}),
            },
        )
        return result

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

            injected_announcements = self._inject_runtime_announcements(agent, request)
            if injected_announcements:
                mark_milestone(
                    "announcements_injected",
                    phase="stream_events",
                    progress="runtime_announcements_injected",
                )

            if timeout_ms is not None:
                await asyncio.wait_for(consume_events(), timeout=float(timeout_ms) / 1000.0)
            else:
                await consume_events()
        except asyncio.TimeoutError:
            mark_milestone("timed_out", phase="timeout", progress="timed_out")
            used_synthetic_fallback = self._should_mark_synthetic_fallback(
                final_content,
                response_parts,
                diagnostics=diagnostics,
            )
            timeout_fallback_mode = self._runtime_timeout_fallback_mode(request)
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
                kind="final" if timeout_fallback_mode == "final" and used_synthetic_fallback else "abort",
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
                    "synthetic_fallback": used_synthetic_fallback,
                    "timeout_fallback_mode": timeout_fallback_mode,
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
            used_synthetic_fallback = self._should_mark_synthetic_fallback(
                final_content,
                response_parts,
                diagnostics=diagnostics,
            )
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
                    "synthetic_fallback": used_synthetic_fallback,
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

        return self.create_config(
            agent_info,
            disable_tools=False,
            use_legacy_context=False,
        )

    def _inject_runtime_announcements(self, agent: Agent, request: TurnRequest) -> bool:
        """Inject structured child-session announcements into the runtime prompt."""
        announcement_block = self._render_runtime_announcements(request)
        if not announcement_block:
            return False
        if not hasattr(agent, "__dict__") and not hasattr(agent, "_system_prompt"):
            return False

        base_prompt = getattr(agent, "_system_prompt", "") or getattr(agent, "_original_system_prompt", "")
        try:
            agent._system_prompt = f"{base_prompt}\n\n{announcement_block}".strip()
        except (AttributeError, TypeError):
            return False
        return True

    def _render_runtime_announcements(self, request: TurnRequest) -> str:
        """Render queued child-session announcements into one prompt block."""
        announcements = request.metadata.get("runtime_announcements")
        if not isinstance(announcements, list) or not announcements:
            return ""

        lines = ["[Runtime Child Results]"]
        for item in announcements:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                f"status={item.get('status', 'unknown')}; "
                f"summary={item.get('summary', '')}; "
                f"unresolved={'; '.join(item.get('unresolved', [])) if isinstance(item.get('unresolved'), list) else item.get('unresolved', '')}; "
                f"artifacts={', '.join(item.get('artifact_refs', [])) if isinstance(item.get('artifact_refs'), list) else item.get('artifact_refs', '')}; "
                f"stats={item.get('stats_line', '')}"
            )
        return "\n".join(lines).strip()

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

    def _should_mark_synthetic_fallback(
        self,
        final_content: str | None,
        response_parts: list[str],
        *,
        diagnostics: dict[str, Any],
    ) -> bool:
        """Return whether the current timeout/abort result relies on synthetic fallback text."""
        if final_content or response_parts:
            return False
        return bool(diagnostics.get("fast_mode"))

    def _runtime_timeout_fallback_mode(self, request: TurnRequest) -> str:
        """Resolve the debug-only timeout fallback mode."""
        mode = request.metadata.get("runtime_timeout_fallback_mode")
        if isinstance(mode, str) and mode in {"abort", "final"}:
            return mode
        return "abort"

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

    def _create_tool_middleware_adapter(
        self,
        *,
        turn_profile,
        tool_policies: dict[str, Any],
    ):
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
                max_tool_calls_total=turn_profile.max_tool_calls if turn_profile else 12,
                max_tool_calls_by_name={
                    name: policy.max_uses_per_turn
                    for name, policy in (tool_policies or {}).items()
                },
                default_repeat_signature_limit=(
                    self._runtime_services.tool_policies.get("__default__").repeat_signature_limit
                    if self._runtime_services.tool_policies.get("__default__") is not None
                    else 2
                ),
                repeat_signature_limit_by_name={
                    name: policy.repeat_signature_limit
                    for name, policy in (tool_policies or {}).items()
                },
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
            final_text = "".join(text_parts)
            if not final_text.strip():
                return None
            return GatewayEvent.message_end(
                content=final_text,
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
                    text = msg.get_text()
                    if not text.strip():
                        continue
                    await session_manager.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=text,
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
