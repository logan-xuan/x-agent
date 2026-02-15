"""Context loader for agent guidance system.

This module provides:
- Bootstrap detection and execution
- Session-aware context loading
- AGENTS.md reloading on user queries
- Integration with existing memory system
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..memory.context_builder import ContextBuilder, get_context_builder
from ..memory.models import (
    ContextBundle,
    ContextFile,
    FileLoadResult,
    SessionType,
    CONTEXT_FILES,
)
from ..memory.spirit_loader import SpiritLoader, get_spirit_loader
from ..services.template_service import TemplateService, get_template_service
from ..utils.file_utils import (
    async_read_file,
    get_file_mtime,
    safe_read_file,
    validate_path_in_workspace,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BootstrapStatus:
    """Status of bootstrap initialization."""
    
    def __init__(
        self,
        exists: bool = False,
        completed: bool = False,
        content: str = ""
    ) -> None:
        self.exists = exists
        self.completed = completed
        self.content = content


class ContextLoader:
    """Loader for agent context with bootstrap support.
    
    Extends the existing ContextBuilder with:
    - Bootstrap.md detection and execution
    - Session-aware MEMORY.md loading
    - AGENTS.md hot-reload support
    """
    
    def __init__(self, workspace_path: str = "workspace") -> None:
        """Initialize context loader.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self._context_builder = ContextBuilder(str(self.workspace_path))
        self._spirit_loader = SpiritLoader(str(self.workspace_path))
        self._template_service = TemplateService(str(self.workspace_path))
        
        # Cache for AGENTS.md
        self._agents_content: str | None = None
        self._agents_mtime: datetime | None = None
        self._agents_loaded_at: float = 0.0
        
        logger.info(
            "ContextLoader initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    # ============ Bootstrap Detection & Execution ============
    
    def check_bootstrap(self) -> BootstrapStatus:
        """Check if BOOTSTRAP.md exists and get its status.
        
        Returns:
            BootstrapStatus with existence and content info
        """
        bootstrap_path = self.workspace_path / "BOOTSTRAP.md"
        
        if not bootstrap_path.exists():
            logger.debug("BOOTSTRAP.md not found")
            return BootstrapStatus(exists=False)
        
        try:
            content = bootstrap_path.read_text(encoding="utf-8")
            logger.info(
                "BOOTSTRAP.md found",
                extra={"content_length": len(content)}
            )
            return BootstrapStatus(exists=True, content=content)
        except Exception as e:
            logger.error(
                "Failed to read BOOTSTRAP.md",
                extra={"error": str(e)}
            )
            return BootstrapStatus(exists=True, completed=False)
    
    def execute_bootstrap(self) -> bool:
        """Execute bootstrap initialization process.
        
        This should be called when BOOTSTRAP.md exists.
        It:
        1. Ensures required files exist (with defaults)
        2. Records bootstrap completion
        3. Optionally deletes BOOTSTRAP.md
        
        Returns:
            True if bootstrap was executed successfully
        """
        bootstrap_status = self.check_bootstrap()
        
        if not bootstrap_status.exists:
            logger.info("No BOOTSTRAP.md found, skipping bootstrap")
            return True  # No bootstrap needed
        
        logger.info("Executing bootstrap initialization")
        
        try:
            # Ensure required files exist
            results = self._template_service.ensure_required_files()
            
            # Log what was created
            created_files = [k for k, v in results.items() if v]
            if created_files:
                logger.info(
                    "Bootstrap created missing files",
                    extra={"files": created_files}
                )
            
            # Delete BOOTSTRAP.md after successful initialization
            self._complete_bootstrap()
            
            logger.info("Bootstrap initialization completed")
            return True
            
        except Exception as e:
            logger.error(
                "Bootstrap initialization failed",
                extra={"error": str(e)}
            )
            return False
    
    def _complete_bootstrap(self) -> None:
        """Complete bootstrap by deleting BOOTSTRAP.md."""
        bootstrap_path = self.workspace_path / "BOOTSTRAP.md"
        
        if bootstrap_path.exists():
            try:
                bootstrap_path.unlink()
                logger.info("BOOTSTRAP.md deleted after initialization")
            except Exception as e:
                logger.warning(
                    "Failed to delete BOOTSTRAP.md",
                    extra={"error": str(e)}
                )
    
    # ============ Session-Aware Context Loading ============
    
    def load_context(
        self,
        session_id: str,
        session_type: SessionType = SessionType.MAIN,
        force_reload: bool = False
    ) -> ContextBundle:
        """Load context based on session type.
        
        This is the main entry point for loading agent context.
        
        Args:
            session_id: Unique session identifier
            session_type: MAIN or SHARED (affects MEMORY.md loading)
            force_reload: Force reload ignoring cache
            
        Returns:
            ContextBundle with loaded context
        """
        start_time = time.time()
        
        # Check bootstrap first
        bootstrap_status = self.check_bootstrap()
        if bootstrap_status.exists:
            logger.info("BOOTSTRAP.md exists, executing initialization")
            self.execute_bootstrap()
        
        # Clear cache if force reload
        if force_reload:
            self._context_builder.clear_cache()
        
        # Build base context using existing ContextBuilder
        context = self._context_builder.build_context()
        
        # Add session-specific fields
        context.session_id = session_id
        context.session_type = session_type
        
        # Session-aware MEMORY.md loading
        if session_type == SessionType.SHARED:
            # Clear MEMORY.md for shared context (privacy protection)
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
        
        # Ensure file exists (graceful degradation)
        if not agents_path.exists():
            self._template_service.create_file_from_template("AGENTS.md", "agents")
        
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
            
        except Exception as e:
            logger.error(
                "Failed to load AGENTS.md",
                extra={"error": str(e)}
            )
            return self._agents_content or "", False
    
    def reload_agents_if_changed(self) -> tuple[str, bool, float]:
        """Reload AGENTS.md if it has changed since last load.
        
        This is called on each user query to ensure fresh guidance.
        
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
            "performance_ok": reload_time_ms < 1000,  # SC-004 requirement
        }
    
    # ============ Utility Methods ============
    
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
                "from_cache": False,  # Would need more tracking for this
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
    
    def clear_all_cache(self) -> None:
        """Clear all cached data."""
        self._context_builder.clear_cache()
        self._spirit_loader.clear_cache()
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
