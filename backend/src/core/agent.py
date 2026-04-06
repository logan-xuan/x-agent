"""Compatibility shim for legacy src.core.agent imports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Agent:
    """Minimal legacy-style agent wrapper used by old integration tests."""

    session_manager: Any
    llm_router: Any
    context_builder: Any

    def __post_init__(self) -> None:
        self._session_manager = self.session_manager
        self._llm_router = self.llm_router
        self._context_builder = self.context_builder
