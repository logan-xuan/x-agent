"""Runtime telemetry helpers for AgentBridge."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..agent_core.types import AssistantMessage, LLMCallLog, LogCategory, LogLevel, ToolCallLog
from .bridge_dependencies import get_agent_logger

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class RuntimeTelemetryRecorder:
    """Encapsulate runtime logging and trace-aware telemetry helpers."""

    def __init__(self, runtime_model_budget_payload) -> None:
        self._runtime_model_budget_payload = runtime_model_budget_payload

    def runtime_request_context(self, request) -> Any:
        try:
            from ..conversation.context import get_current_context

            return get_current_context()
        except Exception:
            return None

    def runtime_trace_id(self, request) -> str:
        """Resolve the active trace id for runtime telemetry."""
        current_context = self.runtime_request_context(request)
        if current_context is not None and getattr(current_context, "trace_id", ""):
            return str(current_context.trace_id)
        trace_id = request.metadata.get("trace_id")
        return str(trace_id) if isinstance(trace_id, str) else ""

    def runtime_log_request(
        self,
        request,
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
        trace_id = self.runtime_trace_id(request)
        if not trace_id:
            return
        get_agent_logger().create_log_entry(
            trace_id=trace_id,
            event=event,
            message=message,
            level=level,
            category=category,
            data=data or {},
            duration_ms=duration_ms,
            error=error,
        )

    def runtime_log_entry(
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
        self.runtime_log_request(
            state.request,
            event=event,
            message=message,
            level=level,
            category=category,
            data=data,
            duration_ms=duration_ms,
            error=error,
        )

    def runtime_log_llm_call_start(
        self,
        state,
        *,
        call_id: str | None = None,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[Any],
    ) -> str:
        """Create one runtime LLM call entry in AgentLogger and return the call id."""
        from ..agent_core.context_transform import estimate_tokens

        trace_id = self.runtime_trace_id(state.request)
        call_id = call_id or f"runtime-{uuid4().hex[:8]}"
        state.metadata["runtime_last_llm_call_id"] = call_id
        if not trace_id:
            return call_id

        get_agent_logger().log_llm_call_start(
            LLMCallLog(
                call_id=call_id,
                trace_id=trace_id,
                model=str(
                    state.metadata.get("model") or state.metadata["runtime_config"].model or ""
                ),
                provider=str(
                    state.metadata.get("provider")
                    or state.metadata["runtime_config"].provider
                    or ""
                ),
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

    def runtime_log_llm_call_end(
        self,
        state,
        *,
        call_id: str,
        assistant_message: AssistantMessage,
        duration_ms: float,
    ) -> None:
        """Close one runtime LLM call entry in AgentLogger."""
        from ..agent_core.context_transform import content_to_dict

        if not self.runtime_trace_id(state.request):
            return
        get_agent_logger().log_llm_call_end(
            call_id=call_id,
            response={
                "content": [content_to_dict(item) for item in assistant_message.content],
                "stop_reason": assistant_message.stop_reason,
            },
            usage=dict(assistant_message.usage or {}),
            duration_ms=duration_ms,
            error=assistant_message.error_message,
        )

    def runtime_log_tool_call_start(
        self,
        state,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Create one runtime tool-call entry in AgentLogger."""
        trace_id = self.runtime_trace_id(state.request)
        if not trace_id:
            return
        get_agent_logger().log_tool_call_start(
            ToolCallLog(
                call_id=tool_call_id,
                trace_id=trace_id,
                llm_call_id=str(state.metadata.get("runtime_last_llm_call_id", "")),
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=dict(arguments),
            )
        )

    def runtime_log_tool_call_end(
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
        if not self.runtime_trace_id(state.request):
            return
        get_agent_logger().log_tool_call_end(
            call_id=tool_call_id,
            result=result,
            duration_ms=duration_ms,
            is_error=is_error,
            error=error,
        )

    def runtime_log_prompt_snapshot(
        self,
        state,
        *,
        call_id: str,
        system_prompt: str,
        messages: list[dict[str, Any]],
        available_tools: list[Any],
    ) -> None:
        try:
            from ..utils.logger import get_llm_prompt_logger

            prompt_logger = get_llm_prompt_logger()
            prompt_logger.log_interaction(
                session_id=state.request.session.session_id,
                trace_id=self.runtime_trace_id(state.request) or None,
                provider=str(
                    state.metadata.get("provider") or state.metadata["runtime_config"].provider or ""
                ),
                model=str(
                    state.metadata.get("model") or state.metadata["runtime_config"].model or ""
                ),
                messages=[
                    {"role": "system", "content": system_prompt},
                    *[dict(message) for message in messages],
                ],
                response="",
                latency_ms=0,
                success=True,
                tools=[tool.to_llm_tool() for tool in available_tools] if available_tools else None,
                call_id=call_id,
                source="runtime_prepared",
                request_metadata={
                    "compression_operations": list(state.metadata.get("compression_operations", [])),
                    "budget_state": dict(state.metadata.get("budget_state", {}) or {}),
                    "runtime_model_budget": dict(self._runtime_model_budget_payload(state) or {}),
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to log runtime prompt snapshot",
                extra={
                    "session_id": state.request.session.session_id,
                    "call_id": call_id,
                    "error": str(exc),
                },
            )
