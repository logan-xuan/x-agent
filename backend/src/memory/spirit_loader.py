"""Spirit loader for AI identity management.

This module provides:
- Loading and parsing SPIRIT.md (AI personality)
- Loading and parsing OWNER.md (user profile)
- Identity initialization detection
- Hot-reload support
"""

from pathlib import Path
from typing import Any

from .md_sync import MarkdownSync, get_md_sync
from .models import OwnerProfile, SpiritConfig
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SpiritLoader:
    """Loader for AI identity files.
    
    Manages loading, caching, and initialization of:
    - SPIRIT.md: AI personality configuration
    - OWNER.md: User profile
    """
    
    def __init__(self, workspace_path: str | None = None) -> None:
        """Initialize spirit loader.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = workspace_path or "workspace"
        self._md_sync = MarkdownSync(self.workspace_path)
        self._spirit_cache: SpiritConfig | None = None
        self._owner_cache: OwnerProfile | None = None
        self._spirit_mtime: float = 0.0
        self._owner_mtime: float = 0.0
        
        logger.info(
            "SpiritLoader initialized",
            extra={"workspace_path": self.workspace_path}
        )
    
    def get_identity_status(self) -> dict[str, bool]:
        """Check identity initialization status.
        
        Returns:
            Dictionary with 'initialized', 'has_spirit', 'has_owner' keys
        """
        status = self._md_sync.check_identity_status()
        
        logger.debug(
            "Identity status checked",
            extra=status
        )
        
        return status
    
    def load_spirit(self) -> SpiritConfig | None:
        """Load AI personality configuration.
        
        Returns cached version if file hasn't changed.
        
        Returns:
            SpiritConfig if file exists, None otherwise
        """
        spirit_path = Path(self.workspace_path) / "SPIRIT.md"
        
        if not spirit_path.exists():
            logger.debug("SPIRIT.md not found")
            return None
        
        # Check if cache is valid
        current_mtime = spirit_path.stat().st_mtime
        if self._spirit_cache and current_mtime == self._spirit_mtime:
            logger.debug("Returning cached SPIRIT.md")
            return self._spirit_cache
        
        # Load fresh
        self._spirit_cache = self._md_sync.load_spirit()
        self._spirit_mtime = current_mtime
        
        if self._spirit_cache:
            logger.info(
                "SPIRIT.md loaded",
                extra={
                    "role": self._spirit_cache.role[:50] if self._spirit_cache.role else "",
                    "cached": True,
                }
            )
        
        return self._spirit_cache
    
    def load_owner(self) -> OwnerProfile | None:
        """Load user profile.
        
        Returns cached version if file hasn't changed.
        
        Returns:
            OwnerProfile if file exists, None otherwise
        """
        owner_path = Path(self.workspace_path) / "OWNER.md"
        
        logger.info(
            "Loading OWNER.md",
            extra={
                "workspace_path": self.workspace_path,
                "owner_path": str(owner_path),
                "exists": owner_path.exists(),
            }
        )
        
        if not owner_path.exists():
            logger.debug("OWNER.md not found")
            return None
        
        # Check if cache is valid
        current_mtime = owner_path.stat().st_mtime
        if self._owner_cache and current_mtime == self._owner_mtime:
            logger.debug("Returning cached OWNER.md")
            return self._owner_cache
        
        # Load fresh
        self._owner_cache = self._md_sync.load_owner()
        self._owner_mtime = current_mtime
        
        if self._owner_cache:
            logger.info(
                "OWNER.md loaded",
                extra={
                    "name": self._owner_cache.name,
                    "interests": self._owner_cache.interests,
                    "preferences": self._owner_cache.preferences,
                }
            )
        
        return self._owner_cache
    
    def initialize_identity(
        self,
        owner_name: str,
        owner_occupation: str = "",
        owner_interests: list[str] | None = None,
        ai_role: str | None = None,
        ai_personality: str | None = None,
    ) -> dict[str, Any]:
        """Initialize identity files.
        
        Creates SPIRIT.md and OWNER.md with initial values.
        
        Args:
            owner_name: User name
            owner_occupation: User occupation
            owner_interests: List of interests
            ai_role: Custom AI role
            ai_personality: Custom AI personality
            
        Returns:
            Dictionary with 'success', 'spirit', 'owner' keys
        """
        logger.info(
            "Initializing identity",
            extra={"owner_name": owner_name}
        )
        
        try:
            # Create owner profile
            owner = OwnerProfile(
                name=owner_name,
                occupation=owner_occupation,
                interests=owner_interests or [],
            )
            self._md_sync.save_owner(owner)
            self._owner_cache = owner
            
            # Create spirit config
            spirit = SpiritConfig(
                role=ai_role or "我是一个专注型 AI 助手，服务于个人知识管理。",
                personality=ai_personality or "温和、理性、主动但不过度打扰",
                values=["尊重隐私", "不编造信息", "帮助用户变得更好"],
                behavior_rules=[
                    "在每次响应前，先回顾当前上下文和长期记忆",
                    "对重要计划进行提醒",
                    "拒绝不合理请求（如执行危险命令）",
                ],
            )
            self._md_sync.save_spirit(spirit)
            self._spirit_cache = spirit
            
            logger.info(
                "Identity initialized successfully",
                extra={
                    "owner_name": owner.name,
                    "spirit_role": spirit.role[:50] if spirit.role else "",
                }
            )
            
            return {
                "success": True,
                "spirit": spirit,
                "owner": owner,
            }
            
        except Exception as e:
            logger.error(
                "Failed to initialize identity",
                extra={"error": str(e)}
            )
            return {
                "success": False,
                "error": str(e),
            }
    
    def update_spirit(self, config: SpiritConfig) -> bool:
        """Update AI personality configuration.
        
        Args:
            config: New spirit configuration
            
        Returns:
            True if updated successfully
        """
        success = self._md_sync.save_spirit(config)
        
        if success:
            self._spirit_cache = config
            logger.info(
                "Spirit config updated",
                extra={"role": config.role[:50] if config.role else ""}
            )
        
        return success
    
    def update_owner(self, profile: OwnerProfile) -> bool:
        """Update user profile.
        
        Args:
            profile: New owner profile
            
        Returns:
            True if updated successfully
        """
        success = self._md_sync.save_owner(profile)
        
        if success:
            self._owner_cache = profile
            logger.info(
                "Owner profile updated",
                extra={"name": profile.name}
            )
        
        return success
    
    def clear_cache(self) -> None:
        """Clear cached identity data.
        
        Forces reload on next access.
        """
        self._spirit_cache = None
        self._owner_cache = None
        self._spirit_mtime = 0.0
        self._owner_mtime = 0.0
        
        logger.info("Identity cache cleared")
    
    def reload(self) -> dict[str, bool]:
        """Force reload all identity files.
        
        Returns:
            Dictionary with 'spirit_loaded', 'owner_loaded' keys
        """
        self.clear_cache()
        
        spirit = self.load_spirit()
        owner = self.load_owner()
        
        return {
            "spirit_loaded": spirit is not None,
            "owner_loaded": owner is not None,
        }
    
    def on_spirit_file_changed(self) -> None:
        """Callback for file watcher when SPIRIT.md changes."""
        logger.info("SPIRIT.md changed, invalidating cache")
        self._spirit_cache = None
        self._spirit_mtime = 0.0
    
    def on_owner_file_changed(self) -> None:
        """Callback for file watcher when OWNER.md changes."""
        logger.info("OWNER.md changed, invalidating cache")
        self._owner_cache = None
        self._owner_mtime = 0.0


# Global spirit loader instance
_spirit_loader: SpiritLoader | None = None


def get_spirit_loader(workspace_path: str | None = None) -> SpiritLoader:
    """Get or create global spirit loader instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        SpiritLoader instance
    """
    global _spirit_loader
    if _spirit_loader is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _spirit_loader = SpiritLoader(workspace_path)
    return _spirit_loader
