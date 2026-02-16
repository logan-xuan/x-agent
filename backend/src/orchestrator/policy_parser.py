"""Policy parser for AGENTS.md.

This module parses AGENTS.md content into structured policies:
- Hard constraints: System-enforced rules
- Soft guidelines: LLM prompt guidelines
- Identity rules: Role and personality definitions
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ..utils.logger import get_logger

logger = get_logger(__name__)


class RuleType(Enum):
    """Type of rule parsed from AGENTS.md."""
    HARD_CONSTRAINT = "hard_constraint"  # System-enforced, non-negotiable
    SOFT_GUIDELINE = "soft_guideline"    # Injected into System Prompt
    IDENTITY = "identity"                # Role and personality definition


@dataclass
class Rule:
    """A single rule parsed from AGENTS.md.
    
    Attributes:
        id: Unique identifier for the rule
        type: Rule type (hard constraint, soft guideline, or identity)
        source_section: The markdown section header where this rule was found
        content: The raw content of the rule
        action: Optional callable for hard constraints
        prompt_text: Optional formatted text for soft guidelines
    """
    id: str
    type: RuleType
    source_section: str
    content: str
    action: Callable[[Any], Any] | None = None
    prompt_text: str | None = None
    
    def to_dict(self) -> dict:
        """Convert rule to dictionary representation."""
        return {
            "id": self.id,
            "type": self.type.value,
            "source_section": self.source_section,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "has_action": self.action is not None,
            "has_prompt": self.prompt_text is not None,
        }


@dataclass
class PolicyBundle:
    """Bundle of all parsed policies from AGENTS.md.
    
    Attributes:
        hard_constraints: Rules that must be enforced by the system
        soft_guidelines: Rules that are injected into the LLM prompt
        identity_rules: Rules defining the agent's identity
        source_hash: Hash of the source content for change detection
        compiled_at: Timestamp when the bundle was compiled
    """
    hard_constraints: list[Rule] = field(default_factory=list)
    soft_guidelines: list[Rule] = field(default_factory=list)
    identity_rules: list[Rule] = field(default_factory=list)
    source_hash: str = ""
    compiled_at: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert bundle to dictionary representation."""
        return {
            "hard_constraints_count": len(self.hard_constraints),
            "soft_guidelines_count": len(self.soft_guidelines),
            "identity_rules_count": len(self.identity_rules),
            "source_hash": self.source_hash[:8],
            "compiled_at": self.compiled_at,
        }


# Section to rule type mapping
SECTION_TYPE_MAP: dict[str, RuleType] = {
    # Hard constraints - system enforced
    "安全准则": RuleType.HARD_CONSTRAINT,
    "外部操作": RuleType.HARD_CONSTRAINT,
    "外部操作 vs 内部操作": RuleType.HARD_CONSTRAINT,
    
    # Soft guidelines - prompt injected
    "避免三连击": RuleType.SOFT_GUIDELINE,
    "表情反应": RuleType.SOFT_GUIDELINE,
    "记忆系统": RuleType.SOFT_GUIDELINE,
    "动手写下来": RuleType.SOFT_GUIDELINE,
    "工具": RuleType.SOFT_GUIDELINE,
    "记忆维护": RuleType.SOFT_GUIDELINE,
    "打造你的风格": RuleType.SOFT_GUIDELINE,
    
    # Identity - role definition
    "首次启动": RuleType.IDENTITY,
    "每次会话开始时": RuleType.IDENTITY,
    "每次会话": RuleType.IDENTITY,
}


