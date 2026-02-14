"""Configuration management module for X-Agent.

This module provides high-cohesion configuration management with:
- YAML-based configuration
- Type validation via Pydantic
- Hot-reload support
- Vendor-agnostic model configuration
- Primary/backup failover support
"""

from .manager import ConfigManager
from .models import Config, LoggingConfig, ModelConfig, ServerConfig

__all__ = [
    "ConfigManager",
    "Config",
    "LoggingConfig",
    "ModelConfig",
    "ServerConfig",
]
