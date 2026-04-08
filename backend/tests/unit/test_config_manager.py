from pathlib import Path
from unittest.mock import sentinel

import pytest

from src.config.manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_config_manager_singleton() -> None:
    ConfigManager._instance = None
    yield
    ConfigManager._instance = None


def _capture_path(path: Path, captured: dict[str, Path]):
    captured["path"] = path
    return sentinel.config


def test_config_manager_loads_backend_config_when_cwd_is_repo_root(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    expected_path = repo_root / "backend" / "x-agent.yaml"
    captured: dict[str, Path] = {}

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        "src.config.manager.load_config",
        lambda path: _capture_path(path, captured),
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
        lambda path: _capture_path(path, captured),
    )

    manager = ConfigManager(config_path=custom_path)

    assert manager.config is sentinel.config
    assert captured["path"] == custom_path
    assert manager.config_path == custom_path
