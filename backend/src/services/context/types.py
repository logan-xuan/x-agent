"""Shared types for lightweight runtime context stateful helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBuildRequest:
    session_id: str
    agent_id: str
    mode: str
    current_messages: list[dict[str, Any]]
    max_prompt_tokens: int
    reserved_output_tokens: int = 0
    session_state_budget_tokens: int = 80
    evidence_budget_tokens: int = 80
    episodic_budget_tokens: int = 80
    artifact_budget_tokens: int = 40
    max_working_set_messages: int = 5


@dataclass
class ContextBuildBundle:
    messages: list[dict[str, Any]]
    session_state_text: str = ""
    token_breakdown: dict[str, int] = field(default_factory=dict)
    evidence_entries: list[Any] = field(default_factory=list)
    episodic_entries: list[Any] = field(default_factory=list)
    artifact_entries: list[Any] = field(default_factory=list)
    used_fallback: bool = False
