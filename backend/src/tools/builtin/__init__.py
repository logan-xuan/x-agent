"""Built-in tools for X-Agent.

This module provides the built-in tools that are always available:
- read_file: Read file contents
- write_file: Write content to a file
- list_dir: List directory contents
- search_files: Search for files by pattern
"""

from .file_ops import ReadFileTool, WriteFileTool, ListDirTool, SearchFilesTool
from .web_search import WebSearchTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "ListDirTool",
    "SearchFilesTool",
    "WebSearchTool",
]


def get_builtin_tools() -> list:
    """Get all built-in tools.
    
    Returns:
        List of built-in tool instances
    """
    return [
        ReadFileTool(),
        WriteFileTool(),
        ListDirTool(),
        SearchFilesTool(),
        WebSearchTool(),
    ]
