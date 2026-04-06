"""Unit tests for the runtime compression verifier skeleton."""

from src.runtime.context import DefaultCompressionVerifier
from src.runtime.context.compression_verifier import CompressionVerifyRequest
from src.runtime.types import ArtifactRef, TaskFrame


def test_compression_verifier_rejects_tool_message_without_assistant_prefix():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Task"),
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
