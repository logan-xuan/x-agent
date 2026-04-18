"""Runtime bootstrap helpers for AgentBridge."""

from __future__ import annotations

import time
from uuid import uuid4

from ..agent_core.adapters.llm_adapter import XAgentLLMAdapter
from ..agent_core.config import AgentCoreConfig
from ..agent_core.types import LogCategory, UserMessage
from ..conversation.dao.models import Agent as AgentORM
from ..runtime.repositories import TranscriptEntry
from ..runtime.types import TurnRequest
from .agent_info import AgentInfo
from .bridge_dependencies import get_agent_logger, get_llm_router, match_and_load_skill_prompt


class RuntimeBootstrapBridge:
    """Handle runtime bootstrap setup and request-scoped config helpers."""

    def __init__(
        self,
        *,
        runtime_session_orchestrator,
        runtime_resume,
        runtime_telemetry,
        runtime_fast_system_prompt: str,
        runtime_fast_max_tokens: int,
    ) -> None:
        self._runtime_session_orchestrator = runtime_session_orchestrator
        self._runtime_resume = runtime_resume
        self._runtime_telemetry = runtime_telemetry
        self._runtime_fast_system_prompt = runtime_fast_system_prompt
        self._runtime_fast_max_tokens = runtime_fast_max_tokens

    def resolve_runtime_agent_info(self, request: TurnRequest) -> AgentInfo:
        """Resolve AgentInfo for runtime execution using request metadata when available."""
        agent_id = request.metadata.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            agent = AgentORM.from_config(agent_id)
            if agent is not None:
                return AgentInfo.from_orm(agent)
        return AgentInfo.default()

    def normalize_runtime_timeout_ms(self, value: object) -> int | None:
        """Normalize per-request wall-time timeout metadata for runtime debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        return None

    def normalize_runtime_max_tokens(self, value: object) -> int | None:
        """Normalize optional runtime max_tokens override for debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
        return None

    def normalize_runtime_temperature(self, value: object) -> float | None:
        """Normalize optional runtime temperature override for debug execution."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)) and 0.0 <= float(value) <= 2.0:
            return float(value)
        return None

    def build_runtime_agent_config(
        self,
        request: TurnRequest,
        agent_info: AgentInfo,
        *,
        create_config,
    ) -> AgentCoreConfig | None:
        """Build an optional runtime-specific agent config for debug execution."""
        disable_tools = bool(request.metadata.get("runtime_disable_tools"))
        disable_skills = bool(request.metadata.get("runtime_disable_skills"))
        if not disable_tools and not disable_skills:
            return None

        if disable_tools:
            llm_router = get_llm_router()
            force_non_streaming = bool(request.metadata.get("runtime_force_non_streaming"))
            runtime_max_tokens = self.normalize_runtime_max_tokens(
                request.metadata.get("runtime_max_tokens")
            )
            runtime_temperature = self.normalize_runtime_temperature(
                request.metadata.get("runtime_temperature")
            )
            return AgentCoreConfig(
                llm=XAgentLLMAdapter(llm_router, force_non_streaming=force_non_streaming),
                tools=None,
                logger=get_agent_logger(),
                context=None,
                system_prompt=self._runtime_fast_system_prompt,
                system_prompt_port=None,
                enable_context_compression=False,
                enable_experience_learning=False,
                temperature=runtime_temperature if runtime_temperature is not None else 0.0,
                thinking_level="off",
                max_tokens=runtime_max_tokens or self._runtime_fast_max_tokens,
                tool_middleware_pipeline=None,
            )

        return create_config(
            agent_info,
            disable_tools=False,
            use_legacy_context=False,
        )

    def render_runtime_announcements(self, request: TurnRequest) -> str:
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

    def runtime_system_prompt(self, request: TurnRequest, config: AgentCoreConfig) -> str:
        """Build the runtime system prompt without creating an Agent instance."""
        system_prompt = config.system_prompt

        if not bool(request.metadata.get("runtime_disable_skills")):
            requested_agent_id = request.metadata.get("agent_id")
            skill_prompt, _ = match_and_load_skill_prompt(
                request.user_input,
                agent_id=requested_agent_id if isinstance(requested_agent_id, str) else None,
            )
            if skill_prompt:
                system_prompt = f"{system_prompt}\n{skill_prompt}".strip()

        announcement_block = self.render_runtime_announcements(request)
        if announcement_block:
            system_prompt = f"{system_prompt}\n\n{announcement_block}".strip()

        return system_prompt

    async def ensure_runtime_turn_bootstrap(
        self,
        state,
        *,
        create_config,
        persist_user_message,
        message_persistence_metadata,
        messages_from_resume,
        summary_chain_messages,
        recent_failures_from_resume,
        load_legacy_history_messages,
        seed_transcript_from_agent_messages,
        artifact_refs_from_resume,
    ) -> None:
        """Load runtime dependencies and session history once per turn request."""
        if state.metadata.get("runtime_bootstrapped"):
            return

        request = state.request
        agent_info = self.resolve_runtime_agent_info(request)
        runtime_config = self.build_runtime_agent_config(
            request,
            agent_info,
            create_config=create_config,
        ) or create_config(
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
            resume_state = await self._runtime_session_orchestrator.resume_session(
                request.session.session_key,
                recent_entries_limit=48,
            )
        state.metadata["runtime_resume_state"] = resume_state
        state.metadata["runtime_summary_chain_messages"] = summary_chain_messages(resume_state)
        state.metadata["runtime_recent_failures"] = recent_failures_from_resume(resume_state)

        history_messages = messages_from_resume(resume_state)
        if history_messages:
            state.active_messages.extend(history_messages)
        elif not bool(request.metadata.get("runtime_skip_history_load")):
            fallback_messages = await load_legacy_history_messages(request.session.session_id)
            state.active_messages.extend(fallback_messages)
            if fallback_messages:
                await seed_transcript_from_agent_messages(
                    request.session.session_id,
                    fallback_messages,
                )
                state.metadata["runtime_history_source"] = "legacy_memory_imported"
            else:
                state.metadata["runtime_history_source"] = "empty"
        else:
            state.metadata["runtime_history_source"] = "empty"

        state.active_artifact_refs = await artifact_refs_from_resume(resume_state)
        if resume_state is not None and resume_state.latest_snapshot is not None:
            state.session_tool_usage = dict(resume_state.latest_snapshot.tool_usage_json or {})

        if bool(request.metadata.get("persist_user_message", True)) and request.user_input.strip():
            state.metadata["runtime_user_msg_id"] = await persist_user_message(
                request.session.session_id,
                request.user_input,
                metadata=message_persistence_metadata(request.metadata, role="user"),
            )

        current_user_message = UserMessage.from_text(request.user_input)
        state.active_messages.append(current_user_message)
        if request.user_input.strip():
            await self._runtime_session_orchestrator.append_transcript_entry(
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
        state.metadata["runtime_system_prompt"] = self.runtime_system_prompt(request, runtime_config)
        self._runtime_telemetry.runtime_log_entry(
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
