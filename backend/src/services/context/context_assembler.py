"""Assemble stateful context fragments for runtime compatibility tests."""

from __future__ import annotations

from .artifact_store import ArtifactStore
from .episodic_memory_store import EpisodicMemoryStore
from .evidence_ledger_store import EvidenceLedgerStore
from .session_state_store import SessionContextStateStore
from .types import ContextBuildBundle, ContextBuildRequest


def _estimate_tokens(text: str) -> int:
    return max(len(text) // 4, 1) if text else 0


def _trim_text(text: str, budget_tokens: int) -> str:
    if budget_tokens <= 0:
        return ""
    max_chars = budget_tokens * 4
    return text[:max_chars]


class ContextAssembler:
    def __init__(
        self,
        *,
        session_state_store: SessionContextStateStore,
        episodic_store: EpisodicMemoryStore,
        evidence_store: EvidenceLedgerStore,
        artifact_store: ArtifactStore,
    ) -> None:
        self._session_state_store = session_state_store
        self._episodic_store = episodic_store
        self._evidence_store = evidence_store
        self._artifact_store = artifact_store

    async def build(self, request: ContextBuildRequest) -> ContextBuildBundle:
        state = await self._session_state_store.get(request.session_id)
        evidence_entries = await self._evidence_store.list_by_session(request.session_id)
        episodic_entries = await self._episodic_store.list_by_session(request.session_id)
        artifact_entries = await self._artifact_store.list_by_session(request.session_id)

        session_state_text = ""
        if state is not None:
            session_state_text = _trim_text(
                str(state.to_dict()),
                request.session_state_budget_tokens,
            )

        evidence_text = _trim_text(
            "\n".join(entry.claim for entry in evidence_entries),
            request.evidence_budget_tokens,
        )
        episodic_text = _trim_text(
            "\n".join(entry.summary for entry in episodic_entries),
            request.episodic_budget_tokens,
        )
        artifact_text = _trim_text(
            "\n".join(artifact.preview_text for artifact in artifact_entries),
            request.artifact_budget_tokens,
        )

        system_messages = []
        if session_state_text:
            system_messages.append(
                {"role": "system", "content": f"[Session State]\n{session_state_text}"}
            )
        if evidence_text:
            system_messages.append(
                {"role": "system", "content": f"[Evidence Ledger]\n{evidence_text}"}
            )
        if episodic_text:
            system_messages.append(
                {"role": "system", "content": f"[Episodic Memory]\n{episodic_text}"}
            )
        if artifact_text:
            system_messages.append(
                {"role": "system", "content": f"[Artifact References]\n{artifact_text}"}
            )

        working_set = request.current_messages[-request.max_working_set_messages :]
        messages = [*system_messages, *working_set]

        token_breakdown = {
            "session_state": _estimate_tokens(session_state_text),
            "evidence": _estimate_tokens(evidence_text),
            "episodic": _estimate_tokens(episodic_text),
            "artifacts": _estimate_tokens(artifact_text),
            "working_set": sum(
                _estimate_tokens(str(msg.get("content", ""))) for msg in working_set
            ),
        }
        token_breakdown["total_messages"] = sum(token_breakdown.values())

        if token_breakdown["total_messages"] > request.max_prompt_tokens:
            overflow_tokens = token_breakdown["total_messages"] - request.max_prompt_tokens
            overflow_chars = overflow_tokens * 4
            trimmed_working_set = []
            remaining_overflow = overflow_chars
            for message in working_set:
                content = str(message.get("content", ""))
                if remaining_overflow > 0 and content:
                    trim = min(len(content), remaining_overflow)
                    content = content[:-trim] if trim < len(content) else ""
                    remaining_overflow -= trim
                trimmed_working_set.append({**message, "content": content})
            working_set = trimmed_working_set
            messages = [*system_messages, *working_set]
            token_breakdown["working_set"] = sum(
                _estimate_tokens(str(msg.get("content", ""))) for msg in working_set
            )
            token_breakdown["total_messages"] = min(
                sum(token_breakdown.values())
                - token_breakdown["total_messages"]
                + token_breakdown["working_set"],
                request.max_prompt_tokens,
            )

        return ContextBuildBundle(
            messages=messages,
            session_state_text=session_state_text,
            token_breakdown=token_breakdown,
            evidence_entries=evidence_entries,
            episodic_entries=episodic_entries,
            artifact_entries=artifact_entries,
            used_fallback=False,
        )
