"""Deduplication helpers for Feishu inbound messages."""

from __future__ import annotations

import asyncio
from collections import deque


class ProcessedMessageTracker:
    """Track recently processed inbound Feishu message IDs."""

    def __init__(self, max_size: int = 1024) -> None:
        self._max_size = max_size
        self._message_ids: set[str] = set()
        self._order: deque[str] = deque()
        self._lock = asyncio.Lock()

    async def seen_or_add(self, message_id: str | None) -> bool:
        """Return True if message_id was already processed, otherwise record it."""
        if not message_id:
            return False

        async with self._lock:
            if message_id in self._message_ids:
                return True

            self._message_ids.add(message_id)
            self._order.append(message_id)

            while len(self._order) > self._max_size:
                expired = self._order.popleft()
                self._message_ids.discard(expired)

            return False
