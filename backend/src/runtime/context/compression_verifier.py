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
        }

        if request.task_frame.objective and not self._objective_preserved(request):
            preserved["objective"] = False
            reasons.append("compressed output no longer preserves the task objective")

        if not self._objective_snapshot_consistent(request):
            preserved["objective"] = False
            reasons.append("objective_mismatch")

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

        if request.original_messages and not request.compressed_messages:
            reasons.append("compressed messages unexpectedly became empty")

        return CompressionPostCheck(ok=not reasons, reasons=reasons, preserved_fields=preserved)

    def _role_ordering_ok(self, messages: list[Any]) -> bool:
        seen_assistant = False
        for message in messages:
            role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
            if role == "assistant":
                seen_assistant = True
            if role in {"tool", "tool_result"} and not seen_assistant:
                return False
        return True

    def _objective_snapshot_consistent(self, request: CompressionVerifyRequest) -> bool:
        before = str(
            request.metadata.get(
                "objective_before",
                request.metadata.get("before_objective", ""),
            )
        ).strip()
        after = str(
            request.metadata.get(
                "objective_after",
                request.metadata.get("after_objective", ""),
            )
        ).strip()
        if not before or not after:
            return True
        return before == after

    def _objective_preserved(self, request: CompressionVerifyRequest) -> bool:
        if request.metadata.get("objective_out_of_band") is True:
            return True

        objective = request.task_frame.objective.strip()
        if not objective:
            return True

        for message in request.compressed_messages:
            content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
            if objective in str(content):
                return True
        return False


__all__ = [
    "CompressionPostCheck",
    "CompressionVerifyRequest",
    "DefaultCompressionVerifier",
]
