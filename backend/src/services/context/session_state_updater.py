"""Incremental updater for structured session state."""

from __future__ import annotations

import re
from typing import Any

from .session_state_store import (
    SessionContextStateStore,
    get_session_context_state_store,
)


class SessionStateUpdater:
    """Derive a compact structured state from recent conversation events."""

    def __init__(self, store: SessionContextStateStore | None = None) -> None:
        self._store = store or get_session_context_state_store()

    async def update_after_turn(
        self,
        *,
        session_id: str,
        agent_id: str,
        mode: str,
        new_messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]] | None = None,
        delegate_results: list[dict[str, Any]] | None = None,
    ) -> None:
        """Update state using the latest turn data."""
        existing = await self._store.get(session_id)
        state = existing.to_dict() if existing else _empty_state()
        metadata = dict(state.get("metadata") or {})

        latest_user = _latest_message(new_messages, "user")
        latest_assistant = _latest_message(new_messages, "assistant")

        if latest_user:
            user_text = _normalize_text(latest_user.get("content"))
            if user_text:
                is_progress_query = _is_progress_query(user_text)
                current_goal = dict(state.get("current_goal") or {})
                previous_primary_goal = current_goal.get("primary_goal")
                current_goal["agent_id"] = agent_id
                current_goal["latest_user_request"] = user_text
                current_goal["is_progress_query"] = is_progress_query
                if not is_progress_query or not current_goal.get("primary_goal"):
                    current_goal["primary_goal"] = user_text
                if (
                    not is_progress_query
                    and previous_primary_goal
                    and previous_primary_goal != current_goal.get("primary_goal")
                ):
                    _reset_tool_usage_metadata(metadata)
                state["current_goal"] = current_goal

                if not is_progress_query:
                    for question in _extract_open_questions(user_text):
                        state["open_questions"] = _append_limited_unique(
                            state["open_questions"],
                            question,
                            limit=10,
                        )
                    for constraint in _extract_constraints(user_text):
                        state["constraints"] = _append_limited_unique(
                            state["constraints"],
                            constraint,
                            limit=12,
                        )
                    for preference in _extract_user_preferences(user_text):
                        state["user_preferences"] = _append_limited_unique(
                            state["user_preferences"],
                            preference,
                            limit=12,
                        )

        if latest_assistant:
            assistant_text = _normalize_text(latest_assistant.get("content"))
            if assistant_text:
                for decision in _extract_decisions(assistant_text):
                    state["decisions"] = _append_limited_unique(
                        state["decisions"],
                        decision,
                        limit=10,
                    )
                for task in _extract_active_subtasks_from_assistant(assistant_text):
                    state["active_subtasks"] = _append_limited_unique(
                        state["active_subtasks"],
                        task,
                        limit=12,
                    )

        tool_names_this_turn: list[str] = []
        for tool_result in tool_results or []:
            tool_name = str(tool_result.get("tool_name") or tool_result.get("name") or "")
            status = "error" if tool_result.get("error") else "completed"
            details = dict(tool_result.get("details") or {})
            if tool_name:
                tool_names_this_turn.append(tool_name)
                _record_tool_usage(metadata, tool_name, status=status, details=details)
            state["active_subtasks"] = _append_limited_unique(
                state["active_subtasks"],
                {"kind": "tool", "name": tool_name, "status": status},
                limit=12,
            )

            artifact_ref = tool_result.get("artifact_ref") or details.get("artifact_ref")
            if artifact_ref:
                state["artifact_refs"] = _append_limited_unique(
                    state["artifact_refs"],
                    artifact_ref,
                    limit=12,
                )

            error_text = _normalize_text(tool_result.get("error"))
            if error_text:
                state["recent_failures"] = _append_limited_unique(
                    state["recent_failures"],
                    {"kind": "tool", "name": tool_name, "error": error_text},
                    limit=10,
                )

        for delegate_result in delegate_results or []:
            agent = str(delegate_result.get("agent_id") or delegate_result.get("target_agent_id") or "")
            status = str(delegate_result.get("status") or ("error" if delegate_result.get("error") else "completed"))
            state["delegate_status"] = _append_limited_unique(
                state["delegate_status"],
                {"agent_id": agent, "status": status},
                limit=12,
            )

            error_text = _normalize_text(delegate_result.get("error"))
            if error_text:
                state["recent_failures"] = _append_limited_unique(
                    state["recent_failures"],
                    {"kind": "delegate", "agent_id": agent, "error": error_text},
                    limit=10,
                )

        metadata["research_only_turns"] = _update_research_only_turns(
            metadata=metadata,
            tool_names=tool_names_this_turn,
        )
        metadata["repeated_call_signatures"] = _build_repeated_call_signatures(metadata)
        metadata["research_coverage"] = _infer_research_coverage(
            state=state,
            metadata=metadata,
        )
        metadata["last_write_status"] = _infer_last_write_status(metadata)
        metadata["suggested_next_step"] = _infer_suggested_next_step(
            state=state,
            metadata=metadata,
        )
        metadata["state_source"] = "session_state_updater"
        metadata["agent_id"] = agent_id
        state["metadata"] = metadata

        summary_text = _build_summary_text(state)
        token_estimate = max(1, len(summary_text) // 4) if summary_text else 0

        await self._store.upsert(
            session_id,
            mode=mode,
            summary_text=summary_text,
            token_estimate=token_estimate,
            current_goal=state["current_goal"],
            active_subtasks=state["active_subtasks"],
            decisions=state["decisions"],
            constraints=state["constraints"],
            open_questions=state["open_questions"],
            artifact_refs=state["artifact_refs"],
            delegate_status=state["delegate_status"],
            recent_failures=state["recent_failures"],
            user_preferences=state["user_preferences"],
            metadata=metadata,
        )


def get_session_state_updater() -> SessionStateUpdater:
    return SessionStateUpdater()


def _empty_state() -> dict[str, Any]:
    return {
        "current_goal": {},
        "active_subtasks": [],
        "decisions": [],
        "constraints": [],
        "open_questions": [],
        "artifact_refs": [],
        "delegate_status": [],
        "recent_failures": [],
        "user_preferences": [],
        "metadata": {},
    }


def _latest_message(messages: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") == role:
            return message
    return None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _append_limited(items: list[Any], value: Any, *, limit: int) -> list[Any]:
    if value in items:
        return items
    return (items + [value])[-limit:]


def _append_limited_unique(items: list[Any], value: Any, *, limit: int) -> list[Any]:
    normalized_value = _normalize_for_compare(value)
    filtered = [
        item
        for item in items
        if _normalize_for_compare(item) != normalized_value
    ]
    filtered.append(value)
    return filtered[-limit:]


def _normalize_for_compare(value: Any) -> str:
    if isinstance(value, dict):
        return "|".join(f"{k}={_normalize_for_compare(v)}" for k, v in sorted(value.items()))
    if isinstance(value, list):
        return "|".join(_normalize_for_compare(v) for v in value)
    return _normalize_text(value).lower()


def _extract_open_questions(text: str) -> list[str]:
    questions: list[str] = []
    for part in re.split(r"[。\n]+", text):
        candidate = part.strip()
        if not candidate:
            continue
        if "？" in candidate or "?" in candidate:
            questions.append(candidate)
    return questions


def _extract_constraints(text: str) -> list[str]:
    constraints: list[str] = []
    for part in re.split(r"[。\n]+", text):
        candidate = part.strip()
        if not candidate:
            continue
        if any(keyword in candidate for keyword in ("不要", "必须", "只能", "不要再", "禁止", "务必")):
            constraints.append(candidate)
    return constraints


def _extract_user_preferences(text: str) -> list[str]:
    preferences: list[str] = []
    for part in re.split(r"[。\n]+", text):
        candidate = part.strip()
        if not candidate:
            continue
        if any(keyword in candidate for keyword in ("喜欢", "偏好", "希望", "更倾向", "习惯")):
            preferences.append(candidate)
    return preferences


def _is_progress_query(text: str) -> bool:
    lowered = text.lower()
    keywords = (
        "在处理吗",
        "还没",
        "好了吗",
        "进展",
        "还在",
        "处理完了吗",
        "完成了吗",
        "做完了吗",
        "finished",
        "progress",
        "status",
    )
    return any(keyword in lowered for keyword in keywords)


def _extract_decisions(text: str) -> list[str]:
    decisions: list[str] = []
    for part in re.split(r"[。\n]+", text):
        candidate = part.strip()
        if not candidate:
            continue
        if any(
            keyword in candidate
            for keyword in ("我会", "先", "采用", "决定", "方案", "接下来", "优先")
        ):
            decisions.append(candidate)
    if not decisions and text:
        decisions.append(text)
    return decisions[-5:]


def _extract_active_subtasks_from_assistant(text: str) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for part in re.split(r"[。\n]+", text):
        candidate = part.strip()
        if not candidate:
            continue
        if any(keyword in candidate for keyword in ("先", "然后", "接下来", "分", "步骤", "方向")):
            tasks.append({"kind": "assistant_plan", "name": candidate, "status": "planned"})
    return tasks[-5:]


def _build_summary_text(state: dict[str, Any]) -> str:
    lines: list[str] = []

    current_goal = state.get("current_goal") or {}
    primary_goal = current_goal.get("primary_goal") or current_goal.get("latest_user_request")
    if primary_goal:
        lines.append(f"[Current Goal] {primary_goal}")

    if state.get("active_subtasks"):
        lines.append("[Active Subtasks]")
        for item in state["active_subtasks"][-5:]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('kind', 'task')}:{item.get('name', '')} ({item.get('status', '')})")
            else:
                lines.append(f"- {item}")

    tool_usage_lines = _render_tool_usage(state.get("metadata") or {})
    if tool_usage_lines:
        lines.append("[Tool Usage]")
        lines.extend(tool_usage_lines)

    state_judgement_lines = _render_state_judgement(state, state.get("metadata") or {})
    if state_judgement_lines:
        lines.append("[State Judgement]")
        lines.extend(state_judgement_lines)

    if state.get("open_questions"):
        lines.append("[Open Questions]")
        for item in state["open_questions"][-5:]:
            lines.append(f"- {item}")

    if state.get("recent_failures"):
        lines.append("[Recent Failures]")
        for item in state["recent_failures"][-3:]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('kind', 'failure')}: {item.get('error', '')}")
            else:
                lines.append(f"- {item}")

    if state.get("artifact_refs"):
        lines.append("[Artifacts]")
        for item in state["artifact_refs"][-5:]:
            lines.append(f"- {item}")

    if state.get("decisions"):
        lines.append("[Recent Decisions]")
        for item in state["decisions"][-3:]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def _reset_tool_usage_metadata(metadata: dict[str, Any]) -> None:
    metadata.pop("tool_usage_counts", None)
    metadata.pop("recent_tool_calls", None)
    metadata.pop("research_only_turns", None)


