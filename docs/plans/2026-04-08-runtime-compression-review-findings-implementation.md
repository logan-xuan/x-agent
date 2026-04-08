# Runtime Compression Review Findings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 runtime 压缩复核中暴露的预算状态缺口，让压缩结果始终暴露可审计的 `budget_state` 元数据。

**Architecture:** 在 `DefaultCompressionPipeline.run` 内显式构建并回传预算状态，覆盖正常返回、rollback 返回和 emergency 后返回三条路径。测试先行，先锁定失败断言，再做最小实现，避免扩大修改面。

**Tech Stack:** Python 3.11+, dataclasses, pytest, runtime context pipeline

---

### Task 1: 锁定 budget_state 缺口（正常路径）

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass():
    result = await pipeline.run(ctx)
    assert "budget_state" in result.metadata
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass -v`
Expected: FAIL with `AssertionError: assert 'budget_state' in result.metadata`

**Step 3: Write minimal implementation**

```python
analyzed = self._analyze_messages(messages)
budget_state = self._build_budget_state(ctx, analyzed, current_estimated_tokens)
```

并将 `budget_state` 序列化写入 `CompressionResult.metadata`。

**Step 4: Run test to verify it passes**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/src/runtime/context/compression_pipeline.py
git commit -m "fix(runtime): expose compression budget state metadata"
```

### Task 2: 锁定 budget_state 在 rollback 路径不丢失

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_compression_pipeline_keeps_budget_state_metadata_when_rollback_happens():
    result = await pipeline.run(ctx)
    assert result.rollback_applied is True
    assert "budget_state" in result.metadata
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -k keeps_budget_state_metadata_when_rollback_happens -v`
Expected: FAIL because rollback metadata currently only has verification/rollback fields.

**Step 3: Write minimal implementation**

```python
metadata={
    **result_metadata,
    "budget_state": budget_state_payload,
    "verification": verification,
    "rollback": {...},
}
```

确保 rollback 分支、rollback-skip 分支、正常分支都包含同一结构的 `budget_state`。

**Step 4: Run test to verify it passes**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -k keeps_budget_state_metadata_when_rollback_happens -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/src/runtime/context/compression_pipeline.py
git commit -m "fix(runtime): retain budget state metadata across rollback"
```

### Task 3: 验证 gateway compact 输出可携带 budget_state

**Files:**
- Modify: `backend/tests/unit/test_runtime_gateway_adapter.py`
- Modify: `backend/src/gateway/agent_bridge.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_agent_bridge_runtime_controller_compact_propagates_budget_state_metadata():
    compact = await bridge._runtime_controller_compact(state, "budget_compact")
    assert compact.metadata["compaction_source"] == "pipeline"
    assert "budget_state" in compact.metadata
```

**Step 2: Run test to verify it fails**

Run: `pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -k propagates_budget_state_metadata -v`
Expected: FAIL if compact metadata path drops pipeline metadata.

**Step 3: Write minimal implementation**

```python
metadata={
    "compaction_source": "pipeline",
    "compression_operations": list(result.operations),
    **dict(result.metadata),
}
```

如果测试已通过，不改生产代码，仅保留测试作为回归保护。

**Step 4: Run test to verify it passes**

Run: `pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -k propagates_budget_state_metadata -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_gateway_adapter.py backend/src/gateway/agent_bridge.py
git commit -m "test(runtime): guard compact budget metadata propagation"
```

### Task 4: 回归验证与收口

**Files:**
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Run focused pipeline suite**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -v`
Expected: 新增测试通过，已有失败项不新增。

**Step 2: Run verifier suite**

Run: `pytest --no-cov backend/tests/unit/test_runtime_compression_verifier.py -v`
Expected: PASS

**Step 3: Run gateway compact regression test**

Run: `pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -k runtime_controller_compact -v`
Expected: PASS

**Step 4: Capture deltas in plan notes**

```text
- 已修复: budget_state 元数据缺失
- 已保护: compact metadata 透传
- 未触碰: 与本任务无关的既有失败用例
```

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_gateway_adapter.py backend/src/runtime/context/compression_pipeline.py
git commit -m "test(runtime): enforce budget-state metadata contract"
```
