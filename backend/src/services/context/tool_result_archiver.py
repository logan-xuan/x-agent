"""Archive tool results into evidence/artifact stores for runtime compatibility tests."""

from __future__ import annotations

from typing import Any

from .artifact_store import ArtifactStore
from .evidence_ledger_store import EvidenceLedgerStore


class ToolResultArchiver:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        evidence_store: EvidenceLedgerStore,
    ) -> None:
        self._artifact_store = artifact_store
        self._evidence_store = evidence_store

    async def archive(
        self,
        *,
        session_id: str,
        tool_name: str,
        result_text: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "web_search":
            results = details.get("structured_results", [])
            query = details.get("query", tool_name)
            count = 0
            for result in results:
                await self._evidence_store.create_entry(
                    session_id=session_id,
                    topic=query,
                    claim=result.get("snippet", result_text),
                    source_url=result.get("url"),
                    source_title=result.get("title"),
                )
                count += 1
            return {"evidence_count": count}

        if tool_name == "fetch_web_content":
            artifact = await self._artifact_store.create_artifact(
                session_id=session_id,
                kind="web_content",
                title=details.get("title", "Fetched content"),
                content_path=str(details.get("metadata", {}).get("markdown_path", "")),
                preview_text=result_text,
                metadata={"url": details.get("url")},
            )
            return {"artifact_ref": f"artifact:{artifact.artifact_id}"}

        artifact = await self._artifact_store.create_artifact(
            session_id=session_id,
            kind="tool_result",
            title=tool_name,
            content_path="",
            preview_text=result_text,
            metadata=details,
        )
        return {"artifact_ref": f"artifact:{artifact.artifact_id}"}
