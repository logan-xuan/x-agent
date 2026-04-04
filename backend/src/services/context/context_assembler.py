"""Assembler for stateful prompt context fragments."""

from __future__ import annotations

from typing import Any

from ...services.compression.token_counter import TokenCounter
from .artifact_store import ArtifactStore, get_artifact_store
from .episodic_memory_store import EpisodicMemoryStore, get_episodic_memory_store
from .evidence_ledger_store import EvidenceLedgerStore, get_evidence_ledger_store
from .session_state_store import SessionContextStateStore, get_session_context_state_store
from .types import ContextBuildRequest, PreparedContextBundle


class ContextAssembler:
    """Build a compact prompt bundle from state, memory, and current messages."""

    def __init__(
        self,
        *,
        session_state_store: SessionContextStateStore | None = None,
        episodic_store: EpisodicMemoryStore | None = None,
        evidence_store: EvidenceLedgerStore | None = None,
        artifact_store: ArtifactStore | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._session_state_store = session_state_store or get_session_context_state_store()
        self._episodic_store = episodic_store or get_episodic_memory_store()
        self._evidence_store = evidence_store or get_evidence_ledger_store()
        self._artifact_store = artifact_store or get_artifact_store()
        self._token_counter = token_counter or TokenCounter()

    async def build(self, request: ContextBuildRequest) -> PreparedContextBundle:
        """Assemble synthetic system messages plus exact working-set messages."""
        state = await self._session_state_store.get(request.session_id)
        episodic = await self._episodic_store.list_by_session(request.session_id, limit=5)
        evidence = await self._evidence_store.list_by_session(request.session_id, limit=5)
        artifacts = await self._artifact_store.list_by_session(request.session_id, limit=5)

        session_state_text = _truncate_text(
            state.summary_text if state else "",
            request.session_state_budget_tokens,
            token_counter=self._token_counter,
        )
        evidence_entries = [item.to_dict() for item in evidence]
        episodic_entries = [item.to_dict() for item in episodic]
        artifact_entries = [item.to_dict() for item in artifacts]

        evidence_text, evidence_entries = _select_entries_by_budget(
            evidence_entries,
            request.evidence_budget_tokens,
            self._token_counter,
            _render_evidence_entry,
        )
        episodic_text, episodic_entries = _select_entries_by_budget(
            episodic_entries,
            request.episodic_budget_tokens,
            self._token_counter,
            _render_episodic_entry,
        )
        artifact_text, artifact_entries = _select_entries_by_budget(
            artifact_entries,
            request.artifact_budget_tokens,
            self._token_counter,
            _render_artifact_entry,
        )

        working_set = list(request.current_messages[-request.max_working_set_messages :])

        messages: list[dict[str, Any]] = []
        if session_state_text:
            messages.append({"role": "system", "content": f"[Session State]\n{session_state_text}"})
        if evidence_text:
            messages.append({"role": "system", "content": f"[Evidence Ledger]\n{evidence_text}"})
        if episodic_text:
            messages.append({"role": "system", "content": f"[Episodic Memory]\n{episodic_text}"})
        if artifact_text:
            messages.append({"role": "system", "content": f"[Artifact References]\n{artifact_text}"})

        fixed_tokens = (
            self._token_counter.count_text(request.system_prompt)
            + self._token_counter.count_messages(messages)
            + self._token_counter.count_tool_definitions(request.tools)
        )
        available_for_working_set = max(
            0,
            request.max_prompt_tokens - request.reserved_output_tokens - fixed_tokens,
        )
        working_set = _trim_working_set(
            working_set,
            available_for_working_set,
            self._token_counter,
        )
        messages.extend(working_set)

        token_breakdown = {
            "system_prompt": self._token_counter.count_text(request.system_prompt),
            "session_state": self._token_counter.count_text(session_state_text),
            "evidence": self._token_counter.count_text(evidence_text),
            "episodic": self._token_counter.count_text(episodic_text),
            "artifacts": self._token_counter.count_text(artifact_text),
            "working_set": self._token_counter.count_messages(working_set),
            "total_messages": self._token_counter.count_messages(messages),
        }

        return PreparedContextBundle(
            messages=messages,
            session_state_text=session_state_text,
            evidence_entries=evidence_entries,
            episodic_entries=episodic_entries,
            artifact_entries=artifact_entries,
            token_breakdown=token_breakdown,
            used_fallback=available_for_working_set == 0,
        )


def get_context_assembler() -> ContextAssembler:
    return ContextAssembler()


def _render_evidence_entry(entry: dict[str, Any]) -> str:
    source = entry.get("source_title") or entry.get("source_url") or "unknown source"
    return f"- [{entry.get('topic', 'topic')}] {entry.get('claim', '')} (source: {source})"


def _render_episodic_entry(entry: dict[str, Any]) -> str:
    return f"- [{entry.get('event_type', 'event')}] {entry.get('title', '')}: {entry.get('summary', '')}"


def _render_artifact_entry(entry: dict[str, Any]) -> str:
    return f"- [{entry.get('kind', 'artifact')}] {entry.get('title', '')} -> {entry.get('content_path', '')}"


def _truncate_text(text: str, max_tokens: int, *, token_counter: TokenCounter) -> str:
    if not text or max_tokens <= 0:
        return ""
    if token_counter.count_text(text) <= max_tokens:
        return text

    suffix = "\n...[truncated]"
    low = 0
    high = len(text)
    best = ""

    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid].rstrip() + suffix
        tokens = token_counter.count_text(candidate)
        if tokens <= max_tokens:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1

    if best:
        return best

    # 极端场景：连 suffix 都超预算，保底返回尽量短的前缀
    return text[: max(1, max_tokens)]


def _select_entries_by_budget(
    entries: list[dict[str, Any]],
    budget_tokens: int,
    token_counter: TokenCounter,
    render_entry,
) -> tuple[str, list[dict[str, Any]]]:
    if budget_tokens <= 0 or not entries:
        return "", []

    selected: list[dict[str, Any]] = []
    rendered_lines: list[str] = []
    used_tokens = 0
    for entry in entries:
        line = render_entry(entry)
        line_tokens = token_counter.count_text(line)
        if selected and used_tokens + line_tokens > budget_tokens:
            break
        if not selected and line_tokens > budget_tokens:
            truncated = _truncate_text(line, budget_tokens, token_counter=token_counter)
            return truncated, [entry]

        selected.append(entry)
        rendered_lines.append(line)
        used_tokens += line_tokens

    return "\n".join(rendered_lines), selected


def _trim_working_set(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    token_counter: TokenCounter,
) -> list[dict[str, Any]]:
    if budget_tokens <= 0 or not messages:
        return []

    selected: list[dict[str, Any]] = []
    used_tokens = 0
    for message in reversed(messages):
        message_tokens = token_counter.count_messages([message])
        if selected and used_tokens + message_tokens > budget_tokens:
            break
        if not selected and message_tokens > budget_tokens:
            truncated = dict(message)
            content = str(truncated.get("content") or "")
            truncated["content"] = _truncate_text(content, max(1, budget_tokens - 4), token_counter=token_counter)
            return [truncated]

        selected.append(message)
        used_tokens += message_tokens

    selected.reverse()
    return selected
