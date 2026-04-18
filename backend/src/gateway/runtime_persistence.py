"""Runtime persistence and observation helpers for AgentBridge."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from ..agent_core.types import AssistantMessage, LogCategory, TextContent, ToolResultMessage
from ..runtime.repositories import (
    CompressionEventRecord,
    StateSnapshotRecord,
    SummaryRecord,
    TranscriptEntry,
)
from ..runtime.types import ArtifactRef, TurnRequest, TurnResult
from .bridge_dependencies import get_session_manager
from .media_background_tasks import MediaBackgroundTask, get_media_background_task_manager

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class RuntimePersistenceBridge:
    """Persist runtime replay state, transcript observations, and tool side effects."""

    def __init__(self, *, runtime_session_orchestrator) -> None:
        self._runtime_session_orchestrator = runtime_session_orchestrator

    async def persist_runtime_turn_result(self, request: TurnRequest, result: TurnResult) -> None:
        """Persist minimal runtime replay state for resume/reconnect and child-session flows."""
        try:
            await self._runtime_session_orchestrator.record_state_snapshot(
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
                    metadata={
                        "kind": result.kind,
                        **{
                            key: value
                            for key, value in result.metadata.items()
                            if key
                            in {
                                "compression_operations",
                                "budget_state",
                                "verifier_result",
                                "rollback",
                                "rollback_applied",
                                "rollback_reason",
                                "runtime_context_summary",
                                "runtime_model_budget",
                            }
                        },
                    },
                    created_at=time.time(),
                )
            )
            if result.output_text:
                await self._runtime_session_orchestrator.record_summary(
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

    async def record_compression_events(
        self,
        state,
        *,
        tokens_before: int,
        result,
        runtime_compression_metadata_payload,
        runtime_model_budget_payload,
        log_entry,
    ) -> None:
        """Persist runtime compression telemetry for this turn."""
        if not getattr(result, "operations", None):
            return

        total_tokens_after = int(getattr(result, "estimated_input_tokens", tokens_before) or 0)
        total_freed_tokens = max(tokens_before - total_tokens_after, 0)
        compression_metadata = runtime_compression_metadata_payload(result)
        runtime_model_budget = runtime_model_budget_payload(state)
        if runtime_model_budget is not None:
            compression_metadata["runtime_model_budget"] = runtime_model_budget
        stage_metrics = dict(getattr(result, "metadata", {}) or {}).get("stage_metrics", {})
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
            metric = stage_metrics.get(normalized_stage) or stage_metrics.get(stage)
            stage_tokens_before = int(
                metric.get("tokens_before", tokens_before) if isinstance(metric, dict) else tokens_before
            )
            stage_tokens_after = int(
                metric.get("tokens_after", total_tokens_after)
                if isinstance(metric, dict)
                else total_tokens_after
            )
            stage_freed_tokens = int(
                metric.get("freed_tokens", total_freed_tokens)
                if isinstance(metric, dict)
                else total_freed_tokens
            )
            stage_affected_artifacts = (
                list(metric.get("affected_artifact_ids", affected_artifacts))
                if isinstance(metric, dict)
                else affected_artifacts
            )
            try:
                await self._runtime_session_orchestrator.append_compression_event(
                    CompressionEventRecord(
                        event_id=f"compression:{uuid4().hex}",
                        session_id=state.request.session.session_id,
                        turn_index=state.turn_index,
                        stage=normalized_stage,
                        tokens_before=stage_tokens_before,
                        tokens_after=stage_tokens_after,
                        freed_tokens=stage_freed_tokens,
                        affected_artifact_ids=stage_affected_artifacts,
                        fallback_used=normalized_stage == "emergency",
                        metadata=compression_metadata,
                        created_at=time.time(),
                    )
                )
                log_entry(
                    state,
                    event=f"runtime_compression_{normalized_stage}",
                    message=f"Runtime compression stage applied: {normalized_stage}",
                    category=LogCategory.CONTEXT,
                    data={
                        "turn_index": state.turn_index,
                        "tokens_before": stage_tokens_before,
                        "tokens_after": stage_tokens_after,
                        "freed_tokens": stage_freed_tokens,
                        "affected_artifact_ids": stage_affected_artifacts,
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

    async def record_assistant_observation(self, state, assistant_message: AssistantMessage) -> None:
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
            await self._runtime_session_orchestrator.append_transcript_entry(
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

        if (
            assistant_message.stop_reason in {"error", "aborted"}
            and assistant_message.error_message
        ):
            recent_failures = state.metadata.setdefault("runtime_recent_failures", [])
            recent_failures.append(assistant_message.error_message)
            del recent_failures[:-6]

    async def maybe_archive_tool_output(
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
        await self._runtime_session_orchestrator.store_artifact(artifact, output_text)
        state.active_artifact_refs.append(artifact)
        return artifact

    async def record_tool_side_effects(self, state, result_message: ToolResultMessage) -> None:
        """Record lightweight stateful side effects after one tool result."""
        details = result_message.details
        await self._maybe_schedule_media_background_task(
            state,
            result_message=result_message,
            details=details,
        )
        try:
            from ..services.context import get_session_state_updater, get_tool_result_archiver

            archiver = get_tool_result_archiver()
            updater = get_session_state_updater()
            archived = {}
            result_text = (
                result_message.get_text()
                if hasattr(result_message, "get_text")
                else "".join(
                    content.text
                    for content in result_message.content
                    if isinstance(content, TextContent)
                )
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

    async def _maybe_schedule_media_background_task(
        self,
        state,
        *,
        result_message: ToolResultMessage,
        details: dict[str, Any],
    ) -> None:
        """Schedule notification-based monitoring for background media jobs."""
        if not details.get("is_background"):
            return
        task_kind = str(details.get("background_task_kind") or "").strip()
        if task_kind not in {"video_pipeline", "image_generation"}:
            return

        runtime_agent_info = state.metadata.get("runtime_agent_info")
        agent_id = getattr(runtime_agent_info, "agent_id", "") if runtime_agent_info else ""
        if not agent_id:
            return

        process_id = str(details.get("process_id") or "").strip()
        provider_task_id = str(details.get("modelscope_task_id") or "").strip()
        if task_kind == "video_pipeline" and not process_id:
            return
        if task_kind == "image_generation" and not provider_task_id:
            return

        get_media_background_task_manager().schedule(
            MediaBackgroundTask(
                process_id=process_id,
                session_id=state.request.session.session_id,
                agent_id=agent_id,
                command=str(details.get("command") or ""),
                working_dir=str(details.get("working_dir") or ""),
                kind=task_kind,
                title=str(details.get("background_task_title") or "后台媒体任务"),
                provider_task_id=provider_task_id,
                prompt=str(details.get("prompt") or details.get("final_prompt") or ""),
                model=str(details.get("model") or ""),
                size=str(details.get("size") or ""),
                count=int(details.get("count") or 0),
            )
        )

    async def persist_runtime_assistant_message(
        self,
        request: TurnRequest,
        result: TurnResult,
        *,
        message_persistence_metadata,
    ) -> str | None:
        """Persist the final assistant answer into the legacy session store for UI history."""
        if not result.output_text:
            return None
        try:
            session_manager = get_session_manager()
            assistant_message = await session_manager.add_message(
                session_id=request.session.session_id,
                role="assistant",
                content=result.output_text,
                metadata={
                    "model": result.metadata.get("model", ""),
                    "provider": result.metadata.get("provider", ""),
                    "stop_reason": result.finish_reason,
                    "usage": result.metadata.get("budget", {}),
                    "user_msg_id": request.metadata.get("runtime_user_msg_id"),
                    **message_persistence_metadata(result.metadata, role="assistant"),
                },
            )
            return assistant_message.id
        except Exception as exc:
            logger.warning(
                "Failed to persist runtime assistant message",
                extra={"session_id": request.session.session_id, "error": str(exc)},
            )
            return None
