"""File operation tools for X-Agent.

Provides tools for:
- Reading files
- Writing files
- Listing directories
- Searching for files
"""

import os
import fnmatch
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ReadFileTool(BaseTool):
    """Tool to read file contents.
    
    Reads the entire contents of a file and returns it as a string.
    Useful for examining configuration files, logs, or any text content.
    """
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read the contents of a file. Use this when you need to see what's in a file. Returns the file content as text."
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ToolParameterType.STRING,
                description="The path to the file to read. Can be absolute or relative.",
                required=True,
            ),
        ]
    
    async def execute(self, file_path: str) -> ToolResult:
        """Execute the file read operation.
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            ToolResult with file contents or error
        """
        try:
            path = Path(file_path).expanduser().resolve()
            
            if not path.exists():
                return ToolResult.error_result(f"File not found: {file_path}")
            
            if not path.is_file():
                return ToolResult.error_result(f"Not a file: {file_path}")
            
            # Check file size (limit to 1MB)
            size = path.stat().st_size
            if size > 1_000_000:
                return ToolResult.error_result(
                    f"File too large ({size} bytes). Maximum size is 1MB."
                )
            
            # Read file
            content = path.read_text(encoding="utf-8", errors="replace")
            
            # Truncate if very long
            max_length = 50000
            if len(content) > max_length:
                content = content[:max_length] + f"\n\n... [truncated, {len(content)} total characters]"
            
            logger.info(
                "File read successfully",
                extra={
                    "file_path": str(path),
                    "size": size,
                    "content_length": len(content),
                }
            )
            
            return ToolResult.ok(
                content,
                file_path=str(path),
                size=size,
            )
            
        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error(
                "Failed to read file",
                extra={"file_path": file_path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to read file: {str(e)}")


class WriteFileTool(BaseTool):
    """Tool to write content to a file.
    
    Creates a new file or overwrites an existing file with the provided content.
    Use with caution as it can overwrite important files.
    """
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file. Creates the file if it doesn't exist, or overwrites if it does. Use carefully as this can erase existing content."
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ToolParameterType.STRING,
                description="The path where the file should be written. Can be absolute or relative.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type=ToolParameterType.STRING,
                description="The content to write to the file.",
                required=True,
            ),
        ]
    
    async def execute(self, file_path: str, content: str) -> ToolResult:
        """Execute the file write operation.
        
        Args:
            file_path: Path where to write the file
            content: Content to write
            
        Returns:
            ToolResult with success or error
        """
        try:
            path = Path(file_path).expanduser().resolve()
            
            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            path.write_text(content, encoding="utf-8")
            
            logger.info(
                "File written successfully",
                extra={
                    "file_path": str(path),
                    "content_length": len(content),
                }
            )
            
            return ToolResult.ok(
                f"Successfully wrote {len(content)} characters to {path}",
                file_path=str(path),
                content_length=len(content),
            )
            
        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error(
                "Failed to write file",
                extra={"file_path": file_path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to write file: {str(e)}")


class ListDirTool(BaseTool):
    """Tool to list directory contents.
    
    Lists all files and directories in a given path.
    Useful for exploring the file system structure.
    """
    
    @property
    def name(self) -> str:
        return "list_dir"
    
    @property
    def description(self) -> str:
        return "List the contents of a directory. Shows files and subdirectories. Use this to explore the file system."
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="path",
                type=ToolParameterType.STRING,
                description="The directory path to list. Defaults to current directory if not specified.",
                required=False,
                default=".",
            ),
        ]
    
    async def execute(self, path: str = ".") -> ToolResult:
        """Execute the directory listing.
        
        Args:
            path: Directory path to list
            
        Returns:
            ToolResult with directory contents
        """
        try:
            dir_path = Path(path).expanduser().resolve()
            
            if not dir_path.exists():
                return ToolResult.error_result(f"Directory not found: {path}")
            
            if not dir_path.is_dir():
                return ToolResult.error_result(f"Not a directory: {path}")
            
            # List contents
            items = []
            for item in sorted(dir_path.iterdir()):
                item_type = "DIR" if item.is_dir() else "FILE"
                size = ""
                if item.is_file():
                    try:
                        size = f" ({item.stat().st_size} bytes)"
                    except:
                        pass
                items.append(f"[{item_type}] {item.name}{size}")
            
            result = f"Contents of {dir_path}:\n\n" + "\n".join(items)
            
            logger.info(
                "Directory listed",
                extra={
                    "path": str(dir_path),
                    "items_count": len(items),
                }
            )
            
            return ToolResult.ok(
                result,
                path=str(dir_path),
                items_count=len(items),
            )
            
        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {path}")
        except Exception as e:
            logger.error(
                "Failed to list directory",
                extra={"path": path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to list directory: {str(e)}")


class SearchFilesTool(BaseTool):
    """Tool to search for files by pattern.
    
    Searches for files matching a pattern (glob or name fragment).
    Recursively searches subdirectories.
    """
    
    @property
    def name(self) -> str:
        return "search_files"
    
    @property
    def description(self) -> str:
        return "Search for files by name or pattern. Supports glob patterns like '*.py' or 'test_*'. Returns matching file paths."
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="pattern",
                type=ToolParameterType.STRING,
                description="The search pattern (e.g., '*.py', 'config*', 'test_*.json')",
                required=True,
            ),
            ToolParameter(
                name="path",
                type=ToolParameterType.STRING,
                description="The directory to search in. Defaults to current directory.",
                required=False,
                default=".",
            ),
        ]
    
    async def execute(self, pattern: str, path: str = ".") -> ToolResult:
        """Execute the file search.
        
        Args:
            pattern: Search pattern (glob)
            path: Directory to search in
            
        Returns:
            ToolResult with matching files
        """
        try:
            search_path = Path(path).expanduser().resolve()
            
            if not search_path.exists():
                return ToolResult.error_result(f"Directory not found: {path}")
            
            if not search_path.is_dir():
                return ToolResult.error_result(f"Not a directory: {path}")
            
            # Search for files
            matches = []
            for root, dirs, files in os.walk(search_path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for filename in files:
                    if fnmatch.fnmatch(filename, pattern):
                        file_path = Path(root) / filename
                        rel_path = file_path.relative_to(search_path)
                        matches.append(str(rel_path))
            
            if not matches:
                result = f"No files matching '{pattern}' found in {search_path}"
            else:
                result = f"Found {len(matches)} files matching '{pattern}':\n\n"
                result += "\n".join(matches[:50])  # Limit to 50 results
                if len(matches) > 50:
                    result += f"\n\n... and {len(matches) - 50} more"
            
            logger.info(
                "File search completed",
                extra={
                    "pattern": pattern,
                    "path": str(search_path),
                    "matches_count": len(matches),
                }
            )
            
            return ToolResult.ok(
                result,
                pattern=pattern,
                path=str(search_path),
                matches_count=len(matches),
            )
            
        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {path}")
        except Exception as e:
            logger.error(
                "Failed to search files",
                extra={"pattern": pattern, "path": path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to search files: {str(e)}")
