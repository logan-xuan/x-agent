"""Tools module for X-Agent.

This module provides the tool system that enables the agent to:
- Execute file operations
- Search the web
- Run shell commands
- Extend with custom tools
"""

from .base import BaseTool, ToolResult, ToolParameter
from .manager import ToolManager, get_tool_manager

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolParameter",
    "ToolManager",
    "get_tool_manager",
]
