"""YAML configuration loader with validation."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Config


class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""

    pass


def load_config(config_path: Path) -> Config:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Validated Config instance

    Raises:
        ConfigLoadError: If file not found or invalid
        ValidationError: If configuration validation fails
    """
    if not config_path.exists():
        raise ConfigLoadError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Invalid YAML format: {exc}") from exc
    except Exception as exc:
        raise ConfigLoadError(f"Failed to read configuration file: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigLoadError("Configuration must be a YAML object")

    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        # Enhance error message with file location
        errors = []
        for error in exc.errors():
            loc = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"  - {loc}: {msg}")
        raise ConfigLoadError("Configuration validation failed:\n" + "\n".join(errors)) from exc


def load_config_from_string(yaml_content: str) -> Config:
    """Load configuration from YAML string (for testing).

    Args:
        yaml_content: YAML configuration as string

    Returns:
        Validated Config instance
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        raise ConfigLoadError(f"Invalid YAML format: {exc}") from exc

    return Config.model_validate(data)
