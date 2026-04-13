"""Heuristic session-state updater for runtime compatibility tests."""

from __future__ import annotations

import re
from typing import Any

from .session_state_store import SessionContextStateStore


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


class SessionStateUpdater:
    def __init__(self, state_store: SessionContextStateStore) -> None:
        self._store = state_store

    async def update_after_turn(
        self,
        *,
        session_id: str,
        agent_id: str,
        mode: str,
        new_messages: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        delegate_results: list[dict[str, Any]],
    ):
        state = await self._store.get(session_id)
        existing = state.to_dict() if state is not None else {}
        user_messages = [
            str(msg.get("content", "")) for msg in new_messages if msg.get("role") == "user"
        ]
        assistant_messages = [
            str(msg.get("content", "")) for msg in new_messages if msg.get("role") == "assistant"
        ]
        latest_user_request = (
            user_messages[-1]
            if user_messages
            else existing.get("current_goal", {}).get("latest_user_request", "")
        )
        progress_query = any(
            token in latest_user_request for token in ["你在处理吗", "进展", "还在", "处理吗"]
        )
        primary_goal = existing.get("current_goal", {}).get("primary_goal", "")
        if user_messages and (not primary_goal or not progress_query):
            primary_goal = user_messages[0]

        open_questions = list(existing.get("open_questions", []))
        constraints = list(existing.get("constraints", []))
        user_preferences = list(existing.get("user_preferences", []))
        decisions = list(existing.get("decisions", []))
        active_subtasks = list(existing.get("active_subtasks", []))

        for text in user_messages:
            for sentence in re.split(r"[。！？!?]", text):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if "吗" in sentence or "?" in text or "？" in text or "怎么" in sentence:
                    open_questions.append(sentence)
                if "不要" in sentence or "必须" in sentence:
                    constraints.append(sentence)
                if "我喜欢" in sentence or "偏向" in sentence:
                    user_preferences.append(sentence)
                if "商业模式" in sentence:
                    decisions.append(sentence)

        for text in assistant_messages:
            if "商业模式" in text:
                decisions.append(text)
            if "先" in text or "然后" in text:
                active_subtasks.append({"kind": "assistant_plan", "content": text})

        for tool in tool_results:
            tool_name = tool.get("tool_name")
            if tool_name:
                active_subtasks.append(
                    {
                        "kind": "tool",
                        "name": tool_name,
                        "artifact_ref": tool.get("artifact_ref"),
                    }
                )

        for delegate in delegate_results:
            if delegate.get("agent_id"):
                active_subtasks.append(
                    {
                        "kind": "delegate",
                        "agent_id": delegate["agent_id"],
                        "status": delegate.get("status"),
                    }
                )

        normalized_subtasks: list[dict[str, Any]] = []
        seen_subtasks: set[str] = set()
        for item in active_subtasks:
            key = str(item)
            if key not in seen_subtasks:
                seen_subtasks.add(key)
                normalized_subtasks.append(item)

        return await self._store.upsert(
            session_id,
            mode=mode,
            summary_text=existing.get("summary_text", ""),
            token_estimate=existing.get("token_estimate", 0),
            current_goal={
                "primary_goal": primary_goal,
                "latest_user_request": latest_user_request,
                "is_progress_query": progress_query,
                "agent_id": agent_id,
            },
            open_questions=_dedupe_text(open_questions),
            constraints=_dedupe_text(constraints),
            user_preferences=_dedupe_text(user_preferences),
            decisions=_dedupe_text(decisions),
            active_subtasks=normalized_subtasks,
            metadata=existing.get("metadata", {}),
        )
