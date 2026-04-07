# Runtime Compression Single-Spine Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前 runtime/legacy 并存的压缩治理收敛为单一 runtime 在线主链路，并补齐可验证回滚与应急策略闭环。

**Architecture:** 以 runtime turn + runtime context pipeline 为唯一在线压缩执行面，adapter/gateway/orchestrator 仅传递材料与配置，不再分散治理决策。通过 verifier 使用真实 before/after 快照做质量闸门，失败时统一 rollback；正常压缩与 emergency 压缩纳入同一状态机语义。

**Tech Stack:** Python 3.11、FastAPI、dataclasses、pytest/pytest-asyncio。

---

### Task 1: 收敛入口契约（runtime 单链路开关）

**Files:**
- Modify: `backend/src/agent_core/adapters/context_adapter.py`
- Modify: `backend/src/runtime/adapters/gateway_adapter.py`
- Modify: `backend/src/runtime/turn/controller.py`
- Test: `backend/tests/unit/test_runtime_budget_controls.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_stateful_runtime_mode_never_calls_legacy_compression_manager():
    adapter = XAgentContextAdapter(...)
    await adapter.prepare_context(...)
    assert legacy_manager.prepare_context.await_count == 0


def test_gateway_metadata_marks_runtime_compression_authority():
    request = adapter.prepare_turn(...)
    assert request.metadata["_runtime_compression_authority"] == "runtime_pipeline"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_runtime_budget_controls.py::test_stateful_runtime_mode_never_calls_legacy_compression_manager tests/unit/test_runtime_gateway_adapter.py::test_gateway_metadata_marks_runtime_compression_authority -v`
Expected: FAIL（缺少 `_runtime_compression_authority` 或仍触发 legacy manager）。

**Step 3: Write minimal implementation**

```python
# context_adapter.py
if mode in {"stateful", "runtime"}:
    return runtime_result

# gateway_adapter.py
metadata["_runtime_compression_authority"] = "runtime_pipeline"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_runtime_budget_controls.py tests/unit/test_runtime_gateway_adapter.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add backend/src/agent_core/adapters/context_adapter.py backend/src/runtime/adapters/gateway_adapter.py backend/tests/unit/test_runtime_budget_controls.py backend/tests/unit/test_runtime_gateway_adapter.py
git commit -m "refactor(runtime): enforce runtime compression authority metadata"
```

---

### Task 2: 打通 compact 决策到真实 pipeline 执行

