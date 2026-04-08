"""Unit tests for the runtime compression verifier skeleton."""

from src.runtime.context import DefaultCompressionVerifier
from src.runtime.context.compression_verifier import CompressionVerifyRequest
from src.runtime.types import ArtifactRef, TaskFrame


def test_compression_verifier_rejects_tool_message_without_assistant_prefix():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(),
        original_messages=[{"role": "assistant", "content": "call tool"}],
        compressed_messages=[{"role": "tool", "content": "orphan"}],
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert "role ordering" in result.reasons[0]


def test_compression_verifier_checks_artifact_refs_are_preserved():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Task"),
        original_messages=[{"role": "user", "content": "x"}],
        compressed_messages=[{"role": "user", "content": "x"}],
        original_artifacts=[ArtifactRef(id="artifact:1", kind="tool", title="A", preview="P")],
        compressed_artifacts=[],
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["artifact_refs"] is False


def test_compression_verifier_rejects_missing_objective_when_not_preserved_out_of_band():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[{"role": "system", "content": "[Collapsed history]"}],
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["objective"] is False


def test_compression_verifier_rejects_missing_recent_failures():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Task"),
        original_messages=[{"role": "assistant", "content": "failed once"}],
        compressed_messages=[{"role": "assistant", "content": "failed once"}],
        metadata={
            "recent_failures_before": ["timeout:web_search"],
            "recent_failures_after": [],
        },
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["recent_failures"] is False






def test_compression_verifier_rejects_objective_when_only_metadata_echoes_it():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[{"role": "system", "content": "[Collapsed history] no objective kept"}],
        metadata={
            "objective_after": "Ship runtime",
        },
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["objective"] is False



def test_compression_verifier_rejects_explicit_objective_snapshot_mismatch():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[{"role": "system", "content": "Objective: Ship runtime"}],
        metadata={"objective_after": "Different objective"},
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["objective"] is False
    assert "objective_mismatch" in result.reasons


def test_compression_verifier_does_not_emit_objective_mismatch_for_missing_objective_evidence_only():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[{"role": "system", "content": "[Collapsed history] no objective kept"}],
        metadata={"objective_after": "Ship runtime"},
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert "objective_mismatch" not in result.reasons


def test_compression_verifier_rejects_lost_key_conclusions():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "assistant", "content": "结论：需要保留 artifact:1"}],
        compressed_messages=[{"role": "system", "content": "Objective: Ship runtime"}],
        metadata={
            "key_conclusions_before": ["保留 artifact:1"],
            "key_conclusions_after": [],
        },
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["conclusion_fidelity"] is False
    assert "key_conclusions_lost" in result.reasons



def test_compression_verifier_rejects_duplicate_objective_mentions():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[
            {"role": "system", "content": "Objective: Ship runtime"},
            {"role": "assistant", "content": "I am still working on Ship runtime."},
        ],
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["objective"] is False
    assert "duplicate_objective" in result.reasons



def test_compression_verifier_allows_objective_snapshot_mismatch_when_objective_is_out_of_band():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Ship runtime"),
        original_messages=[{"role": "user", "content": "do the work"}],
        compressed_messages=[{"role": "system", "content": "[Collapsed history]"}],
        metadata={
            "objective_out_of_band": True,
            "objective_before": "Ship runtime",
            "objective_after": "Different objective",
        },
    )

    result = verifier.verify(request)

    assert result.ok is True
    assert "objective_mismatch" not in result.reasons
