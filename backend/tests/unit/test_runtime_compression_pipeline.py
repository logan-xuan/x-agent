"""Unit tests for the runtime compression pipeline skeleton."""

import pytest

from src.runtime.context import DefaultCompressionPipeline, InMemoryArtifactStore
from src.runtime.context.compression_pipeline import CompressionContext, CompressionProfile
from src.runtime.types import BudgetSnapshot, TaskFrame, TurnBudgetProfile


@pytest.mark.asyncio
async def test_compression_pipeline_persists_large_tool_results():
    store = InMemoryArtifactStore(preview_chars=200)
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    profile = CompressionProfile()
    profile.persist.single_result_chars = 20
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[
            {"role": "assistant", "content": "calling tool"},
            {"role": "tool", "content": "x" * 100, "tool_name": "web_fetch", "tool_call_id": "t1"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "persist" in result.operations
    assert len(result.active_artifacts) == 1
    assert "Persisted large tool result" in result.messages[1]["content"]


@pytest.mark.asyncio
async def test_compression_pipeline_collapses_history_when_pressure_is_high():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=90,
        messages=[{"role": "user", "content": f"message {i} " + ("x" * 80)} for i in range(20)],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "collapse" in result.operations
    assert any(message["content"].startswith("[Collapsed history]") for message in result.messages)


@pytest.mark.asyncio
async def test_compression_pipeline_recomputes_pressure_after_persist():
    store = InMemoryArtifactStore(preview_chars=50)
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    profile = CompressionProfile()
    profile.persist.single_result_chars = 20
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=90,
        messages=[
            {"role": "assistant", "content": "call tool"},
            {"role": "tool", "content": "x" * 120, "tool_name": "web_fetch", "tool_call_id": "t1"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "persist" in result.operations
    assert "collapse" not in result.operations


@pytest.mark.asyncio
async def test_compression_pipeline_respects_disabled_hard_clear():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.pruning.hard_clear_enabled = False
    profile.pruning.min_prunable_tool_chars = 10
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[
            {
                "role": "tool",
                "content": "x" * 50,
                "timestamp_ms": 1,
            }
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        metadata={"now_ms": profile.pruning.ttl_ms + 10},
    )

    result = await pipeline.run(ctx)

    assert "ttl_prune" not in result.operations
    assert result.messages[0]["content"] == "x" * 50


@pytest.mark.asyncio
async def test_compression_pipeline_skips_post_check_when_disabled():
    class RejectingVerifier:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self, request):
            from src.runtime.context.compression_verifier import CompressionPostCheck

            self.calls += 1
            _ = request
            return CompressionPostCheck(ok=False, reasons=["forced failure"])

    verifier = RejectingVerifier()
    pipeline = DefaultCompressionPipeline(verifier=verifier)  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.quality.require_post_check = False
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[{"role": "user", "content": "hello"}],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "rollback" not in result.operations
    assert verifier.calls == 0
    assert result.metadata["verification"] is None


@pytest.mark.asyncio
async def test_emergency_compression_keeps_tail_and_adds_summary():
    pipeline = DefaultCompressionPipeline()
    ctx = CompressionContext(
        session_key="s1",
        turn=3,
        task_frame=TaskFrame(objective="Task", unresolved=["u1"]),
        profile=CompressionProfile(),
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[{"role": "user", "content": f"message {i}"} for i in range(15)],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run_emergency(ctx)

    assert result.operations == ["emergency_compact"]
    assert result.messages[0]["content"].startswith("[Emergency context summary]")


@pytest.mark.asyncio
async def test_emergency_compression_does_not_duplicate_leading_system():
    pipeline = DefaultCompressionPipeline()
    ctx = CompressionContext(
        session_key="s1",
        turn=3,
        task_frame=TaskFrame(objective="Task", unresolved=["u1"]),
        profile=CompressionProfile(),
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[
            {"role": "system", "content": "base system"},
            {"role": "user", "content": "message 1"},
            {"role": "assistant", "content": "message 2"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run_emergency(ctx)

    assert [message["role"] for message in result.messages].count("system") == 2
    assert result.messages[0]["content"] == "base system"
    assert result.messages[2]["role"] == "user"


@pytest.mark.asyncio
async def test_compression_pipeline_applies_profile_preview_sizes():
    store = InMemoryArtifactStore()
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    profile = CompressionProfile()
    profile.persist.single_result_chars = 20
    profile.persist.artifact_preview_chars = 30
    profile.persist.artifact_preview_head_chars = 10
    profile.persist.artifact_preview_tail_chars = 5
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[
            {"role": "assistant", "content": "calling tool"},
            {"role": "tool", "content": "abcdefghijklmnopqrstuvwxyz0123456789", "tool_name": "web_fetch"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert result.active_artifacts
    preview = result.active_artifacts[0].preview
    assert "abcdefghijklmnopqrstuvwxyz" not in preview
    assert "[21 chars omitted]" in preview
