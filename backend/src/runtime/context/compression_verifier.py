"""Post-check verifier for runtime compression output."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..types import ArtifactRef, TaskFrame


@dataclass
class CompressionVerifyRequest:
    """Inputs required to verify a compression candidate."""

    task_frame: TaskFrame
    original_messages: list[Any]
    compressed_messages: list[Any]
    original_artifacts: list[ArtifactRef] = field(default_factory=list)
    compressed_artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompressionPostCheck:
    """Result of compression verification."""

    ok: bool
    reasons: list[str] = field(default_factory=list)
    preserved_fields: dict[str, bool] = field(default_factory=dict)


@dataclass
class DefaultCompressionVerifier:
    """Verify invariants after compression before accepting the candidate."""

    def verify(self, request: CompressionVerifyRequest) -> CompressionPostCheck:
        reasons: list[str] = []
        preserved = {
            "objective": True,
            "unresolved": True,
            "recent_failures": True,
            "artifact_refs": True,
            "role_ordering": True,
            "state_conflicts": True,
            "compression_gain": True,
            "conclusion_fidelity": True,
        }

        if request.task_frame.objective and not self._objective_preserved(request):
            preserved["objective"] = False
            reasons.append("compressed output no longer preserves the task objective")

        if not self._objective_snapshot_consistent(request):
            preserved["objective"] = False
            reasons.append("objective_mismatch")

        if not self._objective_is_unique(request):
            preserved["objective"] = False
            reasons.append("duplicate_objective")

        original_artifact_ids = {artifact.id for artifact in request.original_artifacts}
        compressed_artifact_ids = {artifact.id for artifact in request.compressed_artifacts}
        if not original_artifact_ids.issubset(compressed_artifact_ids):
            preserved["artifact_refs"] = False
            reasons.append("compressed artifacts lost original artifact refs")

        if not self._role_ordering_ok(request.compressed_messages):
            preserved["role_ordering"] = False
            reasons.append("compressed messages violate role ordering")

        if request.task_frame.unresolved != request.metadata.get(
            "compressed_unresolved",
            request.task_frame.unresolved,
        ):
            preserved["unresolved"] = False
            reasons.append("compressed unresolved set diverged from task frame")

        if request.metadata.get("recent_failures_before", []) != request.metadata.get(
            "recent_failures_after",
            request.metadata.get("recent_failures_before", []),
        ):
            preserved["recent_failures"] = False
            reasons.append("compressed recent failures diverged from source state")

        if not self._terminal_state_conflicts_ok(request.compressed_messages):
            preserved["state_conflicts"] = False
            reasons.append("conflicting_terminal_state")

        if not self._compression_gain_ok(request):
            preserved["compression_gain"] = False
            reasons.append("compression_gain_below_threshold")

        if not self._conclusions_preserved(request):
            preserved["conclusion_fidelity"] = False
            reasons.append("key_conclusions_lost")

        if request.original_messages and not request.compressed_messages:
            reasons.append("compressed messages unexpectedly became empty")

        return CompressionPostCheck(ok=not reasons, reasons=reasons, preserved_fields=preserved)

    def _role_ordering_ok(self, messages: list[Any]) -> bool:
        seen_assistant = False
        for message in messages:
            role = (
                message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
            )
            if role == "assistant":
                seen_assistant = True
            if role in {"tool", "tool_result"} and not seen_assistant:
                return False
        return True

    def _objective_snapshot_consistent(self, request: CompressionVerifyRequest) -> bool:
        if request.metadata.get("objective_out_of_band") is True:
            return True

        before = str(
            request.metadata.get(
                "objective_before",
                request.metadata.get("before_objective", request.task_frame.objective),
            )
        ).strip()
        after = str(
            request.metadata.get(
                "objective_after",
                request.metadata.get("after_objective", ""),
            )
        ).strip()

        if (
            after
            and request.task_frame.objective.strip()
            and after != request.task_frame.objective.strip()
        ):
            return False

        if before and after:
            return before == after
        return True

    def _objective_preserved(self, request: CompressionVerifyRequest) -> bool:
        if request.metadata.get("objective_out_of_band") is True:
            return True

        objective = request.task_frame.objective.strip()
        if not objective:
            return True

        match_count = self._objective_match_count(request, objective)
        if match_count > 0:
            return True

        if self._requires_inline_objective(request.compressed_messages):
            return False

        after = str(
            request.metadata.get(
                "objective_after",
                request.metadata.get("after_objective", ""),
            )
        ).strip()
        return bool(after) and after == objective

    def _objective_is_unique(self, request: CompressionVerifyRequest) -> bool:
        objective = request.task_frame.objective.strip()
        if not objective or request.metadata.get("objective_out_of_band") is True:
            return True

        return self._objective_match_count(request, objective) <= 1

    def _objective_match_count(self, request: CompressionVerifyRequest, objective: str) -> int:
        matches = 0
        for message in request.compressed_messages:
            content = (
                message.get("content", "")
                if isinstance(message, dict)
                else getattr(message, "content", "")
            )
            if objective in str(content):
                matches += 1
        return matches

    def _requires_inline_objective(self, messages: list[Any]) -> bool:
        for message in messages:
            content = (
                message.get("content", "")
                if isinstance(message, dict)
                else getattr(message, "content", "")
            )
            normalized = str(content).lower()
            if normalized.startswith("[collapsed history]"):
                return True
            if normalized.startswith("[auto-compacted history]"):
                return True
            if normalized.startswith("[emergency context summary]"):
                return True
        return False

    def _terminal_state_conflicts_ok(self, messages: list[Any]) -> bool:
        task_states: dict[str, set[str]] = {}
        for message in messages:
            content = (
                message.get("content", "")
                if isinstance(message, dict)
                else getattr(message, "content", "")
            )
            normalized = str(content).lower()
            task_id = self._extract_task_id(normalized)
            state = self._extract_state_label(normalized)
            if not task_id or not state:
                continue
            task_states.setdefault(task_id, set()).add(state)

        terminal_states = {"done", "failed", "cancelled"}
        running_states = {"pending", "running", "delegated"}
        for states in task_states.values():
            if states & terminal_states and states & running_states:
                return False
        return True

    def _conclusions_preserved(self, request: CompressionVerifyRequest) -> bool:
        before = [
            str(item).strip()
            for item in request.metadata.get("key_conclusions_before", [])
            if str(item).strip()
        ]
        after = {
            str(item).strip()
            for item in request.metadata.get("key_conclusions_after", [])
            if str(item).strip()
        }
        if not before:
            return True
        return all(item in after for item in before)

    def _compression_gain_ok(self, request: CompressionVerifyRequest) -> bool:
        token_gain = int(request.metadata.get("token_gain", 0) or 0)
        min_gain = int(request.metadata.get("min_compression_gain_tokens", 0) or 0)
        return token_gain >= min_gain

    def _extract_task_id(self, content: str) -> str | None:
        marker = "task-"
        if marker not in content:
            return None
        suffix = content.split(marker, 1)[1]
        token = suffix.split()[0].strip("：:，,。.;")
        return f"task-{token}" if token else None

    def _extract_state_label(self, content: str) -> str | None:
        for state in ("pending", "running", "done", "failed", "cancelled", "delegated"):
            if f"status: {state}" in content or f"状态: {state}" in content:
                return state
        return None


__all__ = [
    "CompressionPostCheck",
    "CompressionVerifyRequest",
    "DefaultCompressionVerifier",
]
