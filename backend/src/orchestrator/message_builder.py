"""Message builder for Orchestrator.

Responsible for building message lists for LLM with:
- System prompt construction
- Session history loading
- Context compression
- Skill context injection
"""

from pathlib import Path
from typing import Any

from ..config.manager import ConfigManager
from ..services.compression import ContextCompressionManager
from ..services.llm.router import LLMRouter
from ..tools.manager import ToolManager
from .plan_context import PlanState
from .policy_engine import PolicyEngine
from ..utils.logger import get_logger

logger = get_logger(__name__)


class MessageBuilder:
    """Builds message lists for LLM with proper context and compression.
    
    Responsibilities:
    - System prompt construction (tools, skills, guidelines)
    - Session history loading and compression
    - Plan state injection
    - Skill context injection
    - Memory integration
    """
    
    def __init__(
        self,
        workspace_path: Path,
        tool_manager: ToolManager,
        skill_registry: Any,
        policy_engine: PolicyEngine,
        llm_router: LLMRouter | None = None,
    ):
        """Initialize message builder.
        
        Args:
            workspace_path: Path to workspace directory
            tool_manager: Tool manager for tool list
            skill_registry: Skill registry for skill list
            policy_engine: Policy engine for guidelines
            llm_router: LLM router for compression (optional)
        """
        self.workspace_path = workspace_path
        self.tool_manager = tool_manager
        self.skill_registry = skill_registry
        self.policy_engine = policy_engine
        self._llm_router = llm_router
        self._compression_manager: ContextCompressionManager | None = None
        
        # System prompt cache (static parts)
        self._cached_tool_list: str | None = None
        self._cached_skill_list: str | None = None
        self._cached_guidelines: str | None = None
        
        logger.info("MessageBuilder initialized")
    
    def _get_compression_manager(self) -> ContextCompressionManager:
        """Get or create compression manager."""
        if self._compression_manager is None and self._llm_router:
            config = ConfigManager().config
            self._compression_manager = ContextCompressionManager(
                config=config.compression,
                workspace_path=str(self.workspace_path),
                llm_service=self._llm_router,
            )
        return self._compression_manager
    
    def _get_cached_tool_list(self) -> str:
        """Get cached tool list (with caching)."""
        if self._cached_tool_list is None:
            tools = self.tool_manager.get_all_tools()
            tool_names = [t.name for t in tools]
            self._cached_tool_list = f"\n# 可用工具\n你可以使用以下工具：{', '.join(tool_names)}"
        return self._cached_tool_list
    
    def _get_cached_skill_list(self, max_skills: int = 20) -> str:
        """Get cached skill list (with caching).
        
        Args:
            max_skills: Maximum number of skills to include
            
        Returns:
            Formatted skill list string
        """
        if self._cached_skill_list is None:
            try:
                skills = self.skill_registry.list_all_skills()
                llm_callable_skills = [
                    s for s in skills
                    if not s.disable_model_invocation and s.user_invocable
                ]
                
                if llm_callable_skills:
                    display_skills = llm_callable_skills[:max_skills]
                    skill_descriptions = []
                    
                    for skill in display_skills:
                        desc = skill.description[:100] if skill.description else ""
                        skill_desc = f"{skill.name}({desc})"
                        skill_descriptions.append(skill_desc)
                    
                    self._cached_skill_list = (
                        f"\n# 可用技能\n你还可以使用以下技能：{', '.join(skill_descriptions)}\n\n"
                        "**技能使用说明**：技能是以目录形式组织的知识包。每个技能包含：\n"
                        "- SKILL.md：详细的使用指南和工作流程（通过 read_file 读取）\n"
                        "- scripts/：可直接运行的示例代码（通过 run_in_terminal 执行）\n"
                        "- references/：参考资料和文档（按需加载）\n"
                        "- assets/：模板和资源文件（直接使用）\n\n"
                        "你可以通过 read_file 工具读取任何技能的文件来学习如何使用它。"
                        "当需要执行脚本时，使用 run_in_terminal 工具。"
                    )
                else:
                    self._cached_skill_list = ""
            except Exception as e:
                logger.warning(f"Failed to load skills: {e}")
                self._cached_skill_list = ""
        
        return self._cached_skill_list
    
    def _get_cached_guidelines(self) -> str:
        """Get cached system guidelines (with caching)."""
        if self._cached_guidelines is None:
            self._cached_guidelines = self.policy_engine.build_system_prompt_guidelines() or ""
        return self._cached_guidelines
    
    def clear_cache(self) -> None:
        """Clear all caches (call when tools/skills change)."""
        self._cached_tool_list = None
        self._cached_skill_list = None
        self._cached_guidelines = None
        logger.info("MessageBuilder cache cleared")
    
    async def build_messages(
        self,
        context: Any,
        user_message: str,
        relevant_memories: list[str] | None = None,
        session_id: str | None = None,
        plan_state: PlanState | None = None,
        skill_context_msg: dict | None = None,
        session_manager: Any | None = None,
    ) -> tuple[list[dict], dict]:
        """Build message list for LLM with compression.
        
        Args:
            context: Loaded context bundle
            user_message: User's message
            relevant_memories: Retrieved memories
            session_id: Session ID for history loading
            plan_state: Current plan state
            skill_context_msg: Skill invocation context
            session_manager: Session manager for history loading
            
        Returns:
            Tuple of (messages list, compression info dict)
        """
        messages = []
        system_parts = []
        
        compression_info = {
            "message_count": 0,
            "token_count": 0,
            "threshold_rounds": None,
            "threshold_tokens": None,
            "needs_compression": False,
            "compressed": False,
        }
        
        # Add cached components (fast)
        guidelines = self._get_cached_guidelines()
        if guidelines:
            system_parts.append(guidelines)
        
        # Add identity
        if context.identity and context.identity.name:
            system_parts.append(f"\n# 你的身份\n你的名字是「{context.identity.name}」。")
        
        # Add spirit
        if context.spirit:
            system_parts.append(f"\n# 角色定位\n你是{context.spirit.role}。")
        
        # Add owner
        if context.owner:
            system_parts.append(f"\n# 用户画像\n姓名: {context.owner.name}")
        
        # Add cached tool list
        tool_list = self._get_cached_tool_list()
        if tool_list:
            system_parts.append(tool_list)
        
        # Add workspace path and file classification
        system_parts.append(
            f"\n\n# 工作目录与文件分类存储（极其重要）\n"
            f"**你的工作目录是：** `{self.workspace_path}`\n\n"
            f"**文件分类存储规则（必须遵守）：**\n"
            f"| 文件类型 | 存储目录 |\n"
            f"|---------|--------|\n"
            f"| Python/JS 脚本 | `scripts/` |\n"
            f"| PPT 演示文稿 | `presentations/` |\n"
            f"| 文档（Word/PDF） | `documents/` |\n"
            f"| Excel 表格 | `spreadsheets/` |\n"
            f"| 图片资源 | `images/` |\n"
            f"| PDF 文件 | `pdfs/` |"
        )
        
        # Only inject skills if no specific skill is being invoked
        if not skill_context_msg:
            skill_list = self._get_cached_skill_list()
            if skill_list:
                system_parts.append(skill_list)
        
        # Inject plan context (if any)
        if plan_state and hasattr(plan_state, 'structured_plan') and plan_state.structured_plan:
            plan_prompt = plan_state.structured_plan.to_prompt()
            system_parts.append(f"\n# 📋 结构化执行计划\n{plan_prompt}")
        
        # Add relevant memories
        if relevant_memories:
            memory_text = "\n".join(relevant_memories)
            system_parts.append(f"\n# 相关记忆\n{memory_text}")
        elif context.long_term_memory:
            system_parts.append(f"\n# 长期记忆\n{context.long_term_memory[:800]}")
        
        # Build system message
        system_message = "\n".join(system_parts) if system_parts else ""
        
        # Add skill invocation context (if any) as the FIRST system message
        if skill_context_msg:
            messages.append(skill_context_msg)
        
        # Add the main system message
        if system_message:
            messages.append({"role": "system", "content": system_message})
        
        # Load conversation history
        history_messages = []
        if session_id and session_manager:
            try:
                history_messages = await session_manager.get_messages_as_dict(session_id)
                logger.info(
                    "Loaded conversation history",
                    extra={"session_id": session_id, "history_count": len(history_messages)}
                )
            except Exception as e:
                logger.warning(f"Failed to load conversation history: {e}")
        
        # Add separator for long history
        if history_messages and len(history_messages) > 4:
            messages.append({
                "role": "system",
                "content": "\n---\n📌 **注意：这是一个新的请求**\n---\n"
            })
        
        messages.extend(history_messages)
        
        # Safety check: if history is empty, add user message
        if not history_messages and user_message:
            messages.append({"role": "user", "content": user_message})
        
        compression_info["message_count"] = len(messages)
        
        # Apply context compression
        if len(messages) > 1 and session_id and self._llm_router:
            try:
                compression_manager = self._get_compression_manager()
                if compression_manager:
                    compression_info["threshold_rounds"] = compression_manager.config.threshold_rounds
                    compression_info["threshold_tokens"] = compression_manager.config.threshold_tokens
                    
                    prepared = await compression_manager.prepare_context(
                        session_id=session_id,
                        current_messages=messages,
                        system_prompt=system_message
                    )
                    messages = prepared.messages
                    
                    compression_info["token_count"] = prepared.total_tokens
                    compression_info["compressed"] = prepared.summary is not None
                    compression_info["needs_compression"] = compression_info["compressed"]
            except Exception as e:
                logger.warning(f"Context compression failed: {e}")
        
        return messages, compression_info
