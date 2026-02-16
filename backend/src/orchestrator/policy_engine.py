"""Policy engine for executing parsed AGENTS.md policies.

This module provides the runtime policy execution engine that:
- Reloads policies when AGENTS.md changes
- Enforces hard constraints at runtime
- Builds soft guidelines for System Prompt injection
- Provides context loading rules based on session type
"""

import time
from pathlib import Path
from typing import Any

from .policy_parser import PolicyParser, PolicyBundle, Rule, RuleType
from ..memory.models import SessionType
from ..utils.logger import get_logger

logger = get_logger(__name__)


class PolicyEngine:
    """Runtime policy execution engine.
    
    Coordinates policy loading and enforcement:
    - Hot-reload policies when AGENTS.md changes
    - Apply hard constraints at runtime
    - Generate soft guidelines for LLM prompts
    
    Example:
        engine = PolicyEngine("/path/to/workspace")
        
        # Check for changes and reload
        policy, changed = engine.reload_if_changed()
        
        # Apply session rules
        rules = engine.enforce_session_rules(SessionType.MAIN)
        
        # Build prompt guidelines
        guidelines = engine.build_system_prompt_guidelines()
    """
    
    def __init__(self, workspace_path: str) -> None:
        """Initialize the policy engine.
        
        Args:
            workspace_path: Path to the workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self.parser = PolicyParser(workspace_path)
        
        # Current policy
        self._policy: PolicyBundle | None = None
        self._last_reload_time: float = 0
        
        logger.info(
            "PolicyEngine initialized",
            extra={"workspace_path": str(self.workspace_path)}
        )
    
    @property
    def policy(self) -> PolicyBundle:
        """Get current policy, loading if necessary."""
        if self._policy is None:
            self._policy = self.parser.parse()
        return self._policy
    
    def reload_if_changed(self) -> tuple[PolicyBundle, bool]:
        """Reload policy if AGENTS.md has changed.
        
        Returns:
            Tuple of (PolicyBundle, was_reloaded)
        """
        bundle, changed = self.parser.parse_if_changed()
        
        if changed:
            self._policy = bundle
            self._last_reload_time = time.time()
            logger.info(
                "Policy reloaded",
                extra={
                    "hard_constraints": len(bundle.hard_constraints),
                    "soft_guidelines": len(bundle.soft_guidelines),
                }
            )
        
        return bundle, changed
    
    def enforce_session_rules(
        self,
        session_type: SessionType | str,
    ) -> dict[str, Any]:
        """Enforce session-related hard constraints.
        
        Determines which context files can be loaded based on session type
        and hard constraint rules from AGENTS.md.
        
        Args:
            session_type: The type of session (MAIN or SHARED)
            
        Returns:
            Dict with context loading rules
        """
        # Normalize session type
        if isinstance(session_type, str):
            session_type = SessionType(session_type)
        
        # Default rules
        rules = {
            "load_memory_md": True,       # Can load MEMORY.md
            "load_owner_md": True,        # Can load OWNER.md
            "sandbox_mode": False,        # Is in sandbox mode
            "reason": None,
        }
        
        # Apply hard constraints
        for rule in self.policy.hard_constraints:
            if rule.action is None:
                continue
            
            # Check for session-related rules
            if "安全准则" in rule.source_section or "session" in rule.content.lower():
                try:
                    result = rule.action(session_type.value)
                    if isinstance(result, dict):
                        rules.update(result)
                        rules["reason"] = f"Rule: {rule.source_section}"
                except Exception as e:
                    logger.warning(
                        "Failed to apply session rule",
                        extra={
                            "rule": rule.id,
                            "error": str(e),
                        }
                    )
        
        # Hard-coded safety: shared sessions never get MEMORY.md
        if session_type == SessionType.SHARED:
            rules["load_memory_md"] = False
            rules["sandbox_mode"] = True
            rules["reason"] = "Shared context: MEMORY.md blocked for privacy"
        
        logger.debug(
            "Session rules enforced",
            extra={
                "session_type": session_type.value,
                "rules": rules,
            }
        )
        
        return rules
    
    def check_tool_permission(self, tool_name: str) -> dict[str, Any]:
        """Check if a tool call is allowed.
        
        Applies hard constraint rules to determine:
        - Whether the tool can be used
        - Whether user confirmation is required
        
        Args:
            tool_name: Name of the tool to check
            
        Returns:
            Dict with permission info:
            - allowed: bool - Whether the tool can be used
            - need_confirm: bool - Whether user confirmation is needed
            - reason: str | None - Reason for the decision
        """
        # Default: allow all tools without confirmation (trust mode)
        result = {
            "allowed": True,
            "need_confirm": False,
            "reason": None,
        }
        
        # Apply hard constraints
        for rule in self.policy.hard_constraints:
            if rule.action is None:
                continue
            
            # Check for external operation rules
            if "外部操作" in rule.source_section:
                try:
                    check_result = rule.action(tool_name)
                    if isinstance(check_result, dict):
                        result.update(check_result)
                        if check_result.get("need_confirm"):
                            result["reason"] = f"Rule: {rule.source_section}"
                except Exception as e:
                    logger.warning(
                        "Failed to check tool permission",
                        extra={
                            "rule": rule.id,
                            "tool": tool_name,
                            "error": str(e),
                        }
                    )
        
        logger.debug(
            "Tool permission checked",
            extra={
                "tool": tool_name,
                "result": result,
            }
        )
        
        return result
    
    def build_system_prompt_guidelines(self) -> str:
        """Build soft guidelines for System Prompt injection.

        Formats all soft guidelines from AGENTS.md into a single
        prompt section that can be injected into the LLM's system prompt.
        Also includes P0 hard constraints that should be explicitly known to the LLM.
        Only includes essential guidelines that are beneficial for LLM
        understanding while minimizing token usage.

        Returns:
            Formatted string with all soft guidelines and P0 hard constraints
        """
        parts: list[str] = []

        # Add header
        parts.append("# 行为准则")
        parts.append("以下是你需要遵循的行为规范：")

        # Add each soft guideline with optimization
        # Only include specific sections that are essential for LLM behavior
        essential_sections = ["首次启动"]

        for rule in self.policy.soft_guidelines:
            if rule.prompt_text and any(essential in rule.source_section for essential in essential_sections):
                # Only include essential guidelines for LLM
                parts.append(f"\n{rule.prompt_text}")

        # Add identity rules (these are also prompt-injected)
        # Only include "首次启动" related identity rules
        for rule in self.policy.identity_rules:
            if rule.prompt_text and "首次启动" in rule.source_section:
                parts.append(f"\n{rule.prompt_text}")

        # Add P0 hard constraints that should be explicitly known to LLM
        # These are critical safety/security constraints that need dual protection:
        # 1. Known to LLM in system prompt (first line of defense)
        # 2. Enforced by PolicyEngine at runtime (fallback protection)
        p0_hard_constraint_sections = ["安全准则"]
        for rule in self.policy.hard_constraints:
            if rule.prompt_text and any(p0_section in rule.source_section for p0_section in p0_hard_constraint_sections):
                parts.append(f"\n{rule.prompt_text}")

        guidelines = "\n".join(parts)

        # Further optimize by limiting length if too large
        if len(guidelines) > 500:  # Further reduced limit to ~500 characters
            guidelines = guidelines[:500] + "\n... (内容截断以优化性能)"

        logger.debug(
            "System prompt guidelines built",
            extra={
                "length": len(guidelines),
                "guidelines_summary": guidelines[:200] + ("..." if len(guidelines) > 200 else "")
            }
        )

        return guidelines
    
    def get_context_load_order(self) -> list[str]:
        """Get the order of context files to load.
        
        Returns:
            List of file names in load order
        """
        # Standard load order
        return [
            "AGENTS.md",
            "SPIRIT.md",
            "IDENTITY.md",
            "OWNER.md",
            "TOOLS.md",
            "MEMORY.md",
            "memory/",  # Daily logs
        ]
    
    def get_stats(self) -> dict[str, Any]:
        """Get policy engine statistics.
        
        Returns:
            Dict with engine stats
        """
        return {
            "policy": self.policy.to_dict() if self._policy else None,
            "last_reload_time": self._last_reload_time,
            "workspace_path": str(self.workspace_path),
        }
    
    def clear_cache(self) -> None:
        """Clear all cached policies."""
        self.parser.clear_cache()
        self._policy = None
        self._last_reload_time = 0
        logger.info("PolicyEngine cache cleared")


# Global policy engine instance
_policy_engine: PolicyEngine | None = None


def get_policy_engine(workspace_path: str | None = None) -> PolicyEngine:
    """Get or create the global policy engine instance.
    
    Args:
        workspace_path: Optional workspace path. Required on first call.
        
    Returns:
        PolicyEngine instance
    """
    global _policy_engine
    
    if _policy_engine is None:
        if workspace_path is None:
            raise ValueError("workspace_path is required for first initialization")
        _policy_engine = PolicyEngine(workspace_path)
    
    return _policy_engine


def clear_policy_engine() -> None:
    """Clear the global policy engine instance."""
    global _policy_engine
    _policy_engine = None
