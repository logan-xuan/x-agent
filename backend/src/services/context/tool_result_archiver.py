"""Archive high-value tool results into stateful context stores."""

from __future__ import annotations

from typing import Any

from .artifact_store import ArtifactStore, get_artifact_store
from .evidence_ledger_store import EvidenceLedgerStore, get_evidence_ledger_store


class ToolResultArchiver:
    """Persist tool outputs that are useful for later stateful retrieval."""

    def __init__(
        self,
        artifact_store: ArtifactStore | None = None,
        evidence_store: EvidenceLedgerStore | None = None,
    ) -> None:
        self._artifact_store = artifact_store or get_artifact_store()
        self._evidence_store = evidence_store or get_evidence_ledger_store()

    async def archive(
        self,
        *,
        session_id: str,
        tool_name: str,
        result_text: str,
        details: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Archive a tool result and return enriched metadata."""
        details = dict(details or {})

        if tool_name == "fetch_web_content":
            artifact_ref = await self._archive_fetch_web_content(
                session_id=session_id,
                result_text=result_text,
                details=details,
            )
            if artifact_ref:
                details["artifact_ref"] = artifact_ref
            return details

        if tool_name == "web_search":
            evidence_count = await self._archive_web_search(
                session_id=session_id,
                result_text=result_text,
                details=details,
            )
            if evidence_count:
                details["evidence_count"] = evidence_count
            return details

        return details

    async def _archive_fetch_web_content(
        self,
        *,
        session_id: str,
        result_text: str,
        details: dict[str, Any],
    ) -> str | None:
        if details.get("batch_mode") and isinstance(details.get("results"), list):
            refs: list[str] = []
            for item in details["results"]:
                ref = await self._create_artifact_from_fetch_result(
                    session_id=session_id,
                    result=item,
                )
                if ref:
                    refs.append(ref)
            if refs:
                details["artifact_refs"] = refs
                return refs[0]
            return None

        return await self._create_artifact_from_fetch_result(
            session_id=session_id,
            result={
                "title": details.get("title", ""),
                "url": details.get("url", ""),
                "markdown_path": details.get("markdown_path") or _nested(details, "metadata", "markdown_path"),
                "body": result_text,
            },
        )

    async def _create_artifact_from_fetch_result(
        self,
        *,
        session_id: str,
        result: dict[str, Any],
    ) -> str | None:
        markdown_path = result.get("markdown_path") or _nested(result, "metadata", "markdown_path")
        if not markdown_path:
            return None

        title = str(result.get("title") or result.get("url") or "Fetched Content")
        artifact = await self._artifact_store.create_artifact(
            session_id=session_id,
            kind="web_content",
            title=title,
            content_path=str(markdown_path),
            preview_text=str(result.get("body") or "")[:500],
            metadata={
                "url": result.get("url"),
                "title": result.get("title"),
                "source_tool": "fetch_web_content",
            },
        )
        return f"artifact:{artifact.id}"

    async def _archive_web_search(
        self,
        *,
        session_id: str,
        result_text: str,
        details: dict[str, Any],
    ) -> int:
        query = str(details.get("query") or "")
        structured_results = details.get("results") or details.get("structured_results") or []

        created = 0
        for item in structured_results[:5]:
            snippet = str(item.get("snippet") or "").strip()
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip() or None
            if not snippet and not title:
                continue

            claim = f"{title} - {snippet}".strip(" -")
            await self._evidence_store.create_entry(
                session_id=session_id,
                topic=query or "web_search",
                claim=claim[:1000],
                source_url=url,
                source_title=title or None,
                source_type="web_search",
                confidence=0.6,
                metadata={
                    "source_tool": "web_search",
                    "query": query,
                },
            )
            created += 1

        if created == 0 and result_text:
            preview = result_text[:600]
            await self._evidence_store.create_entry(
                session_id=session_id,
                topic=query or "web_search",
                claim=preview,
                source_title="web_search_result_preview",
                source_type="web_search",
                confidence=0.3,
                metadata={
                    "source_tool": "web_search",
                    "query": query,
                    "fallback": True,
                },
            )
            created = 1

        return created


def get_tool_result_archiver() -> ToolResultArchiver:
    return ToolResultArchiver()


def _nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current
