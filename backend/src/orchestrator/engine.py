"""Compatibility orchestrator shim for legacy skill integration tests."""

from __future__ import annotations

from pathlib import Path

try:
    from ..services.skill_registry import get_skill_registry
except ImportError:  # 顶层 orchestrator.* 导入兼容
    from services.skill_registry import get_skill_registry  # type: ignore


class Orchestrator:
    """Minimal compatibility orchestrator exposing a skill registry."""

    def __init__(self, *, workspace_path: str) -> None:
        self.workspace_path = Path(workspace_path)
        self._skill_registry = get_skill_registry(self.workspace_path)
