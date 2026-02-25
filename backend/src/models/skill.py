"""Skill metadata models for X-Agent.

This module defines the data structures for Skill metadata, following the Anthropic Skills specification.
See: https://code.claude.com/docs/zh-CN/skills
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillMetadata:
    """Skill metadata parsed from SKILL.md YAML frontmatter.
    
    Attributes:
        name: Skill identifier (lowercase/alphanumeric/hyphens, 1-64 chars)
        description: What the skill does and when to use it (1-1-1024 chars)
        path: Path to the skill directory
        keywords: List of trigger keywords for auto-detection (comma-separated)
        has_scripts: Whether the skill has a scripts/ directory
        has_references: Whether the skill has a references/ directory
        has_assets: Whether the skill has an assets/ directory
        
        # Phase 2 optional fields
        disable_model_invocation: Prevent LLM from auto-triggering (default: False)
        user_invocable: Available via / command menu (default: True)
        argument_hint: Argument completion hint (e.g., "[filename] [format]")
        allowed_tools: List of tools allowed when this skill is active
        forbidden_tools: List of tools forbidden when this skill is active
        context: Execution context ("fork" for isolated execution)
        license: License identifier (e.g., "Apache-2.0", "Proprietary")
        
        # Phase 3: Skill matching and prioritization
        auto_trigger: Whether skill can be auto-triggered by LLM (default: True)
        priority: Skill priority (lower number = higher priority, default: 999)
    """
    name: str
    description: str
    path: Path
    
    # Directory structure detection
    has_scripts: bool = False
    has_references: bool = False
    has_assets: bool = False
    
    # Phase 2 optional fields
    disable_model_invocation: bool = False
    user_invocable: bool = True
    argument_hint: str | None = None
    allowed_tools: list[str] | None = None
    forbidden_tools: list[str] = field(default_factory=list)  # ✅ NEW: Dynamic forbidden tools
    context: str | None = None
    license: str | None = None
    keywords: list[str] = field(default_factory=list)  # ✅ NEW: Auto-trigger keywords
    
    # Phase 3: Skill matching and prioritization
    auto_trigger: bool = True  # 🔥 NEW: Auto-trigger configuration
    priority: int = 999  # 🔥 NEW: Priority (lower = higher priority)
    
    # Additional metadata (for future extensibility)
    extra: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        # Validate name
        if not self.name:
            raise ValueError("Skill name is required")
        if len(self.name) > 64:
            raise ValueError(f"Skill name too long: {len(self.name)} > 64")
        if not all(c.islower() or c.isdigit() or c in '-_' for c in self.name):
            raise ValueError(
                f"Skill name must be lowercase alphanumeric with hyphens: {self.name}"
            )
        
        # Validate description
        if not self.description:
            raise ValueError("Skill description is required")
        if len(self.description) > 1024:
            raise ValueError(
                f"Skill description too long: {len(self.description)} > 1024"
            )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "has_scripts": self.has_scripts,
            "has_references": self.has_references,
            "has_assets": self.has_assets,
            "disable_model_invocation": self.disable_model_invocation,
            "user_invocable": self.user_invocable,
            "argument_hint": self.argument_hint,
            "allowed_tools": self.allowed_tools,
            "forbidden_tools": self.forbidden_tools,  # ✅ NEW
            "keywords": self.keywords,  # ✅ NEW
            "context": self.context,
            "license": self.license,
            "auto_trigger": self.auto_trigger,  # 🔥 NEW
            "priority": self.priority,  # 🔥 NEW
            **self.extra
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillMetadata":
        """Create from dictionary format."""
        return cls(
            name=data["name"],
            description=data["description"],
            path=Path(data["path"]),
            has_scripts=data.get("has_scripts", False),
            has_references=data.get("has_references", False),
            has_assets=data.get("has_assets", False),
            disable_model_invocation=data.get("disable_model_invocation", False),
            user_invocable=data.get("user_invocable", True),
            argument_hint=data.get("argument_hint"),
            allowed_tools=data.get("allowed_tools"),
            forbidden_tools=data.get("forbidden_tools", []),  # ✅ NEW
            keywords=data.get("keywords", []),  # ✅ NEW
            context=data.get("context"),
            license=data.get("license"),
            auto_trigger=data.get("auto_trigger", True),  # 🔥 NEW
            priority=data.get("priority", 999),  # 🔥 NEW
            extra={k: v for k, v in data.items() if k not in [
                "name", "description", "path", "has_scripts", "has_references",
                "has_assets", "disable_model_invocation", "user_invocable",
                "argument_hint", "allowed_tools", "forbidden_tools", "keywords",
                "context", "license", "auto_trigger", "priority"
            ]}
        )
