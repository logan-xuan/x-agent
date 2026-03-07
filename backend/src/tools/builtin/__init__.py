"""Built-in tools for X-Agent.

This module provides the built-in tools that are always available:
- read_file: Read file contents
- write_file: Write content to a file
- list_dir: List directory contents
- search_files: Search for files by pattern
- run_in_terminal: Execute shell commands
- get_terminal_output: Check background process output
- kill_process: Kill a background process
- get_current_time: Get current local time
- fetch_web_content: Fetch web page content
- memory_search: Search long-term memory
"""

from .file_ops import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, SearchFilesTool
from .aliyun_web_search import AliyunWebSearchTool
from .get_current_time import GetCurrentTimeTool
from .fetch_web_content import FetchWebContentTool
from .memory_search import MemorySearchTool
from .terminal import RunInTerminalTool, GetTerminalOutputTool, KillProcessTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirTool",
    "SearchFilesTool",
    "AliyunWebSearchTool",
    "GetCurrentTimeTool",
    "FetchWebContentTool",
    "MemorySearchTool",
    "RunInTerminalTool",
    "GetTerminalOutputTool",
    "KillProcessTool",
    "get_builtin_tools",
]

def get_builtin_tools() -> list:
    """Get all built-in tools.
    
    Returns:
        List of built-in tool instances
    """
    # Create terminal tool first (needed by other tools)
    terminal_tool = RunInTerminalTool()
    
    return [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListDirTool(),
        SearchFilesTool(),
        AliyunWebSearchTool(),
        GetCurrentTimeTool(),
        FetchWebContentTool(),
        MemorySearchTool(),
        terminal_tool,
        GetTerminalOutputTool(terminal_tool),
        KillProcessTool(terminal_tool),
    ]