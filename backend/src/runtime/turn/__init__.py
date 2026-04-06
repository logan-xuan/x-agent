"""Turn-level runtime components."""

from __future__ import annotations

from .finish_reason import FinishReason, is_budget_stop_reason, is_finish_reason

__all__ = [
    "DefaultAssessmentEngine",
    "DefaultTurnController",
    "DefaultToolGovernor",
    "DefaultBudgetManager",
    "FailureCluster",
    "FinishReason",
    "ToolCallSignature",
    "TurnState",
    "is_budget_stop_reason",
    "is_finish_reason",
]


def __getattr__(name: str):
    """Lazy exports keep package imports stable without introducing import cycles."""
    if name == "DefaultBudgetManager":
        from .budget import DefaultBudgetManager

        return DefaultBudgetManager
    if name == "DefaultAssessmentEngine":
        from .assessment import DefaultAssessmentEngine

        return DefaultAssessmentEngine
    if name == "DefaultToolGovernor":
        from .tool_governor import DefaultToolGovernor

        return DefaultToolGovernor
    if name == "DefaultTurnController":
        from .controller import DefaultTurnController

        return DefaultTurnController
    if name in {"FailureCluster", "ToolCallSignature", "TurnState"}:
        from .state import FailureCluster, ToolCallSignature, TurnState

        return {
            "FailureCluster": FailureCluster,
            "ToolCallSignature": ToolCallSignature,
            "TurnState": TurnState,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
