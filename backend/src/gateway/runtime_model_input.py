"""Runtime model-input and compression preparation helpers for AgentBridge."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from ..agent_core.types import LogCategory
from ..runtime.model_budget import derive_model_aware_turn_budget_profile
from ..runtime.types import TurnBudgetProfile, TurnRequest


class RuntimeModelInputBridge:
    """Build LLM payloads, resolve runtime budget hints, and prepare compressed context."""

    def __init__(
        self,
        *,
        runtime_services,
    ) -> None:
        self._runtime_services = runtime_services

    def messages_to_llm_payload(self, messages: list[Any]) -> list[dict[str, Any]]:
        """Normalize mixed runtime message lists into raw LLM payload dicts."""
        from ..agent_core.context_transform import convert_message_to_llm

        raw_messages: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, dict):
                raw_messages.append(dict(message))
                continue
            raw_messages.append(convert_message_to_llm(message))
        return raw_messages

    def resolve_compression_profile(self, request: TurnRequest):
        profile_name = str(
            request.metadata.get("_runtime_compression_profile_name")
            or self._runtime_services.default_compression_profile
        )
        try:
            return self._runtime_services.compression_profiles.get(profile_name)
        except KeyError:
            return self._runtime_services.compression_profiles.get(
                self._runtime_services.default_compression_profile
            )

    def apply_model_aware_budget(self, request: TurnRequest) -> None:
        base_profile = self.resolve_base_budget_profile(request)
        compression_profile = self.resolve_compression_profile(request)
        model_config = self.resolve_model_config(request)
        derived_profile, hints = derive_model_aware_turn_budget_profile(
            base_profile=base_profile,
            compression_profile=compression_profile,
            model_config=model_config,
        )
        request.metadata["_runtime_budget_profile"] = derived_profile
        if hints is not None:
            request.metadata["_runtime_model_budget_hints"] = hints.to_metadata()

    def resolve_base_budget_profile(self, request: TurnRequest) -> TurnBudgetProfile:
        current = request.metadata.get("_runtime_budget_profile")
        if isinstance(current, TurnBudgetProfile):
            return current
        named_profile = self._runtime_services.turn_profiles.get(request.session.budget_profile)
        if named_profile is not None:
            return named_profile
        return self._runtime_services.turn_profiles[self._runtime_services.default_turn_profile]

    def resolve_model_context_window(
        self,
        request: TurnRequest,
        *,
        state_budget_profile: TurnBudgetProfile | None,
        compression_profile,
        fallback_window: int,
    ) -> int:
        compression_context_window_override = request.metadata.get("runtime_compression_context_window")
        if (
            isinstance(compression_context_window_override, int)
            and compression_context_window_override > 0
        ):
            return compression_context_window_override

        budget_profile = state_budget_profile or self.resolve_base_budget_profile(request)
        model_config = self.resolve_model_config(request)
        derived_profile, hints = derive_model_aware_turn_budget_profile(
            base_profile=budget_profile,
            compression_profile=compression_profile,
            model_config=model_config,
        )
        if hints is not None:
            request.metadata["_runtime_model_budget_hints"] = hints.to_metadata()
        return derived_profile.max_total_tokens or fallback_window

    def resolve_model_config(self, request: TurnRequest):
        from ..config.manager import get_config

        config = get_config()
        if not config.models:
            return None

        provider_name = str(
            request.metadata.get("provider")
            or request.metadata.get("_runtime_provider_name")
            or ""
        ).strip()
        model_id = str(
            request.metadata.get("model")
            or request.metadata.get("_runtime_model_id")
            or ""
        ).strip()

        if provider_name:
            for model in config.models:
                if model.name != provider_name:
                    continue
                if not model_id or model.model_id == model_id:
                    return model

        if model_id:
            exact = [model for model in config.models if model.model_id == model_id]
            if exact:
                primary = next((model for model in exact if model.is_primary), None)
                return primary or exact[0]

        primary = next((model for model in config.models if model.is_primary), None)
        return primary or config.models[0]

    def serialize_compression_verifier_result(self, value: object) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "ok") and hasattr(value, "reasons") and hasattr(value, "preserved_fields"):
            return {
                "ok": bool(getattr(value, "ok", False)),
                "reasons": list(getattr(value, "reasons", []) or []),
                "preserved_fields": dict(getattr(value, "preserved_fields", {}) or {}),
            }
        return None

    def runtime_compression_metadata_payload(self, result) -> dict[str, Any]:
        raw_metadata = dict(getattr(result, "metadata", {}) or {})
        operations = list(getattr(result, "operations", []) or [])
        payload: dict[str, Any] = {
            "operations": operations,
            "compression_operations": operations,
            "rollback_applied": bool(getattr(result, "rollback_applied", False)),
            "rollback_reason": getattr(result, "rollback_reason", None),
        }
        if isinstance(raw_metadata.get("budget_state"), dict):
            payload["budget_state"] = dict(raw_metadata["budget_state"])
        if isinstance(raw_metadata.get("rollback"), dict):
            payload["rollback"] = dict(raw_metadata["rollback"])

        verifier_payload = self.serialize_compression_verifier_result(
            getattr(result, "verifier_result", None)
            or raw_metadata.get("verifier_result")
            or raw_metadata.get("verification")
        )
        if verifier_payload is not None:
            payload["verifier_result"] = verifier_payload
        return payload

    def runtime_model_budget_payload(self, state) -> dict[str, Any] | None:
        runtime_model_budget = state.metadata.get("runtime_model_budget")
        if isinstance(runtime_model_budget, dict):
            return dict(runtime_model_budget)
        request_budget_hints = state.request.metadata.get("_runtime_model_budget_hints")
        if isinstance(request_budget_hints, dict):
            return dict(request_budget_hints)
        return None

    async def prepare_model_input(
        self,
        state,
        *,
        system_prompt: str,
        available_tools: list[Any],
        llm_call_id: str | None = None,
        context_builder,
        compression_pipeline,
        messages_to_llm_payload,
        resolve_compression_profile,
        resolve_model_context_window,
        runtime_compression_metadata_payload,
        runtime_model_budget_payload,
        record_compression_events,
        log_entry,
        log_prompt_snapshot,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Build runtime model input directly from transcript, summaries, artifacts, and compression."""
        from ..runtime.context import CompressionContext, ContextBuildRequest

        raw_messages = messages_to_llm_payload(state.active_messages)
        profile = resolve_compression_profile(state.request)

        build_result = await context_builder.build(
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

        model_context_window = resolve_model_context_window(
            state.request,
            state_budget_profile=state.budget.profile,
            compression_profile=profile,
            fallback_window=max(build_result.estimated_input_tokens, 1),
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
        compression_result = await compression_pipeline.run(compression_ctx)
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
            compression_result = await compression_pipeline.run_emergency(
                emergency_ctx
            )

        state.active_artifact_refs = list(compression_result.active_artifacts)
        state.metadata.update(runtime_compression_metadata_payload(compression_result))
        runtime_model_budget = runtime_model_budget_payload(state)
        if runtime_model_budget is not None:
            state.metadata["runtime_model_budget"] = dict(runtime_model_budget)
        await record_compression_events(
            state,
            tokens_before=build_result.estimated_input_tokens,
            result=compression_result,
        )
        state.metadata["runtime_context_summary"] = ", ".join(compression_result.operations)
        log_entry(
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
                **(
                    {"runtime_model_budget": dict(runtime_model_budget)}
                    if runtime_model_budget is not None
                    else {}
                ),
            },
        )
        log_prompt_snapshot(
            state,
            call_id=llm_call_id or f"runtime-{uuid4().hex[:8]}",
            system_prompt=build_result.system_prompt or system_prompt,
            messages=list(compression_result.messages),
            available_tools=available_tools,
        )
        return build_result.system_prompt or system_prompt, list(compression_result.messages)
