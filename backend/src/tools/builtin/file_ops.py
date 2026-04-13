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

import contextlib
import fnmatch
import os
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

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


def _get_project_root() -> Path:
    """返回 x-agent 项目根目录."""

    return Path(__file__).resolve().parents[4]


def _resolve_workspace_candidate(raw_path: str) -> Path:
    """按项目约定解析 workspace 路径."""

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    backend_dir = _get_project_root() / "backend"
    return (backend_dir / candidate).resolve()


def _is_relative_to(path: Path, base: Path) -> bool:
    """兼容 Path.relative_to 的布尔判断."""

    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _get_configured_workspace_paths() -> list[Path]:
    """返回配置文件中声明的所有 workspace 路径."""

    workspaces: list[Path] = []

    try:
        from ...config.manager import get_config

        config = get_config()

        if getattr(config, "workspace", None) and config.workspace and config.workspace.path:
            workspaces.append(_resolve_workspace_candidate(config.workspace.path))

        if getattr(config, "multi_agent", None) and config.multi_agent and config.multi_agent.agents:
            for agent_config in config.multi_agent.agents:
                workspace = getattr(agent_config, "workspace", None)
                if workspace:
                    workspaces.append(_resolve_workspace_candidate(workspace))
    except Exception:
        return []

    unique_paths: list[Path] = []
    seen: set[str] = set()
    for workspace in workspaces:
        key = str(workspace)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(workspace)

    return unique_paths


def _is_protected_file(file_path: Path) -> bool:
    """Check if a file is protected from editing.

    Args:
        file_path: Path to check

    Returns:
        True if file is protected, False otherwise
    """
    resolved_path = file_path.expanduser().resolve()

    # Git 元数据始终禁止 agent 修改
    if ".git" in resolved_path.parts:
        return True

    # 任一已配置 workspace 内的文件默认可编辑
    for workspace_path in _get_configured_workspace_paths():
        if _is_relative_to(resolved_path, workspace_path):
            return False

    # 当前 agent 的 workspace 作为兜底放行
    workspace_path = _get_workspace_path().expanduser().resolve()
    if _is_relative_to(resolved_path, workspace_path):
        return False

    project_root = _get_project_root()

    # Check if file is in protected directory
    for protected_dir in PROTECTED_DIRECTORIES:
        protected_path = (project_root / protected_dir).resolve()
        if _is_relative_to(resolved_path, protected_path):
            return True

    # Check if file matches protected patterns
    return any(fnmatch.fnmatch(resolved_path.name, pattern) for pattern in PROTECTED_PATTERNS)


