"""Runtime context builder with layered prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..types import ArtifactRef, BudgetSnapshot, PromptMode, SessionDescriptor, TaskFrame
from .history_view import DefaultHistoryViewBuilder


@dataclass
class ContextBuildRequest:
    """Input for runtime context building."""

    session: SessionDescriptor
    task_frame: TaskFrame
    raw_messages: list[Any]
    prompt_mode: PromptMode = "full"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBuildResult:
    """Output for runtime context building."""

    system_prompt: str
    active_messages: list[Any]
    active_artifacts: list[ArtifactRef]
    estimated_input_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DefaultContextBuilder:
    """Compose runtime prompt layers and derive active history."""

    history_builder: DefaultHistoryViewBuilder = field(default_factory=DefaultHistoryViewBuilder)

    async def build(self, request: ContextBuildRequest) -> ContextBuildResult:
        """Build a layered model input view from raw session state."""
        summary_chain = list(request.metadata.get("summary_chain", []))
        history_view = self.history_builder.build(
            request.raw_messages,
            summary_chain=summary_chain,
        )
        artifacts = list(request.metadata.get("artifact_refs", []))
        budget = request.metadata.get("budget")
        system_prompt = self._build_system_prompt(request, artifacts=artifacts, budget=budget)
        estimated_tokens = self._estimate_tokens(system_prompt, history_view.active_messages)
        return ContextBuildResult(
            system_prompt=system_prompt,
            active_messages=history_view.active_messages,
            active_artifacts=artifacts,
            estimated_input_tokens=estimated_tokens,
            metadata={
                "prompt_mode": request.prompt_mode,
                "history_view": history_view.metadata,
            },
        )

    def _build_system_prompt(
        self,
        request: ContextBuildRequest,
        *,
        artifacts: list[ArtifactRef],
        budget: BudgetSnapshot | None,
    ) -> str:
        if request.prompt_mode == "none":
            return ""

        stable_prefix = request.metadata.get("stable_prefix", "").strip()
        semi_stable_sections = [
            section.strip()
            for section in request.metadata.get("semi_stable_sections", [])
            if str(section).strip()
        ]
        dynamic_lines = self._dynamic_lines(request.task_frame, artifacts=artifacts, budget=budget)

        if request.prompt_mode == "minimal":
            sections = [stable_prefix, "\n".join(dynamic_lines)]
        else:
            sections = [stable_prefix, "\n\n".join(semi_stable_sections), "\n".join(dynamic_lines)]

        return "\n\n".join(section for section in sections if section)

    def _dynamic_lines(
        self,
        task_frame: TaskFrame,
        *,
        artifacts: list[ArtifactRef],
        budget: BudgetSnapshot | None,
    ) -> list[str]:
        lines = [f"Objective: {task_frame.objective or '(empty)'}"]
        if task_frame.deliverable:
            lines.append(f"Deliverable: {task_frame.deliverable}")
        if task_frame.constraints:
            lines.append("Constraints: " + "; ".join(task_frame.constraints))
        if task_frame.unresolved:
            lines.append("Unresolved: " + "; ".join(task_frame.unresolved))
        if task_frame.working_plan:
            lines.append("Working plan: " + "; ".join(task_frame.working_plan))
        if artifacts:
            lines.append("Artifacts: " + ", ".join(artifact.id for artifact in artifacts))
        if budget is not None:
            lines.append(
                "Budget: "
                f"profile={budget.profile_name}, turns={budget.turns_taken}, "
                f"tokens={budget.total_tokens}, tool_calls={budget.total_tool_calls}"
            )
        return lines

    def _estimate_tokens(self, system_prompt: str, messages: list[Any]) -> int:
        total_chars = len(system_prompt)
        for message in messages:
            if isinstance(message, dict):
                total_chars += len(str(message.get("content", "")))
            else:
                total_chars += len(str(getattr(message, "content", "")))
        return max(total_chars // 4, 0)


__all__ = ["ContextBuildRequest", "ContextBuildResult", "DefaultContextBuilder"]
