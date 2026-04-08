# Runtime Compression Failing Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add high-signal failing tests that lock the runtime compression invariants identified in review findings before any production-code updates.

**Architecture:** We will extend the existing runtime unit suites first (TDD red phase) to enforce stronger autocompact pressure assertions and explicit must-fit behavior contracts. The implementation phase then makes minimal changes in `compression_pipeline.py` to satisfy those tests without broad refactors.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, runtime compression pipeline (`src/runtime/context/compression_pipeline.py`), runtime gateway bridge (`src/gateway/agent_bridge.py`).

---

### Task 1: Strengthen autocompact pressure regression test

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_pipeline.py` (existing `test_compression_pipeline_autocompacts_when_pressure_remains_high`)
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

Replace the weak assertions in `test_compression_pipeline_autocompacts_when_pressure_remains_high` with strict checks:

```python
assert "autocompact" in result.operations
assert result.operations.count("autocompact") == 1
assert "collapse" not in result.operations
assert result.estimated_input_tokens < ctx.estimated_input_tokens
assert result.estimated_input_tokens <= int(ctx.model_context_window * ctx.profile.pressure.red_pct)
summary = next(
    message["content"]
    for message in result.messages
    if message["content"].startswith("[Auto-compacted history]")
)
assert "Objective: Task" in summary
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_autocompacts_when_pressure_remains_high -v --no-cov
```

Expected: FAIL if autocompact path does not reduce tokens enough or does not produce expected summary structure.

**Step 3: Write minimal implementation**

Only if red: update `backend/src/runtime/context/compression_pipeline.py` `_autocompact` to ensure candidate reduction meets pressure contract for this scenario.

**Step 4: Run test to verify it passes**

Run same command and expect PASS.

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/src/runtime/context/compression_pipeline.py
git commit -m "test(runtime): strengthen autocompact pressure regression contract"
```

---

### Task 2: Add must-fit budget contract test (pipeline-level)

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`

**Step 1: Write the failing test**

Add a new test that forces must-fit pressure lower than red threshold and verifies the final output fits `must_fit` expectation, not only `red_pct`:

```python
@pytest.mark.asyncio
async def test_compression_pipeline_honors_budget_must_fit_tokens_threshold():
    pipeline = DefaultCompressionPipeline()
    profile = CompressionProfile()
    profile.autocompact.trigger_pct = 0.20
    profile.collapse.enabled = False
    budget = BudgetSnapshot.from_profile(TurnBudgetProfile())
    budget.must_fit_input_tokens = 24

    ctx = CompressionContext(
        session_key="s1",
        turn=3,
        task_frame=TaskFrame(objective="Task"),
        profile=profile,
        model_context_window=100,
        estimated_input_tokens=95,
        messages=[{"role": "user", "content": f"message {i} " + ("x" * 120)} for i in range(20)],
        active_artifacts=[],
        budget=budget,
    )

    result = await pipeline.run(ctx)

    assert result.estimated_input_tokens <= 24
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_honors_budget_must_fit_tokens_threshold -v --no-cov
```

Expected: FAIL because current `_must_fit_tokens` ignores `ctx.budget.must_fit_input_tokens`.

**Step 3: Write minimal implementation**

Update `_must_fit_tokens` in `backend/src/runtime/context/compression_pipeline.py` to prefer `ctx.budget.must_fit_input_tokens` when it is a positive integer, with fallback to `int(model_context_window * red_pct)`.

Minimal implementation target:

```python
def _must_fit_tokens(self, ctx: CompressionContext) -> int:
    budget_must_fit = int(getattr(ctx.budget, "must_fit_input_tokens", 0) or 0)
    if budget_must_fit > 0:
        return budget_must_fit
    return int(ctx.model_context_window * ctx.profile.pressure.red_pct)
```

**Step 4: Run test to verify it passes**

Run same command and expect PASS.

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/src/runtime/context/compression_pipeline.py
git commit -m "fix(runtime): honor must-fit token threshold in compression pipeline"
```

---

### Task 3: Add verifier-side must-fit metadata regression test

**Files:**
- Modify: `backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_compression_verifier.py`

**Step 1: Write the failing test**

Add a verifier metadata contract test to ensure a too-low `token_gain` against a configured minimum is rejected explicitly:

