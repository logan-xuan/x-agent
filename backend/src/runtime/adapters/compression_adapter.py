"""Bridge current compression manager concepts into the runtime package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..context.compression_pipeline import CompressionContext, CompressionProfile
from ..types import BudgetSnapshot, TaskFrame


@dataclass
class CompressionAdapter:
    """Translate legacy compression inputs into runtime compression contexts."""

    def build_context(
        self,
        *,
        session_key: str,
        messages: list[dict[str, Any]],
        estimated_input_tokens: int,
        task_frame: TaskFrame | None = None,
        budget: BudgetSnapshot | None = None,
        profile: CompressionProfile | None = None,
    ) -> CompressionContext:
        """Build a runtime compression context from current legacy data."""
        return CompressionContext(
            session_key=session_key,
            turn=0,
            task_frame=task_frame or TaskFrame(),
            profile=profile or CompressionProfile(),
            model_context_window=(budget.profile.max_total_tokens if budget else 120000),
            estimated_input_tokens=estimated_input_tokens,
            messages=[dict(message) for message in messages],
            active_artifacts=[],
            budget=budget or BudgetSnapshot(),
        )


__all__ = ["CompressionAdapter"]
