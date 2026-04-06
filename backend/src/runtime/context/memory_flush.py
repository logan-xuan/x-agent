"""Memory flush hooks used by the runtime compression pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryFlushRequest:
    """Request envelope for pre-compaction memory flush."""

    session_key: str
    messages: list[Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryFlushResult:
    """Result of a memory flush attempt."""

    flushed: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class NoopMemoryFlusher:
    """Default placeholder flusher for the initial runtime skeleton."""

    async def flush(self, request: MemoryFlushRequest) -> MemoryFlushResult:
        _ = request
        return MemoryFlushResult(flushed=False, notes=["noop_memory_flush"])


__all__ = ["MemoryFlushRequest", "MemoryFlushResult", "NoopMemoryFlusher"]
