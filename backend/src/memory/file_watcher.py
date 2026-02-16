"""File watcher for hot-reload and bidirectional sync.

This module provides:
- File system monitoring using watchdog
- Hot-reload of identity files (SPIRIT.md, OWNER.md)
- Event handlers for .md file changes
"""

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MemoryFileHandler(FileSystemEventHandler):
    """Handler for memory file system events.
    
    Monitors changes to .md files in the workspace directory
    and triggers appropriate callbacks.
    """
    
    def __init__(
        self,
        on_spirit_changed: Callable[[], None] | None = None,
        on_owner_changed: Callable[[], None] | None = None,
        on_tools_changed: Callable[[], None] | None = None,
        on_memory_changed: Callable[[str], None] | None = None,
        on_agents_changed: Callable[[], None] | None = None,
        on_identity_changed: Callable[[], None] | None = None,
    ) -> None:
        """Initialize file handler.
        
        Args:
            on_spirit_changed: Callback for SPIRIT.md changes
            on_owner_changed: Callback for OWNER.md changes
            on_tools_changed: Callback for TOOLS.md changes
            on_memory_changed: Callback for memory/*.md changes (receives file path)
            on_agents_changed: Callback for AGENTS.md changes (hot-reload)
            on_identity_changed: Callback for IDENTITY.md changes (AI name changes)
        """
        super().__init__()
        self.on_spirit_changed = on_spirit_changed
        self.on_owner_changed = on_owner_changed
        self.on_tools_changed = on_tools_changed
        self.on_memory_changed = on_memory_changed
        self.on_agents_changed = on_agents_changed
        self.on_identity_changed = on_identity_changed
        
        logger.debug("MemoryFileHandler initialized")
    
    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification event."""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        
        # Only process .md files
        if path.suffix != ".md":
            return
        
        logger.info(
            "File modified detected",
            extra={
                "file_path": str(path),
                "file_name": path.name,
            }
        )
        
        # Trigger appropriate callback
        if path.name == "SPIRIT.md" and self.on_spirit_changed:
            logger.info("SPIRIT.md changed, triggering reload")
            self.on_spirit_changed()
        elif path.name == "OWNER.md" and self.on_owner_changed:
            logger.info("OWNER.md changed, triggering reload")
            self.on_owner_changed()
        elif path.name == "IDENTITY.md" and self.on_identity_changed:
            logger.info("IDENTITY.md changed, triggering reload")
            self.on_identity_changed()
        elif path.name == "TOOLS.md" and self.on_tools_changed:
            logger.info("TOOLS.md changed, triggering reload")
            self.on_tools_changed()
        elif path.name == "AGENTS.md" and self.on_agents_changed:
            logger.info("AGENTS.md changed, triggering hot-reload")
            self.on_agents_changed()
        elif path.parent.name == "memory" and self.on_memory_changed:
            logger.info("Memory file changed, triggering sync", extra={"file_path": str(path)})
            self.on_memory_changed(str(path))
    
    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation event."""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        
        if path.suffix != ".md":
            return
        
        logger.info(
            "File created detected",
            extra={"file_path": str(path)}
        )
        
        # Treat creation same as modification for simplicity
        self.on_modified(event)
    
    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion event."""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        
        logger.warning(
            "File deleted detected",
            extra={"file_path": str(path)}
        )


class FileWatcher:
    """File watcher for memory system.
    
    Monitors the workspace directory for file changes and
    triggers appropriate callbacks for hot-reload.
    """
    
    def __init__(self, workspace_path: str) -> None:
        """Initialize file watcher.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self._observer: Observer | None = None
        self._handler: MemoryFileHandler | None = None
        self._running = False
        
        logger.info(
            "FileWatcher created",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    def start(
        self,
        on_spirit_changed: Callable[[], None] | None = None,
        on_owner_changed: Callable[[], None] | None = None,
        on_tools_changed: Callable[[], None] | None = None,
        on_memory_changed: Callable[[str], None] | None = None,
        on_agents_changed: Callable[[], None] | None = None,
        on_identity_changed: Callable[[], None] | None = None,
    ) -> None:
        """Start watching for file changes.
        
        Args:
            on_spirit_changed: Callback for SPIRIT.md changes
            on_owner_changed: Callback for OWNER.md changes
            on_tools_changed: Callback for TOOLS.md changes
            on_memory_changed: Callback for memory/*.md changes
            on_agents_changed: Callback for AGENTS.md changes (hot-reload)
            on_identity_changed: Callback for IDENTITY.md changes (AI name changes)
        """
        if self._running:
            logger.warning("FileWatcher already running")
            return
        
        self._handler = MemoryFileHandler(
            on_spirit_changed=on_spirit_changed,
            on_owner_changed=on_owner_changed,
            on_tools_changed=on_tools_changed,
            on_memory_changed=on_memory_changed,
            on_agents_changed=on_agents_changed,
            on_identity_changed=on_identity_changed,
        )
        
        self._observer = Observer()
        self._observer.schedule(
            self._handler,
            str(self.workspace_path),
            recursive=True  # Watch subdirectories (memory/)
        )
        self._observer.start()
        self._running = True
        
        logger.info(
            "FileWatcher started",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running or self._observer is None:
            return
        
        self._observer.stop()
        self._observer.join()
        self._running = False
        
        logger.info("FileWatcher stopped")
    
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running


# Global file watcher instance
_file_watcher: FileWatcher | None = None


def get_file_watcher(workspace_path: str | None = None) -> FileWatcher:
    """Get or create global file watcher instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        FileWatcher instance
    """
    global _file_watcher
    if _file_watcher is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _file_watcher = FileWatcher(workspace_path)
    return _file_watcher