def _record_tool_usage(
    metadata: dict[str, Any],
    tool_name: str,
    *,
    status: str,
    details: dict[str, Any],
) -> None:
    counts = dict(metadata.get("tool_usage_counts") or {})
    counts[tool_name] = int(counts.get(tool_name, 0)) + 1
    metadata["tool_usage_counts"] = counts

    recent_calls = list(metadata.get("recent_tool_calls") or [])
    record: dict[str, Any] = {
        "name": tool_name,
        "status": status,
    }

    target = _extract_tool_target(details)
    if target:
        record["target"] = target

    duration_ms = details.get("duration_ms")
    if isinstance(duration_ms, (int, float)):
        record["duration_ms"] = int(duration_ms)

    recent_calls.append(record)
    metadata["recent_tool_calls"] = recent_calls[-8:]


def _update_research_only_turns(
    *,
    metadata: dict[str, Any],
    tool_names: list[str],
) -> int:
    if not tool_names:
        return int(metadata.get("research_only_turns") or 0)

    research_tools = {"web_search", "fetch_web_content", "read_file", "list_dir", "search_files"}
    writing_tools = {"write_file", "append_file", "edit_file"}

    if any(name in writing_tools for name in tool_names):
        return 0

    if all(name in research_tools for name in tool_names):
        return int(metadata.get("research_only_turns") or 0) + 1

    return 0


