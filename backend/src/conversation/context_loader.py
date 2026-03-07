"""Context loader for agent guidance system.

This module provides:
- AGENTS.md hot-reload with mtime caching
- Context file information queries
- Session-aware context loading

Note: Bootstrap detection/execution and identity checking are handled
by SystemPromptBuilder. This module focuses on AGENTS.md hot-reload
and file information queries.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..memory.models import (
    ContextBundle,
    ContextFile,
    FileLoadResult,
    SessionType,
    CONTEXT_FILES,
)
from ..utils.file_utils import (
    get_file_mtime,
)
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from ..memory.context_builder import ContextBuilder

logger = get_logger(__name__)

class ContextLoader:
    """Loader for agent context.
    
    Provides:
    - AGENTS.md hot-reload with mtime caching
    - Context file information queries for API
    - Session-aware context loading (delegates to ContextBuilder)
    """
    
    def __init__(self, workspace_path: str = "workspace") -> None:
        """Initialize context loader.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        # Lazy initialization to avoid circular import
        self._context_builder: "ContextBuilder | None" = None
        
        # Cache for AGENTS.md
        self._agents_content: str | None = None
        self._agents_mtime: datetime | None = None
        self._agents_loaded_at: float = 0.0
        
        logger.info(
            "ContextLoader initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    def _get_context_builder(self) -> "ContextBuilder":
        """Get or create ContextBuilder instance (lazy initialization)."""
        if self._context_builder is None:
            from ..memory.context_builder import ContextBuilder
            self._context_builder = ContextBuilder(str(self.workspace_path))
        return self._context_builder
    
    # ============ Session-Aware Context Loading ============
    
    def load_context(
        self,
        session_id: str,
        session_type: SessionType = SessionType.MAIN,
        force_reload: bool = False
    ) -> ContextBundle:
        """Load context based on session type.
        
        Args:
            session_id: Unique session identifier
            session_type: MAIN or SHARED (affects MEMORY.md loading)
            force_reload: Force reload ignoring cache
            
        Returns:
            ContextBundle with loaded context
        """
        start_time = time.time()
        
        # Clear cache if force reload
        if force_reload:
            self._get_context_builder().clear_cache()
        
        # Build base context using existing ContextBuilder
        context = self._get_context_builder().build_context()
        
        # Add session-specific fields
        context.session_id = session_id
        context.session_type = session_type
        
        # Session-aware MEMORY.md loading
        if session_type == SessionType.SHARED:
            context.long_term_memory = ""
            logger.info(
                "MEMORY.md excluded for shared context",
                extra={"session_id": session_id}
            )
        
        # Track loaded files
        context.loaded_files = self._get_loaded_file_paths()
        
        # Record load time
        context.load_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "Context loaded",
            extra={
                "session_id": session_id,
                "session_type": session_type.value,
                "load_time_ms": context.load_time_ms,
                "files_count": len(context.loaded_files),
            }
        )
        
        return context
    
    def _get_loaded_file_paths(self) -> list[str]:
        """Get list of loaded file paths."""
        files = []
        
        for name in ["AGENTS.md", "SPIRIT.md", "OWNER.md", "TOOLS.md", "MEMORY.md"]:
            path = self.workspace_path / name
            if path.exists():
                files.append(str(path))
        
        # Check memory directory
        memory_dir = self.workspace_path / "memory"
        if memory_dir.exists():
            for md_file in memory_dir.glob("*.md"):
                files.append(str(md_file))
        
        return files
    
    # ============ AGENTS.md Hot-Reload ============
    
    def load_agents_content(self, force_reload: bool = False) -> tuple[str, bool]:
        """Load AGENTS.md content with caching.
        
        Args:
            force_reload: Force reload ignoring cache
            
        Returns:
            Tuple of (content, was_reloaded)
        """
        agents_path = self.workspace_path / "AGENTS.md"
        
        if not agents_path.exists():
            return "", False
        
        # Check modification time
        current_mtime = get_file_mtime(agents_path)
        
        # Use cache if valid
        if not force_reload and self._agents_content is not None:
            if current_mtime == self._agents_mtime:
                logger.debug("Using cached AGENTS.md")
                return self._agents_content, False
        
        # Load fresh content
        try:
            content = agents_path.read_text(encoding="utf-8")
            self._agents_content = content
            self._agents_mtime = current_mtime
            self._agents_loaded_at = time.time()
            
            logger.info(
                "AGENTS.md loaded",
                extra={
                    "content_length": len(content),
                    "mtime": current_mtime.isoformat() if current_mtime else None
                }
            )
            return content, True
            
        except Exception as error:
            logger.error(
                "Failed to load AGENTS.md",
                extra={"error": str(error)}
            )
            return self._agents_content or "", False
    
    def reload_agents_if_changed(self) -> tuple[str, bool, float]:
        """Reload AGENTS.md if it has changed since last load.
        
        Returns:
            Tuple of (content, was_reloaded, reload_time_ms)
        """
        start_time = time.time()
        content, was_reloaded = self.load_agents_content(force_reload=False)
        reload_time_ms = (time.time() - start_time) * 1000
        
        if was_reloaded:
            logger.info(
                "AGENTS.md reloaded",
                extra={"reload_time_ms": reload_time_ms}
            )
        
        return content, was_reloaded, reload_time_ms
    
    def get_context_reload_info(self, session_id: str) -> dict:
        """Get information about context reload status.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with reload status information
        """
        content, was_reloaded, reload_time_ms = self.reload_agents_if_changed()
        
        return {
            "session_id": session_id,
            "agents_reloaded": was_reloaded,
            "reload_time_ms": reload_time_ms,
            "agents_mtime": self._agents_mtime.isoformat() if self._agents_mtime else None,
            "performance_ok": reload_time_ms < 1000,
        }
    
    # ============ File Information ============
    
    def get_loaded_files_info(self, session_id: str) -> list[dict]:
        """Get detailed information about loaded files.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of file information dictionaries
        """
        files_info = []
        
        for context_file in CONTEXT_FILES:
            path = self.workspace_path / context_file.name
            exists = path.exists()
            
            info = {
                "name": context_file.name,
                "path": str(path),
                "required": context_file.required,
                "main_session_only": context_file.main_session_only,
                "loaded": exists,
                "from_cache": False,
                "is_default": not exists,
            }
            
            if exists:
                stat = path.stat()
                info["last_modified"] = datetime.fromtimestamp(
                    stat.st_mtime
                ).isoformat()
                info["size_bytes"] = stat.st_size
            
            files_info.append(info)
        
        # Add daily memory files
        memory_dir = self.workspace_path / "memory"
        if memory_dir.exists():
            for md_file in sorted(memory_dir.glob("*.md")):
                stat = md_file.stat()
                files_info.append({
                    "name": md_file.name,
                    "path": str(md_file),
                    "required": False,
                    "main_session_only": False,
                    "loaded": True,
                    "from_cache": False,
                    "is_default": False,
                    "last_modified": datetime.fromtimestamp(
                        stat.st_mtime
                    ).isoformat(),
                    "size_bytes": stat.st_size,
                })
        
        return files_info
    
    # ============ Cache Management ============
    
    def clear_all_cache(self) -> None:
        """Clear all cached data."""
        if self._context_builder is not None:
            self._context_builder.clear_cache()
        self._agents_content = None
        self._agents_mtime = None
        
        logger.info("All context cache cleared")


# Global context loader instance
_context_loader: ContextLoader | None = None


def get_context_loader(workspace_path: str | None = None) -> ContextLoader:
    """Get or create global context loader instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        ContextLoader instance
    """
    global _context_loader
    if _context_loader is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _context_loader = ContextLoader(workspace_path)
    return _context_loader