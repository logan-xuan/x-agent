# Repo-Root Config Path Resolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the default backend configuration resolution work when tests or application entrypoints are launched from the repository root, while preserving explicit `config_path` overrides.

**Architecture:** Keep `ConfigManager`'s public API unchanged and only change how its default path is derived. Instead of relying on the current working directory, compute the default config path from `backend/src/config/manager.py`'s location so the implicit config always points at `backend/x-agent.yaml`. Cover the change with focused unit tests that verify both repo-root behavior and explicit override behavior.

**Tech Stack:** Python 3.11+, pathlib, pytest, monkeypatch, existing backend config loader

---

### Task 1: Add regression tests for default and explicit config paths

**Files:**
- Create: `backend/tests/unit/test_config_manager.py`
- Modify: `backend/src/config/manager.py`

**Step 1: Write the failing tests**

Create `backend/tests/unit/test_config_manager.py` with focused singleton-reset coverage:

```python
from pathlib import Path
from unittest.mock import sentinel

import pytest

from src.config.manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_config_manager_singleton() -> None:
    ConfigManager._instance = None
    yield
    ConfigManager._instance = None


def test_config_manager_loads_backend_config_when_cwd_is_repo_root(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    expected_path = repo_root / "backend" / "x-agent.yaml"
    captured: dict[str, Path] = {}

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        "src.config.manager.load_config",
        lambda path: captured.setdefault("path", path) or sentinel.config,
    )

    manager = ConfigManager()

    assert manager.config is sentinel.config
    assert captured["path"] == expected_path
    assert manager.config_path == expected_path


def test_config_manager_preserves_explicit_config_path_override(tmp_path: Path, monkeypatch) -> None:
    custom_path = tmp_path / "custom-x-agent.yaml"
    captured: dict[str, Path] = {}

    monkeypatch.setattr(
        "src.config.manager.load_config",
        lambda path: captured.setdefault("path", path) or sentinel.config,
    )

    manager = ConfigManager(config_path=custom_path)

    assert manager.config is sentinel.config
    assert captured["path"] == custom_path
    assert manager.config_path == custom_path
```

If the `lambda ... or sentinel.config` pattern is too opaque, replace it with a small local function that stores `path` then returns `sentinel.config`.

**Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_config_manager.py -v --no-cov
```

Expected: the repo-root test FAILS because `ConfigManager` currently uses `Path("x-agent.yaml")`, which resolves to `<repo>/x-agent.yaml` instead of `<repo>/backend/x-agent.yaml`.

**Step 3: Commit the red tests**

```bash
git add backend/tests/unit/test_config_manager.py
git commit -m "test(config): add repo-root config path regression coverage"
```

---

### Task 2: Make default config resolution independent of current working directory

**Files:**
- Modify: `backend/src/config/manager.py`
- Test: `backend/tests/unit/test_config_manager.py`

**Step 1: Write the minimal implementation**

Update `backend/src/config/manager.py` so the default path is derived from the module location:

```python
class ConfigManager:
    ...

    @staticmethod
    def _default_config_path() -> Path:
        return Path(__file__).resolve().parents[2] / "x-agent.yaml"

    def __init__(self, config_path: Path | None = None) -> None:
        if self._initialized:
            return

        self._config_path = config_path or self._default_config_path()
        self._config: Config | None = None
        ...
```

Notes:
- `manager.py` lives at `backend/src/config/manager.py`, so `Path(__file__).resolve().parents[2]` resolves to the `backend/` directory.
- Do not change any call sites.
- Do not add environment-variable or CLI fallback logic; that is outside the approved scope.

**Step 2: Run the focused tests to verify they pass**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_config_manager.py -v --no-cov
```

Expected: PASS.

**Step 3: Run one real runtime regression from repo root**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent && pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass -v --no-cov
```

Expected: PASS, proving repo-root execution now finds `backend/x-agent.yaml` through the default path.

**Step 4: Commit the implementation**

```bash
git add backend/src/config/manager.py backend/tests/unit/test_config_manager.py
git commit -m "fix(config): resolve default config from backend root"
```

---

### Task 3: Verify no config-path regressions in existing config consumers

**Files:**
- Test: `backend/tests/unit/test_config_manager.py`
- Test: `backend/tests/unit/test_runtime_compression_pipeline.py`
- Test: `backend/tests/unit/test_runtime_turn_controller.py`

**Step 1: Run the focused verification set**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent/backend && pytest tests/unit/test_config_manager.py tests/unit/test_runtime_turn_controller.py -v --no-cov
```

Expected: PASS.

**Step 2: Re-run the repo-root regression proof**

Run:

```bash
cd /Users/xuan.lx/Documents/x-agent && pytest backend/tests/unit/test_runtime_compression_pipeline.py::test_compression_pipeline_exposes_budget_state_metadata_from_runtime_pass -v --no-cov
```

Expected: PASS.

**Step 3: Confirm only intended files changed**

Run:

```bash
git status --short
```

Expected: only `backend/src/config/manager.py` and `backend/tests/unit/test_config_manager.py` are newly changed for this task unless the user requested additional cleanup.

**Step 4: Final commit if Task 1 red-test commit was skipped**

```bash
git add backend/src/config/manager.py backend/tests/unit/test_config_manager.py
git commit -m "fix(config): support repo-root config loading"
```

Use this final commit only if the earlier per-task commits were intentionally skipped.