def _extract_tool_target(details: dict[str, Any]) -> str:
    for key in ("file_path", "path", "url", "pattern", "query"):
        value = _normalize_text(details.get(key))
        if value:
            return _shorten_tool_target(value)
    return ""


def _shorten_tool_target(value: str, *, limit: int = 72) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit-3]}..."


def _render_tool_usage(metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    counts = metadata.get("tool_usage_counts") or {}
    if counts:
        sorted_counts = sorted(
            counts.items(),
            key=lambda item: (-int(item[1]), item[0]),
        )
        summary = ", ".join(f"{name} x{count}" for name, count in sorted_counts[:6])
        if summary:
            lines.append(f"- counts: {summary}")

    research_only_turns = metadata.get("research_only_turns")
    if research_only_turns:
        lines.append(f"- consecutive_research_only_turns: {research_only_turns}")

    recent_calls = metadata.get("recent_tool_calls") or []
    for item in recent_calls[-5:]:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "tool")
        status = item.get("status", "")
        target = item.get("target", "")
        duration_ms = item.get("duration_ms")
        suffix_parts: list[str] = []
        if target:
            suffix_parts.append(target)
        if duration_ms:
            suffix_parts.append(f"{duration_ms}ms")
        suffix = f" -> {' | '.join(suffix_parts)}" if suffix_parts else ""
        lines.append(f"- recent: {name} ({status}){suffix}")

    repeated_signatures = metadata.get("repeated_call_signatures") or []
    for item in repeated_signatures[:5]:
        lines.append(f"- repeated: {item}")

    return lines


