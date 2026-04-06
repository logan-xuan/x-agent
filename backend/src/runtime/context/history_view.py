"""History view construction for runtime context building."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoryView:
    """Layered view derived from raw transcript and summary chain."""

    raw_messages: list[Any]
    summary_chain: list[Any] = field(default_factory=list)
    active_messages: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DefaultHistoryViewBuilder:
    """Build the active history view that will actually reach the model."""

    recent_message_count: int = 12
    preserve_recent_assistants: int = 2
    strip_leading_system: bool = True

    def build(
        self,
        raw_messages: list[Any],
        *,
        summary_chain: list[Any] | None = None,
    ) -> HistoryView:
        """Construct an active history view from raw transcript messages."""
        summary_chain = list(summary_chain or [])
        messages = list(raw_messages)
        if self.strip_leading_system and messages and self._role(messages[0]) == "system":
            messages.pop(0)

        start_index = max(len(messages) - self.recent_message_count, 0)
        assistant_kept = 0
        for index in range(len(messages) - 1, -1, -1):
            if self._role(messages[index]) == "assistant":
                assistant_kept += 1
            if assistant_kept >= self.preserve_recent_assistants:
                start_index = min(start_index, index)
                break

        active_messages = [*summary_chain, *messages[start_index:]]
        return HistoryView(
            raw_messages=list(raw_messages),
            summary_chain=summary_chain,
            active_messages=active_messages,
            metadata={
                "retained_from_index": start_index,
                "raw_count": len(raw_messages),
                "active_count": len(active_messages),
            },
        )

    def _role(self, message: Any) -> str:
        if isinstance(message, dict):
            return str(message.get("role", ""))
        return str(getattr(message, "role", ""))


__all__ = ["DefaultHistoryViewBuilder", "HistoryView"]
