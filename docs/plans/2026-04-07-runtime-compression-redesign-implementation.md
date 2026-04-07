# Runtime Compression Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 runtime compression redesign 落地为唯一在线压缩主链路，完成契约收敛、真实校验回滚、应急压缩与持久化事件闭环。

**Architecture:** 以 `GatewayAdapter/AgentBridge` 负责请求与持久化编排，`TurnController` 仅输出 compact/continue/stop 决策，`compression_pipeline + verifier` 作为唯一压缩治理域。实现阶段按“先测试、后实现、再收敛开关”的顺序推进，确保可回滚、可观测、可分阶段上线。所有改动坚持 DRY/YAGNI，并按小步提交。

**Tech Stack:** Python 3.11, FastAPI runtime backend, pytest/pytest-asyncio, dataclass-based runtime types, in-memory runtime repositories.

---

> 设计输入文档：`/Users/xuan.lx/Documents/x-agent/docs/plans/2026-04-07-runtime-compression-redesign-design.md`
>
> 实施过程请同时使用：`@superpowers:test-driven-development` + `@superpowers:verification-before-completion`。

### Task 1: 收敛压缩输入/输出契约（runtime context 层）

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_verifier.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/types.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py`

**Step 1: Write the failing test**

```python
async def test_pipeline_result_exposes_contract_fields_for_verifier_and_rollback():
    result = await pipeline.run(ctx)
    assert "verifier_result" in result.metadata
    assert "rollback_applied" in result.metadata
    assert isinstance(result.operations, list)
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_result_exposes_contract_fields_for_verifier_and_rollback -v`
Expected: FAIL with missing metadata keys / contract mismatch.

**Step 3: Write minimal implementation**

```python
# compression_pipeline.py
result.metadata["verifier_result"] = verifier_result.to_dict()
result.metadata["rollback_applied"] = rollback_applied
result.metadata["rollback_reason"] = rollback_reason
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_result_exposes_contract_fields_for_verifier_and_rollback -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/src/runtime/context/compression_verifier.py backend/src/runtime/types.py backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py
git commit -m "feat(runtime): align compression result contract with verifier and rollback state"
```

### Task 2: 强化 verifier 真实性（before/after 快照）

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_verifier.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py`

**Step 1: Write the failing test**

```python
def test_verifier_rejects_when_after_uses_inconsistent_snapshot_fields():
    request = CompressionVerifyRequest(before=before_ctx, after=forged_after_ctx)
    result = verifier.verify(request)
    assert result.ok is False
    assert result.reason == "objective_mismatch"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_verifier.py::test_verifier_rejects_when_after_uses_inconsistent_snapshot_fields -v`
Expected: FAIL because verifier currently accepts weak/incomplete comparison.

**Step 3: Write minimal implementation**

```python
# compression_verifier.py
if before.objective != after.objective:
    return CompressionPostCheck(ok=False, reason="objective_mismatch", preserved_fields={"objective": False})
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_verifier.py::test_verifier_rejects_when_after_uses_inconsistent_snapshot_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_verifier.py backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py
git commit -m "fix(runtime): enforce verifier checks on real before-after snapshots"
```

### Task 3: 回滚与 compression_event 持久化打通

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_bridge.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/session/orchestrator.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_session_orchestrator.py`

**Step 1: Write the failing test**

```python
async def test_pipeline_records_rollback_reason_and_bridge_persists_event():
    result = await pipeline.run(ctx_with_forced_verifier_fail)
    assert result.metadata["rollback_applied"] is True
    assert result.metadata["rollback_reason"] == "artifact_refs_not_preserved"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_records_rollback_reason_and_bridge_persists_event -v`
Expected: FAIL with missing rollback metadata or no event append.

**Step 3: Write minimal implementation**

```python
# agent_bridge.py in _runtime_record_compression_events
await self.runtime_session_orchestrator.append_compression_event(
    CompressionEventRecord(..., metadata={"rollback_reason": rollback_reason, "operations": list(result.operations)})
)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_pipeline_records_rollback_reason_and_bridge_persists_event backend/tests/unit/test_runtime_gateway_adapter.py::test_agent_bridge_runtime_model_call_uses_runtime_context_pipeline_not_legacy_adapter -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/src/gateway/agent_bridge.py backend/src/runtime/session/orchestrator.py backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_gateway_adapter.py backend/tests/unit/test_runtime_session_orchestrator.py
git commit -m "feat(runtime): persist rollback-aware compression events"
```

### Task 4: Gateway/Turn 层契约收敛（只输出决策，不泄漏压缩细节）

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/turn/controller.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/turn/assessment.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/adapters/gateway_adapter.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_turn_controller.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Write the failing test**

```python
def test_turn_controller_compact_decision_does_not_embed_pipeline_stage_details():
    result = asyncio.run(controller.run(request))
    assert result.metadata.get("compression_stage") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_turn_controller.py::test_turn_controller_compact_decision_does_not_embed_pipeline_stage_details -v`
Expected: FAIL if controller metadata leaks stage internals.

**Step 3: Write minimal implementation**

```python
# controller.py
metadata = self._metadata(state)
metadata.pop("compression_stage", None)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_turn_controller.py::test_turn_controller_compact_decision_does_not_embed_pipeline_stage_details backend/tests/unit/test_runtime_gateway_adapter.py::test_runtime_gateway_adapter_prepares_turn_from_envelope -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/turn/controller.py backend/src/runtime/turn/assessment.py backend/src/runtime/adapters/gateway_adapter.py backend/tests/unit/test_runtime_turn_controller.py backend/tests/unit/test_runtime_gateway_adapter.py
git commit -m "refactor(runtime): keep compression details inside context governance layer"
```

### Task 5: 单主链路切换（legacy manager 降级为显式兜底）

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/agent_core/adapters/context_adapter.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/manager.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_bridge.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_budget_controls.py`

