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
