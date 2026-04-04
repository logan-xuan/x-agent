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

        latest_user = _latest_message(new_messages, "user")
        latest_assistant = _latest_message(new_messages, "assistant")

        if latest_user:
            user_text = _normalize_text(latest_user.get("content"))
            if user_text:
                is_progress_query = _is_progress_query(user_text)
                current_goal = dict(state.get("current_goal") or {})
                current_goal["agent_id"] = agent_id
                current_goal["latest_user_request"] = user_text
                current_goal["is_progress_query"] = is_progress_query
                if not is_progress_query or not current_goal.get("primary_goal"):
                    current_goal["primary_goal"] = user_text
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

        for tool_result in tool_results or []:
            tool_name = str(tool_result.get("tool_name") or tool_result.get("name") or "")
            status = "error" if tool_result.get("error") else "completed"
            state["active_subtasks"] = _append_limited_unique(
                state["active_subtasks"],
                {"kind": "tool", "name": tool_name, "status": status},
                limit=12,
            )

            artifact_ref = tool_result.get("artifact_ref")
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
            metadata={"state_source": "session_state_updater", "agent_id": agent_id},
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
