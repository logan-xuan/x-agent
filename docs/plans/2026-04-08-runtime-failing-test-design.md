# Runtime Compression Failing-Test Design Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic failing tests that capture the runtime compression contract changes (objective preservation + rollback semantics), then define the minimal follow-up updates needed to restore a green pipeline test suite.

**Architecture:** We keep production code unchanged in phase 1 and lock in current behavior using targeted red tests in `test_runtime_compression_pipeline.py`. The tests isolate verifier-driven rollback interactions from budget/autocompact checks with explicit fixtures and assertions. After the red baseline is established, phase 2 updates test expectations (or implementation if approved) one contract at a time.

**Tech Stack:** Python 3.13, pytest, pytest-asyncio, runtime compression pipeline/verifier modules.

---

### Task 1: Capture current red baseline for runtime compression suites

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Write baseline marker test (failing by design)**

```python
@pytest.mark.asyncio
async def test_baseline_pipeline_contract_regressions_are_detected() -> None:
    """记录当前回归基线：当 objective 未被压缩结果显式保留时会触发 rollback。"""
    pipeline = DefaultCompressionPipeline()
    ctx = CompressionContext(
        session_key="baseline",
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

    # 该断言在当前实现下应 FAIL（当前会 rollback_applied=True）
    assert result.rollback_applied is False
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py::test_baseline_pipeline_contract_regressions_are_detected -q`
Expected: FAIL with `assert True is False` (rollback applied).

**Step 3: Keep failure output as baseline evidence**

```text
FAILED ... assert result.rollback_applied is False
E assert True is False
```

**Step 4: Re-run focused suite to confirm failure is stable**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py -q`
Expected: verifier+gateway pass, pipeline has the known 7+ baseline failures.

**Step 5: Commit baseline test**

```bash
git add /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "test(runtime): lock failing baseline for compression rollback contract"
```

---

### Task 2: Add failing tests for objective-preservation rollback contract

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write failing test for persisted tool result + objective loss rollback**

```python
@pytest.mark.asyncio
async def test_pipeline_rolls_back_when_persist_runs_but_objective_not_preserved() -> None:
    """当触发 persist 但 objective 未保留时，应回滚并清空新增 artifact。"""
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
    assert result.rollback_applied is False  # 当前应 FAIL
```
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_rolls_back_when_persist_runs_but_objective_not_preserved -q`
Expected: FAIL, showing rollback is actually applied.

**Step 3: Write failing test for verifier result contract exposure**

```python
@pytest.mark.asyncio
async def test_pipeline_contract_exposes_non_rollback_path_for_simple_message() -> None:
    """简单消息路径应暴露 verifier 结果且不回滚（当前实现会回滚，先锁红）。"""
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

    assert result.verifier_result is not None
    assert result.rollback_applied is False  # 当前应 FAIL
```

**Step 4: Run both tests to verify failures are deterministic**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py -k "rolls_back_when_persist_runs or exposes_non_rollback_path" -q`
Expected: both FAIL, same rollback reason category.

**Step 5: Commit tests**

```bash
git add /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "test(runtime): add red tests for objective-preservation rollback contract"
```

---

### Task 3: Add failing tests for budget/autocompact expectation drift

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write failing test for budget metadata expectation**

```python
@pytest.mark.asyncio
async def test_pipeline_exposes_budget_state_without_rollback_on_runtime_pass() -> None:
    """预算元数据应可见且运行时压缩通过时不回滚（当前行为锁红）。"""
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()

    ctx = CompressionContext(
        session_key="budget",
        turn=2,
        task_frame=TaskFrame(objective="Ship runtime"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[{"role": "user", "content": "x" * 180}],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert result.metadata.get("budget") is not None
    assert result.rollback_applied is False  # 当前应 FAIL
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_exposes_budget_state_without_rollback_on_runtime_pass -q`
Expected: FAIL with rollback assertion.

**Step 3: Write failing test for microcompact/collapse expectation**

```python
@pytest.mark.asyncio
async def test_pipeline_microcompact_path_keeps_artifact_updates_visible() -> None:
    """微压缩路径应保留 artifact 预览更新（当前回滚下会丢失，先锁红）。"""
    store = InMemoryArtifactStore(preview_chars=120)
    pipeline = DefaultCompressionPipeline(artifact_store=store)
    profile = CompressionProfile()
    profile.persist.single_result_chars = 30

    ctx = CompressionContext(
        session_key="artifact",
        turn=3,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=120,
        estimated_input_tokens=110,
        messages=[
            {"role": "assistant", "content": "call"},
            {"role": "tool", "content": "y" * 200, "tool_name": "web_fetch", "tool_call_id": "t2"},
        ],
        active_artifacts=[],
        budget=BudgetSnapshot.from_profile(TurnBudgetProfile()),
    )

    result = await pipeline.run(ctx)

    assert len(result.active_artifacts) >= 1  # 当前应 FAIL
```

**Step 4: Run targeted group to verify failures**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py -k "budget_state_without_rollback or microcompact_path_keeps_artifact_updates_visible" -q`
Expected: FAIL, matching known contract drift.

**Step 5: Commit tests**

```bash
git add /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "test(runtime): add red tests for budget and microcompact contract drift"
```

---

### Task 4: Verify non-pipeline runtime regressions remain green

**Files:**
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_turn_controller.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_resume_flow.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_child_flow.py`

**Step 1: Run verifier + gateway suites**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py -q`
Expected: PASS.

**Step 2: Run controller suite**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_turn_controller.py -q`
Expected: PASS.

**Step 3: Run runtime integrations**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_resume_flow.py /Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_child_flow.py -q`
Expected: PASS.

**Step 4: Record current known-red list in PR description**

```text
Known red (pipeline only):
- test_compression_pipeline_persists_large_tool_results
- test_compression_pipeline_exposes_verifier_result_contract_fields
- test_compression_pipeline_verification_metadata_does_not_fabricate_missing_objective
- test_compression_pipeline_applies_profile_preview_sizes
- test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass
- test_compression_pipeline_microcompacts_large_tool_results_before_collapse
- test_deduped_artifact_preview_updates_for_new_profile
```

**Step 5: Commit test-only verification note (if stored in repo)**

```bash
git add /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "test(runtime): document isolated red pipeline regressions"
```

---

### Task 5: Prepare follow-up green strategy (after approval)

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_verifier.py`

**Step 1: Decide per test: expectation update vs implementation fix**

```text
Rule:
- If contract intentionally changed by verifier hardening, update test expectation.
- If behavior violates agreed runtime contract, patch implementation minimally.
```

**Step 2: Implement exactly one green fix path for first failing test**

```python
# 示例（仅示意）：更新断言为 rollback_applied is True，并校验 rollback_reason 包含 objective 保留失败原因
assert result.rollback_applied is True
assert "objective" in (result.rollback_reason or "")
```

**Step 3: Run single test to green**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_verifier_result_contract_fields -q`
Expected: PASS.

**Step 4: Expand to full pipeline suite**

Run: `pytest --no-cov /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py -q`
Expected: failing count reduced by 1+ with no new regressions.

**Step 5: Commit incremental green change**

```bash
git add /Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py /Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py /Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_verifier.py
git commit -m "test(runtime): align first pipeline contract case with verifier rollback semantics"
```
