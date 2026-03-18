"""File operation tools for X-Agent.

Provides tools for:
- Reading files
- Writing files
- Listing directories
- Searching for files

Security features:
- Source code protection to prevent accidental modifications
- File path validation
- Workspace restriction
"""

import os
import fnmatch
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Office Open XML file extensions and their corresponding skills
OFFICE_EXTENSIONS = {
    ".pptx": "pptx",
    ".xlsx": "xlsx", 
    ".docx": "docx",
}

# ZIP file magic bytes (Office Open XML files are ZIP archives)
ZIP_MAGIC_BYTES = b"PK"

# Protected directories that should not be edited by agent
PROTECTED_DIRECTORIES = {
    "backend/src",
    "frontend/src",
    ".git",
}

# Protected file patterns
PROTECTED_PATTERNS = {
    "*.py",
    "*.ts",
    "*.tsx",
    "*.js",
    "*.jsx",
    "*.go",
    "*.java",
    "*.cpp",
    "*.c",
    "*.h",
}

def _is_protected_file(file_path: Path) -> bool:
    """Check if a file is protected from editing.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if file is protected, False otherwise
    """
    # Check if file is in protected directory
    for protected_dir in PROTECTED_DIRECTORIES:
        try:
            file_path.relative_to(protected_dir)
            return True
        except ValueError:
            continue
    
    # Check if file matches protected patterns
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(file_path.name, pattern):
            return True
    
    return False


def _get_workspace_path() -> Path:
    """获取当前 agent 的 workspace 路径.

    解析优先级：
    1. 从当前请求上下文获取 agent_id，查找对应的 agent workspace
    2. 全局配置的 workspace.path（fallback）

    Returns:
        workspace 路径，如果配置加载失败则返回默认路径
    """
    # 优先级 1: 从当前请求上下文获取 agent 专属 workspace
    try:
        from ...conversation.context import get_current_context
        context = get_current_context()
        if context is not None and context.agent_id:
            # 尝试从 MultiAgentContextLoader 获取
            try:
                from ...conversation.multi_agent_context_loader import get_multi_agent_context_loader
                loader = get_multi_agent_context_loader()
                if loader is not None:
                    agent_context = loader.get_agent_context(context.agent_id)
                    if agent_context is not None:
                        resolved = Path(str(agent_context.workspace_path)).expanduser().resolve()
                        logger.debug(
                            "Resolved agent workspace for file ops",
                            extra={"agent_id": context.agent_id, "workspace": str(resolved)},
                        )
                        return resolved
            except Exception:
                pass

            # 尝试从配置中直接查找 agent workspace
            try:
                from ...config.manager import get_config
                config = get_config()
                if hasattr(config, 'multi_agent') and config.multi_agent and config.multi_agent.agents:
                    for agent_config in config.multi_agent.agents:
                        if agent_config.id == context.agent_id and agent_config.workspace:
                            resolved = Path(agent_config.workspace).expanduser().resolve()
                            logger.debug(
                                "Resolved agent workspace from config for file ops",
                                extra={"agent_id": context.agent_id, "workspace": str(resolved)},
                            )
                            return resolved
            except Exception:
                pass
    except Exception:
        pass

    # 优先级 2: 全局配置的 workspace.path
    try:
        from ...config.manager import ConfigManager
        workspace_path = ConfigManager().config.workspace.path
        return Path(workspace_path).expanduser().resolve()
    except Exception:
        return Path("~/.x-agent/workspace").expanduser().resolve()


def _resolve_file_path(file_path: str) -> Path:
    """解析文件路径.
    
    如果是相对路径，则相对于 workspace 目录解析。
    如果是绝对路径，则直接使用。
    
    Args:
        file_path: 用户提供的文件路径
    
    Returns:
        解析后的绝对路径
    """
    path = Path(file_path).expanduser()
    
    # 如果是绝对路径，直接返回
    if path.is_absolute():
        return path.resolve()
    
    # 相对路径：相对于 workspace 目录
    workspace = _get_workspace_path()
    return (workspace / path).resolve()


