"""Skill metadata parser for X-Agent.

This module parses SKILL.md files and extracts metadata from YAML frontmatter,
following the Anthropic Skills specification.
"""

import yaml
from pathlib import Path
from typing import Any

from ..models.skill import SkillMetadata
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SkillParseError(Exception):
    """Exception raised when parsing SKILL.md fails."""
    pass


class SkillParser:
    """Parser for SKILL.md files.
    
    Example:
        parser = SkillParser()
        metadata = parser.parse(Path("/path/to/skill/SKILL.md"))
    """
    
    def __init__(self) -> None:
        """Initialize the skill parser."""
        logger.info("SkillParser initialized")
    
    def parse(self, skill_md_path: Path) -> SkillMetadata:
        """Parse SKILL.md and extract metadata.
        
        Args:
            skill_md_path: Path to SKILL.md file
            
        Returns:
            Parsed SkillMetadata object
            
        Raises:
            SkillParseError: If parsing fails
        """
        try:
            # Read file content
            if not skill_md_path.exists():
                raise SkillParseError(f"SKILL.md not found: {skill_md_path}")
            
            if not skill_md_path.is_file():
                raise SkillParseError(f"Not a file: {skill_md_path}")
            
            content = skill_md_path.read_text(encoding='utf-8')
            
            # Parse YAML frontmatter
            metadata_dict = self._parse_frontmatter(content, skill_md_path)
            
            # Detect directory structure
            skill_dir = skill_md_path.parent
            has_scripts = (skill_dir / 'scripts').exists()
            has_references = (skill_dir / 'references').exists()
            has_assets = (skill_dir / 'assets').exists()
            
            # Create metadata object
            metadata = SkillMetadata(
                name=metadata_dict['name'],
                description=metadata_dict['description'],
                path=skill_dir,
                has_scripts=has_scripts,
                has_references=has_references,
                has_assets=has_assets,
                # Phase 2 fields
                disable_model_invocation=metadata_dict.get('disable-model-invocation', False),
                user_invocable=metadata_dict.get('user-invocable', True),
                argument_hint=metadata_dict.get('argument-hint'),
                allowed_tools=metadata_dict.get('allowed_tools'),  # Use underscore to match SKILL.md format
                context=metadata_dict.get('context'),
                license=metadata_dict.get('license'),
            )
            
            logger.info(
                f"Parsed skill: {metadata.name}",
                extra={
                    "path": str(skill_dir),
                    "has_scripts": has_scripts,
                    "has_references": has_references,
                    "has_assets": has_assets,
                }
            )
            
            return metadata
            
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML in SKILL.md: {e}") from e
        except ValueError as e:
            raise SkillParseError(f"Invalid metadata: {e}") from e
        except Exception as e:
            raise SkillParseError(f"Failed to parse SKILL.md: {e}") from e
    
    def _parse_frontmatter(
        self, 
        content: str, 
        file_path: Path
    ) -> dict[str, Any]:
        """Parse YAML frontmatter from SKILL.md content.
        
        Args:
            content: Full content of SKILL.md
            file_path: Path to the file (for error messages)
            
        Returns:
            Dictionary of metadata fields
            
        Raises:
            SkillParseError: If frontmatter is missing or invalid
        """
        # Check for YAML frontmatter
        if not content.strip().startswith('---'):
            raise SkillParseError(
                f"SKILL.md must start with YAML frontmatter (---): {file_path}"
            )
        
        # Split frontmatter
        parts = content.split('---', 2)
        if len(parts) < 3:
            raise SkillParseError(
                f"Invalid YAML frontmatter format (missing closing ---): {file_path}"
            )
        
        yaml_content = parts[1].strip()
        
        # Parse YAML
        try:
            metadata = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            raise SkillParseError(f"Invalid YAML: {e}") from e
        
        # Fix: Ensure metadata is a dict before accessing
        if metadata is None:
            raise SkillParseError(
                f"YAML frontmatter is empty or invalid: {file_path}"
            )
        
        if not isinstance(metadata, dict):
            raise SkillParseError(
                f"YAML frontmatter must be a mapping (key: value pairs), got {type(metadata).__name__}: {file_path}"
            )
        
        # Validate required fields
        if 'name' not in metadata:
            raise SkillParseError(
                f"SKILL.md must have 'name' field: {file_path}"
            )
        if 'description' not in metadata:
            raise SkillParseError(
                f"SKILL.md must have 'description' field: {file_path}"
            )
        
        return metadata


def parse_skill_metadata(skill_md_path: Path) -> SkillMetadata:
    """Convenience function to parse SKILL.md.
    
    Args:
        skill_md_path: Path to SKILL.md file
        
    Returns:
        Parsed SkillMetadata object
    """
    parser = SkillParser()
    return parser.parse(skill_md_path)
