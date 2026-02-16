"""Session guard for enforcing session-related policies.

This guard enforces rules about what context can be loaded
based on session type (main vs shared).
"""

from typing import Any

from ..policy_parser import Rule, RuleType
from ...memory.models import SessionType
from ...utils.logger import get_logger

logger = get_logger(__name__)


class SessionGuard:
    """Guard for session-related policy enforcement.
    
    Enforces rules like:
    - Shared sessions cannot load MEMORY.md
    - Shared sessions operate in sandbox mode
    
    Example:
        guard = SessionGuard()
        rules = guard.apply_rules(SessionType.SHARED, hard_constraints)
        # rules["load_memory_md"] == False
        # rules["sandbox_mode"] == True
    """
    
    def __init__(self) -> None:
        """Initialize the session guard."""
        logger.debug("SessionGuard initialized")
    
    def apply_rules(
        self,
        session_type: SessionType | str,
        hard_constraints: list[Rule],
    ) -> dict[str, Any]:
        """Apply session-related hard constraints.
        
        Args:
            session_type: The type of session
            hard_constraints: List of hard constraint rules
            
        Returns:
            Dict with context loading rules
        """
        # Normalize session type
        if isinstance(session_type, str):
            session_type = SessionType(session_type)
        
        # Default rules
        rules = {
            "load_memory_md": True,
            "load_owner_md": True,
            "sandbox_mode": False,
            "applied_rules": [],
        }
        
        # Shared sessions are always sandboxed
        if session_type == SessionType.SHARED:
            rules["load_memory_md"] = False
            rules["sandbox_mode"] = True
            rules["applied_rules"].append("shared_session_sandbox")
            
            logger.info(
                "Session sandbox enforced",
                extra={"session_type": session_type.value}
            )
        
        # Apply custom rules from AGENTS.md
        for rule in hard_constraints:
            if rule.action is None:
                continue
            
            # Check if rule is session-related
            if self._is_session_rule(rule):
                try:
                    result = rule.action(session_type.value)
                    if isinstance(result, dict):
                        rules.update(result)
                        rules["applied_rules"].append(rule.id)
                except Exception as e:
                    logger.warning(
                        "Failed to apply session rule",
                        extra={
                            "rule_id": rule.id,
                            "error": str(e),
                        }
                    )
        
        return rules
    
    def _is_session_rule(self, rule: Rule) -> bool:
        """Check if a rule is session-related.
        
        Args:
            rule: The rule to check
            
        Returns:
            True if the rule affects session behavior
        """
        session_keywords = [
            "session", "shared", "main", "memory.md",
            "安全准则", "隐私", "私有",
        ]
        
        content_lower = rule.content.lower()
        section_lower = rule.source_section.lower()
        
        for keyword in session_keywords:
            if keyword.lower() in content_lower or keyword.lower() in section_lower:
                return True
        
        return False
    
    def validate_context_load(
        self,
        file_name: str,
        session_type: SessionType | str,
    ) -> tuple[bool, str | None]:
        """Validate if a file can be loaded for the given session type.
        
        Args:
            file_name: Name of the file to load
            session_type: Type of session
            
        Returns:
            Tuple of (is_allowed, reason_if_blocked)
        """
        if isinstance(session_type, str):
            session_type = SessionType(session_type)
        
        # Shared sessions cannot load MEMORY.md
        if session_type == SessionType.SHARED:
            if file_name.upper() == "MEMORY.MD":
                return False, "MEMORY.md is blocked in shared sessions for privacy"
        
        # All other files are allowed
        return True, None
