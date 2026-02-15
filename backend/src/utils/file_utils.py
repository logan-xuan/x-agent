"""File utilities for agent guidance system.

This module provides:
- Async file reading and writing
- Path validation for security
- File locking for concurrent access
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os

try:
    from filelock import FileLock, Timeout as FileLockTimeout
except ImportError:
    FileLock = None  # type: ignore
    FileLockTimeout = None  # type: ignore

from ..utils.logger import get_logger

logger = get_logger(__name__)


class PathValidationError(Exception):
    """Raised when a path fails validation."""
    pass


class LockAcquireTimeout(Exception):
    """Raised when file lock acquisition times out."""
    pass


def validate_path_in_workspace(
    file_path: str | Path,
    workspace_path: str | Path = "workspace"
) -> Path:
    """Validate that a path is within the workspace directory.
    
    This prevents path traversal attacks by ensuring all file operations
    are confined to the workspace.
    
    Args:
        file_path: Path to validate
        workspace_path: Path to workspace directory
        
    Returns:
        Resolved absolute path
        
    Raises:
        PathValidationError: If path is outside workspace
    """
    workspace = Path(workspace_path).resolve()
    target = Path(file_path).resolve()
    
    # Check if target is within workspace
    try:
        target.relative_to(workspace)
    except ValueError:
        raise PathValidationError(
            f"Path '{file_path}' is outside workspace '{workspace_path}'"
        )
    
    # Check for symlink escape
    if target.is_symlink():
        real_target = target.resolve()
        try:
            real_target.relative_to(workspace)
        except ValueError:
            raise PathValidationError(
                f"Symlink '{file_path}' points outside workspace"
            )
    
    return target


async def async_read_file(
    file_path: str | Path,
    encoding: str = "utf-8",
    max_size_mb: float = 1.0
) -> tuple[str, bool]:
    """Read file content asynchronously.
    
    Args:
        file_path: Path to file
        encoding: File encoding
        max_size_mb: Maximum file size in MB
        
    Returns:
        Tuple of (content, success)
    """
    path = Path(file_path)
    
    if not path.exists():
        logger.debug(f"File not found: {path}")
        return "", False
    
    # Check file size
    try:
        stat = await aiofiles.os.stat(path)
        size_mb = stat.st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            logger.warning(
                f"File too large: {path} ({size_mb:.2f}MB > {max_size_mb}MB)"
            )
            return "", False
    except Exception as e:
        logger.error(f"Failed to stat file: {path}", extra={"error": str(e)})
        return "", False
    
    try:
        async with aiofiles.open(path, mode="r", encoding=encoding) as f:
            content = await f.read()
        logger.debug(f"File read: {path}", extra={"size": len(content)})
        return content, True
    except Exception as e:
        logger.error(f"Failed to read file: {path}", extra={"error": str(e)})
        return "", False


async def async_write_file(
    file_path: str | Path,
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = True
) -> bool:
    """Write file content asynchronously.
    
    Uses atomic write pattern: write to temp file, then rename.
    
    Args:
        file_path: Path to file
        content: Content to write
        encoding: File encoding
        create_dirs: Whether to create parent directories
        
    Returns:
        True if successful
    """
    path = Path(file_path)
    
    if create_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first (atomic write)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    
    try:
        async with aiofiles.open(temp_path, mode="w", encoding=encoding) as f:
            await f.write(content)
        
        # Atomic rename
        await aiofiles.os.rename(temp_path, path)
        
        logger.debug(f"File written: {path}", extra={"size": len(content)})
        return True
        
    except Exception as e:
        logger.error(f"Failed to write file: {path}", extra={"error": str(e)})
        # Clean up temp file
        try:
            await aiofiles.os.remove(temp_path)
        except Exception:
            pass
        return False


def get_file_mtime(file_path: str | Path) -> datetime | None:
    """Get file modification time.
    
    Args:
        file_path: Path to file
        
    Returns:
        Modification time or None if file doesn't exist
    """
    path = Path(file_path)
    
    if not path.exists():
        return None
    
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return None


class AsyncFileLock:
    """Async wrapper for file locking.
    
    Provides a context manager for safe concurrent file access.
    """
    
    def __init__(
        self,
        file_path: str | Path,
        timeout: float = 10.0
    ) -> None:
        """Initialize file lock.
        
        Args:
            file_path: Path to file (lock file will be .lock suffix)
            timeout: Timeout in seconds for acquiring lock
        """
        self.lock_path = Path(str(file_path) + ".lock")
        self.timeout = timeout
        self._lock: FileLock | None = None
    
    def __enter__(self) -> "AsyncFileLock":
        """Acquire lock synchronously."""
        if FileLock is None:
            logger.warning("filelock not available, skipping lock")
            return self
        
        self._lock = FileLock(self.lock_path)
        try:
            self._lock.acquire(timeout=self.timeout)
            logger.debug(f"Lock acquired: {self.lock_path}")
            return self
        except Exception as e:
            # Handle both filelock.Timeout and general exceptions
            if "timeout" in str(e).lower() or FileLockTimeout is not None and isinstance(e, type(FileLockTimeout)):
                raise LockAcquireTimeout(
                    f"Failed to acquire lock: {self.lock_path} (timeout: {self.timeout}s)"
                )
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release lock."""
        if self._lock is not None:
            self._lock.release()
            logger.debug(f"Lock released: {self.lock_path}")
    
    async def __aenter__(self) -> "AsyncFileLock":
        """Acquire lock asynchronously (same as sync for filelock)."""
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release lock."""
        self.__exit__(exc_type, exc_val, exc_tb)


async def safe_read_file(
    file_path: str | Path,
    workspace_path: str | Path = "workspace",
    encoding: str = "utf-8",
    use_lock: bool = False
) -> tuple[str, bool]:
    """Safely read a file with validation and optional locking.
    
    Args:
        file_path: Path to file
        workspace_path: Workspace path for validation
        encoding: File encoding
        use_lock: Whether to use file locking
        
    Returns:
        Tuple of (content, success)
    """
    # Validate path
    try:
        validated_path = validate_path_in_workspace(file_path, workspace_path)
    except PathValidationError as e:
        logger.error(f"Path validation failed: {e}")
        return "", False
    
    if use_lock:
        async with AsyncFileLock(validated_path):
            return await async_read_file(validated_path, encoding)
    else:
        return await async_read_file(validated_path, encoding)


async def safe_write_file(
    file_path: str | Path,
    content: str,
    workspace_path: str | Path = "workspace",
    encoding: str = "utf-8",
    use_lock: bool = True
) -> bool:
    """Safely write a file with validation and locking.
    
    Args:
        file_path: Path to file
        content: Content to write
        workspace_path: Workspace path for validation
        encoding: File encoding
        use_lock: Whether to use file locking (default True for writes)
        
    Returns:
        True if successful
    """
    # Validate path
    try:
        validated_path = validate_path_in_workspace(file_path, workspace_path)
    except PathValidationError as e:
        logger.error(f"Path validation failed: {e}")
        return False
    
    if use_lock:
        async with AsyncFileLock(validated_path):
            return await async_write_file(validated_path, content, encoding)
    else:
        return await async_write_file(validated_path, content, encoding)


def ensure_memory_directory(workspace_path: str | Path = "workspace") -> Path:
    """Ensure memory directory exists.
    
    Args:
        workspace_path: Path to workspace
        
    Returns:
        Path to memory directory
    """
    memory_dir = Path(workspace_path) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def get_daily_memory_path(
    date: datetime | str | None = None,
    workspace_path: str | Path = "workspace"
) -> Path:
    """Get path to daily memory file.
    
    Args:
        date: Date for the file (default: today)
        workspace_path: Path to workspace
        
    Returns:
        Path to daily memory file
    """
    if date is None:
        date = datetime.now()
    elif isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d")
    
    memory_dir = ensure_memory_directory(workspace_path)
    return memory_dir / f"{date.strftime('%Y-%m-%d')}.md"


def get_yesterday_memory_path(
    workspace_path: str | Path = "workspace"
) -> Path:
    """Get path to yesterday's memory file.
    
    Args:
        workspace_path: Path to workspace
        
    Returns:
        Path to yesterday's memory file
    """
    from datetime import timedelta
    yesterday = datetime.now() - timedelta(days=1)
    return get_daily_memory_path(yesterday, workspace_path)