```python
def test_compression_verifier_rejects_when_compression_gain_below_required_minimum():
    verifier = DefaultCompressionVerifier()
    request = CompressionVerifyRequest(
        task_frame=TaskFrame(objective="Task"),
        original_messages=[{"role": "user", "content": "x" * 200}],
        compressed_messages=[{"role": "system", "content": "[Collapsed history]"}],
        metadata={
            "token_gain": 5,
            "min_compression_gain_tokens": 20,
        },
    )

    result = verifier.verify(request)

    assert result.ok is False
    assert result.preserved_fields["compression_gain"] is False
    assert "compression_gain_below_threshold" in result.reasons
```

**Step 2: Run test to verify it fails (if missing behavior)**

Run:

```bash
pytest backend/tests/unit/test_runtime_compression_verifier.py::test_compression_verifier_rejects_when_compression_gain_below_required_minimum -v --no-cov
```

Expected: If behavior already exists, this may pass immediately; in that case keep the test as regression coverage and skip implementation.

**Step 3: Write minimal implementation (only if red)**

If failing, adjust `_compression_gain_ok` handling in `backend/src/runtime/context/compression_verifier.py`.

**Step 4: Run test to verify it passes**

Run same command and expect PASS.

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_compression_verifier.py backend/src/runtime/context/compression_verifier.py
git commit -m "test(runtime): lock compression gain verifier contract"
```

---

### Task 4: Add gateway adapter metadata passthrough regression test

**Files:**
- Modify: `backend/tests/unit/test_runtime_gateway_adapter.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Write the failing test**

Add a test proving pipeline metadata keys survive wrapping into `CompactResult` unchanged:

```python
@pytest.mark.asyncio
async def test_agent_bridge_runtime_controller_compact_preserves_pipeline_metadata_keys():
    from src.runtime.context.compression_pipeline import CompressionResult

    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-compact-meta", session_id="sess-compact-meta"),
        user_input="compress now",
        task_frame=TaskFrame(objective="Task"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.active_messages = [{"role": "user", "content": "x" * 200}]

    bridge._runtime_compression_pipeline.run = AsyncMock(  # type: ignore[method-assign]
        return_value=CompressionResult(
            messages=[{"role": "system", "content": "[Collapsed history]"}],
            active_artifacts=[],
            estimated_input_tokens=20,
            operations=["autocompact"],
            metadata={"rollback_applied": False, "must_fit_target": 24},
        )
    )

    result = await bridge._runtime_controller_compact(state, "budget_compact")

    assert result.metadata["compaction_source"] == "pipeline"
    assert result.metadata["compression_operations"] == ["autocompact"]
    assert result.metadata["rollback_applied"] is False
    assert result.metadata["must_fit_target"] == 24
```

**Step 2: Run test to verify it fails (if regression exists)**

Run:

```bash
pytest backend/tests/unit/test_runtime_gateway_adapter.py::test_agent_bridge_runtime_controller_compact_preserves_pipeline_metadata_keys -v --no-cov
```

Expected: PASS or FAIL depending on current bridge behavior. Keep it as permanent regression lock either way.

**Step 3: Write minimal implementation (only if red)**

If red, patch `backend/src/gateway/agent_bridge.py` `_runtime_controller_compact` metadata merge.

**Step 4: Run test to verify it passes**

Run same command and expect PASS.

**Step 5: Commit**

```bash
git add backend/tests/unit/test_runtime_gateway_adapter.py backend/src/gateway/agent_bridge.py
git commit -m "test(runtime): lock compact metadata passthrough behavior"
```

---

### Task 5: Run focused runtime suite and finalize

**Files:**
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_compression_verifier.py`
- Test: `backend/tests/unit/test_runtime_gateway_adapter.py`

**Step 1: Run focused suite**

Run:

```bash
pytest \
  backend/tests/unit/test_runtime_compression_pipeline.py \
  backend/tests/unit/test_runtime_compression_verifier.py \
  backend/tests/unit/test_runtime_gateway_adapter.py \
  -v --no-cov
```

Expected: all selected tests PASS.

**Step 2: Confirm no unintended file edits**

Run:

```bash
git status
```

Expected: only intended runtime test/runtime compression files are modified.

**Step 3: Final commit**

If changes span multiple tasks and no intermediate commits were made:

```bash
git add backend/tests/unit/test_runtime_compression_pipeline.py backend/tests/unit/test_runtime_compression_verifier.py backend/tests/unit/test_runtime_gateway_adapter.py backend/src/runtime/context/compression_pipeline.py backend/src/runtime/context/compression_verifier.py backend/src/gateway/agent_bridge.py
git commit -m "test(runtime): add failing-test contracts for compression invariants"
```

**Step 4: Hand-off validation note**

Document in PR description which tests were intentionally red-first and which were pure regression locks that passed immediately.
