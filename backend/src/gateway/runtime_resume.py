"""Runtime resume and transcript compatibility helpers for AgentBridge."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..agent_core.types import (
    AssistantMessage,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    UserMessage,
)
from ..runtime.repositories import TranscriptEntry

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class RuntimeResumeBridge:
    """Handle runtime resume-state conversion and legacy transcript import."""

    def __init__(self, runtime_session_orchestrator) -> None:
        self._runtime_session_orchestrator = runtime_session_orchestrator

    async def load_legacy_history_messages(self, session_id: str) -> list[Any]:
        """Fallback loader for sessions not yet replayed into runtime stores."""
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

    def messages_from_resume(self, resume_state) -> list[Any]:
        """Convert persisted runtime transcript entries back into agent-core messages."""
        if resume_state is None:
            return []

        messages: list[Any] = []
        for entry in resume_state.recent_entries:
            message = self.entry_to_message(entry)
            if message is not None:
                messages.append(message)
        return messages

    def entry_to_message(self, entry: TranscriptEntry) -> Any | None:
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

    def summary_chain_messages(self, resume_state) -> list[dict[str, str]]:
        """Convert persisted summary chain into compact system summary messages."""
        if resume_state is None:
            return []

        messages: list[dict[str, str]] = []
        for summary in self.relevant_summaries(resume_state):
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

    def recent_failures_from_resume(self, resume_state) -> list[str]:
        """Recover persisted failure summaries for compression invariants and assessment context."""
        if resume_state is None:
            return []

        failures: list[str] = []
        for summary in self.relevant_summaries(resume_state):
            failures.extend(summary.recent_failures)
        return failures[-6:]

    def relevant_summaries(self, resume_state) -> list[Any]:
        """Select only the latest effective compression snapshot plus child results."""
        if resume_state is None:
            return []

        compression_types = {"microcompact", "collapse", "autocompact", "memory_flush"}
        latest_compression = None
        child_results: list[Any] = []

        for summary in resume_state.summary_chain:
            if summary.summary_type in compression_types:
                if latest_compression is None or summary.created_at >= latest_compression.created_at:
                    latest_compression = summary
            elif summary.summary_type == "child_result":
                child_results.append(summary)

        selected = [*child_results]
        if latest_compression is not None:
            selected.append(latest_compression)
        return sorted(selected, key=lambda summary: getattr(summary, "created_at", 0.0))

    async def artifact_refs_from_resume(self, resume_state) -> list[Any]:
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
                stored = await self._runtime_session_orchestrator.artifact_repository.get(
                    artifact_id
                )
            except Exception as exc:
                logger.warning(
                    "Failed to resolve runtime artifact reference",
                    extra={
                        "session_id": resume_state.session.session_id,
                        "artifact_id": artifact_id,
                        "error": str(exc),
                    },
                )
                continue
            if stored is None:
                continue
            artifact_ref, _content = stored
            refs.append(artifact_ref)
        return refs

    async def seed_transcript_from_agent_messages(
        self,
        session_id: str,
        messages: list[Any],
    ) -> None:
        """Import legacy agent messages into runtime transcript storage once."""
        for index, message in enumerate(messages):
            entry = self.message_to_transcript_entry(
                session_id=session_id,
                turn_index=index,
                message=message,
            )
            if entry is None:
                continue
            await self._runtime_session_orchestrator.append_transcript_entry(entry)

    def message_to_transcript_entry(
        self,
        *,
        session_id: str,
        turn_index: int,
        message: Any,
    ) -> TranscriptEntry | None:
        """Convert an agent-core message into a runtime transcript entry."""
        if isinstance(message, UserMessage):
            text = "".join(
                content.text for content in message.content if isinstance(content, TextContent)
            )
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
            text = "".join(
                content.text for content in message.content if isinstance(content, TextContent)
            )
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