class PolicyParser:
    """Parser for AGENTS.md content.
    
    Parses markdown content into structured rules and policies.
    Supports hot-reload via content hash comparison.
    
    Example:
        parser = PolicyParser("/path/to/workspace")
        bundle = parser.parse()
        
        # Check for changes
        new_bundle, changed = parser.parse_if_changed()
    """
    
    def __init__(self, workspace_path: str) -> None:
        """Initialize the policy parser.
        
        Args:
            workspace_path: Path to the workspace directory containing AGENTS.md
        """
        self.workspace_path = Path(workspace_path)
        self.agents_path = self.workspace_path / "AGENTS.md"
        
        # Cache
        self._cached_bundle: PolicyBundle | None = None
        self._source_hash: str = ""
        
        logger.info(
            "PolicyParser initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    def parse(self, content: str | None = None) -> PolicyBundle:
        """Parse AGENTS.md content into a policy bundle.
        
        Args:
            content: Optional content to parse. If None, reads from AGENTS.md.
            
        Returns:
            PolicyBundle with parsed rules
        """
        # Read content if not provided
        if content is None:
            if self.agents_path.exists():
                content = self.agents_path.read_text(encoding="utf-8")
            else:
                logger.warning("AGENTS.md not found, using empty policy")
                content = ""
        
        # Calculate hash for change detection
        new_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Return cached bundle if unchanged
        if self._cached_bundle is not None and new_hash == self._source_hash:
            logger.debug("Using cached policy bundle")
            return self._cached_bundle
        
        # Parse rules from content
        rules = self._extract_rules(content)
        
        # Create bundle
        bundle = PolicyBundle(
            hard_constraints=[r for r in rules if r.type == RuleType.HARD_CONSTRAINT],
            soft_guidelines=[r for r in rules if r.type == RuleType.SOFT_GUIDELINE],
            identity_rules=[r for r in rules if r.type == RuleType.IDENTITY],
            source_hash=new_hash,
            compiled_at=time.time(),
        )
        
        # Update cache
        self._cached_bundle = bundle
        self._source_hash = new_hash
        
        logger.info(
            "Policy bundle compiled",
            extra={
                "hard_constraints": len(bundle.hard_constraints),
                "soft_guidelines": len(bundle.soft_guidelines),
                "identity_rules": len(bundle.identity_rules),
                "hash": new_hash[:8],
            }
        )
        
        return bundle
    
    def parse_if_changed(self) -> tuple[PolicyBundle, bool]:
        """Parse only if content has changed.
        
        Returns:
            Tuple of (PolicyBundle, was_changed)
        """
        # Read current content
        if self.agents_path.exists():
            content = self.agents_path.read_text(encoding="utf-8")
        else:
            content = ""
        
        # Calculate hash
        new_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Check if changed
        if self._cached_bundle is not None and new_hash == self._source_hash:
            return self._cached_bundle, False
        
        # Parse and return
        bundle = self.parse(content)
        return bundle, True
    
    def _extract_rules(self, content: str) -> list[Rule]:
        """Extract rules from markdown content.
        
        Parses sections (## headers) and extracts rules from each.
        
        Args:
            content: Markdown content to parse
            
        Returns:
            List of extracted rules
        """
        rules: list[Rule] = []
        
        # Pattern to match sections: ## Section Name\n content
        section_pattern = r"##\s+([^#\n]+)\n([\s\S]*?)(?=##|$)"
        
        for i, match in enumerate(re.finditer(section_pattern, content)):
            section_name = match.group(1).strip()
            section_content = match.group(2).strip()
            
            # Determine rule type
            rule_type = self._determine_rule_type(section_name)
            
            # Create rule
            rule = Rule(
                id=f"rule_{i}_{section_name.lower().replace(' ', '_')}",
                type=rule_type,
                source_section=section_name,
                content=section_content,
                action=self._compile_action(section_name, section_content),
                prompt_text=self._extract_prompt_text(section_name, section_content),
            )
            rules.append(rule)
            
            logger.debug(
                "Rule extracted",
                extra={
                    "section": section_name,
                    "type": rule_type.value,
                    "content_length": len(section_content),
                }
            )
        
        return rules
    
    def _determine_rule_type(self, section_name: str) -> RuleType:
        """Determine the rule type for a section.
        
        Args:
            section_name: The section header text
            
        Returns:
            The appropriate RuleType
        """
        # Direct match
        if section_name in SECTION_TYPE_MAP:
            return SECTION_TYPE_MAP[section_name]
        
        # Partial match (section name contains key)
        for key, rule_type in SECTION_TYPE_MAP.items():
            if key in section_name or section_name in key:
                return rule_type
        
        # Default to soft guideline
        return RuleType.SOFT_GUIDELINE
    
    def _compile_action(self, section: str, content: str) -> Callable[[Any], Any] | None:
        """Compile a hard constraint into an executable action.
        
        This creates callable functions that enforce rules at runtime.
        
        Args:
            section: Section name
            content: Section content
            
        Returns:
            A callable that enforces the rule, or None for non-hard constraints
        """
        # Session rules - enforce MEMORY.md restrictions
        if "安全准则" in section or "共享上下文" in content:
            def check_session_rules(session_type: str) -> dict:
                """Check session-related rules."""
                return {
                    "load_memory_md": session_type != "shared",
                    "sandbox_mode": session_type == "shared",
                }
            return check_session_rules
        
        # External operation rules - require confirmation
        if "外部操作" in section:
            def check_external_operation(operation: str) -> dict:
                """Check if an operation requires user confirmation."""
                # Operations that always need confirmation
                confirm_required = {"send_email", "post_social", "execute_command"}
                # Safe operations
                safe_operations = {"read_file", "list_dir", "search_web", "read_memory"}
                
                if operation in safe_operations:
                    return {"allowed": True, "need_confirm": False}
                elif operation in confirm_required:
                    return {"allowed": True, "need_confirm": True}
                else:
                    # Unknown operations default to needing confirmation
                    return {"allowed": True, "need_confirm": True}
            return check_external_operation
        
        return None
    
    def _extract_prompt_text(self, section: str, content: str) -> str | None:
        """Extract text suitable for System Prompt injection.
        
        For soft guidelines, extracts bullet points and key instructions.
        
        Args:
            section: Section name
            content: Section content
            
        Returns:
            Formatted text for prompt injection, or None
        """
        lines = content.split("\n")
        
        # Extract bullet points
        bullets = []
        for line in lines:
            line = line.strip()
            if line.startswith("- "):
                bullets.append(line[2:])  # Remove "- " prefix
            elif line.startswith("* "):
                bullets.append(line[2:])  # Remove "* " prefix
            elif line.startswith("> "):
                bullets.append(line[2:])  # Remove "> " prefix
        
        if bullets:
            # Format as bullet list, limit to 5 items
            formatted = "\n".join(f"- {b}" for b in bullets[:5])
            return f"**{section}**\n{formatted}"
        
        # If no bullets, return first 200 chars
        if content:
            preview = content[:200]
            if len(content) > 200:
                preview += "..."
            return f"**{section}**: {preview}"
        
        return None
    
    def clear_cache(self) -> None:
        """Clear the cached policy bundle."""
        self._cached_bundle = None
        self._source_hash = ""
        logger.info("Policy cache cleared")
