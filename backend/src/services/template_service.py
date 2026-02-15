"""Template service for managing default workspace file templates.

This module provides:
- Default template retrieval
- Template-based file creation
- Workspace initialization support
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .templates import (
    AGENTS_TEMPLATE,
    BOOTSTRAP_TEMPLATE,
    MEMORY_TEMPLATE,
    OWNER_TEMPLATE,
    SPIRIT_TEMPLATE,
    TOOLS_TEMPLATE,
    get_daily_memory_template,
    get_template,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class TemplateService:
    """Service for managing workspace file templates.
    
    Provides templates and creates default files for the agent guidance system.
    """
    
    def __init__(self, workspace_path: str = "workspace") -> None:
        """Initialize template service.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = Path(workspace_path)
        
        logger.info(
            "TemplateService initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    def get_template(self, template_name: str) -> str:
        """Get template content by name.
        
        Args:
            template_name: Name of template (agents, spirit, owner, memory, tools, bootstrap)
            
        Returns:
            Template content string
        """
        return get_template(template_name)
    
    def create_file_from_template(
        self,
        file_name: str,
        template_name: str,
        overwrite: bool = False
    ) -> bool:
        """Create a file from template if it doesn't exist.
        
        Args:
            file_name: Name of the file to create
            template_name: Name of the template to use
            overwrite: Whether to overwrite existing file
            
        Returns:
            True if file was created, False if it already existed
        """
        file_path = self.workspace_path / file_name
        
        if file_path.exists() and not overwrite:
            logger.debug(
                "File already exists, skipping",
                extra={"file_path": str(file_path)}
            )
            return False
        
        template = self.get_template(template_name)
        if not template:
            logger.warning(
                "Template not found",
                extra={"template_name": template_name}
            )
            return False
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(template, encoding="utf-8")
            
            logger.info(
                "File created from template",
                extra={
                    "file_path": str(file_path),
                    "template_name": template_name
                }
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to create file from template",
                extra={
                    "file_path": str(file_path),
                    "error": str(e)
                }
            )
            return False
    
    def create_daily_memory_file(self, date: Optional[str] = None) -> bool:
        """Create daily memory file for a specific date.
        
        Args:
            date: Date string in YYYY-MM-DD format, defaults to today
            
        Returns:
            True if file was created, False if it already existed
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        memory_dir = self.workspace_path / "memory"
        file_path = memory_dir / f"{date}.md"
        
        if file_path.exists():
            logger.debug(
                "Daily memory file already exists",
                extra={"file_path": str(file_path)}
            )
            return False
        
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
            content = get_daily_memory_template(date)
            file_path.write_text(content, encoding="utf-8")
            
            logger.info(
                "Daily memory file created",
                extra={"file_path": str(file_path), "date": date}
            )
            return True
            
        except Exception as e:
            logger.error(
                "Failed to create daily memory file",
                extra={"file_path": str(file_path), "error": str(e)}
            )
            return False
    
    def initialize_workspace(self, create_bootstrap: bool = True) -> dict[str, bool]:
        """Initialize workspace with all default files.
        
        Args:
            create_bootstrap: Whether to create BOOTSTRAP.md for first-time setup
            
        Returns:
            Dictionary with file names as keys and creation status as values
        """
        results: dict[str, bool] = {}
        
        # Create core files
        results["AGENTS.md"] = self.create_file_from_template("AGENTS.md", "agents")
        results["SPIRIT.md"] = self.create_file_from_template("SPIRIT.md", "spirit")
        results["OWNER.md"] = self.create_file_from_template("OWNER.md", "owner")
        results["MEMORY.md"] = self.create_file_from_template("MEMORY.md", "memory")
        results["TOOLS.md"] = self.create_file_from_template("TOOLS.md", "tools")
        
        # Create memory directory and today's file
        memory_dir = self.workspace_path / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        results["memory/today"] = self.create_daily_memory_file()
        
        # Create bootstrap file if requested
        if create_bootstrap:
            results["BOOTSTRAP.md"] = self.create_file_from_template(
                "BOOTSTRAP.md", "bootstrap"
            )
        
        logger.info(
            "Workspace initialization complete",
            extra={
                "workspace_path": str(self.workspace_path),
                "files_created": sum(1 for v in results.values() if v)
            }
        )
        
        return results
    
    def ensure_required_files(self) -> dict[str, bool]:
        """Ensure all required workspace files exist, creating if missing.
        
        This implements the "graceful degradation" strategy - missing files
        are created with defaults rather than causing errors.
        
        Returns:
            Dictionary with file names as keys and whether they were created
        """
        results: dict[str, bool] = {}
        
        required_files = [
            ("AGENTS.md", "agents"),
            ("SPIRIT.md", "spirit"),
            ("OWNER.md", "owner"),
        ]
        
        optional_files = [
            ("MEMORY.md", "memory"),
            ("TOOLS.md", "tools"),
        ]
        
        # Create required files
        for file_name, template_name in required_files:
            results[file_name] = self.create_file_from_template(file_name, template_name)
        
        # Create optional files
        for file_name, template_name in optional_files:
            results[file_name] = self.create_file_from_template(file_name, template_name)
        
        # Ensure memory directory exists
        memory_dir = self.workspace_path / "memory"
        if not memory_dir.exists():
            memory_dir.mkdir(parents=True, exist_ok=True)
            results["memory/"] = True
        else:
            results["memory/"] = False
        
        # Create today's memory file if missing
        results["memory/today"] = self.create_daily_memory_file()
        
        created_count = sum(1 for v in results.values() if v)
        if created_count > 0:
            logger.info(
                "Created missing workspace files",
                extra={
                    "files_created": created_count,
                    "files": [k for k, v in results.items() if v]
                }
            )
        
        return results


# Global template service instance
_template_service: TemplateService | None = None


def get_template_service(workspace_path: str | None = None) -> TemplateService:
    """Get or create global template service instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        TemplateService instance
    """
    global _template_service
    if _template_service is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _template_service = TemplateService(workspace_path)
    return _template_service
