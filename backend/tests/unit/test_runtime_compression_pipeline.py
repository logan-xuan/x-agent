"""Unit tests for the runtime compression pipeline skeleton."""

import pytest

from src.runtime.context import DefaultCompressionPipeline, InMemoryArtifactStore
from src.runtime.context.compression_pipeline import CompressionContext, CompressionProfile
from src.runtime.types import ArtifactRef, BudgetSnapshot, TaskFrame, TurnBudgetProfile


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

    assert verifier.calls == 0
    assert "rollback" not in result.operations


@pytest.mark.asyncio
async def test_compression_pipeline_exposes_verifier_result_contract_fields():
    pipeline = DefaultCompressionPipeline()
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=CompressionProfile(),
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[{"role": "user", "content": "hello"}],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert isinstance(result.operations, list)
    assert result.verifier_result is not None
    assert result.rollback_applied is False
    assert result.rollback_reason is None


@pytest.mark.asyncio
async def test_compression_pipeline_sets_rollback_metadata_when_verification_fails():
    from src.runtime.context.compression_verifier import CompressionPostCheck

    class RejectingVerifier:
        def verify(self, request):
            _ = request
            return CompressionPostCheck(ok=False, reasons=["forced failure"])

    pipeline = DefaultCompressionPipeline(verifier=RejectingVerifier())  # type: ignore[arg-type]
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=CompressionProfile(),
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[{"role": "user", "content": "hello"}],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert result.operations[-1] == "rollback"
    assert result.verifier_result is not None
    assert result.rollback_applied is True
    assert result.rollback_reason == "forced failure"
    assert result.metadata["rollback"] == {
        "applied": True,
        "reason": "forced failure",
    }
    assert result.metadata["rollback_applied"] is True
    assert result.metadata["rollback_reason"] == "forced failure"


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
    assert result.metadata["fallback_summary_used"] is True
    assert result.metadata["rollback_ready"] is True


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
async def test_emergency_compression_includes_active_artifact_refs():
    pipeline = DefaultCompressionPipeline()
    ctx = CompressionContext(
        session_key="s1",
        turn=3,
        task_frame=TaskFrame(objective="Task", unresolved=["u1"]),
        profile=CompressionProfile(),
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[{"role": "user", "content": "message 1"}],
        active_artifacts=[
            ArtifactRef(
                id="artifact-1",
                kind="tool",
                title="Artifact",
                preview="preview",
            )
        ],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run_emergency(ctx)

    assert "Artifacts: artifact-1" in result.messages[0]["content"]


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


@pytest.mark.asyncio
async def test_compression_pipeline_microcompacts_large_tool_results_before_collapse():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.microcompact.trigger_pct = 0.10
    profile.pruning.soft_trim_max_chars = 30
    profile.pruning.soft_trim_head_chars = 10
    profile.pruning.soft_trim_tail_chars = 10
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=800,
        messages=[
            {"role": "assistant", "content": "calling tool"},
            {"role": "tool", "content": "x" * 120},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "microcompact" in result.operations
    assert "...[microcompact]..." in result.messages[1]["content"]


@pytest.mark.asyncio
async def test_compression_pipeline_autocompacts_when_pressure_remains_high():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.collapse.enabled = False
    profile.autocompact.trigger_pct = 0.30
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=90,
        messages=[{"role": "user", "content": f"message {i} " + ("x" * 60)} for i in range(12)],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "autocompact" in result.operations
    assert any(message["content"].startswith("[Auto-compacted history]") for message in result.messages)


@pytest.mark.asyncio
async def test_deduped_artifact_preview_updates_for_new_profile():
    store = InMemoryArtifactStore()
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    content = "abcdefghijklmnopqrstuvwxyz0123456789"

    first_profile = CompressionProfile()
    first_profile.persist.single_result_chars = 20
    first_profile.persist.artifact_preview_chars = 30
    first_profile.persist.artifact_preview_head_chars = 10
    first_profile.persist.artifact_preview_tail_chars = 5

    second_profile = CompressionProfile()
    second_profile.persist.single_result_chars = 20
    second_profile.persist.artifact_preview_chars = 16
    second_profile.persist.artifact_preview_head_chars = 4
    second_profile.persist.artifact_preview_tail_chars = 4

    first_result = await pipeline.run(
        CompressionContext(
            session_key="s1",
            turn=1,
            task_frame=TaskFrame(objective="Task"),
            profile=first_profile,
            model_context_window=1000,
            estimated_input_tokens=100,
            messages=[
                {"role": "assistant", "content": "calling tool"},
                {"role": "tool", "content": content, "tool_name": "web_fetch"},
            ],
            active_artifacts=[],
            budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        )
    )
    second_result = await pipeline.run(
        CompressionContext(
            session_key="s1",
            turn=2,
            task_frame=TaskFrame(objective="Task"),
            profile=second_profile,
            model_context_window=1000,
            estimated_input_tokens=100,
            messages=[
                {"role": "assistant", "content": "calling tool"},
                {"role": "tool", "content": content, "tool_name": "web_fetch"},
            ],
            active_artifacts=[],
            budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        )
    )

    assert first_result.active_artifacts[0].id == second_result.active_artifacts[0].id
    assert second_result.active_artifacts[0].preview.startswith("abcd")
    assert second_result.active_artifacts[0].preview.endswith("6789")
