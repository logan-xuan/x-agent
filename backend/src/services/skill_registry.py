"""Skill registry for discovering and managing skills in X-Agent.

This module implements skill discovery from multiple directories with priority-based
overriding, following the Anthropic Skills specification.

Includes intelligent caching with:
- File system watching for auto-reload
- Environment-based TTL configuration
- Manual refresh API

Discovery paths (priority high → low):
1. User-level: configured in x-agent.yaml (default: workspace/skills/)
2. System-level: backend/src/skills/
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..models.skill import SkillMetadata
from .skill_parser import SkillParser, SkillParseError
from ..utils.logger import get_logger

logger = get_logger(__name__)


# System skills path (will be resolved relative to backend directory)
SYSTEM_SKILLS_PATH = "src/skills"


class SkillRegistry:
    """Registry for discovering and managing skills.
    
    The registry scans multiple directories for skills and maintains a cache
    for performance. Higher priority skills override lower priority ones with
    the same name.
    
    Example:
        registry = SkillRegistry(workspace_path=Path("/workspace"))
        skills = registry.list_all_skills()
        
        # Get specific skill
        skill = registry.get_skill_metadata("pptx")
        
        # Force reload
        registry.reload_if_changed()
    """
    
    def __init__(self, workspace_path: Path) -> None:
        """Initialize the skill registry.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = workspace_path.resolve()
        self._parser = SkillParser()
        self._cache: dict[str, SkillMetadata] = {}
        self._last_scan_time: datetime | None = None
        
        # Environment-based cache TTL configuration
        # Development: 30 seconds for fast iteration
        # Production: 5 minutes for performance
        env = os.getenv("X_AGENT_ENV", "production").lower()
        if env == "development":
            self._cache_ttl = timedelta(seconds=30)
        else:
            self._cache_ttl = timedelta(seconds=300)  # 5 minutes
        
        # File watching (optional, implemented via watchdog)
        self._file_watcher = None
        self._watch_enabled = os.getenv("X_AGENT_WATCH_SKILLS", "false").lower() == "true"
        
        # Load user skills directory from configuration
        try:
            from ..config.manager import ConfigManager
            config = ConfigManager().config
            self.user_skills_dir = config.workspace.skills_dir
        except Exception as e:
            logger.warning(f"Failed to load workspace config, using default: {e}")
            self.user_skills_dir = "skills"
        
        logger.info(
            "SkillRegistry initialized",
            extra={
                "workspace_path": str(self.workspace_path),
                "user_skills_dir": self.user_skills_dir,
                "cache_ttl_seconds": self._cache_ttl.total_seconds(),
                "environment": env,
                "file_watching": self._watch_enabled,
            }
        )
        
        # Start file watching if enabled
        if self._watch_enabled:
            self._setup_file_watcher()
    
    def _setup_file_watcher(self) -> None:
        """Setup file system watcher for automatic cache invalidation.
        
        Requires watchdog library: pip install watchdog
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
            
            class SkillFileHandler(FileSystemEventHandler):
                """Handler for skill file changes."""
                
                def __init__(self, registry: "SkillRegistry"):
                    self.registry = registry
                
                def on_any_event(self, event: FileSystemEvent) -> None:
                    """Handle any file system event."""
                    if event.is_directory:
                        return
                    
                    # Check if this is a SKILL.md file
                    if event.src_path.endswith("SKILL.md"):
                        logger.info(
                            "Skill file changed, invalidating cache",
                            extra={"file_path": event.src_path, "event_type": event.event_type}
                        )
                        self.registry.clear_cache()
            
            self._file_watcher = Observer()
            handler = SkillFileHandler(self)
            
            # Watch user skills directory
            user_skills_path = self.workspace_path / self.user_skills_dir
            if user_skills_path.exists():
                self._file_watcher.schedule(handler, str(user_skills_path), recursive=True)
                self._file_watcher.start()
                logger.info(f"File watching enabled for {user_skills_path}")
        
        except ImportError:
            logger.warning(
                "watchdog library not installed, file watching disabled. "
                "Install with: pip install watchdog"
            )
            self._watch_enabled = False
        except Exception as e:
            logger.warning(f"Failed to setup file watcher: {e}")
            self._watch_enabled = False
    
    def __del__(self) -> None:
        """Cleanup file watcher on destruction."""
        if self._file_watcher:
            try:
                self._file_watcher.stop()
                self._file_watcher.join(timeout=1)
            except Exception as e:
                logger.warning(f"Error stopping file watcher: {e}")
    
    def list_all_skills(self) -> list[SkillMetadata]:
        """List all available skills (with caching).
        
        Returns:
            List of SkillMetadata objects
        """
        if self._is_cache_valid():
            logger.debug("Using cached skills")
            return list(self._cache.values())
        
        # Reload skills
        skills = self._discover_all_skills()
        self._cache = {s.name: s for s in skills}
        self._last_scan_time = datetime.now()
        
        logger.info(
            f"Discovered {len(skills)} skills",
            extra={
                "skill_names": [s.name for s in skills],
                "cache_ttl_seconds": self._cache_ttl.total_seconds(),
            }
        )
        
        return list(self._cache.values())
    
    def get_skill_metadata(self, name: str) -> SkillMetadata | None:
        """Get metadata for a specific skill by name.
        
        Args:
            name: Skill name
            
        Returns:
            SkillMetadata if found, None otherwise
        """
        # Try cache first
        if name in self._cache:
            return self._cache[name]
        
        # Refresh and try again
        self.list_all_skills()
        return self._cache.get(name)
    
    def reload_if_changed(self) -> bool:
        """Force reload of skills (e.g., when files change).
        
        DEPRECATED: Use clear_cache() or set X_AGENT_WATCH_SKILLS=true for automatic reloading.
        
        Returns:
            True if skills were reloaded
        """
        logger.warning(
            "reload_if_changed() is deprecated, use clear_cache() instead"
        )
        old_count = len(self._cache)
        
        skills = self._discover_all_skills()
        self._cache = {s.name: s for s in skills}
        self._last_scan_time = datetime.now()
        
        new_count = len(self._cache)
        logger.info(
            f"Skills reloaded: {old_count} → {new_count}",
            extra={"added": new_count - old_count}
        )
        
        return True
    
    def clear_cache(self) -> None:
        """Clear the skill cache, forcing a reload on next access.
        
        This method can be called:
        - Manually via API when skills are added/modified
        - Automatically by file watcher when SKILL.md files change
        - By external processes via signal/IPC
        
        Example:
            # In development, force refresh after editing SKILL.md
            registry.clear_cache()
            skills = registry.list_all_skills()  # Will reload from disk
        """
        self._cache.clear()
        self._last_scan_time = None
        logger.info("Skill cache cleared, will reload on next access")
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid.
        
        Returns:
            True if cache is valid
        """
        if self._last_scan_time is None:
            return False
        
        return datetime.now() - self._last_scan_time < self._cache_ttl
    
    def _discover_all_skills(self) -> list[SkillMetadata]:
        """Discover all skills from configured paths.
        
        Scans paths in priority order (low to high), allowing higher priority
        skills to override lower priority ones with the same name.
        
        Returns:
            List of SkillMetadata objects
        """
        skills: dict[str, SkillMetadata] = {}
        
        # Scan system skills first (lowest priority)
        try:
            backend_dir = Path(__file__).parent.parent.parent
            system_skills_path = backend_dir / SYSTEM_SKILLS_PATH
            if system_skills_path.exists():
                system_skills = self._scan_directory(system_skills_path, "system")
                skills.update({s.name: s for s in system_skills})
                logger.info(
                    f"Found {len(system_skills)} system skills",
                    extra={"path": str(system_skills_path)}
                )
        except Exception as e:
            logger.warning(f"Failed to scan system skills: {e}")
        
        # Scan workspace/user skills directory (higher priority, from config)
        user_skills_path = self.workspace_path / self.user_skills_dir
        if user_skills_path.exists():
            try:
                user_skills = self._scan_directory(user_skills_path, "user")
                # Override lower priority skills
                for skill in user_skills:
                    if skill.name in skills:
                        logger.info(
                            f"Overriding skill '{skill.name}' from user skills",
                            extra={"path": str(user_skills_path)}
                        )
                    skills[skill.name] = skill
                
                logger.info(
                    f"Found {len(user_skills)} user skills",
                    extra={"path": str(user_skills_path)}
                )
            except Exception as e:
                logger.warning(f"Failed to scan user skills at {user_skills_path}: {e}")
        else:
            logger.debug(f"User skills directory not found: {user_skills_path}")
        
        return list(skills.values())
    
    def _scan_directory(
        self, 
        directory: Path, 
        level: str = "unknown"
    ) -> list[SkillMetadata]:
        """Scan a directory for skills.
        
        Args:
            directory: Directory to scan
            level: Priority level (for logging)
            
        Returns:
            List of SkillMetadata objects
        """
        skills = []
        
        if not directory.exists() or not directory.is_dir():
            return skills
        
        # Iterate through subdirectories
        for item in directory.iterdir():
            if not item.is_dir():
                continue
            
            # Look for SKILL.md
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                logger.debug(f"No SKILL.md found in {item}")
                continue
            
            try:
                metadata = self._parser.parse(skill_md)
                skills.append(metadata)
            except SkillParseError as e:
                logger.warning(f"Failed to parse skill {item.name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error parsing skill {item.name}: {e}")
        
        return skills
    
    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics.
        
        Returns:
            Dictionary with stats
        """
        return {
            "skills_count": len(self._cache),
            "skill_names": sorted(self._cache.keys()),
            "cache_valid": self._is_cache_valid(),
            "last_scan_time": self._last_scan_time.isoformat() if self._last_scan_time else None,
            "cache_ttl_seconds": self._cache_ttl.total_seconds(),
        }


# Global registry instance (lazy initialization)
_registry: SkillRegistry | None = None


def get_skill_registry(workspace_path: Path | None = None) -> SkillRegistry:
    """Get or create the global skill registry.
    
    Args:
        workspace_path: Path to workspace directory (required on first call)
        
    Returns:
        SkillRegistry instance
    """
    global _registry
    
    if _registry is None:
        if workspace_path is None:
            raise ValueError("workspace_path is required for first initialization")
        _registry = SkillRegistry(workspace_path)
    
    return _registry


def reset_skill_registry() -> None:
    """Reset the global skill registry."""
    global _registry
    _registry = None
