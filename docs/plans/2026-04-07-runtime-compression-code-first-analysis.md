# Runtime Compression Code-First Analysis Document Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a strictly code-backed compression architecture analysis and redesign document at `arch/compact/compact.md`.

**Architecture:** The plan reverse-engineers the current runtime+legacy compression behavior directly from Python code and unit tests, then writes a single analysis artifact with explicit current-state chains, diagrams, evidence, and refactor guidance. Every claim must map to concrete files/tests, and no architecture markdown files are used as source-of-truth.

**Tech Stack:** Markdown, Mermaid, Python runtime modules, FastAPI gateway/runtime adapters, pytest unit tests

---

### Task 1: Build code-backed source inventory

**Files:**
- Read: `backend/src/runtime/adapters/gateway_adapter.py`
- Read: `backend/src/runtime/session/orchestrator.py`
- Read: `backend/src/runtime/turn/budget.py`
- Read: `backend/src/runtime/turn/controller.py`
- Read: `backend/src/runtime/context/compression_pipeline.py`
- Read: `backend/src/runtime/context/compression_verifier.py`
- Read: `backend/src/runtime/types.py`
- Read: `backend/src/config/models.py`

**Step 1: Trace runtime request entry and profile injection**
Run: `python - <<'PY'\nfrom pathlib import Path\nprint(Path('backend/src/runtime/adapters/gateway_adapter.py').exists())\nPY`
Expected: `True`

**Step 2: Record exact trigger points with file:line references**
Capture references for:
- `_runtime_budget_profile` and `_runtime_compression_profile_name` injection
- `BudgetDecision.compact(...)` and `BudgetDecision.stop(...)` paths
- `DefaultTurnController.run(...)` compact/stop branches

**Step 3: Record pipeline stage order from code**
Document exact order from `DefaultCompressionPipeline.run(...)`:
1) persist
2) aggregate_budget
3) ttl_prune
4) microcompact
5) collapse
6) autocompact
7) memory_flush
8) verifier + rollback

**Step 4: Record emergency behavior from code**
Document exact behavior of `run_emergency(...)`:
- keep leading system message (if present)
- inject `[Emergency context summary]`
- keep recent tail (`retain_recent_messages`)
- return `operations=["emergency_compact"]`

**Step 5: Commit inventory notes**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): map runtime compression chain from code"
```

### Task 2: Verify alternate/legacy compression paths

**Files:**
- Read: `backend/src/agent_core/adapters/context_adapter.py`
- Read: `backend/src/services/compression/manager.py`
- Read: `backend/src/services/context/context_assembler.py`
- Read: `backend/src/agent_core/agent_loop.py`

**Step 1: Confirm legacy manager involvement**
Run: `pytest backend/tests/unit/test_runtime_budget_controls.py::TestRuntimeBudgetControls::test_context_adapter_stateful_mode_bypasses_legacy_compression -v`
Expected: PASS

**Step 2: Confirm hybrid mode still calls manager path**
Run: `pytest backend/tests/unit/test_runtime_budget_controls.py::TestRuntimeBudgetControls::test_context_adapter_hybrid_mode_uses_context_assembler -v`
Expected: PASS

**Step 3: Capture coexistence conclusion**
Write evidence bullets describing runtime path + legacy path coexistence and where each is called.

**Step 4: Commit legacy-path evidence**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): add runtime and legacy coexistence evidence"
```

### Task 3: Draft document skeleton and current-state chain

**Files:**
- Create/Modify: `arch/compact/compact.md`

**Step 1: Write fixed section skeleton**
Include:
1. 背景与目标
2. 当前代码压缩机制全链路
3. 当前机制合理性评估
4. 关键问题与根因
5. 推荐改造方案
6. 图示
7. 案例分析
8. 分阶段落地建议

**Step 2: Write code-first chain with precise references**
For each step, include explicit references like:
- `backend/src/gateway/dispatcher.py`
- `backend/src/runtime/adapters/gateway_adapter.py`
- `backend/src/runtime/turn/controller.py`
- `backend/src/runtime/context/compression_pipeline.py`
- `backend/src/runtime/session/orchestrator.py`

**Step 3: Add current strengths and risks bullets**
Include only claims supported by current code/tests.