**Step 1: Write the failing test**

```python
async def test_runtime_path_is_default_and_legacy_only_used_when_force_flag_enabled():
    result = await bridge.run_runtime_turn(request)
    assert result.metadata.get("legacy_bridge") is not True
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_gateway_adapter.py::test_runtime_path_is_default_and_legacy_only_used_when_force_flag_enabled -v`
Expected: FAIL if legacy path is still implicitly selected.

**Step 3: Write minimal implementation**

```python
# context_adapter.py
if request.metadata.get("runtime_force_legacy_bridge") is True:
    return await self._manager.prepare_context(...)
return await self._prepare_runtime_context(...)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_gateway_adapter.py::test_runtime_path_is_default_and_legacy_only_used_when_force_flag_enabled backend/tests/unit/test_runtime_budget_controls.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agent_core/adapters/context_adapter.py backend/src/services/compression/manager.py backend/src/gateway/agent_bridge.py backend/tests/unit/test_runtime_gateway_adapter.py backend/tests/unit/test_runtime_budget_controls.py
git commit -m "feat(runtime): switch to runtime-first compression with explicit legacy fallback"
```

### Task 6: 应急压缩策略与性能回归门禁

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/compression_pipeline.py`
- Modify: `/Users/xuan.lx/Documents/x-agent/backend/src/runtime/context/profile_provider.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_budget_controls.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_resume_flow.py`

**Step 1: Write the failing test**

```python
async def test_emergency_compact_keeps_tail_and_marks_fallback_used():
    result = await pipeline.run_emergency(ctx)
    assert result.metadata["fallback_summary_used"] is True
    assert result.operations == ["emergency_compact"]
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_emergency_compact_keeps_tail_and_marks_fallback_used -v`
Expected: FAIL if fallback metadata/operation contract is missing.

**Step 3: Write minimal implementation**

```python
# compression_pipeline.py
return CompressionResult(
    messages=trimmed,
    operations=["emergency_compact"],
    metadata={"fallback_summary_used": True},
)
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_emergency_compact_keeps_tail_and_marks_fallback_used backend/tests/unit/test_runtime_budget_controls.py backend/tests/integration/test_runtime_resume_flow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/src/runtime/context/profile_provider.py backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_budget_controls.py backend/tests/integration/test_runtime_resume_flow.py
git commit -m "feat(runtime): harden emergency compression strategy and regression coverage"
```

### Task 7: 全链路验收与文档同步

**Files:**
- Modify: `/Users/xuan.lx/Documents/x-agent/arch/compact/compact.md`
- Modify: `/Users/xuan.lx/Documents/x-agent/docs/plans/2026-04-07-runtime-compression-redesign-design.md`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_turn_controller.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_session_orchestrator.py`
- Test: `/Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_runtime_resume_flow.py`

**Step 1: Write the failing test**

```python
def test_runtime_compression_redesign_acceptance_matrix_is_satisfied():
    # 该测试作为聚合检查入口，校验关键 case 已被覆盖并可执行
    assert run_acceptance_matrix() is True
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/integration/test_runtime_resume_flow.py -v`
Expected: FAIL (coverage gaps / assertion mismatch before final sync).

**Step 3: Write minimal implementation**

```python
# 同步 acceptance matrix 到现有测试与文档，补齐缺口 case
ACCEPTANCE_CASES = [
    "rollback_on_verifier_fail",
    "emergency_tail_preserved",
    "resume_snapshot_priority",
]
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_turn_controller.py backend/tests/unit/test_runtime_gateway_adapter.py backend/tests/unit/test_runtime_session_orchestrator.py backend/tests/integration/test_runtime_resume_flow.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add arch/compact/compact.md docs/plans/2026-04-07-runtime-compression-redesign-design.md backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_turn_controller.py backend/tests/unit/test_runtime_gateway_adapter.py backend/tests/unit/test_runtime_session_orchestrator.py backend/tests/integration/test_runtime_resume_flow.py
git commit -m "docs(runtime): sync redesign acceptance criteria and verification matrix"
```

## 执行顺序与检查点

1. 按 Task 1 → Task 7 顺序执行，不并行跨层改动。
2. 每个 Task 完成后必须执行对应最小测试命令，再执行该 Task commit。
3. Task 5（单主链路切换）前必须保证 Task 1-4 全部绿色。
4. Task 7 前必须先跑一次全量相关单测，记录失败项后再补齐。

## 最终验收命令

```bash
pytest backend/tests/unit/test_runtime_compression_pipeline.py \
       backend/tests/unit/test_runtime_compression_verifier.py \
       backend/tests/unit/test_runtime_turn_controller.py \
       backend/tests/unit/test_runtime_gateway_adapter.py \
       backend/tests/unit/test_runtime_session_orchestrator.py \
       backend/tests/unit/test_runtime_budget_controls.py \
       backend/tests/integration/test_runtime_resume_flow.py -v
```

预期：全部 PASS，且不出现新增 flaky、timeout 级别回归。
