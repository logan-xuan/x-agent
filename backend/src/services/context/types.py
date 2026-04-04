"""Shared request/response types for stateful context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextBuildRequest:
    """Input for assembling a stateful prompt context."""

    session_id: str
    agent_id: str
    mode: str
    current_messages: list[dict[str, Any]]
    max_prompt_tokens: int
    reserved_output_tokens: int = 0
    tools: list[dict[str, Any]] | None = None
    session_state_budget_tokens: int = 1200
    evidence_budget_tokens: int = 2000
    episodic_budget_tokens: int = 2000
    artifact_budget_tokens: int = 1200
    max_working_set_messages: int = 8


@dataclass
class PreparedContextBundle:
    """Assembled prompt fragments and token breakdown."""

    messages: list[dict[str, Any]]
    session_state_text: str = ""
    evidence_entries: list[dict[str, Any]] = field(default_factory=list)
    episodic_entries: list[dict[str, Any]] = field(default_factory=list)
    artifact_entries: list[dict[str, Any]] = field(default_factory=list)
    token_breakdown: dict[str, int] = field(default_factory=dict)
    used_fallback: bool = False
