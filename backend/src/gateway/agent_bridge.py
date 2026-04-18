"""Agent Core 桥接器。

AgentBridge 是 Gateway 与 Agent Core 之间的唯一连接点。
封装 AgentCoreConfig 的创建、Agent 实例管理、技能调度和 agent_loop 的调用。

从 agent_core/api/websocket.py 中的以下逻辑迁移而来：
- create_agent_config(): 创建 AgentCoreConfig
- bridge_dependencies: 依赖获取与技能匹配
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
from typing import Any
from uuid import uuid4

from ..agent_core.agent import Agent
from ..agent_core.config import AgentCoreConfig
from ..agent_core.types import (
    AssistantMessage,
    LogCategory,
    LogLevel,
    MessageEndEvent,
    TextContent,
    ToolExecutionEndEvent,
    ToolResultMessage,
)
from ..conversation.dao.models import Agent as AgentORM
from ..runtime.repositories import TranscriptEntry
from ..runtime.routing import IntentRouter
from ..runtime.service import get_runtime_services
from ..runtime.turn import DefaultToolGovernor, DefaultTurnController
from ..runtime.types import (
    ToolCallSpec,
    ToolExecutionPlan,
    ToolExecutionResult,
    TurnBudgetProfile,
    TurnRequest,
    TurnResult,
)
from .agent_info import AgentInfo
from .bridge_dependencies import (
    get_skill_registry,
)
from .legacy_stream_bridge import LegacyAgentStreamBridge
from .response import GatewayEvent
from .runtime_bootstrap import RuntimeBootstrapBridge
from .runtime_model_input import RuntimeModelInputBridge
from .runtime_persistence import RuntimePersistenceBridge
from .runtime_resume import RuntimeResumeBridge
from .runtime_telemetry import RuntimeTelemetryRecorder
from .tool_result_normalizer import RuntimeToolResultNormalizer

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
        self._legacy_stream_bridge = LegacyAgentStreamBridge(self._runtime_services)
        self.runtime_session_orchestrator = self._runtime_services.orchestrator
        self._runtime_resume = RuntimeResumeBridge(self.runtime_session_orchestrator)
        self._runtime_telemetry = RuntimeTelemetryRecorder(self._runtime_model_budget_payload)
        self._runtime_bootstrap = RuntimeBootstrapBridge(
            runtime_session_orchestrator=self.runtime_session_orchestrator,
            runtime_resume=self._runtime_resume,
            runtime_telemetry=self._runtime_telemetry,
            runtime_fast_system_prompt=_RUNTIME_FAST_SYSTEM_PROMPT,
            runtime_fast_max_tokens=_RUNTIME_FAST_MAX_TOKENS,
        )
        self._runtime_persistence = RuntimePersistenceBridge(
            runtime_session_orchestrator=self.runtime_session_orchestrator,
        )
        from ..runtime.context import DefaultCompressionPipeline, DefaultContextBuilder

        self._runtime_context_builder = DefaultContextBuilder()
        self._runtime_compression_pipeline = DefaultCompressionPipeline()
        self._runtime_model_input = RuntimeModelInputBridge(
            runtime_services=self._runtime_services,
        )
        self._runtime_tool_result_normalizer = RuntimeToolResultNormalizer()
        self._intent_router = IntentRouter(
            skill_registry=None,
            skill_registry_provider=self._resolve_intent_router_skill_registry,
            agent_catalog_provider=AgentORM.list_all,
        )
        self.runtime_turn_controller = self._create_runtime_turn_controller()

    def create_config(
        self,
        agent_info: AgentInfo | None = None,
        *,
        disable_tools: bool = False,
        use_legacy_context: bool = True,
    ) -> AgentCoreConfig:
        """创建 Agent 配置。"""
        return self._legacy_stream_bridge.create_config(
            self,
            agent_info,
            disable_tools=disable_tools,
            use_legacy_context=use_legacy_context,
        )

    def create_agent(
        self,
        config: AgentCoreConfig | None = None,
        agent_info: AgentInfo | None = None,
    ) -> Agent:
        """创建 Agent 实例。"""
        return self._legacy_stream_bridge.create_agent(self, config, agent_info)

    async def load_session_history(self, agent: Agent, session_id: str) -> None:
        """从数据库加载会话历史消息到 Agent 内存。"""
        await self._legacy_stream_bridge.load_session_history(agent, session_id)

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
        user_metadata: dict[str, Any] | None = None,
        disable_skills: bool = False,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """执行 legacy Agent Loop 并产出 GatewayEvent。"""
        async for event in self._legacy_stream_bridge.run(
            self,
            agent=agent,
            content=content,
            session_id=session_id,
            agent_info=agent_info,
            images=images,
            abort_event=abort_event,
            persist_user_message=persist_user_message,
            user_metadata=user_metadata,
            disable_skills=disable_skills,
        ):
            yield event

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
        await self._ensure_runtime_turn_bootstrap(state)
        routed_plan = self._runtime_maybe_route_intent_plan(state)
        if routed_plan is not None:
            return routed_plan
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
        state.metadata["provider"] = assistant_message.provider or state.metadata.get(
            "provider", ""
        )

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
            state.metadata["final_output_text"] = text_output or self._runtime_best_effort_output(
                state
            )
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

    def _runtime_maybe_route_intent_plan(self, state) -> ToolExecutionPlan | None:
        """Resolve deterministic routing decisions before the free-form LLM planner."""
        runtime_agent_info = state.metadata.get("runtime_agent_info")
        current_agent_id = getattr(runtime_agent_info, "agent_id", "") if runtime_agent_info else ""
        decision = self._intent_router.decide(
            user_input=state.request.user_input,
            available_tool_names={tool.name for tool in self._runtime_available_tools(state)},
            turn_index=state.turn_index,
            metadata={
                **dict(state.request.metadata),
                "current_agent_id": current_agent_id,
            },
        )
        if decision is None or decision.tool_plan is None:
            return None
        state.metadata["runtime_route_decision"] = {
            "policy_id": decision.policy_id,
            "reason": decision.reason,
            **dict(decision.metadata or {}),
        }
        self._runtime_log_entry(
            state,
            event="runtime_route_decision",
            message=f"Intent router selected {decision.policy_id}",
            category=LogCategory.AGENT_LOOP,
            data={
                "policy_id": decision.policy_id,
                "reason": decision.reason,
                "tool_names": [call.tool_name for call in decision.tool_plan.calls],
            },
        )
        return decision.tool_plan

    @staticmethod
    def _resolve_intent_router_skill_registry(metadata: dict[str, Any]):
        """Resolve skill registry lazily so AgentBridge init does not prewarm a fallback workspace."""
        return get_skill_registry(str(metadata.get("current_agent_id") or "").strip() or None)

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
            raw_output_text = ""
            if event.result is not None:
                details = dict(event.result.details)
                raw_output_text = "".join(
                    content.text
                    for content in event.result.content
                    if isinstance(content, TextContent)
                )
                normalized_result = self._runtime_tool_result_normalizer.normalize(
                    tool_name=event.tool_name,
                    output_text=raw_output_text,
                    details=details,
                )
                output_text = normalized_result.display_text
                details = normalized_result.details
            artifact_ref = await self._runtime_maybe_archive_tool_output(
                state,
                tool_name=event.tool_name,
                output_text=raw_output_text,
                details=details,
            )
            if artifact_ref is not None:
                details["artifact_ref"] = artifact_ref.id
                output_text = self._runtime_tool_result_normalizer.attach_artifact_ref(
                    tool_name=event.tool_name,
                    display_text=output_text,
                    artifact_ref=artifact_ref,
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
                state.metadata["runtime_synthesis_instruction"] = (
                    self._runtime_delegate_synthesis_instruction(
                        tool_name=event.tool_name,
                        details=details,
                        result_text=result_text,
                    )
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

            if details.get("is_background") and details.get("background_task_kind") in {
                "video_pipeline",
                "image_generation",
            }:
                state.metadata["runtime_synthesis_instruction"] = (
                    self._runtime_background_task_synthesis_instruction(
                        tool_name=event.tool_name,
                        details=details,
                    )
                )
                disabled = state.metadata.setdefault("disabled_tool_names", set())
                disabled.update(tool.name for tool in self._runtime_available_tools(state))
                self._runtime_log_entry(
                    state,
                    event="background_media_task_started",
                    message="Media pipeline moved to background execution; forcing handoff synthesis",
                    category=LogCategory.AGENT_LOOP,
                    data={
                        "process_id": details.get("process_id", ""),
                        "provider_task_id": details.get("modelscope_task_id", ""),
                        "background_task_kind": details.get("background_task_kind", ""),
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

    def _runtime_background_task_synthesis_instruction(
        self,
        *,
        tool_name: str,
        details: dict[str, Any],
    ) -> str:
        """Force the runtime to stop polling and hand the user a background-task receipt."""
        process_id = str(details.get("process_id") or "").strip()
        provider_task_id = str(details.get("modelscope_task_id") or "").strip()
        title = str(details.get("background_task_title") or "后台任务").strip()
        command = str(details.get("command") or "").strip()
        lines = [
            f"{title}已由工具 {tool_name} 转入后台执行。",
            "不要继续调用任何工具，也不要同步等待最终产物。",
            "请直接告诉用户：任务已经开始后台处理，完成后系统会自动把结果推送回当前会话。",
        ]
        if process_id:
            lines.append(f"进程 ID: {process_id}")
        if provider_task_id:
            lines.append(f"任务 ID: {provider_task_id}")
        if command:
            lines.append(f"后台命令: {command}")
        return "\n".join(lines)

    async def _persist_runtime_turn_result(self, request: TurnRequest, result: TurnResult) -> None:
        """Persist minimal runtime replay state for resume/reconnect and child-session flows."""
        await self._runtime_persistence.persist_runtime_turn_result(request, result)

    async def _runtime_controller_compact(self, state, reason: str):
        """Mark runtime compaction decisions while letting runtime compression produce the final payload."""
        from ..runtime.context import CompressionContext
        from ..runtime.types import CompactResult

        state.metadata["last_compaction_reason"] = reason
        state.metadata["compaction_count"] = state.metadata.get("compaction_count", 0) + 1
        state.metadata["request_compact"] = False

        profile = self._runtime_resolve_compression_profile(state.request)

        raw_messages = self._runtime_messages_to_llm_payload(state.active_messages)
        estimated_input_tokens = max(
            sum(len(str(message.get("content", ""))) for message in raw_messages) // 4,
            1,
        )
        model_context_window = self._runtime_resolve_model_context_window(
            state.request,
            state_budget_profile=state.budget.profile,
            compression_profile=profile,
            fallback_window=estimated_input_tokens,
        )

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
        compression_metadata = self._runtime_compression_metadata_payload(result)
        passthrough_metadata = {
            key: value
            for key, value in dict(result.metadata).items()
            if key
            not in {
                "budget_state",
                "verification",
                "verifier_result",
                "rollback",
                "rollback_applied",
                "rollback_reason",
            }
        }
        return CompactResult(
            active_messages=list(result.messages),
            active_artifact_refs=list(result.active_artifacts),
            task_frame=state.task_frame,
            metadata={
                "compaction_source": "pipeline",
                **passthrough_metadata,
                **compression_metadata,
            },
        )

    async def _ensure_runtime_turn_bootstrap(self, state) -> None:
        """Load runtime dependencies and session history once per turn request."""
        await self._runtime_bootstrap.ensure_runtime_turn_bootstrap(
            state,
            create_config=self.create_config,
            persist_user_message=self._persist_user_message,
            message_persistence_metadata=self._message_persistence_metadata,
            messages_from_resume=self._runtime_messages_from_resume,
            summary_chain_messages=self._runtime_summary_chain_messages,
            recent_failures_from_resume=self._runtime_recent_failures_from_resume,
            load_legacy_history_messages=self._runtime_load_legacy_history_messages,
            seed_transcript_from_agent_messages=self._runtime_seed_transcript_from_agent_messages,
            artifact_refs_from_resume=self._runtime_artifact_refs_from_resume,
        )

    async def _runtime_load_legacy_history_messages(self, session_id: str) -> list[Any]:
        """Fallback loader for older sessions that have not been replayed into runtime stores yet."""
        return await self._runtime_resume.load_legacy_history_messages(session_id)

    def _runtime_messages_from_resume(self, resume_state) -> list[Any]:
        """Convert persisted runtime transcript entries back into agent-core messages."""
        return self._runtime_resume.messages_from_resume(resume_state)

    def _runtime_entry_to_message(self, entry: TranscriptEntry) -> Any | None:
        """Map one runtime transcript entry into an agent-core message."""
        return self._runtime_resume.entry_to_message(entry)

    def _runtime_summary_chain_messages(self, resume_state) -> list[dict[str, str]]:
        """Convert persisted summary chain into compact system summary messages."""
        return self._runtime_resume.summary_chain_messages(resume_state)

    def _runtime_recent_failures_from_resume(self, resume_state) -> list[str]:
        """Recover persisted failure summaries for compression invariants and assessment context."""
        return self._runtime_resume.recent_failures_from_resume(resume_state)

    def _runtime_relevant_summaries(self, resume_state) -> list[Any]:
        """Select only the latest effective compression snapshot plus child results."""
        return self._runtime_resume.relevant_summaries(resume_state)

    async def _runtime_artifact_refs_from_resume(self, resume_state) -> list[Any]:
        """Resolve active artifact refs from the latest runtime snapshot when available."""
        return await self._runtime_resume.artifact_refs_from_resume(resume_state)

    async def _runtime_seed_transcript_from_agent_messages(
        self,
        session_id: str,
        messages: list[Any],
    ) -> None:
        """Import legacy agent messages into runtime transcript storage once, for compatibility migration."""
        await self._runtime_resume.seed_transcript_from_agent_messages(session_id, messages)

    def _runtime_message_to_transcript_entry(
        self,
        *,
        session_id: str,
        turn_index: int,
        message: Any,
    ) -> TranscriptEntry | None:
        """Convert an agent-core message into a runtime transcript entry."""
        return self._runtime_resume.message_to_transcript_entry(
            session_id=session_id,
            turn_index=turn_index,
            message=message,
        )

    def _runtime_system_prompt(self, request: TurnRequest, config: AgentCoreConfig) -> str:
        """Build the runtime system prompt without creating an Agent instance."""
        return self._runtime_bootstrap.runtime_system_prompt(request, config)

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
        llm_call_id = f"runtime-{uuid4().hex[:8]}"
        system_prompt, llm_messages = await self._runtime_prepare_model_input(
            state,
            system_prompt=state.metadata["runtime_system_prompt"],
            available_tools=available_tools,
            llm_call_id=llm_call_id,
        )
        synthesis_instruction = state.metadata.get("runtime_synthesis_instruction")
        if isinstance(synthesis_instruction, str) and synthesis_instruction.strip():
            system_prompt = (
                f"{system_prompt}\n\n[Runtime Synthesis Directive]\n{synthesis_instruction}".strip()
            )
        llm_call_id = self._runtime_log_llm_call_start(
            state,
            call_id=llm_call_id,
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

        if (
            assistant_message.stop_reason in {"error", "aborted"}
            and not assistant_message.get_text().strip()
        ):
            assistant_message.content = [
                TextContent(
                    text=self._runtime_best_effort_output(
                        state,
                        error_message=assistant_message.error_message
                        or assistant_message.stop_reason,
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
        llm_call_id: str | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Build runtime model input directly from transcript, summaries, artifacts, and compression."""
        return await self._runtime_model_input.prepare_model_input(
            state,
            system_prompt=system_prompt,
            available_tools=available_tools,
            llm_call_id=llm_call_id,
            context_builder=self._runtime_context_builder,
            compression_pipeline=self._runtime_compression_pipeline,
            messages_to_llm_payload=self._runtime_messages_to_llm_payload,
            resolve_compression_profile=self._runtime_resolve_compression_profile,
            resolve_model_context_window=self._runtime_resolve_model_context_window,
            runtime_compression_metadata_payload=self._runtime_compression_metadata_payload,
            runtime_model_budget_payload=self._runtime_model_budget_payload,
            record_compression_events=self._runtime_record_compression_events,
            log_entry=self._runtime_log_entry,
            log_prompt_snapshot=self._runtime_log_prompt_snapshot,
        )

    def _runtime_log_prompt_snapshot(
        self,
        state,
        *,
        call_id: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        available_tools: list[Any],
    ) -> None:
        self._runtime_telemetry.runtime_log_prompt_snapshot(
            state,
            call_id=call_id,
            system_prompt=system_prompt,
            messages=messages,
            available_tools=available_tools,
        )

    def _runtime_messages_to_llm_payload(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Normalize mixed runtime message lists into raw LLM payload dicts."""
        return self._runtime_model_input.messages_to_llm_payload(messages)

    def _runtime_resolve_compression_profile(self, request: TurnRequest):
        return self._runtime_model_input.resolve_compression_profile(request)

    def _runtime_apply_model_aware_budget(self, request: TurnRequest) -> None:
        self._runtime_model_input.apply_model_aware_budget(request)

    def _runtime_resolve_base_budget_profile(self, request: TurnRequest) -> TurnBudgetProfile:
        return self._runtime_model_input.resolve_base_budget_profile(request)

    def _runtime_resolve_model_context_window(
        self,
        request: TurnRequest,
        *,
        state_budget_profile: TurnBudgetProfile | None,
        compression_profile,
        fallback_window: int,
    ) -> int:
        return self._runtime_model_input.resolve_model_context_window(
            request,
            state_budget_profile=state_budget_profile,
            compression_profile=compression_profile,
            fallback_window=fallback_window,
        )

    def _runtime_resolve_model_config(self, request: TurnRequest):
        return self._runtime_model_input.resolve_model_config(request)

    def _serialize_compression_verifier_result(self, value: object) -> dict[str, Any] | None:
        return self._runtime_model_input.serialize_compression_verifier_result(value)

    def _runtime_compression_metadata_payload(self, result) -> dict[str, Any]:
        return self._runtime_model_input.runtime_compression_metadata_payload(result)

    def _runtime_model_budget_payload(self, state) -> dict[str, Any] | None:
        return self._runtime_model_input.runtime_model_budget_payload(state)

    async def _runtime_record_compression_events(
        self,
        state,
        *,
        tokens_before: int,
        result,
    ) -> None:
        """Persist runtime compression telemetry for this turn."""
        await self._runtime_persistence.record_compression_events(
            state,
            tokens_before=tokens_before,
            result=result,
            runtime_compression_metadata_payload=self._runtime_compression_metadata_payload,
            runtime_model_budget_payload=self._runtime_model_budget_payload,
            log_entry=self._runtime_log_entry,
        )

    async def _runtime_record_assistant_observation(
        self, state, assistant_message: AssistantMessage
    ) -> None:
        """Persist runtime transcript entries for assistant text and tool-call planning."""
        await self._runtime_persistence.record_assistant_observation(state, assistant_message)

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
        return await self._runtime_persistence.maybe_archive_tool_output(
            state,
            tool_name=tool_name,
            output_text=output_text,
            details=details,
        )

    async def _runtime_record_tool_side_effects(
        self, state, result_message: ToolResultMessage
    ) -> None:
        """Record lightweight stateful side effects after one tool result."""
        await self._runtime_persistence.record_tool_side_effects(state, result_message)

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
        return self._runtime_telemetry.runtime_request_context(request)

    def _runtime_trace_id(self, request: TurnRequest) -> str:
        """Resolve the active trace id for runtime telemetry."""
        return self._runtime_telemetry.runtime_trace_id(request)

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
        self._runtime_telemetry.runtime_log_request(
            request,
            event=event,
            message=message,
            level=level,
            category=category,
            data=data,
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
        self._runtime_telemetry.runtime_log_entry(
            state,
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
        call_id: str | None = None,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
    ) -> str:
        """Create one runtime LLM call entry in AgentLogger and return the call id."""
        return self._runtime_telemetry.runtime_log_llm_call_start(
            state,
            call_id=call_id,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
        )

    def _runtime_log_llm_call_end(
        self,
        state,
        *,
        call_id: str,
        assistant_message: AssistantMessage,
        duration_ms: float,
    ) -> None:
        """Close one runtime LLM call entry in AgentLogger."""
        self._runtime_telemetry.runtime_log_llm_call_end(
            state,
            call_id=call_id,
            assistant_message=assistant_message,
            duration_ms=duration_ms,
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
        self._runtime_telemetry.runtime_log_tool_call_start(
            state,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
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
        self._runtime_telemetry.runtime_log_tool_call_end(
            state,
            tool_call_id=tool_call_id,
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

    async def _persist_runtime_assistant_message(
        self, request: TurnRequest, result: TurnResult
    ) -> str | None:
        """Persist the final assistant answer into the legacy session store for UI history."""
        return await self._runtime_persistence.persist_runtime_assistant_message(
            request,
            result,
            message_persistence_metadata=self._message_persistence_metadata,
        )

    async def run_runtime_turn(
        self,
        request: TurnRequest,
        *,
        controller=None,
    ) -> TurnResult:
        """Execute a prepared runtime turn through the bounded runtime controller."""
        runtime_controller = controller or self.runtime_turn_controller
        self._runtime_apply_model_aware_budget(request)
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
            result.metadata["runtime_assistant_msg_id"] = await self._persist_runtime_assistant_message(
                request, result
            )
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

    def _resolve_runtime_agent_info(self, request: TurnRequest) -> AgentInfo:
        """Resolve AgentInfo for runtime execution using request metadata when available."""
        return self._runtime_bootstrap.resolve_runtime_agent_info(request)

    def _normalize_runtime_timeout_ms(self, value: object) -> int | None:
        """Normalize per-request wall-time timeout metadata for runtime debug execution."""
        return self._runtime_bootstrap.normalize_runtime_timeout_ms(value)

    def _normalize_runtime_max_tokens(self, value: object) -> int | None:
        """Normalize optional runtime max_tokens override for debug execution."""
        return self._runtime_bootstrap.normalize_runtime_max_tokens(value)

    def _normalize_runtime_temperature(self, value: object) -> float | None:
        """Normalize optional runtime temperature override for debug execution."""
        return self._runtime_bootstrap.normalize_runtime_temperature(value)

    def _build_runtime_agent_config(
        self,
        request: TurnRequest,
        agent_info: AgentInfo,
    ) -> AgentCoreConfig | None:
        """Build an optional runtime-specific agent config for debug execution."""
        return self._runtime_bootstrap.build_runtime_agent_config(
            request,
            agent_info,
            create_config=self.create_config,
        )

    def _render_runtime_announcements(self, request: TurnRequest) -> str:
        """Render queued child-session announcements into one prompt block."""
        return self._runtime_bootstrap.render_runtime_announcements(request)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _resolve_agent_workspace(self, agent_info: AgentInfo | None) -> str | None:
        """解析 Agent 对应的 workspace 路径。"""
        return self._legacy_stream_bridge.resolve_agent_workspace(agent_info)

    def _create_context_adapter(
        self,
        llm_router,
        agent_info: AgentInfo | None = None,
        workspace_path: str | None = None,
    ):
        """创建 ContextPort adapter（上下文压缩）。"""
        _ = agent_info
        return self._legacy_stream_bridge.create_context_adapter(
            llm_router,
            workspace_path=workspace_path,
        )

    def _create_tool_middleware_adapter(
        self,
        *,
        turn_profile,
        tool_policies: dict[str, Any],
    ):
        """创建工具中间件适配器（可选）。"""
        return self._legacy_stream_bridge.create_tool_middleware_adapter(
            turn_profile=turn_profile,
            tool_policies=tool_policies,
        )

    def _message_persistence_metadata(
        self,
        metadata: dict[str, Any] | None,
        *,
        role: str,
    ) -> dict[str, Any]:
        """Extract stable metadata that should survive in session history."""
        return self._legacy_stream_bridge.message_persistence_metadata(metadata, role=role)

    async def _persist_user_message(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """持久化用户消息（在发送到 LLM 之前）。"""
        return await self._legacy_stream_bridge.persist_user_message(
            session_id,
            content,
            metadata=metadata,
        )

    def _inject_skill_prompt(
        self,
        agent: Agent,
        content: str,
        *,
        agent_id: str | None = None,
    ) -> None:
        """匹配技能并注入 prompt 到 Agent 的 system_prompt。"""
        self._legacy_stream_bridge.inject_skill_prompt(agent, content, agent_id=agent_id)

    def _restore_system_prompt(self, agent: Agent) -> None:
        """恢复 Agent 的原始 system prompt。"""
        self._legacy_stream_bridge.restore_system_prompt(agent)

    def _convert_agent_event(
        self,
        event,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent | None:
        """将 AgentEvent 转换为 GatewayEvent。"""
        return self._legacy_stream_bridge.convert_agent_event(
            event,
            agent_id=agent_id,
            agent_name=agent_name,
        )

    async def _persist_assistant_messages(
        self,
        session_id: str,
        event: Any,
        user_msg_id: str | None = None,
    ) -> None:
        """持久化 assistant 消息到会话。"""
        await self._legacy_stream_bridge.persist_assistant_messages(
            session_id,
            event,
            user_msg_id,
        )

    async def _persist_partial_response(
        self,
        session_id: str,
        assistant_content: list[str],
        error_message: str,
    ) -> None:
        """即使出错也尝试保存部分响应。"""
        await self._legacy_stream_bridge.persist_partial_response(
            session_id,
            assistant_content,
            error_message,
        )
