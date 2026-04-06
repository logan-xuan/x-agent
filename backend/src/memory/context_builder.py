"""Context builder for multi-level context loading.

This module provides:
- Multi-level context loading (identity, tools, memory)
- Context formatting for AI prompts
- Caching for performance
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .md_sync import MarkdownSync
    from .models import (
        ContextBundle,
        DailyLog,
        IdentityConfig,
        OwnerProfile,
        SpiritConfig,
        ToolDefinition,
    )
    from .spirit_loader import SpiritLoader
    from ..utils.logger import get_logger
except ImportError:  # 顶层 memory.* 导入兼容
    from memory.md_sync import MarkdownSync  # type: ignore
    from memory.models import (  # type: ignore
        ContextBundle,
        DailyLog,
        IdentityConfig,
        OwnerProfile,
        SpiritConfig,
        ToolDefinition,
    )
    from memory.spirit_loader import SpiritLoader  # type: ignore
    from utils.logger import get_logger  # type: ignore

logger = get_logger(__name__)


class ContextBuilder:
    """Builder for AI response context.
    
    Loads and bundles context from multiple sources:
    - Level 0: AGENTS.md (main guidance from ContextLoader)
    - Level 1: Identity (SPIRIT.md, OWNER.md)
    - Level 2: Tools (TOOLS.md)
    - Level 3: Recent memory (memory/*.md)
    - Level 4: Long-term memory (MEMORY.md)
    """
    
    def __init__(self, workspace_path: str | None = None) -> None:
        """Initialize context builder.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.workspace_path = workspace_path or "workspace"
        self._spirit_loader = SpiritLoader(self.workspace_path)
        self._md_sync = MarkdownSync(self.workspace_path)
        
        # Cache
        self._tools: list[ToolDefinition] | None = None
        self._last_load_time: datetime | None = None
        self._cached_context: ContextBundle | None = None
        self._cache_ttl_seconds = 60  # Cache for 60 seconds
        
        logger.info(
            "ContextBuilder initialized",
            extra={"workspace_path": self.workspace_path}
        )
    
    def build_context(self) -> ContextBundle:
        """Build context bundle for AI response.
        
        Loads all context levels and bundles them together.
        Note: Bootstrap detection and AGENTS.md loading are handled
        by SystemPromptBuilder, not here.
        
        Returns:
            ContextBundle with all loaded context
        """
        logger.info("Building context")
        
        # Check cache validity
        if self._is_cache_valid() and self._cached_context is not None:
            logger.debug("Using cached context")
            return self._cached_context
        
        # Load all components
        spirit = self._spirit_loader.load_spirit()
        identity = self._load_identity()
        owner = self._spirit_loader.load_owner()
        tools = self._load_tools()
        recent_logs = self._load_recent_logs()
        long_term_memory = self._load_long_term_memory()
        
        context = ContextBundle(
            spirit=spirit,
            identity=identity,
            owner=owner,
            tools=tools,
            recent_logs=recent_logs,
            long_term_memory=long_term_memory,
            loaded_at=datetime.now(),
        )
        
        # Save to cache
        self._cached_context = context
        self._last_load_time = datetime.now()
        
        logger.info(
            "Context built",
            extra={
                "has_spirit": spirit is not None,
                "has_identity": identity is not None,
                "identity_name": identity.name if identity else None,
                "has_owner": owner is not None,
                "tools_count": len(tools),
                "logs_count": len(recent_logs),
            }
        )
        
        return context
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._last_load_time is None:
            return False
        
        elapsed = (datetime.now() - self._last_load_time).total_seconds()
        return elapsed < self._cache_ttl_seconds
    
    def _build_from_cache(self) -> ContextBundle:
        """Build context from cached data."""
        spirit = self._spirit_loader.load_spirit()
        owner = self._spirit_loader.load_owner()
        
        return ContextBundle(
            spirit=spirit,
            owner=owner,
            tools=self._tools or [],
            recent_logs=[],
            long_term_memory="",
            loaded_at=self._last_load_time or datetime.now(),
        )
    
    def _load_tools(self) -> list[ToolDefinition]:
        """Load tool definitions from TOOLS.md."""
        if self._tools is not None:
            return self._tools
        
        tools = self._md_sync.load_tools()
        self._tools = tools
        
        logger.debug(
            "Tools loaded",
            extra={"count": len(tools)}
        )
        
        return tools
    
    def _load_recent_logs(self, days: int = 7) -> list[DailyLog]:
        """Load recent daily logs.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of DailyLog objects
        """
        logs: list[DailyLog] = []
        memory_dir = Path(self.workspace_path) / "memory"
        
        if not memory_dir.exists():
            return logs
        
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            log = self._md_sync.load_daily_log(date_str)
            if log:
                logs.append(log)
        
        logger.debug(
            "Recent logs loaded",
            extra={"count": len(logs), "days": days}
        )
        
        return logs
    
    def _load_identity(self) -> IdentityConfig | None:
        """Load AI identity from IDENTITY.md.
        
        Returns:
            IdentityConfig if file exists, None otherwise
        """
        import re
        
        identity_path = Path(self.workspace_path) / "IDENTITY.md"
        
        if not identity_path.exists():
            logger.debug("IDENTITY.md not found")
            return None
        
        try:
            content = identity_path.read_text(encoding="utf-8")
            
            # Parse identity fields from markdown
            config = IdentityConfig()
            
            # Parse name: - **Name:** value
            name_match = re.search(r"\*\*Name:\*\*\s*(.+)", content)
            if name_match:
                config.name = name_match.group(1).strip()
            
            # Parse form/creature
            form_match = re.search(r"\*\*Creature:\*\*\s*(.+)", content)
            if form_match:
                config.form = form_match.group(1).strip()
            
            # Parse style/vibe
            style_match = re.search(r"\*\*Vibe:\*\*\s*(.+)", content)
            if style_match:
                config.style = style_match.group(1).strip()
            
            # Parse emoji
            emoji_match = re.search(r"\*\*Emoji:\*\*\s*(.+)", content)
            if emoji_match:
                config.emoji = emoji_match.group(1).strip()
            
            config.file_path = str(identity_path)
            
            logger.info(
                "IDENTITY.md loaded",
                extra={
                    "name": config.name,
                    "form": config.form,
                    "style": config.style,
                }
            )
            
            return config
            
        except Exception as e:
            logger.error(
                "Failed to load IDENTITY.md",
                extra={"error": str(e)}
            )
            return None
    
    def _load_long_term_memory(self) -> str:
        """Load long-term memory from MEMORY.md.
        
        Returns:
            Long-term memory content
        """
        memory_path = Path(self.workspace_path) / "MEMORY.md"
        
        logger.info(
            "Loading MEMORY.md",
            extra={
                "workspace_path": self.workspace_path,
                "memory_path": str(memory_path),
                "exists": memory_path.exists(),
            }
        )
        
        if not memory_path.exists():
            return ""
        
        try:
            content = memory_path.read_text(encoding="utf-8")
            logger.info("Long-term memory loaded", extra={"content_length": len(content)})
            return content
        except Exception as e:
            logger.error(
                "Failed to load long-term memory",
                extra={"error": str(e)}
            )
            return ""
    
    def format_context_for_prompt(self, context: ContextBundle) -> str:
        """Format context for AI prompt injection.
        
        Args:
            context: Context bundle to format
            
        Returns:
            Formatted context string for prompt
        """
        parts: list[str] = []
        
        # Add identity context
        if context.spirit:
            parts.append("## AI 身份")
            parts.append(f"角色: {context.spirit.role}")
            if context.spirit.personality:
                parts.append(f"性格: {context.spirit.personality}")
            if context.spirit.values:
                parts.append(f"价值观: {', '.join(context.spirit.values)}")
        
        if context.owner:
            parts.append("\n## 用户画像")
            parts.append(f"姓名: {context.owner.name}")
            if context.owner.occupation:
                parts.append(f"职业: {context.owner.occupation}")
            if context.owner.interests:
                parts.append(f"兴趣: {', '.join(context.owner.interests)}")
            if context.owner.goals:
                parts.append(f"目标: {', '.join(context.owner.goals)}")
        
        # Add tools context
        if context.tools:
            parts.append("\n## 可用工具")
            for tool in context.tools[:10]:  # Limit to 10 tools
                parts.append(f"- {tool.name}: {tool.description}")
        
        # Add long-term memory (keep most recent entries at the end)
        if context.long_term_memory:
            parts.append("\n## 长期记忆")
            memory_content = context.long_term_memory.strip()
            if len(memory_content) > 1000:
                memory_content = "...\n" + memory_content[-1000:]
            parts.append(memory_content)
        
        prompt = "\n".join(parts)
        
        logger.debug(
            "Context formatted for prompt",
            extra={"prompt_length": len(prompt)}
        )
        
        return prompt
    
    def get_system_prompt(self, context: ContextBundle) -> str:
        """Generate system prompt from context.
        
        Note: This is a legacy method. The primary system prompt is now
        built by SystemPromptBuilder. This method is kept for backward
        compatibility with ContextLoader consumers.
        
        Args:
            context: Context bundle
            
        Returns:
            System prompt string with context summary
        """
        parts: list[str] = []
        
        # AI Identity
        if context.identity and context.identity.name:
            parts.append(f"# AI 身份: {context.identity.name}")
        
        if context.spirit:
            parts.append(f"角色: {context.spirit.role}")
        
        # User Profile
        if context.owner:
            parts.append(f"\n# 用户: {context.owner.name}")
        
        # Long-term Memory (keep most recent entries)
        if context.long_term_memory:
            parts.append("\n# 长期记忆")
            memory_content = context.long_term_memory.strip()
            if len(memory_content) > 800:
                memory_content = "...\n" + memory_content[-800:]
            parts.append(memory_content)
        
        return "\n".join(parts)
    
    def clear_cache(self) -> None:
        """Clear all cached data.
        
        Forces reload on next build_context call.
        """
        self._spirit_loader.clear_cache()
        self._tools = None
        self._cached_context = None
        self._last_load_time = None
        
        logger.info("Context cache cleared")
    
    def update_tools_cache(self, tools: list[ToolDefinition]) -> None:
        """Update tools cache.
        
        Args:
            tools: New tools list to cache
        """
        self._tools = tools
        logger.debug("Tools cache updated")


# Global context builder instance
_context_builder: ContextBuilder | None = None


def get_context_builder(workspace_path: str | None = None) -> ContextBuilder:
    """Get or create global context builder instance.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        ContextBuilder instance
    """
    global _context_builder
    if _context_builder is None:
        if workspace_path is None:
            workspace_path = "workspace"
        _context_builder = ContextBuilder(workspace_path)
    return _context_builder