def _get_workspace_path() -> Path:
    """获取当前 agent 的 workspace 路径.

    解析优先级：
    1. 从当前请求上下文获取 agent_id，查找对应的 agent workspace
    2. 默认 Agent 的 workspace（fallback）
    3. 全局配置的 workspace.path（最终 fallback）

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
                from ...conversation.multi_agent_context_loader import (
                    get_multi_agent_context_loader,
                )

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
                if (
                    hasattr(config, "multi_agent")
                    and config.multi_agent
                    and config.multi_agent.agents
                ):
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

    # 优先级 2: 默认 Agent 的 workspace，其次回退到全局 workspace.path
    try:
        from ...config.manager import get_config
        from ...conversation.dao.bootstrap import DEFAULT_AGENT_ID

        config = get_config()
        if getattr(config, "multi_agent", None) and config.multi_agent and config.multi_agent.agents:
            for agent_config in config.multi_agent.agents:
                if agent_config.id == DEFAULT_AGENT_ID and agent_config.workspace:
                    return _resolve_workspace_candidate(agent_config.workspace)

        return _resolve_workspace_candidate(config.workspace.path)
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


def _summarize_directory(path: Path) -> tuple[str, dict[str, Any]]:
    """为 read_file 工具生成目录摘要，避免把目录误判为硬错误。"""
    entries = sorted(path.iterdir(), key=lambda item: item.name)
    files = [item for item in entries if item.is_file()]
    directories = [item for item in entries if item.is_dir()]
    latest_file = max(files, key=lambda item: item.stat().st_mtime, default=None)
    latest_preview = ""

    lines = [
        f"Directory summary: {path}",
        f"- files: {len(files)}",
        f"- directories: {len(directories)}",
    ]
    if latest_file is not None:
        lines.append(f"- latest_file: {latest_file.name}")
        with contextlib.suppress(Exception):
            if latest_file.suffix.lower() in {".json", ".md", ".txt", ".yaml", ".yml"}:
                latest_preview = latest_file.read_text(encoding="utf-8", errors="replace")[:800]
                if latest_preview:
                    lines.append("- latest_file_preview:")
                    lines.append(latest_preview)

    preview = [item.name + ("/" if item.is_dir() else "") for item in entries[:20]]
    if preview:
        lines.append("- entries:")
        lines.extend(f"  - {name}" for name in preview)

    return "\n".join(lines), {
        "is_directory": True,
        "files_count": len(files),
        "directories_count": len(directories),
        "latest_file": str(latest_file) if latest_file is not None else "",
        "latest_file_preview": latest_preview,
        "entries": preview,
    }


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
                if path.is_dir():
                    summary, metadata = _summarize_directory(path)
                    logger.info(
                        "ReadFileTool received directory path, returning summary",
                        extra={"file_path": str(path), **metadata},
                    )
                    return ToolResult.ok(summary, **metadata)
                return ToolResult.error_result(f"Not a file: {file_path}")

            # Check if file is protected (source code protection)
            if _is_protected_file(path):
                logger.warning("Attempted to edit protected file", extra={"file_path": str(path)})
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
                },
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
            logger.error("Failed to edit file", extra={"file_path": file_path, "error": str(e)})
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
        return (
            "Read the contents of a file. Use this when you need to inspect a file. "
            "Supports optional line-range reads via start_line and line_count for chunked reading."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="file_path",
                type=ToolParameterType.STRING,
                description="The path to the file to read. Can be absolute or relative.",
                required=True,
            ),
            ToolParameter(
                name="start_line",
                type=ToolParameterType.INTEGER,
                description="Optional 1-based start line for chunked reading.",
                required=False,
                min_value=1,
            ),
            ToolParameter(
                name="line_count",
                type=ToolParameterType.INTEGER,
                description="Optional number of lines to read when using chunked mode. Recommended <= 400.",
                required=False,
                min_value=1,
                max_value=400,
            ),
        ]

    async def execute(
        self,
        file_path: str,
        start_line: int | None = None,
        line_count: int | None = None,
    ) -> ToolResult:
        """Execute the file read operation.

        Args:
            file_path: Path to the file to read
            start_line: Optional 1-based line offset for chunked reading
            line_count: Optional line count for chunked reading

        Returns:
            ToolResult with file contents or error
        """
        try:
            path = _resolve_file_path(file_path)

            if not path.exists():
                return ToolResult.error_result(f"File not found: {file_path}")

            if not path.is_file():
                if path.is_dir():
                    summary, metadata = _summarize_directory(path)
                    logger.info(
                        "ReadFileTool received directory path, returning summary",
                        extra={"file_path": str(path), **metadata},
                    )
                    return ToolResult.ok(summary, **metadata)
                return ToolResult.error_result(f"Not a file: {file_path}")

            # Check file size (limit to 1MB)
            size = path.stat().st_size
            if size > 1_000_000:
                return ToolResult.error_result(
                    f"File too large ({size} bytes). Maximum size is 1MB."
                )

            # Read file
            content = path.read_text(encoding="utf-8", errors="replace")
            chunked_mode = start_line is not None or line_count is not None

            metadata: dict[str, Any] = {
                "file_path": str(path),
                "size": size,
            }

            if chunked_mode:
                all_lines = content.splitlines(keepends=True)
                total_lines = len(all_lines)
                resolved_start_line = start_line or 1
                resolved_line_count = line_count or 200
                start_index = max(resolved_start_line - 1, 0)
                end_index = min(start_index + resolved_line_count, total_lines)
                content = "".join(all_lines[start_index:end_index])

                metadata.update(
                    {
                        "start_line": resolved_start_line,
                        "end_line": end_index,
                        "total_lines": total_lines,
                        "line_count": max(end_index - start_index, 0),
                        "has_more": end_index < total_lines,
                        "next_start_line": end_index + 1 if end_index < total_lines else None,
                    }
                )

            # Truncate if very long
            max_length = 20000 if chunked_mode else 50000
            if len(content) > max_length:
                content = (
                    content[:max_length] + f"\n\n... [truncated, {len(content)} total characters]"
                )
                metadata["truncated"] = True

            logger.info(
                "File read successfully",
                extra={
                    "file_path": str(path),
                    "size": size,
                    "content_length": len(content),
                    "chunked_mode": chunked_mode,
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                },
            )

            return ToolResult.ok(
                content,
                **metadata,
            )

        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error("Failed to read file", extra={"file_path": file_path, "error": str(e)})
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

            if _is_protected_file(path):
                logger.warning("Attempted to write protected file", extra={"file_path": str(path)})
                return ToolResult.error_result(
                    f"Cannot write protected file: {file_path}. "
                    f"Source code files are protected from modification by the agent. "
                    f"Please use manual editing or request explicit permission."
                )

            # Validate Office file formats
            # Office Open XML files (.pptx, .xlsx, .docx) must be ZIP archives, not plain text
            file_ext = path.suffix.lower()
            if file_ext in OFFICE_EXTENSIONS:
                skill_name = OFFICE_EXTENSIONS[file_ext]
                # Check if content looks like valid ZIP (Office files are ZIP archives)
                content_bytes = content.encode("utf-8", errors="replace")
                if not content_bytes.startswith(ZIP_MAGIC_BYTES):
                    logger.warning(
                        "Blocked invalid Office file creation",
                        extra={
                            "file_path": str(path),
                            "extension": file_ext,
                            "content_preview": content[:50],
                            "suggested_skill": skill_name,
                        },
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
                },
            )

            return ToolResult.ok(
                f"Successfully wrote {len(content)} characters to {path}",
                file_path=str(path),
                content_length=len(content),
            )

        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {file_path}")
        except Exception as e:
            logger.error("Failed to write file", extra={"file_path": file_path, "error": str(e)})
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
                    with contextlib.suppress(BaseException):
                        size = f" ({item.stat().st_size} bytes)"
                items.append(f"[{item_type}] {item.name}{size}")

            result = f"Contents of {dir_path}:\n\n" + "\n".join(items)

            logger.info(
                "Directory listed",
                extra={
                    "path": str(dir_path),
                    "items_count": len(items),
                },
            )

            return ToolResult.ok(
                result,
                path=str(dir_path),
                items_count=len(items),
            )

        except PermissionError:
            return ToolResult.error_result(f"Permission denied: {path}")
        except Exception as e:
            logger.error("Failed to list directory", extra={"path": path, "error": str(e)})
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
                dirs[:] = [d for d in dirs if not d.startswith(".")]

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
                },
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
                "Failed to search files", extra={"pattern": pattern, "path": path, "error": str(e)}
            )
            return ToolResult.error_result(f"Failed to search files: {str(e)}")
