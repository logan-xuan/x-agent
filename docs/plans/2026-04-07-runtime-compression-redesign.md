# Runtime Compression Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 runtime 压缩从固定阶段流水线收敛为预算驱动、具备语义护栏与唯一状态快照的上下文治理机制。

**Architecture:** 保留 `DefaultCompressionPipeline` 作为外部入口，但内部引入预算状态、消息语义分析、唯一 collapse state 与增强 verifier。先以 runtime pipeline 和 verifier 为中心完成闭环，再让 turn controller 的 compact hook 真正接上 pipeline 结果。

**Tech Stack:** Python 3.11+, dataclasses, pytest, existing runtime context/turn modules

---

### Task 1: 建立预算状态与语义分析骨架

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
def test_compression_pipeline_detects_repeated_summaries_and_terminal_overrides():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k repeated_summaries -v`
Expected: FAIL because semantic analysis helpers do not exist yet.

**Step 3: Write minimal implementation**

- 新增 `AnalyzedMessage`、`CompressionBudgetState` 数据结构。
- 新增 `_analyze_messages()`、`_build_budget_state()`。
- 识别 summary、status、tool、chatter；识别 `done/failed/cancelled` 覆盖 `pending/running/delegated`。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k repeated_summaries -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "feat(runtime): add compression semantic analysis"
```

### Task 2: 用语义规则重写 microcompact

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_microcompact_removes_redundant_summaries_and_superseded_statuses():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k microcompact_removes_redundant -v`
Expected: FAIL because microcompact still only trims tool payloads.

**Step 3: Write minimal implementation**

- 让 `microcompact` 优先删除 P3：重复 `[Collapsed history]` / `[Auto-compacted history]`、礼貌播报、被终态覆盖的状态。
- 保留 objective/unresolved/最近关键结论。
- 仅在还需要时再对大 tool 内容做结构化摘录。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k microcompact_removes_redundant -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "feat(runtime): make microcompact semantics-aware"
```

### Task 3: 用唯一状态快照重写 collapse

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_collapse_rewrites_history_into_single_state_snapshot():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k single_state_snapshot -v`
Expected: FAIL because collapse still appends free-form message summaries.

**Step 3: Write minimal implementation**

- 新增 `CollapseState` 与 formatter。
- collapse 从 archived history 抽取 objective、unresolved、finalized_tasks、active_failures、artifact_refs、evidence_summaries。
- 输出唯一 `[Collapsed history]` 状态快照，避免 summary 套 summary。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k single_state_snapshot -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "feat(runtime): rewrite collapse as state snapshot"
```

### Task 4: 用 must-fit 目标重写 autocompact

**Files:**
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_autocompact_stops_once_budget_target_is_met():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k budget_target_is_met -v`
Expected: FAIL because autocompact does not iterate toward a target budget.

**Step 3: Write minimal implementation**

- 引入 `observe_tokens / target_tokens / must_fit_tokens`。
- `autocompact` 按优先级压缩 P2/P1 内容，每步重算 token，达标即停。
- 无法达标时保留 emergency 入口。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py -k budget_target_is_met -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_pipeline.py backend/tests/unit/test_runtime_compression_pipeline.py
git commit -m "feat(runtime): make autocompact budget-driven"
```

### Task 5: 扩展 verifier 语义护栏

**Files:**
- Modify: `backend/src/runtime/context/compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_compression_verifier.py`

**Step 1: Write the failing test**

```python
def test_compression_verifier_rejects_conflicting_terminal_and_running_states():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_compression_verifier.py -k conflicting_terminal -v`
Expected: FAIL because verifier does not detect state conflicts or duplicate objectives yet.

**Step 3: Write minimal implementation**

- 增加 objective 唯一性、unresolved 可追溯性、终态覆盖冲突、结论保真、最小压缩收益校验。
- 将这些结果写入 `preserved_fields`/`reasons`。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_compression_verifier.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/context/compression_verifier.py backend/tests/unit/test_runtime_compression_verifier.py
git commit -m "feat(runtime): extend compression verifier semantics"
```

### Task 6: 让 turn controller 的 compact 决策真正闭环

**Files:**
- Modify: `backend/src/runtime/turn/controller.py`
- Test: `backend/tests/unit/test_runtime_turn_controller.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_turn_controller_compact_path_updates_state_with_real_compaction_result():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_runtime_turn_controller.py -k real_compaction_result -v`
Expected: FAIL because default compact hook only mutates metadata.

**Step 3: Write minimal implementation**

- 为 controller 补充 compact result contract。
- 将 pipeline 产物回写到 turn state metadata / active context 输入位。
- 保留默认 stub，但让 runtime 集成路径可以注入真实闭环 compact_fn。

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_runtime_turn_controller.py -k real_compaction_result -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/runtime/turn/controller.py backend/tests/unit/test_runtime_turn_controller.py
git commit -m "feat(runtime): close controller compaction loop"
```

### Task 7: 运行回归、请求代码评审并做端到端验证

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Modify: `backend/tests/unit/test_runtime_compression_verifier.py`
- Modify: `backend/tests/unit/test_runtime_turn_controller.py`
- Modify: `backend/src/runtime/context/compression_pipeline.py`
- Modify: `backend/src/runtime/context/compression_verifier.py`
- Modify: `backend/src/runtime/turn/controller.py`

**Step 1: Run focused unit suites**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_turn_controller.py -v`
Expected: PASS

**Step 2: Run broader runtime regression**

Run: `pytest backend/tests/unit/test_runtime_* -v`
Expected: PASS

**Step 3: Request code review**

- 用 `superpowers:code-reviewer` 审查 compact redesign 改动。
- 修复 Critical/Important 问题后再继续。

**Step 4: Run end-to-end verification**

Run: `pytest backend/tests/integration -k runtime -v`
Expected: PASS, or if environment missing config, capture the exact blocker and verify the highest-fidelity available runtime integration path.

**Step 5: Final verification**

Run: `pytest backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_turn_controller.py -v`
Expected: PASS with fresh evidence before any completion claim.
