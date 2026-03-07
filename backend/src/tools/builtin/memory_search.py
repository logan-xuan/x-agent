"""Tool to search long-term memory.

This tool allows the agent to proactively search its memory system
for relevant past conversations, decisions, preferences, and knowledge.
Delegates to MemoryManager.search() for hybrid (vector + text) retrieval.
"""

from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

logger = get_logger(__name__)


class MemorySearchTool(BaseTool):
    """Search long-term memory for relevant information.

    Uses hybrid search (vector similarity + text similarity) to find
    past conversations, decisions, preferences, and archived knowledge.

    Typical use cases:
    - Recall user preferences or past decisions
    - Find previously discussed topics
    - Retrieve archived knowledge before it was compressed
    - Check if a topic has been discussed before
    """

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search your long-term memory for relevant information. "
            "Use this tool when you need to recall past conversations, "
            "user preferences, previous decisions, or any previously "
            "stored knowledge. Returns results ranked by relevance. "
            "Supports filtering by content type (conversation, decision, "
            "summary, manual) and minimum relevance score."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type=ToolParameterType.STRING,
                description="Natural language search query describing what you want to recall.",
                required=True,
                min_length=1,
                max_length=500,
            ),
            ToolParameter(
                name="limit",
                type=ToolParameterType.INTEGER,
                description="Maximum number of results to return (1-20).",
                required=False,
                default=5,
                min_value=1,
                max_value=20,
            ),
            ToolParameter(
                name="content_type",
                type=ToolParameterType.STRING,
                description=(
                    "Filter by content type. Options: "
                    "'conversation' (past dialogues), "
                    "'decision' (important decisions), "
                    "'summary' (session summaries), "
                    "'manual' (manually recorded entries). "
                    "Leave empty to search all types."
                ),
                required=False,
                default=None,
                enum=["conversation", "decision", "summary", "manual"],
            ),
            ToolParameter(
                name="min_score",
                type=ToolParameterType.NUMBER,
                description="Minimum relevance score threshold (0.0-1.0). Higher values return more relevant but fewer results.",
                required=False,
                default=0.0,
                min_value=0.0,
                max_value=1.0,
            ),
        ]

    async def execute(
        self,
        query: str,
        limit: int = 5,
        content_type: str | None = None,
        min_score: float | None = None,
    ) -> ToolResult:
        """Execute memory search.

        Args:
            query: Natural language search query
            limit: Maximum number of results
            content_type: Filter by content type
            min_score: Minimum relevance score threshold (None uses config default)

        Returns:
            ToolResult with formatted search results
        """
        try:
            from src.memory.manager import get_memory_manager
            from src.memory.models import MemoryContentType

            memory_manager = get_memory_manager()

            content_type_enum = None
            if content_type:
                try:
                    content_type_enum = MemoryContentType(content_type)
                except ValueError:
                    return ToolResult.error_result(
                        f"Invalid content_type: '{content_type}'. "
                        f"Valid options: conversation, decision, summary, manual"
                    )

            search_kwargs: dict[str, Any] = {
                "query": query,
                "limit": limit,
                "content_type": content_type_enum,
            }
            if min_score is not None:
                search_kwargs["min_score"] = min_score

            results = memory_manager.search(**search_kwargs)

            if not results:
                logger.info(
                    "Memory search returned no results",
                    extra={"query": query[:50]},
                )
                return ToolResult.ok(
                    f"No relevant memories found for query: \"{query}\"",
                    result_count=0,
                )

            formatted_lines = [f"Found {len(results)} relevant memories:\n"]
            for index, result in enumerate(results, start=1):
                entry = result.entry
                score_display = f"{result.score:.2f}"
                entry_type = entry.content_type.value if hasattr(entry.content_type, "value") else str(entry.content_type)
                content_preview = entry.content[:300]
                if len(entry.content) > 300:
                    content_preview += "..."

                formatted_lines.append(
                    f"[{index}] (score: {score_display}, type: {entry_type})\n"
                    f"    {content_preview}\n"
                )

            output = "\n".join(formatted_lines)

            logger.info(
                "Memory search completed",
                extra={
                    "query": query[:50],
                    "result_count": len(results),
                    "top_score": f"{results[0].score:.2f}" if results else "N/A",
                },
            )

            return ToolResult.ok(
                output,
                result_count=len(results),
                top_score=results[0].score if results else 0.0,
            )

        except RuntimeError as exc:
            logger.warning(
                "MemoryManager not initialized",
                extra={"error": str(exc)},
            )
            return ToolResult.error_result(
                "Memory system is not initialized yet. Cannot search memories."
            )
        except Exception as exc:
            logger.error(
                "Memory search failed",
                extra={"query": query[:50], "error": str(exc)},
                exc_info=True,
            )
            return ToolResult.error_result(f"Memory search failed: {str(exc)}")