def _build_repeated_call_signatures(metadata: dict[str, Any]) -> list[str]:
    recent_calls = metadata.get("recent_tool_calls") or []
    signature_counts: dict[str, int] = {}
    for item in recent_calls:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        target = _normalize_text(item.get("target"))
        if not name:
            continue
        signature = f"{name}:{target}" if target else name
        signature_counts[signature] = signature_counts.get(signature, 0) + 1

    repeated = [
        f"{signature} x{count}"
        for signature, count in sorted(
            signature_counts.items(),
            key=lambda kv: (-kv[1], kv[0]),
        )
        if count >= 2
    ]
    return repeated[:5]


def _infer_research_coverage(
    *,
    state: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, str]:
    goal_text = _normalize_text((state.get("current_goal") or {}).get("primary_goal"))
    evidence_text = " ".join(str(item) for item in (state.get("decisions") or []))
    counts = metadata.get("tool_usage_counts") or {}

    combined = f"{goal_text}\n{evidence_text}".lower()
    coverage: dict[str, str] = {}

    coverage["market"] = "covered" if any(word in combined for word in ("市场", "规模", "增长", "赛道")) else "unknown"
    coverage["business_model"] = "covered" if any(word in combined for word in ("商业模式", "盈利", "变现", "收费")) else "unknown"
    coverage["cases"] = "covered" if any(word in combined for word in ("案例", "成功案例", "里程碑", "融资")) else "unknown"
    coverage["technology"] = "covered" if any(word in combined for word in ("技术", "大模型", "agent", "多模态")) else "unknown"
    coverage["risk"] = "covered" if any(word in combined for word in ("风险", "挑战", "合规", "伦理")) else "unknown"

    if int(counts.get("fetch_web_content", 0)) > 0:
        for key, value in list(coverage.items()):
            if value == "unknown":
                coverage[key] = "partial"

    return coverage


def _infer_last_write_status(metadata: dict[str, Any]) -> str:
    recent_calls = metadata.get("recent_tool_calls") or []
    for item in reversed(recent_calls):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name in {"write_file", "append_file", "edit_file"}:
            target = _normalize_text(item.get("target"))
            status = _normalize_text(item.get("status")) or "unknown"
            if target:
                return f"{name} ({status}) -> {target}"
            return f"{name} ({status})"
    return "no file write observed yet"


def _infer_suggested_next_step(
    *,
    state: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    counts = metadata.get("tool_usage_counts") or {}
    research_only_turns = int(metadata.get("research_only_turns") or 0)
    last_write_status = _infer_last_write_status(metadata)
    coverage = metadata.get("research_coverage") or {}

    covered_count = sum(1 for value in coverage.values() if value in {"covered", "partial"})
    has_heavy_research = int(counts.get("web_search", 0)) + int(counts.get("read_file", 0)) >= 6
    writing_started = last_write_status != "no file write observed yet"

    if not writing_started and has_heavy_research and research_only_turns >= 2 and covered_count >= 3:
        return "materials appear sufficient; start writing skeleton and sections"
    if writing_started:
        return "continue drafting sections and refine the artifact"
    return "continue gathering only the missing evidence for uncovered sections"


def _render_state_judgement(state: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    coverage = metadata.get("research_coverage") or {}
    if coverage:
        coverage_summary = ", ".join(f"{key}={value}" for key, value in coverage.items())
        lines.append(f"- research_coverage: {coverage_summary}")

    last_write_status = _normalize_text(metadata.get("last_write_status"))
    if last_write_status:
        lines.append(f"- last_write_status: {last_write_status}")

    suggested_next_step = _normalize_text(metadata.get("suggested_next_step"))
    if suggested_next_step:
        lines.append(f"- suggested_next_step: {suggested_next_step}")

    return lines