**Files:**
- Modify: `backend/src/runtime/turn/controller.py`
- Modify: `backend/src/runtime/session/orchestrator.py`
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_turn_controller.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_budget_compact_executes_runtime_pipeline_not_only_metadata():
    controller = DefaultTurnController(compact_fn=real_compact_fn, ...)
    result = await controller.run(request)
    assert result.metadata["compression_operations"]
    assert "compact" in result.metadata["runtime_event_timeline"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_runtime_turn_controller.py::test_budget_compact_executes_runtime_pipeline_not_only_metadata -v`
Expected: FAIL（当前默认 compact 仅标记 metadata）。

**Step 3: Write minimal implementation**

```python
# controller.py
state = await self.compact_fn(state, budget_decision.reason or "budget_compact")
state.metadata.setdefault("runtime_event_timeline", []).append("compact")

# compact_fn 实现回写
state.metadata["compression_operations"] = compression_result.operations
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_runtime_turn_controller.py tests/unit/test_runtime_compression_pipeline.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add backend/src/runtime/turn/controller.py backend/src/runtime/session/orchestrator.py backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_turn_controller.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "feat(runtime): execute real compression pipeline on compact decisions"
```

---

### Task 3: 强化 verifier 输入真实性（before/after 快照）

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Modify: `backend/src/runtime/context/compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
def test_verifier_detects_unresolved_loss_from_real_snapshot_diff():
    request = CompressionVerifyRequest(
        original_messages=[...],
        compressed_messages=[...],
        metadata={
            "compressed_unresolved": ["u1"],
            "recent_failures_before": ["f1"],
            "recent_failures_after": [],
            "objective_out_of_band": False,
        },
        ...
    )
    result = verifier.verify(request)
    assert result.ok is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_runtime_compression_verifier.py::test_verifier_detects_unresolved_loss_from_real_snapshot_diff -v`
Expected: FAIL（校验未严格基于 before/after 快照）。

**Step 3: Write minimal implementation**

```python
# compression_pipeline.py
verification = self.verifier.verify(
    CompressionVerifyRequest(
        ...,
        metadata={
            "objective_out_of_band": False,
            "compressed_unresolved": list(ctx.task_frame.unresolved),
            "recent_failures_before": list(ctx.metadata.get("recent_failures_before", [])),
            "recent_failures_after": list(ctx.metadata.get("recent_failures_after", [])),
        },
    )
)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_runtime_compression_verifier.py tests/unit/test_runtime_compression_pipeline.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/src/runtime/context/compression_verifier.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "fix(runtime): verify compression invariants from real before/after snapshots"
```

---

### Task 4: 统一 normal/emergency 压缩状态机语义

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Modify: `backend/src/runtime/turn/state.py`
- Modify: `backend/src/runtime/turn/controller.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_turn_controller.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_emergency_compact_records_state_machine_transition():
    result = await pipeline.run_emergency(ctx)
    assert result.metadata["compression_state"] == "emergency_compact"
    assert result.metadata["previous_state"] in {"normal_compact", "rollback"}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_runtime_compression_pipeline.py::test_emergency_compact_records_state_machine_transition -v`
Expected: FAIL（当前缺少统一状态字段）。

**Step 3: Write minimal implementation**

```python
# compression_pipeline.py
metadata={
    "compression_state": "emergency_compact",
    "previous_state": ctx.metadata.get("compression_state", "normal_compact"),
    ...
}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_runtime_compression_pipeline.py tests/unit/test_runtime_turn_controller.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/src/runtime/turn/state.py backend/src/runtime/turn/controller.py backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_turn_controller.py
git commit -m "feat(runtime): align emergency compression with unified state semantics"
```

---

### Task 5: 迁移收口与回归保障

**Files:**
- Modify: `backend/src/services/compression/manager.py`
- Modify: `backend/src/agent_core/adapters/context_adapter.py`
- Modify: `backend/x-agent.yaml.example`
- Test: `backend/tests/unit/test_runtime_budget_controls.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_runtime_authority_mode_disables_legacy_manager_path():
    prepared = await adapter.prepare_context(...)
    assert prepared.metadata["compression_path"] == "runtime"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_runtime_budget_controls.py::test_runtime_authority_mode_disables_legacy_manager_path -v`
Expected: FAIL（迁移开关未完全生效）。

**Step 3: Write minimal implementation**

```python
# manager.py / adapter.py
if runtime_authority_enabled:
    skip_legacy = True
```

并在 `x-agent.yaml.example` 补充迁移开关与回滚开关示例配置。

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_runtime_budget_controls.py tests/unit/test_runtime_gateway_adapter.py tests/unit/test_runtime_compression_pipeline.py -v`
Expected: PASS。

**Step 5: Commit**

```bash
git add backend/src/services/compression/manager.py backend/src/agent_core/adapters/context_adapter.py backend/x-agent.yaml.example backend/tests/unit/test_runtime_budget_controls.py backend/tests/unit/test_runtime_gateway_adapter.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "chore(runtime): add migration guardrails for single-spine compression rollout"
```

---

## Full Validation Checklist

- `cd backend && pytest tests/unit/test_runtime_turn_controller.py -v`
- `cd backend && pytest tests/unit/test_runtime_compression_pipeline.py -v`
- `cd backend && pytest tests/unit/test_runtime_compression_verifier.py -v`
- `cd backend && pytest tests/unit/test_runtime_gateway_adapter.py -v`
- `cd backend && pytest tests/unit/test_runtime_budget_controls.py -v`

Expected: 全部 PASS，且关键 metadata 字段可观测：
- `_runtime_compression_authority`
- `compression_operations`
- `compression_state`
- `runtime_event_timeline`

---

## Non-Goals (YAGNI)

- 不引入新的独立压缩服务进程。
- 不在本轮实现复杂语义摘要模型调用。
- 不扩展与压缩无关的会话协议字段。

---

## Execution Handoff Options

### Option A: Full TDD Batch Execution（推荐）
- 使用 `superpowers:executing-plans` 严格按 Task 1 → Task 5 顺序执行。
- 每个任务均执行“先写失败测试 → 最小实现 → 回归验证 → 小步提交”。
- 适用于当前需要最强可追溯性与回滚可控性的主干演进。

### Option B: Risk-First Slice（先高风险后收口）
- 先执行 Task 2 + Task 3（compact 执行闭环、verifier 真实性），再执行 Task 1/4/5。
- 优点是优先消除“只打 metadata 不真实压缩”和“弱校验通过”两类核心风险。
- 适用于短周期内先恢复质量闸门可信度。

### Option C: Contract-First Rollout（契约先行）
- 先执行 Task 1 + Task 5（入口 authority 与迁移开关），将 runtime/legacy 路径改为互斥。
- 再执行 Task 2/3/4 完成压缩状态机与校验增强。
- 适用于需要先稳定线上链路识别与灰度治理的场景。

## Recommended Handoff Package

1. 交接输入
   - 设计文档：`docs/plans/2026-04-07-runtime-compression-redesign-design.md`
   - 现状分析：`arch/compact/compact.md`
   - 本实施计划：`docs/plans/2026-04-07-compact-analysis-design.md`
2. 执行约束
   - 必须保持 Gateway 对外协议不变。
   - 每个 Task 完成后运行对应单测并记录结果。
   - 回滚事件与关键 metadata 字段需可观测（`_runtime_compression_authority`、`compression_operations`、`compression_state`、`runtime_event_timeline`）。
3. 完成定义
   - Full Validation Checklist 全部通过。
   - 文档中的关键场景回归（含 resume / rollback / emergency）均有测试覆盖。

