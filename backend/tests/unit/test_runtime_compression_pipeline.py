"""Unit tests for the runtime compression pipeline skeleton."""

import pytest

from src.runtime.context import (
    ArtifactBackedMemoryFlusher,
    DefaultCompressionPipeline,
    InMemoryArtifactStore,
)
from src.runtime.context.compression_pipeline import CompressionContext, CompressionProfile
from src.runtime.context.compression_verifier import DefaultCompressionVerifier
from src.runtime.types import ArtifactRef, BudgetSnapshot, TaskFrame, TurnBudgetProfile


def test_compression_pipeline_detects_repeated_summaries_and_terminal_overrides():
    pipeline = DefaultCompressionPipeline()
    messages = [
        {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
        {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
        {"role": "assistant", "content": "任务 task-1 status: pending"},
        {"role": "assistant", "content": "任务 task-1 status: done"},
        {"role": "assistant", "content": "请稍等，我稍后回传结果。"},
    ]

    analyzed = pipeline._analyze_messages(messages)
    budget_state = pipeline._build_budget_state(
        CompressionContext(
            session_key="s1",
            turn=1,
            task_frame=TaskFrame(objective="Ship runtime"),
            profile=CompressionProfile(),
            model_context_window=200,
            estimated_input_tokens=160,
            messages=messages,
            active_artifacts=[],
            budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        ),
        analyzed,
        current_tokens=160,
    )

    assert budget_state.repeated_summary_ratio > 0
    assert analyzed[0].message_kind == "summary"
    assert analyzed[1].droppable is True
    assert analyzed[2].superseded_by_terminal is True
    assert analyzed[4].semantic_priority == "P3"


@pytest.mark.asyncio
async def test_microcompact_removes_redundant_summaries_and_superseded_statuses():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.microcompact.trigger_pct = 0.50
    profile.microcompact.max_units_per_pass = 8
    profile.pruning.soft_trim_max_chars = 30
    profile.pruning.soft_trim_head_chars = 10
    profile.pruning.soft_trim_tail_chars = 10
    messages = [
        {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
        {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
        {"role": "assistant", "content": "任务 task-1 status: pending"},
        {"role": "assistant", "content": "任务 task-1 status: done"},
        {"role": "assistant", "content": "请稍等，我稍后回传结果。"},
        {"role": "tool", "content": "abcdefghijklmnopqrstuvwxyz0123456789"},
    ]
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Ship runtime"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=55,
        messages=messages,
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    compacted, applied = pipeline._microcompact(ctx, messages, estimated_input_tokens=55)

    assert applied is True
    contents = [message["content"] for message in compacted]
    assert "[Collapsed history]\nObjective: Ship runtime" in contents


@pytest.mark.asyncio
async def test_collapse_rewrites_history_into_single_state_snapshot():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    messages = [
        {"role": "system", "content": "[Collapsed history]\nObjective: Old objective"},
        {"role": "assistant", "content": "任务 task-1 status: pending"},
        {"role": "assistant", "content": "任务 task-1 status: done"},
        {"role": "assistant", "content": "error: upstream timeout"},
        {"role": "user", "content": "recent request"},
        {"role": "assistant", "content": "recent answer"},
    ]
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(
            objective="Ship runtime",
            constraints=["Do not widen scope"],
            unresolved=["verifier gap"],
        ),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=90,
        messages=messages,
        active_artifacts=[
            ArtifactRef(id="artifact-1", kind="tool", title="Artifact", preview="preview")
        ],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    collapsed, applied = pipeline._collapse_history(ctx, messages, estimated_input_tokens=90)

    assert applied is True
    snapshots = [message for message in collapsed if message["content"].startswith("[Collapsed history]")]
    assert len(snapshots) == 1
    snapshot = snapshots[0]["content"]
    assert "Objective: Ship runtime" in snapshot
    assert "Constraints: Do not widen scope" in snapshot
    assert "Unresolved: verifier gap" in snapshot
    assert "Finalized tasks: task-1 done" in snapshot
    assert "Active failures: error: upstream timeout" in snapshot
    assert "Artifacts: artifact-1" in snapshot
    assert "Evidence summaries: task-1 done" in snapshot


@pytest.mark.asyncio
async def test_compression_pipeline_derives_verifier_metadata_from_compacted_output():
    class CapturingVerifier:
        def __init__(self) -> None:
            self.request = None

        def verify(self, request):
            from src.runtime.context.compression_verifier import CompressionPostCheck

            self.request = request
            return CompressionPostCheck(ok=True)

    verifier = CapturingVerifier()
    pipeline = DefaultCompressionPipeline(verifier=verifier)  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.collapse.trigger_pct = 0.10
    profile.retain_recent_messages = 2
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(
            objective="Ship runtime",
            constraints=["Do not widen scope"],
            unresolved=["verifier gap"],
        ),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=90,
        messages=[
            {"role": "assistant", "content": "任务 task-1 status: pending"},
            {"role": "assistant", "content": "任务 task-1 status: done"},
            {"role": "assistant", "content": "error: upstream timeout"},
            {"role": "user", "content": "recent request"},
            {"role": "assistant", "content": "recent answer"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        metadata={"recent_failures": ["stale failure"]},
    )

    await pipeline.run(ctx)

    assert verifier.request is not None
    assert verifier.request.metadata["objective_out_of_band"] is False
    assert verifier.request.metadata["compressed_unresolved"] == ["verifier gap"]


@pytest.mark.asyncio
async def test_compression_pipeline_derives_unresolved_and_conclusions_from_compressed_messages():
    class CapturingVerifier:
        def __init__(self) -> None:
            self.request = None

        def verify(self, request):
            from src.runtime.context.compression_verifier import CompressionPostCheck

            self.request = request
            return CompressionPostCheck(ok=True)

    verifier = CapturingVerifier()
    pipeline = DefaultCompressionPipeline(verifier=verifier)  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.collapse.trigger_pct = 0.10
    profile.retain_recent_messages = 2
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(
            objective="Ship runtime",
            unresolved=["verifier gap"],
        ),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[
            {"role": "assistant", "content": "任务 task-1 status: done"},
            {"role": "assistant", "content": "error: upstream timeout"},
            {"role": "user", "content": "recent request"},
            {"role": "assistant", "content": "recent answer"},
            {"role": "assistant", "content": "final answer"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    await pipeline.run(ctx)

    assert verifier.request is not None
    assert verifier.request.metadata["compressed_unresolved"] == ["verifier gap"]
    assert "task-1 done" in verifier.request.metadata["key_conclusions_after"]
    assert verifier.request.metadata["key_conclusions_before"] == ["task-1 done"]


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
async def test_compression_pipeline_autocompacts_when_history_share_is_high_even_below_token_trigger():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.collapse.enabled = False
    profile.autocompact.trigger_pct = 0.95
    profile.autocompact.max_history_share = 0.30
    profile.autocompact.reserve_tokens_floor = 10
    profile.retain_recent_messages = 4
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=250,
        messages=[
            {"role": "assistant", "content": f"任务 task-{i} status: done"}
            for i in range(8)
        ]
        + [
            {"role": "user", "content": "recent request"},
            {"role": "assistant", "content": "recent answer"},
            {"role": "user", "content": "recent follow-up"},
            {"role": "assistant", "content": "final answer"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "autocompact" in result.operations
    assert any(message["content"].startswith("[Auto-compacted history]") for message in result.messages)


@pytest.mark.asyncio
async def test_compression_pipeline_recomputes_pressure_after_collapse_before_autocompact():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.autocompact.max_history_share = 0.10
    profile.retain_recent_messages = 4
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
    assert "autocompact" not in result.operations
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

    await pipeline.run(ctx)



@pytest.mark.asyncio
async def test_compression_pipeline_keeps_objective_verification_enabled_without_summary_compaction():
    class CapturingVerifier:
        def __init__(self) -> None:
            self.request = None

        def verify(self, request):
            from src.runtime.context.compression_verifier import CompressionPostCheck

            self.request = request
            return CompressionPostCheck(ok=True)

    verifier = CapturingVerifier()
    pipeline = DefaultCompressionPipeline(verifier=verifier)  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.collapse.trigger_pct = 0.95
    profile.autocompact.trigger_pct = 0.98
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Ship runtime"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=50,
        messages=[
            {"role": "user", "content": "Need to ship runtime without changing scope."},
            {"role": "assistant", "content": "I will keep the current objective intact."},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    await pipeline.run(ctx)

    assert verifier.request is not None
    assert verifier.request.metadata["objective_out_of_band"] is False


@pytest.mark.asyncio
async def test_compression_pipeline_recomputes_stage_pressure_after_persist_before_collapse():
    store = InMemoryArtifactStore(preview_chars=50)
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    profile = CompressionProfile()
    profile.persist.single_result_chars = 20
    profile.collapse.trigger_pct = 0.90
    profile.retain_recent_messages = 1
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
            {"role": "user", "content": "follow-up question"},
            {"role": "assistant", "content": "follow-up answer"},
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
    assert result.active_artifacts[0].id == "artifact-1"

@pytest.mark.asyncio
async def test_compression_pipeline_does_not_rollback_to_oversized_original_after_emergency_verifier_failure():
    from src.runtime.context.compression_verifier import CompressionPostCheck

    class RejectingVerifier:
        def verify(self, request):
            _ = request
            return CompressionPostCheck(ok=False, reasons=["compressed recent failures diverged from source state"])

    pipeline = DefaultCompressionPipeline(verifier=RejectingVerifier())  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.autocompact.fallback_summary_max_chars = 40
    profile.retain_recent_messages = 12
    ctx = CompressionContext(
        session_key="s1",
        turn=4,
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["must-fit gap"]),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[
            {"role": "user", "content": f"message {i} " + ("x" * 120)}
            for i in range(18)
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        metadata={"recent_failures": ["timeout:web_search"]},
    )

    result = await pipeline.run(ctx)

    assert result.messages != ctx.messages
    assert result.rollback_applied is False
    assert result.estimated_input_tokens <= int(ctx.model_context_window * ctx.profile.pressure.red_pct)
    assert result.metadata["fallback_summary_used"] is True


@pytest.mark.asyncio
async def test_compression_pipeline_verification_metadata_does_not_fabricate_missing_objective():
    class CapturingVerifier:
        def __init__(self) -> None:
            self.request = None

        def verify(self, request):
            from src.runtime.context.compression_verifier import CompressionPostCheck

            self.request = request
            return CompressionPostCheck(ok=True)

    verifier = CapturingVerifier()
    pipeline = DefaultCompressionPipeline(verifier=verifier)  # type: ignore[arg-type]
    profile = CompressionProfile()
    profile.collapse.trigger_pct = 0.10
    profile.retain_recent_messages = 2
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["verifier gap"]),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[
            {"role": "user", "content": f"message {i} " + ("x" * 80)}
            for i in range(10)
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    await pipeline.run(ctx)

    assert verifier.request is not None
    assert verifier.request.metadata["objective_out_of_band"] is False
    assert verifier.request.metadata["objective_after"] == ""


@pytest.mark.asyncio
async def test_compression_pipeline_falls_back_to_emergency_when_must_fit_budget_still_exceeded():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.autocompact.fallback_summary_max_chars = 40
    profile.retain_recent_messages = 12
    ctx = CompressionContext(
        session_key="s1",
        turn=4,
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["must-fit gap"]),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[
            {"role": "user", "content": f"message {i} " + ("x" * 120)}
            for i in range(18)
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert result.operations[-1] == "emergency_compact"
    assert "rollback" not in result.operations
    assert result.rollback_applied is False
    assert result.metadata["fallback_summary_used"] is True
    assert result.estimated_input_tokens <= int(ctx.model_context_window * ctx.profile.pressure.red_pct)
    assert result.messages[0]["content"].startswith("[Emergency context summary]")


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
async def test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.pressure.yellow_pct = 0.30
    profile.pressure.orange_pct = 0.45
    profile.pressure.red_pct = 0.60
    profile.microcompact.trigger_pct = 0.95
    profile.collapse.trigger_pct = 0.95
    profile.autocompact.trigger_pct = 0.95
    ctx = CompressionContext(
        session_key="s1",
        turn=3,
        task_frame=TaskFrame(objective="Ship runtime"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=50,
        messages=[
            {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
            {"role": "system", "content": "[Collapsed history]\nObjective: Ship runtime"},
            {"role": "assistant", "content": "任务 task-1 status: pending"},
            {"role": "assistant", "content": "任务 task-1 status: done"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "budget_state" in result.metadata
    assert result.metadata["budget_state"]["pressure_level"] in {"yellow", "orange", "red"}
    assert result.metadata["budget_state"]["repeated_summary_ratio"] > 0


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
    assert result.estimated_input_tokens <= int(ctx.model_context_window * ctx.profile.pressure.red_pct)


@pytest.mark.asyncio
async def test_autocompact_stops_once_budget_target_is_met():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.collapse.enabled = False
    profile.autocompact.trigger_pct = 0.30
    profile.autocompact.max_history_share = 0.30
    profile.autocompact.reserve_tokens_floor = 10
    profile.retain_recent_messages = 3
    messages = [
        {"role": "user", "content": "objective context " + ("x" * 120)},
        {"role": "assistant", "content": "status update " + ("y" * 120)},
        {"role": "assistant", "content": "completed result " + ("z" * 120)},
        {"role": "user", "content": "recent request " + ("a" * 120)},
        {"role": "assistant", "content": "recent answer " + ("b" * 120)},
        {"role": "assistant", "content": "recent followup " + ("c" * 120)},
    ]
    ctx = CompressionContext(
        session_key="s1",
        turn=2,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=140,
        messages=messages,
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "autocompact" in result.operations
    assert result.estimated_input_tokens <= int(ctx.model_context_window * ctx.profile.pressure.orange_pct)
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


@pytest.mark.asyncio
async def test_compression_pipeline_respects_objective_out_of_band_during_snapshot_check():
    profile = CompressionProfile()
    ctx = CompressionContext(
        session_key="s1",
        turn=1,
        task_frame=TaskFrame(objective="Ship runtime"),
        profile=profile,
        model_context_window=1000,
        estimated_input_tokens=100,
        messages=[{"role": "user", "content": "hello"}],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
        metadata={
            "objective_out_of_band": True,
            "objective_before": "Ship runtime",
            "objective_after": "Different objective",
        },
    )

    result = await DefaultCompressionPipeline().run(ctx)

    assert result.rollback_applied is False
    assert result.rollback_reason is None


@pytest.mark.asyncio
async def test_compression_pipeline_does_not_infer_unresolved_from_plain_user_prompt_text():
    profile = CompressionProfile()
    profile.microcompact.trigger_pct = 0.99
    profile.collapse.trigger_pct = 0.99
    profile.autocompact.trigger_pct = 0.99
    profile.memory_flush.soft_threshold_tokens = 1
    ctx = CompressionContext(
        session_key="s-unresolved",
        turn=1,
        task_frame=TaskFrame(objective="压缩验证", unresolved=[]),
        profile=profile,
        model_context_window=120000,
        estimated_input_tokens=6206,
        messages=[
            {
                "role": "user",
                "content": "请继续保留目标、未完成事项和失败信息。未完成事项：A、B、C。",
            },
            {"role": "assistant", "content": "已记录。"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await DefaultCompressionPipeline().run(ctx)

    assert "memory_flush" not in result.operations
    assert result.rollback_applied is False
    assert result.rollback_reason is None


@pytest.mark.asyncio
async def test_memory_flush_rewrites_old_tool_results_into_artifact_refs():
    profile = CompressionProfile()
    profile.microcompact.trigger_pct = 0.99
    profile.collapse.trigger_pct = 0.99
    profile.autocompact.trigger_pct = 0.99
    profile.memory_flush.soft_threshold_tokens = 1
    profile.retain_recent_messages = 2
    pipeline = DefaultCompressionPipeline(memory_flusher=ArtifactBackedMemoryFlusher())
    long_tool_result = "杭州明天中雨，18到24度，东北风2级。" + ("x" * 5000)
    ctx = CompressionContext(
        session_key="s-memory-flush",
        turn=1,
        task_frame=TaskFrame(objective="生成可执行 PPT 模版"),
        profile=profile,
        model_context_window=120000,
        estimated_input_tokens=6206,
        messages=[
            {"role": "user", "content": "请生成一个PPT模板"},
            {"role": "assistant", "content": "我先查询一些示例"},
            {"role": "tool", "tool_name": "web_search", "content": long_tool_result},
            {"role": "assistant", "content": "我已拿到示例，继续整理"},
            {"role": "user", "content": "继续"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert "memory_flush" in result.operations
    flushed_messages = [
        message for message in result.messages if str(message.get("content", "")).startswith("[Memory-flushed tool result]")
    ]
    assert len(flushed_messages) == 1
    assert flushed_messages[0]["role"] == "tool"
    assert "Tool: web_search" in flushed_messages[0]["content"]
    assert "Artifact: artifact:1" in flushed_messages[0]["content"]
    assert len(result.active_artifacts) == 1
    assert result.active_artifacts[0].id == "artifact:1"


def test_collapse_history_preserves_role_ordering_when_suffix_starts_with_tool():
    pipeline = DefaultCompressionPipeline()
    verifier = DefaultCompressionVerifier()
    profile = CompressionProfile()
    profile.retain_recent_messages = 2
    messages = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": "call tool"},
        {"role": "tool", "content": "tool result"},
        {"role": "system", "content": "recent system note"},
    ]
    ctx = CompressionContext(
        session_key="s-role-collapse",
        turn=1,
        task_frame=TaskFrame(objective="验证 role ordering"),
        profile=profile,
        model_context_window=4,
        estimated_input_tokens=999,
        messages=messages,
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    collapsed, applied = pipeline._collapse_history(ctx, messages, estimated_input_tokens=999)

    assert applied is True
    assert verifier._role_ordering_ok(collapsed) is True


@pytest.mark.asyncio
async def test_emergency_compression_preserves_role_ordering_when_tail_starts_with_tool():
    pipeline = DefaultCompressionPipeline()
    verifier = DefaultCompressionVerifier()
    profile = CompressionProfile()
    profile.retain_recent_messages = 2
    ctx = CompressionContext(
        session_key="s-role-emergency",
        turn=1,
        task_frame=TaskFrame(objective="验证 role ordering"),
        profile=profile,
        model_context_window=4,
        estimated_input_tokens=999,
        messages=[
            {"role": "user", "content": "start"},
            {"role": "assistant", "content": "call tool"},
            {"role": "tool", "content": "tool result"},
            {"role": "system", "content": "recent system note"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run_emergency(ctx)

    assert verifier._role_ordering_ok(result.messages) is True