**Step 4: Commit skeleton and chain**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): add code-backed current-state chain"
```

### Task 4: Add executable diagrams (architecture + sequence + state)

**Files:**
- Modify: `arch/compact/compact.md`

**Step 1: Add one architecture diagram (Mermaid)**
Must include: gateway endpoint, dispatcher, gateway adapter, orchestrator, controller/budget, context builder/history view, compression pipeline, verifier, repositories, resume path.

**Step 2: Add normal-turn sequence diagram**
Flow: event ingress -> prepare turn -> assess budget/pressure -> select/apply compression -> verify -> emit model input -> persist side effects.

**Step 3: Add overflow/emergency sequence diagram**
Flow: overflow or insufficient normal compaction -> `run_emergency(...)` -> retry/finalize.

**Step 4: Add compression state diagram**
States: green/yellow/orange/red/emergency/rollback/stabilized with transitions tied to budget decisions and verifier outcomes.

**Step 5: Validate Mermaid blocks are syntactically valid**
Run: `python - <<'PY'\nfrom pathlib import Path\ntext=Path('arch/compact/compact.md').read_text()\nassert '```mermaid' in text\nprint('ok')\nPY`
Expected: `ok`

**Step 6: Commit diagrams**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): add architecture sequence and state diagrams"
```

### Task 5: Add code-backed case studies

**Files:**
- Modify: `arch/compact/compact.md`
- Evidence: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Evidence: `backend/tests/unit/test_runtime_gateway_adapter.py`
- Evidence: `backend/tests/unit/test_runtime_turn_controller.py`

**Step 1: Add case 1 (single huge tool output)**
Base on `_persist_large_results(...)` and `test_compression_pipeline_persists_large_tool_results`.

**Step 2: Add case 2 (aggregate over-budget multi-tool outputs)**
Base on `_aggregate_budget(...)` and related pipeline tests.

**Step 3: Add case 3 (resume with oversized active context)**
Base on `resume_session(...)` + `prepare_resumed_turn(...)` + resume tests.

**Step 4: Add case 4 (budget stop / emergency fallback split)**
Base on `DefaultBudgetManager.evaluate(...)`, `DefaultTurnController._finish_from_budget(...)`, and emergency pipeline tests.

**Step 5: Use fixed template for each case**
- 场景
- 当前机制如何处理
- 当前机制的问题
- 推荐机制如何处理
- 为什么更优

**Step 6: Commit case section**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): add operational case studies"
```

### Task 6: Add redesign and phased migration roadmap

**Files:**
- Modify: `arch/compact/compact.md`

**Step 1: Write target principle**
Use one line principle: “Compression is context governance for bounded reasoning, not text shortening.”

**Step 2: Define target layered model grounded in current code seams**
Layers:
- Raw transcript
- Summary chain
- Active history view
- Final model input
- Artifact/memory side stores

**Step 3: Define single decision center migration target**
Converge decisions currently split across:
- `backend/src/runtime/turn/budget.py`
- `backend/src/runtime/turn/controller.py`
- `backend/src/runtime/context/compression_pipeline.py`
- `backend/src/agent_core/adapters/context_adapter.py`
- `backend/src/services/compression/manager.py`

**Step 4: Define phases with concrete files**
- Phase 1: terminology + observability alignment
- Phase 2: single budget/compaction decision entry
- Phase 3: verifier quality gates strengthening
- Phase 4: semantic compression units + tool transaction integrity
- Phase 5: unified resume/emergency/memory flush closure

**Step 5: Commit redesign roadmap**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): add redesign and phased migration roadmap"
```

### Task 7: Evidence and consistency verification

**Files:**
- Verify: `arch/compact/compact.md`
- Verify against code/tests listed above

**Step 1: Verify all major claims map to code paths**
Run targeted checks with `rg`/read to confirm every diagram edge and chain claim has a code anchor.

**Step 2: Verify tested behaviors cited are real**
Run:
- `pytest backend/tests/unit/test_runtime_compression_pipeline.py -q`
- `pytest backend/tests/unit/test_runtime_compression_verifier.py -q`
- `pytest backend/tests/unit/test_runtime_turn_controller.py -q`
- `pytest backend/tests/unit/test_runtime_gateway_adapter.py -q`

Expected: PASS (or capture failures and adjust document claims to match reality).

**Step 3: Final deliverable check**
Confirm `arch/compact/compact.md` contains:
- current-state chain
- architecture diagram
- normal sequence diagram
- emergency sequence diagram
- state diagram
- >=4 cases
- clear redesign recommendation

**Step 4: Final commit**
```bash
git add arch/compact/compact.md
git commit -m "docs(compact): finalize code-first compression analysis blueprint"
```
