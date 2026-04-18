"""Legacy agent stream bridge extracted from AgentBridge."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from ..agent_core.adapters.llm_adapter import XAgentLLMAdapter
from ..agent_core.adapters.system_prompt_adapter import create_system_prompt_adapter
from ..agent_core.adapters.tool_adapter import XAgentToolAdapter
from ..agent_core.adapters.tool_middleware_adapter import create_tool_middleware_adapter
from ..agent_core.agent import Agent
from ..agent_core.config import AgentCoreConfig
from ..agent_core.types import (
    AgentEndEvent,
    AgentStartEvent,
    AssistantMessage,
    MessageEndEvent,
    MessageUpdateEvent,
    TextContent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
)
from .agent_info import AgentInfo
from .bridge_dependencies import (
    get_agent_logger,
    get_llm_router,
    get_session_manager,
    get_tool_manager,
    logger,
    match_and_load_skill_prompt,
)
from .response import GatewayEvent

if TYPE_CHECKING:
    from .agent_bridge import AgentBridge


class LegacyAgentStreamBridge:
    """Encapsulate the legacy Agent -> GatewayEvent streaming path."""

    def __init__(self, runtime_services: Any) -> None:
        self._runtime_services = runtime_services

    def create_config(
        self,
        bridge: AgentBridge,
        agent_info: AgentInfo | None = None,
        *,
        disable_tools: bool = False,
        use_legacy_context: bool = True,
    ) -> AgentCoreConfig:
        """创建 Agent 配置。"""
        llm_router = get_llm_router()
        llm_adapter = XAgentLLMAdapter(llm_router)
        tool_adapter = None if disable_tools else XAgentToolAdapter(get_tool_manager())
        agent_logger = get_agent_logger()
        model_name = getattr(getattr(llm_router, "_primary", None), "model_id", "")
        provider_name = getattr(getattr(llm_router, "_primary", None), "name", "")
        turn_profile = self._runtime_services.turn_profiles[
            self._runtime_services.default_turn_profile
        ]
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

        workspace_path = bridge._resolve_agent_workspace(agent_info)
        system_prompt_adapter = create_system_prompt_adapter(workspace_path=workspace_path)
        system_prompt = system_prompt_adapter.build_system_prompt()
        context_adapter = (
            bridge._create_context_adapter(
                llm_router,
                agent_info,
                workspace_path=workspace_path,
            )
            if use_legacy_context
            else None
        )
        tool_middleware_adapter = (
            None
            if disable_tools
            else bridge._create_tool_middleware_adapter(
                turn_profile=turn_profile,
                tool_policies=tool_policies,
            )
        )

        return AgentCoreConfig(
            llm=llm_adapter,
            tools=tool_adapter,
            logger=agent_logger,
            context=context_adapter,
            system_prompt=system_prompt,
            system_prompt_port=system_prompt_adapter,
            tool_middleware_pipeline=tool_middleware_adapter.pipeline
            if tool_middleware_adapter
            else None,
            max_turns=turn_profile.max_turns,
            model=model_name,
            provider=provider_name,
            enable_context_compression=use_legacy_context,
        )

    def create_agent(
        self,
        bridge: AgentBridge,
        config: AgentCoreConfig | None = None,
        agent_info: AgentInfo | None = None,
    ) -> Agent:
        """创建 Agent 实例。"""
        if config is None:
            config = self.create_config(bridge, agent_info)
        return Agent(config)

    async def load_session_history(self, agent: Agent, session_id: str) -> None:
        """从数据库加载会话历史消息到 Agent 内存。"""
        try:
            from ..memory.manager import get_memory_manager

            memory_manager = get_memory_manager()
            agent_messages = await memory_manager.get_session_history_as_agent_messages(
                session_id,
                limit=200,
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
        bridge: AgentBridge,
        *,
        agent: Agent,
        content: str,
        session_id: str,
        agent_info: AgentInfo | None = None,
        images: list[tuple[str, str]] | None = None,
        abort_event: asyncio.Event | None = None,
        persist_user_message: bool = True,
        user_metadata: dict[str, Any] | None = None,
        disable_skills: bool = False,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """执行 legacy Agent loop 并产出 GatewayEvent。"""
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
            if persist_user_message:
                user_msg_id = await bridge._persist_user_message(
                    session_id,
                    content,
                    metadata=user_metadata,
                )

            if not disable_skills:
                bridge._inject_skill_prompt(agent, content, agent_id=event_agent_id)

            if abort_event is not None:
                abort_forwarder = asyncio.create_task(forward_abort())
            async for event in agent.prompt(content, images):
                gateway_event = bridge._convert_agent_event(
                    event,
                    agent_id=event_agent_id,
                    agent_name=event_agent_name,
                )

                if isinstance(event, MessageUpdateEvent) and event.delta_type == "text":
                    assistant_content.append(event.delta)

                if isinstance(event, AgentEndEvent):
                    await bridge._persist_assistant_messages(
                        session_id,
                        event,
                        user_msg_id,
                    )

                if gateway_event is not None:
                    yield gateway_event

            bridge._restore_system_prompt(agent)
        except Exception as exc:
            logger.exception(
                "Error in AgentBridge.run",
                extra={"session_id": session_id, "error": str(exc)},
            )

            if assistant_content:
                await bridge._persist_partial_response(
                    session_id,
                    assistant_content,
                    str(exc),
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
            bridge._restore_system_prompt(agent)

    def resolve_agent_workspace(self, agent_info: AgentInfo | None) -> str | None:
        """解析 Agent 对应的 workspace 路径。"""
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

        try:
            from ..config.manager import get_config
            from ..conversation.multi_agent_context_loader import get_multi_agent_context_loader

            config = get_config()
            has_multi_agent = (
                hasattr(config, "multi_agent") and config.multi_agent and config.multi_agent.agents
            )
            if has_multi_agent:
                multi_agent_context_loader = get_multi_agent_context_loader()
                if multi_agent_context_loader is not None:
                    agent_context = multi_agent_context_loader.get_agent_context(
                        agent_info.agent_id
                    )
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
                            "available_agent_ids": str(
                                list(multi_agent_context_loader.agent_contexts.keys())
                            ),
                        },
                    )
        except Exception as exc:
            logger.warning(
                "[workspace-debug] MultiAgentContextLoader lookup failed",
                extra={"agent_id": agent_info.agent_id, "error": str(exc)},
            )

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

    def create_context_adapter(
        self,
        llm_router: Any,
        workspace_path: str | None = None,
    ):
        """创建 ContextPort adapter（上下文压缩）。"""
        try:
            from ..agent_core.adapters.context_adapter import create_context_adapter
            from ..config.manager import get_config

            config = get_config()
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

    def create_tool_middleware_adapter(
        self,
        *,
        turn_profile: Any,
        tool_policies: dict[str, Any],
    ):
        """创建工具中间件适配器。"""
        try:
            from ..config.manager import get_config

            config = get_config()
            high_risk_tools = None
            if hasattr(config, "tools") and hasattr(config.tools, "high_risk_tools"):
                high_risk_tools = config.tools.high_risk_tools

            return create_tool_middleware_adapter(
                enable_timing=True,
                enable_logging=True,
                high_risk_tools=high_risk_tools,
                max_tool_calls_total=turn_profile.max_tool_calls if turn_profile else 12,
                max_tool_calls_by_name={
                    name: policy.max_uses_per_turn for name, policy in (tool_policies or {}).items()
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

    def message_persistence_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        role: str,
    ) -> dict[str, Any]:
        """Extract stable metadata that should survive in session history."""
        if not metadata:
            return {}

        persisted: dict[str, Any] = {}
        if role == "user":
            if isinstance(metadata.get("audio"), dict):
                persisted["audio"] = dict(metadata["audio"])
            if isinstance(metadata.get("transcript"), dict):
                persisted["transcript"] = dict(metadata["transcript"])
        if role == "assistant" and isinstance(metadata.get("audio_reply"), dict):
            persisted["audio_reply"] = dict(metadata["audio_reply"])
        return persisted

    async def persist_user_message(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """持久化用户消息。"""
        try:
            session_manager = get_session_manager()
            user_msg = await session_manager.add_message(
                session_id=session_id,
                role="user",
                content=content,
                metadata=metadata,
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

    def inject_skill_prompt(
        self,
        agent: Agent,
        content: str,
        *,
        agent_id: str | None = None,
    ) -> None:
        """匹配技能并注入 prompt 到 Agent 的 system_prompt。"""
        skill_prompt, _invocation = match_and_load_skill_prompt(content, agent_id=agent_id)

        from ..conversation.system_prompt_builder import SKILLS_INJECTION_MARKER

        base_prompt = agent._original_system_prompt
        if skill_prompt:
            if SKILLS_INJECTION_MARKER in base_prompt:
                agent._system_prompt = base_prompt.replace(
                    SKILLS_INJECTION_MARKER,
                    skill_prompt.strip(),
                )
            else:
                agent._system_prompt = base_prompt + skill_prompt
            logger.debug(
                "Skill prompt injected",
                extra={"skill_prompt_length": len(skill_prompt)},
            )
        elif SKILLS_INJECTION_MARKER in base_prompt:
            agent._system_prompt = base_prompt.replace(SKILLS_INJECTION_MARKER, "")

    def restore_system_prompt(self, agent: Agent) -> None:
        """恢复 Agent 的原始 system prompt。"""
        agent._system_prompt = agent._original_system_prompt

    def convert_agent_event(
        self,
        event: Any,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent | None:
        """将 AgentEvent 转换为 GatewayEvent。"""
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
                text_parts = [c.text for c in event.result.content if isinstance(c, TextContent)]
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

        return None

    async def persist_assistant_messages(
        self,
        session_id: str,
        event: AgentEndEvent,
        user_msg_id: str | None = None,
    ) -> None:
        """持久化 assistant 消息到会话。"""
        try:
            session_manager = get_session_manager()
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

    async def persist_partial_response(
        self,
        session_id: str,
        assistant_content: list[str],
        error_message: str,
    ) -> None:
        """即使出错也尝试保存部分响应。"""
        try:
            session_manager = get_session_manager()
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