class EditFileTool(BaseTool):
    """Tool to edit a file by replacing specific text.
    
    Performs a targeted search-and-replace within a file, modifying only the
    matched portion while preserving the rest of the content. Much more efficient
    and safer than rewriting the entire file with write_file.
    """
    
    @property
    def name(self) -> str:
        return "edit_file"
    
    @property
    def description(self) -> str:
        return (
            "Edit a file by replacing a specific piece of text with new text. "
            "Only the matched section is changed; the rest of the file is preserved. "
            "Use this instead of write_file when you need to modify part of an existing file. "
            "The old_text must match exactly (including whitespace and indentation)."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ToolParameterType.STRING,
                description="The path to the file to edit. Can be absolute or relative.",
                required=True,
            ),
            ToolParameter(
                name="old_text",
                type=ToolParameterType.STRING,
                description="The exact text to find and replace. Must match the file content exactly, including whitespace and indentation.",
                required=True,
            ),
            ToolParameter(
                name="new_text",
                type=ToolParameterType.STRING,
                description="The new text to replace old_text with. Can be empty string to delete the matched text.",
                required=True,
            ),
        ]
    
    async def execute(self, file_path: str, old_text: str, new_text: str) -> ToolResult:
        """Execute the file edit operation.
        
        Args:
            file_path: Path to the file to edit
            old_text: Text to find
            new_text: Replacement text
            
        Returns:
            ToolResult with success or error
        """
        try:
            path = _resolve_file_path(file_path)
            
            if not path.exists():
                return ToolResult.error_result(f"File not found: {file_path}")
            
            if not path.is_file():
                return ToolResult.error_result(f"Not a file: {file_path}")
            
            # Check if file is protected (source code protection)
            if _is_protected_file(path):
                logger.warning(
                    "Attempted to edit protected file",
                    extra={"file_path": str(path)}
                )
                return ToolResult.error_result(
                    f"Cannot edit protected file: {file_path}. "
                    f"Source code files are protected from modification by the agent. "
                    f"Please use manual editing or request explicit permission."
                )
            
            # Read current content
            content = path.read_text(encoding="utf-8", errors="replace")
            
            # Check that old_text exists in the file
            occurrence_count = content.count(old_text)
            if occurrence_count == 0:
                # Provide helpful context for debugging
                preview_length = 200
                content_preview = content[:preview_length]
                if len(content) > preview_length:
                    content_preview += "..."
                return ToolResult.error_result(
                    f"old_text not found in {file_path}. "
                    f"Make sure the text matches exactly, including whitespace and indentation. "
                    f"File starts with:\n{content_preview}"
                )
            
            if occurrence_count > 1:
                return ToolResult.error_result(
                    f"old_text found {occurrence_count} times in {file_path}. "
                    f"Please provide a more specific/unique text snippet to avoid ambiguous edits."
                )
            
            # Perform the replacement (exactly one occurrence)
            new_content = content.replace(old_text, new_text, 1)
            
            # Write back
            path.write_text(new_content, encoding="utf-8")
            
            # Calculate change stats
            old_lines = old_text.count("\n") + 1
            new_lines = new_text.count("\n") + 1
            
            logger.info(
                "File edited successfully",
                extra={
                    "file_path": str(path),
                    "old_lines": old_lines,
                    "new_lines": new_lines,
                }
            )
            
            return ToolResult.ok(
                f"Successfully edited {path}: replaced {old_lines} line(s) with {new_lines} line(s).",
                file_path=str(path),
                old_lines=old_lines,
                new_lines=new_lines,
            )
            
        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error(
                "Failed to edit file",
                extra={"file_path": file_path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to edit file: {str(e)}")


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
            path = _resolve_file_path(file_path)
            
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
            path = _resolve_file_path(file_path)
            
            # Validate Office file formats
            # Office Open XML files (.pptx, .xlsx, .docx) must be ZIP archives, not plain text
            file_ext = path.suffix.lower()
            if file_ext in OFFICE_EXTENSIONS:
                skill_name = OFFICE_EXTENSIONS[file_ext]
                # Check if content looks like valid ZIP (Office files are ZIP archives)
                content_bytes = content.encode('utf-8', errors='replace')
                if not content_bytes.startswith(ZIP_MAGIC_BYTES):
                    logger.warning(
                        "Blocked invalid Office file creation",
                        extra={
                            "file_path": str(path),
                            "extension": file_ext,
                            "content_preview": content[:50],
                            "suggested_skill": skill_name,
                        }
                    )
                    return ToolResult.error_result(
                        f"Cannot create {file_ext} file with plain text content. "
                        f"Office files ({file_ext}) require proper binary format (Office Open XML/ZIP). "
                        f"Please use the '{skill_name}' skill to create valid {file_ext} files: "
                        f"invoke the /{skill_name} command or let the system auto-trigger the skill.",
                        invalid_format=True,
                        suggested_skill=skill_name,
                        file_extension=file_ext,
                    )
            
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
            dir_path = _resolve_file_path(path)
            
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
