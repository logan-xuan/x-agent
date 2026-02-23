"""Plugin system for X-Agent.

X-Agent plugin system provides extensibility through:
- Base plugin class with lifecycle hooks
- Plugin manager for discovery and execution
- Built-in plugins for extended functionality
"""

from .base import (
    Plugin,
    PluginInfo,
    PluginContext,
    PluginResult,
    PluginState,
    PluginPriority,
)
from .manager import (
    PluginManager,
    get_plugin_manager,
    initialize_plugins,
    shutdown_plugins,
)

__all__ = [
    # Base classes
    "Plugin",
    "PluginInfo",
    "PluginContext",
    "PluginResult",
    "PluginState",
    "PluginPriority",
    
    # Manager
    "PluginManager",
    "get_plugin_manager",
    "initialize_plugins",
    "shutdown_plugins",
]
