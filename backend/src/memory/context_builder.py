"""Context builder for multi-level context loading.

This module provides:
- Multi-level context loading (identity, tools, memory)
- Context formatting for AI prompts
- Caching for performance
- Integration with ContextLoader for AGENTS.md and Bootstrap
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
from ..core.context_loader import ContextLoader, get_context_loader
from ..utils.logger import get_logger

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
        
        # Use the new ContextLoader for AGENTS.md and Bootstrap
        self._context_loader = get_context_loader(self.workspace_path)
        
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
        Now includes:
        - Bootstrap content injection (NOT auto-deletion)
        - AGENTS.md hot-reload
        
        Returns:
            ContextBundle with all loaded context
        """
        logger.info("Building context")
        
        # ===== Bootstrap Detection (First-time startup) =====
        # Check if BOOTSTRAP.md exists and get its content
        bootstrap_status = self._context_loader.check_bootstrap()
        if bootstrap_status.exists:
            logger.info(
                "BOOTSTRAP.md detected, content will be injected for Agent to process",
                extra={"has_content": bool(bootstrap_status.content)}
            )
            # DO NOT auto-delete - let Agent process it and decide when to delete
        
        # ===== AGENTS.md Hot-Reload =====
        # Always check for AGENTS.md changes (hot-reload on every user query)
        agents_content, agents_reloaded = self._context_loader.load_agents_content()
        if agents_reloaded:
            logger.info("AGENTS.md reloaded with fresh content")
        
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
                "agents_reloaded": agents_reloaded,
                "has_bootstrap": bootstrap_status.exists,
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
        
        # Add long-term memory
        if context.long_term_memory:
            parts.append("\n## 长期记忆")
            # Truncate to avoid token limit
            memory_preview = context.long_term_memory[:1000]
            parts.append(memory_preview)
        
        prompt = "\n".join(parts)
        
        logger.debug(
            "Context formatted for prompt",
            extra={"prompt_length": len(prompt)}
        )
        
        return prompt
    
    def get_system_prompt(self, context: ContextBundle) -> str:
        """Generate system prompt from context.
        
        This method generates a complete system prompt that includes:
        - BOOTSTRAP.md: First-time initialization guide (if exists)
        - AGENTS.md: Main guidance and behavior rules (from ContextLoader)
        - AI identity (SPIRIT.md): role, personality, values, behavior rules
        - User profile (OWNER.md): name, occupation, interests, goals
        - Available tools (TOOLS.md)
        - Recent memory logs (memory/*.md)
        - Long-term memory (MEMORY.md)
        
        Args:
            context: Context bundle
            
        Returns:
            System prompt string with full context
        """
        parts: list[str] = []
        
        # ===== BOOTSTRAP.md (First-time initialization) =====
        # Only load BOOTSTRAP.md if it exists AND identity is not yet set up
        # Once identity is set up, the main guidance comes from AGENTS.md
        bootstrap_status = self._context_loader.check_bootstrap()
        if bootstrap_status.exists and bootstrap_status.content and not bootstrap_status.completed:
            parts.append("# 🌟 首次启动初始化")
            parts.append(bootstrap_status.content)
            parts.append("\n---\n")  # Separator
            parts.append("**重要**: 请按照上述指引与用户对话，完成身份设定后，用户会删除此文件。\n")
        
        # ===== AGENTS.md (Main Guidance - Level 0) =====
        # Load AGENTS.md content via ContextLoader (hot-reload support)
        agents_content, _ = self._context_loader.load_agents_content()
        if agents_content:
            parts.append("# 行为规范指导")
            parts.append(agents_content)
            parts.append("")  # Add spacing
        
        # ===== AI Identity (SPIRIT.md + IDENTITY.md) =====
        # First, add AI name from IDENTITY.md
        if context.identity and context.identity.name:
            parts.append("# AI 身份设定")
            parts.append(f"你的名字是「{context.identity.name}」。")
            
            if context.identity.form:
                parts.append(f"存在形式: {context.identity.form}")
            
            if context.identity.style:
                parts.append(f"气质风格: {context.identity.style}")
            
            if context.identity.emoji:
                parts.append(f"标志性表情: {context.identity.emoji}")
            
            parts.append("")  # Spacing
        
        # Then add role/personality from SPIRIT.md
        if context.spirit:
            if not (context.identity and context.identity.name):
                parts.append("# AI 身份设定")
            
            parts.append(f"你是{context.spirit.role}。")
            
            if context.spirit.personality:
                parts.append(f"\n## 性格特点\n{context.spirit.personality}")
            
            if context.spirit.values:
                parts.append("\n## 价值观")
                for value in context.spirit.values:
                    parts.append(f"- {value}")
            
            if context.spirit.behavior_rules:
                parts.append("\n## 行为准则")
                for rule in context.spirit.behavior_rules:
                    parts.append(f"- {rule}")
        
        # ===== User Profile (OWNER.md) =====
        if context.owner:
            parts.append("\n# 用户画像")
            parts.append(f"姓名: {context.owner.name}")
            
            if context.owner.occupation:
                parts.append(f"职业: {context.owner.occupation}")
            
            if context.owner.interests:
                parts.append(f"兴趣: {', '.join(context.owner.interests)}")
            
            if context.owner.goals:
                parts.append(f"目标: {', '.join(context.owner.goals)}")
            
            if context.owner.preferences:
                parts.append("偏好:")
                for key, value in context.owner.preferences.items():
                    parts.append(f"  - {key}: {value}")
        
        # ===== Available Tools (TOOLS.md) =====
        if context.tools:
            parts.append("\n# 可用工具")
            for tool in context.tools[:15]:  # Limit to 15 tools to avoid token limit
                tool_desc = f"- {tool.name}"
                if tool.description:
                    tool_desc += f": {tool.description}"
                parts.append(tool_desc)
        
        # ===== Long-term Memory (MEMORY.md) =====
        if context.long_term_memory:
            parts.append("\n# 长期记忆")
            # Truncate to avoid token limit (about 800 chars)
            memory_content = context.long_term_memory.strip()
            if len(memory_content) > 800:
                memory_content = memory_content[:800] + "..."
            parts.append(memory_content)
        
        # ===== Recent Daily Logs (memory/*.md) =====
        if context.recent_logs:
            parts.append("\n# 近期记录")
            for log in context.recent_logs[:7]:  # Limit to 7 days
                # DailyLog has 'summary' and 'entries', not 'content'
                log_text = log.summary if log.summary else f"({len(log.entries)} 条记录)"
                if log_text and log_text.strip():
                    parts.append(f"\n## {log.date}\n{log_text.strip()[:200]}")
        
        prompt = "\n".join(parts)
        
        logger.debug(
            "System prompt generated",
            extra={
                "prompt_length": len(prompt),
                "has_spirit": context.spirit is not None,
                "has_owner": context.owner is not None,
                "tools_count": len(context.tools) if context.tools else 0,
                "has_memory": bool(context.long_term_memory),
                "logs_count": len(context.recent_logs) if context.recent_logs else 0,
            }
        )
        
        return prompt
    
    def clear_cache(self) -> None:
        """Clear all cached data.
        
        Forces reload on next build_context call.
        """
        self._spirit_loader.clear_cache()
        self._tools = None
        self._cached_context = None
        self._last_load_time = None
        
        # Also clear ContextLoader cache
        self._context_loader.clear_all_cache()
        
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
