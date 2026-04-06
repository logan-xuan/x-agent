"""Lane scheduler for isolated session execution queues."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..types import LaneName

AsyncTask = Callable[[], Awaitable[object]]


@dataclass
class InMemoryLaneScheduler:
    """Track per-lane depth and execute tasks under independent semaphores."""

    lane_limits: dict[LaneName, int] = field(
        default_factory=lambda: {
            "main": 1,
            "followup": 2,
            "subagent": 4,
            "cron": 2,
            "background_tool": 2,
        }
    )
    _depths: dict[LaneName, int] = field(default_factory=lambda: defaultdict(int))
    _semaphores: dict[LaneName, asyncio.Semaphore] = field(default_factory=dict)

    async def enqueue(self, lane: LaneName, fn: AsyncTask) -> object:
        """Execute a task inside the lane concurrency guard."""
        semaphore = self._semaphore(lane)
        self._depths[lane] += 1
        try:
            async with semaphore:
                return await fn()
        finally:
            self._depths[lane] = max(self._depths[lane] - 1, 0)

    def get_depth(self, lane: LaneName) -> int:
        """Return the number of currently queued/executing tasks for a lane."""
        return self._depths[lane]

    def _semaphore(self, lane: LaneName) -> asyncio.Semaphore:
        if lane not in self._semaphores:
            self._semaphores[lane] = asyncio.Semaphore(self.lane_limits.get(lane, 1))
        return self._semaphores[lane]


__all__ = ["InMemoryLaneScheduler"]
