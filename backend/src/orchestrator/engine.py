"""Orchestrator engine for X-Agent.

The Orchestrator is the central coordinator that:
- Loads and applies AGENTS.md policies
- Coordinates context loading
- Manages the ReAct loop
- Executes tools
- Handles memory writing
- Loads session history with context compression

This is the main entry point for processing user requests.
"""

import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .policy_engine import PolicyEngine
from .react_loop import (
    ReActLoop,
    REACT_EVENT_THINKING,
    REACT_EVENT_TOOL_CALL,
    REACT_EVENT_TOOL_RESULT,
    REACT_EVENT_FINAL,
    REACT_EVENT_ERROR,
)
from .guards import SessionGuard, ResponseGuard
from .task_analyzer import TaskAnalyzer, get_task_analyzer
from .light_planner import LightPlanner, get_light_planner
from .structured_planner import StructuredPlanner, get_structured_planner
from .plan_context import PlanContext, PlanState, get_plan_context
# Use relative imports within the orchestrator package
from .models.plan import StructuredPlan, ToolConstraints
from .validators.tool_validator import ToolConstraintValidator
from .validators.milestone_validator import MilestoneValidator
from ..config.manager import ConfigManager
from ..memory.context_builder import ContextBuilder, get_context_builder
from ..memory.hybrid_search import HybridSearch, get_hybrid_search
from ..memory.md_sync import get_md_sync
from ..memory.models import SessionType
from ..memory.vector_store import get_vector_store
from ..memory.embedder import get_embedder
from ..services.compression import ContextCompressionManager
from ..services.llm.router import LLMRouter
from ..services.smart_memory import get_smart_memory_service
from ..services.skill_registry import SkillRegistry, get_skill_registry
from ..tools.manager import ToolManager, get_tool_manager
from ..tools.builtin import get_builtin_tools
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from ..core.session import SessionManager

logger = get_logger(__name__)


# Orchestrator event types
ORCH_EVENT_POLICY = "policy_check"
ORCH_EVENT_CONTEXT = "context_loaded"
ORCH_EVENT_THINKING = "thinking"
ORCH_EVENT_TOOL_CALL = "tool_call"
ORCH_EVENT_TOOL_RESULT = "tool_result"
ORCH_EVENT_CHUNK = "chunk"
ORCH_EVENT_FINAL = "final_answer"
ORCH_EVENT_ERROR = "error"

# Plan-related event types
ORCH_EVENT_TASK_ANALYSIS = "task_analysis"
ORCH_EVENT_PLAN_GENERATED = "plan_generated"
ORCH_EVENT_PLAN_ADJUSTMENT = "plan_adjustment"


class Orchestrator:
    """Central orchestrator for X-Agent request processing."""
    
    def __init__(
        self,
        workspace_path: str,
        llm_router: LLMRouter | None = None,
        session_manager: "SessionManager | None" = None,
    ) -> None:
        """Initialize the orchestrator.
        
        Args:
            workspace_path: Path to workspace directory
            llm_router: LLM router instance
            session_manager: Session manager for loading conversation history
        """
        self.workspace_path = Path(workspace_path).resolve()
        
        # Initialize components
        self.policy_engine = PolicyEngine(str(self.workspace_path))
        self.session_guard = SessionGuard()
        self.response_guard = ResponseGuard()
        
        # Session manager for conversation history
        self._session_manager = session_manager
        
        # Context builder
        self._context_builder: ContextBuilder | None = None
        
        # Hybrid search for memory retrieval
        self._hybrid_search: HybridSearch | None = None
        
        # LLM router
        if llm_router is None:
            config = ConfigManager().config
            self._llm_router = LLMRouter(config.models)
        else:
            self._llm_router = llm_router
        
        # Context compression manager
        self._compression_manager: ContextCompressionManager | None = None
        
        # Tool manager with built-in tools
        self._tool_manager = get_tool_manager()
        self._register_builtin_tools()
        
        # ReAct loop
        self._react_loop = ReActLoop(
            llm_router=self._llm_router,
            tool_manager=self._tool_manager,
        )
        
        # Skill registry for discovering and managing skills
        self._skill_registry = SkillRegistry(self.workspace_path)
        
        # Phase 2: Store current skill context for tool restrictions
        self._current_skill_context: Any = None
        
        # Task planning components
        from ..config.manager import ConfigManager
        
        try:
            config_manager = ConfigManager()
            # Initialize task analyzer with skills config for better skill matching
            self._task_analyzer = TaskAnalyzer(skills_config=config_manager.config.skills)
        except Exception:
            # Fallback to default without skills config
            self._task_analyzer = TaskAnalyzer()
        
        self._light_planner: LightPlanner | None = None
        
        # Structured Planner for v2.0 (optional, used when skill is specified)
        self._structured_planner: StructuredPlanner | None = None
        
        # Plan context manager (uses config from x-agent.yaml)
        from ..config.models import PlanConfig
        
        try:
            config_manager = ConfigManager()
            plan_config = config_manager.config.plan
        except Exception:
            # Fallback to default config if loading fails
            plan_config = PlanConfig()
        
        self._plan_context = PlanContext(config=plan_config)
        
        # Tool constraint validator (will be initialized per request when needed)
        self._tool_validator: ToolConstraintValidator | None = None
        
        # Milestone validator (will be initialized per request when needed)
        self._milestone_validator: MilestoneValidator | None = None
        
        # Skill registry (for discovering and managing skills)
        from ..services.skill_registry import get_skill_registry
        self._skill_registry = get_skill_registry(self.workspace_path)
        
        logger.info(
            "Orchestrator initialized",
            extra={
                "workspace_path": str(self.workspace_path),
                "tools_count": len(self._tool_manager.get_tool_names()),
                "skills_count": len(self._skill_registry.list_all_skills()),
                "has_session_manager": session_manager is not None,
            }
        )
    
    def _get_context_builder(self) -> ContextBuilder:
        """Get or create context builder."""
        if self._context_builder is None:
            self._context_builder = get_context_builder(str(self.workspace_path))
        return self._context_builder
    
    def _get_session_manager(self) -> "SessionManager":
        """Get or create session manager."""
        if self._session_manager is None:
            from ..core.session import SessionManager
            self._session_manager = SessionManager()
        return self._session_manager
    
    def _get_compression_manager(self) -> ContextCompressionManager:
        """Get or create compression manager."""
        if self._compression_manager is None:
            config = ConfigManager().config
            self._compression_manager = ContextCompressionManager(
                config=config.compression,
                workspace_path=str(self.workspace_path),
                llm_service=self._llm_router,
            )
        return self._compression_manager
    
    def _get_hybrid_search(self) -> HybridSearch:
        """Get or create hybrid search instance."""
        if self._hybrid_search is None:
            try:
                vector_store = get_vector_store()
                embedder = get_embedder()
                self._hybrid_search = get_hybrid_search(
                    vector_store=vector_store,
                    embedder=embedder,
                )
            except Exception as e:
                logger.warning(
                    "Failed to initialize hybrid search, using text-only",
                    extra={"error": str(e)}
                )
                self._hybrid_search = HybridSearch()
        return self._hybrid_search
    
    def _get_light_planner(self) -> LightPlanner:
        """Get or create light planner instance."""
        if self._light_planner is None:
            self._light_planner = LightPlanner(self._llm_router)
        return self._light_planner
    
    def _get_structured_planner(self) -> StructuredPlanner:
        """Get or create structured planner instance."""
        if self._structured_planner is None:
            self._structured_planner = StructuredPlanner(
                llm_router=self._llm_router,
                skill_registry=self._skill_registry,
            )
        return self._structured_planner
    
    def _search_relevant_memory(
        self,
        query: str,
        limit: int | None = None,
        min_score: float | None = None,
    ) -> list[str]:
        """Search for relevant memory entries based on query.
        
        Uses hybrid search (vector + text) to find relevant memories.
        
        Args:
            query: User's question/message
            limit: Maximum number of results (default from config)
            min_score: Minimum relevance score filter (default from config)
            
        Returns:
            List of relevant memory content strings
        """
        try:
            # Load defaults from config
            try:
                from ..config import get_config
                config = get_config()
                if limit is None:
                    limit = config.search.limit
                if min_score is None:
                    min_score = config.search.min_score
            except Exception:
                limit = limit or 10
                min_score = min_score or 0.0
            
            hybrid_search = self._get_hybrid_search()
            md_sync = get_md_sync(str(self.workspace_path))
            
            # Get all entries for searching (consistent with API endpoint)
            entries = md_sync.list_all_entries(limit=1000)
            
            if not entries:
                return []
            
            # Perform hybrid search (same params as /api/v1/memory/search)
            results = hybrid_search.search(
                query=query,
                entries=entries,
                limit=limit,
                offset=0,
                min_score=min_score,
            )
            
            # Extract content from results
            relevant_memories = []
            for result in results:
                if result.entry and result.entry.content:
                    # Include score for context
                    relevant_memories.append(
                        f"[相关度:{result.score:.2f}] {result.entry.content[:200]}"
                    )
            
            logger.info(
                "Memory search completed",
                extra={
                    "query": query[:50],
                    "results_count": len(relevant_memories),
                }
            )
            
            return relevant_memories
            
        except Exception as e:
            logger.warning(
                "Memory search failed",
                extra={"error": str(e)}
            )
            return []
    
    def _register_builtin_tools(self) -> None:
        """Register built-in tools."""
        for tool in get_builtin_tools():
            self._tool_manager.register(tool)
    
    def register_tool(self, tool: Any) -> None:
        """Register a custom tool."""
        self._tool_manager.register(tool)
    
    async def process_request(
        self,
        session_id: str,
        user_message: str,
        session_type: SessionType | str = SessionType.MAIN,
        stream: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Process a user request."""
        start_time = time.time()
        
        if isinstance(session_type, str):
            session_type = SessionType(session_type)
        
        logger.info(
            "Processing request",
            extra={
                "session_id": session_id,
                "session_type": session_type.value,
                "message_length": len(user_message),
                "user_message_preview": user_message[:100] if len(user_message) > 100 else user_message,
            }
        )
        
        # ===== CRITICAL DEBUG LOGS =====
        logger.info(f"[PROCESS_REQUEST_START] session={session_id}, message={user_message[:100]}")
        
        # Step 0: Task Analysis (fast rule-based, no LLM call)
        logger.info(f"[TASK_ANALYSIS_START] Analyzing message: {user_message[:50]}...")
        analysis = self._task_analyzer.analyze(user_message)
        logger.info(f"[TASK_ANALYSIS_DONE] complexity={analysis.complexity}, needs_plan={analysis.needs_plan}, matched_skills={analysis.matched_skills}")
        logger.info(
            "Task analysis completed",
            extra={
                "session_id": session_id,
                "complexity": analysis.complexity,
                "confidence": analysis.confidence,
                "needs_plan": analysis.needs_plan,
                "indicators": analysis.indicators,
                "matched_skills": [s["name"] for s in analysis.matched_skills] if analysis.matched_skills else [],
                "recommended_skill": analysis.recommended_skill["name"] if analysis.recommended_skill else None,
            }
        )
        yield {
            "type": ORCH_EVENT_TASK_ANALYSIS,
            "complexity": analysis.complexity,
            "needs_plan": analysis.needs_plan,
            "matched_skills": analysis.matched_skills,
            "recommended_skill": analysis.recommended_skill,
        }
        
        # Step 0.5: Parse Skill Command (Phase 2 - Argument Passing)
        logger.info(f"[SKILL_PARSE_START] Parsing skill command from: {user_message[:50]}...")
        
        # Try exact /command format first
        skill_name, arguments = TaskAnalyzer.parse_skill_command(user_message)
        
        # If not /command format, try fuzzy matching with skill names
        if not skill_name:
            # Get available skills from registry cache
            all_skills = self._skill_registry.list_all_skills()
            if all_skills:
                available_skills = [skill.name for skill in all_skills]
                extracted_skill, remaining_msg = TaskAnalyzer.extract_skill_name(user_message, available_skills)
                if extracted_skill:
                    skill_name = extracted_skill
                    arguments = remaining_msg
                    logger.info(
                        "Skill name detected via fuzzy matching (without slash)",
                        extra={
                            "skill_name": skill_name,
                            "arguments": arguments,
                        }
                    )
        
        logger.info(f"[SKILL_PARSE_RESULT] skill_name={skill_name}, arguments={arguments}")
        
        if skill_name:
            logger.info(
                "Skill command detected",
                extra={
                    "session_id": session_id,
                    "skill_name": skill_name,
                    "arguments": arguments,
                }
            )
            
            # ===== FAST PATH: Direct skill execution =====
            # If user explicitly invoked a skill with /command, skip complex planning
            # and execute directly using the skill's CLI binding
            # Note: Only trigger FAST PATH for simple CLI commands, not natural language
            if skill_name and arguments:
                # Check if arguments look like natural language (need semantic understanding)
                # If so, fall through to ReAct loop for proper interpretation
                # CRITICAL: Must distinguish between CLI commands and natural language
                
                # CLI command patterns (NOT natural language)
                cli_command_patterns = [
                    r'^open\s+https?://',      # open https://example.com
                    r'^open\s+www\.',          # open www.example.com
                    r'^open\s+[a-z0-9.-]+\.',  # open example.com (domain pattern)
                    r'^get\s+text\s+',         # get text <selector>
                    r'^click\s+',              # click <selector>
                    r'^screenshot',            # screenshot
                    r'^close',                 # close
                    r'^fill\s+',               # fill <selector> <value>
                    r'^type\s+',               # type <selector> <value>
                    r'^navigate',              # navigate
                    r'^back',                  # back
                    r'^forward',               # forward
                    r'^reload',                # reload
                    r'^snapshot',              # snapshot
                ]
                
                is_cli_command = any(re.match(pattern, arguments.strip()) for pattern in cli_command_patterns)
                
                # Natural language indicators
                natural_language_indicators = [
                    '帮我', '请', '想要', '需要',  # Request indicators
                    '获取.*内容', '打开.*网页', '点击.*按钮',  # Chinese verb-object phrases
                    '搜索', '并', '然后', '最后',  # Multi-step indicators
                    '数据', '信息', '结果',  # Data extraction indicators
                ]
                
                # Check if there's additional natural language after CLI command
                has_natural_language_suffix = False
                if is_cli_command:
                    # Try to detect if there's natural language after the CLI command
                    # e.g., "open www.baidu.com 搜索今日天气" → should use ReAct
                    cli_match = None
                    for pattern in cli_command_patterns:
                        match = re.match(pattern, arguments.strip())
                        if match:
                            cli_match = match
                            break
                    
                    if cli_match:
                        # Extract the part after the CLI command
                        remaining_text = arguments[cli_match.end():].strip()
                        if remaining_text:
                            # Check if remaining text contains natural language
                            has_natural_language_suffix = any(
                                indicator in remaining_text 
                                for indicator in natural_language_indicators
                            )
                            
                            if has_natural_language_suffix:
                                logger.info(
                                    "Natural language suffix detected after CLI command",
                                    extra={
                                        "skill_name": skill_name,
                                        "cli_command": arguments[:cli_match.end()],
                                        "natural_suffix": remaining_text,
                                    }
                                )
                
                is_natural_language = (
                    not is_cli_command and  # Not a CLI command
                    any(indicator in arguments for indicator in natural_language_indicators)
                ) or has_natural_language_suffix
                
                if is_natural_language:
                    logger.info(
                        "Natural language detected, using ReAct loop for interpretation",
                        extra={
                            "skill_name": skill_name,
                            "arguments": arguments,
                        }
                    )
                    # Fall through to normal ReAct path
                else:
                    # Get skill metadata
                    skill = self._skill_registry.get_skill_metadata(skill_name)
                    
                    # Check if this is a CLI-bound skill (has run_in_terminal in allowed_tools)
                    # This includes skills without scripts but with CLI tool access
                    if skill and ('run_in_terminal' in (skill.allowed_tools or [])):
                        logger.info(
                            "FAST PATH: Direct skill execution (bypassing ReAct loop)",
                            extra={
                                "skill_name": skill.name,
                                "has_scripts": skill.has_scripts,
                                "allowed_tools": skill.allowed_tools,
                            }
                        )
                        
                        # Execute skill's CLI command directly
                        async for event in _execute_skill_directly(self._tool_manager, skill, arguments, session_id):
                            yield event
                        return
            
            # Fall back to normal path for skills without scripts or complex tasks
            # Get skill metadata - CRITICAL DEBUG POINT
            logger.info(f"[SKILL_METADATA_START] Getting metadata for skill: {skill_name}")
            try:
                skill = self._skill_registry.get_skill_metadata(skill_name)
                logger.info(f"[SKILL_METADATA_RESULT] skill type={type(skill).__name__}, has_scripts={skill.has_scripts if skill else None}")
            except Exception as e:
                logger.error(f"[SKILL_METADATA_ERROR] Failed to get skill metadata: {e}", exc_info=True)
                raise
            
            if skill:
                # Phase 2: Set current skill context for tool restrictions
                self._current_skill_context = skill
                
                # Debug: Check skill attributes
                logger.info(f"[SKILL_CHECK] skill.name={skill.name}, type(skill.description)={type(skill.description).__name__}, skill.description={skill.description[:50] if skill.description else None}...")
                logger.info(f"[SKILL_CHECK] skill.has_scripts={skill.has_scripts}, skill.allowed_tools={skill.allowed_tools}, skill.argument_hint={skill.argument_hint}")
                
                logger.info(
                    f"Skill '{skill_name}' loaded",
                    extra={
                        "session_id": session_id,
                        "has_scripts": skill.has_scripts,
                        "allowed_tools": skill.allowed_tools,
                        "argument_hint": skill.argument_hint,
                    }
                )
                
                # Add skill context to messages
                messages = []  # Initialize messages list for building message history
                skill_context_msg = {
                    "role": "system",
                    "content": (
                        f"🔧 **Skill Invocation: {skill_name}**\n\n"
                        f"**Description**: {skill.description}\n"
                        f"**Arguments**: {arguments if arguments else '(none)'}\n"
                        f"**Available Scripts**: {'Yes' if skill.has_scripts else 'No'}\n\n"
                        f"You are now executing the '{skill_name}' skill. "
                        f"Follow the guidelines in this skill's SKILL.md and use the provided arguments.\n\n"
                    )
                }
                
                # Add CLI command format guidance for skills with run_in_terminal
                if 'run_in_terminal' in (skill.allowed_tools or []):
                    cli_guidance_msg = {
                        "role": "system",
                        "content": (
                            f"⚡ **CLI Command Format Important**:\n\n"
                            f"The argument `{arguments}` starts with a CLI command pattern.\n"
                            f"Use the appropriate CLI tool for this skill as documented in its SKILL.md file.\n\n"
                            f"**Available Commands**: Refer to the skill's documentation for exact command format.\n\n"
                            f"---\n"
                        )
                    }
                    # Insert after skill_context_msg
                    messages.insert(len(messages), cli_guidance_msg)
            else:
                logger.warning(
                    f"Skill '{skill_name}' not found in registry",
                    extra={"session_id": session_id}
                )
                skill_context_msg = {
                    "role": "system",
                    "content": (
                        f"⚠️ **Unknown Skill: {skill_name}**\n\n"
                        f"The skill '{skill_name}' was not found in the skill registry. "
                        f"Please check the skill name and try again.\n\n"
                        f"---\n"
                    )
                }
        else:
            skill_context_msg = None
            # Clear skill context for non-skill commands
            self._current_skill_context = None
        
        # Step 1: Policy Reload
        policy, reloaded = self.policy_engine.reload_if_changed()
        yield {
            "type": ORCH_EVENT_POLICY,
            "reloaded": reloaded,
            "policy_hash": policy.source_hash[:8],
        }
        
        # Step 2: Session Rules
        session_rules = self.session_guard.apply_rules(
            session_type,
            policy.hard_constraints,
        )
        
        # Step 3: Load Context
        try:
            context = self._load_context(session_type, session_rules)
            yield {
                "type": ORCH_EVENT_CONTEXT,
                "has_spirit": context.spirit is not None,
                "has_owner": context.owner is not None,
                "tools_count": len(context.tools),
            }
        except Exception as e:
            yield {
                "type": ORCH_EVENT_ERROR,
                "error": f"Failed to load context: {str(e)}",
            }
            return
        
        # Step 3.5: Search Relevant Memory (before reasoning)
        relevant_memories = self._search_relevant_memory(user_message, limit=5)
        if relevant_memories:
            logger.info(
                "Relevant memories retrieved",
                extra={
                    "session_id": session_id,
                    "memories_count": len(relevant_memories),
                }
            )
        
        # Step 3.6: Generate Plan (if needed)
        plan_state: PlanState | None = None
        structured_plan: StructuredPlan | None = None
        
        if analysis.needs_plan:
            try:
                # Check if skill is specified - use Structured Planner v2.0
                if skill_name and analysis.matched_skills:
                    logger.info(
                        "Using StructuredPlanner v2.0 for skill-based task",
                        extra={
                            "session_id": session_id,
                            "skill_name": skill_name,
                        }
                    )
                    structured_planner = self._get_structured_planner()
                    structured_plan = await structured_planner.generate(
                        goal=user_message,
                        skill_name=skill_name,
                    )
                    
                    # Initialize validators
                    self._tool_validator = ToolConstraintValidator(structured_plan)
                    self._milestone_validator = MilestoneValidator(structured_plan)
                    
                    # Convert to PlanState for backward compatibility
                    plan_text = structured_plan.to_prompt()
                    plan_state = PlanState(
                        original_plan=plan_text,
                        current_step=1,
                        total_steps=len(structured_plan.steps),
                        completed_steps=[],
                        failed_count=0,
                        last_adjustment=None,
                        structured_plan=structured_plan,  # Store reference
                    )
                    
                    logger.info(
                        "StructuredPlan v2.0 generated",
                        extra={
                            "session_id": session_id,
                            "skill_binding": structured_plan.skill_binding,
                            "tool_constraints": structured_plan.tool_constraints,
                            "steps_count": len(structured_plan.steps),
                            "milestones_count": len(structured_plan.milestones),
                        }
                    )
                else:
                    # Fallback to LightPlanner v1.0
                    light_planner = self._get_light_planner()
                    plan_text = await light_planner.generate(
                        goal=user_message,
                        tools=[t.name for t in self._tool_manager.get_all_tools()],
                    )
                    plan_state = PlanState(
                        original_plan=plan_text,
                        current_step=1,
                        total_steps=plan_text.count("\n") + 1,
                        completed_steps=[],
                        failed_count=0,
                        last_adjustment=None,
                    )
                    logger.info(
                        "LightPlan v1.0 generated",
                        extra={
                            "session_id": session_id,
                            "plan_steps": plan_state.total_steps,
                            "plan_preview": plan_text[:100],
                        }
                    )
                
                yield {
                    "type": ORCH_EVENT_PLAN_GENERATED,
                    "plan": plan_text,
                    "is_structured": structured_plan is not None,
                }
            except Exception as e:
                logger.warning(
                    "Plan generation failed, continuing without plan",
                    extra={
                        "session_id": session_id,
                        "error": str(e),
                    }
                )
        
        # Step 4: Build Messages (with session history and compression)
        messages, compression_info = await self._build_messages(
            context, user_message, policy, relevant_memories, session_id, plan_state, skill_context_msg
        )
        
        # Yield compression status event for frontend debugging
        yield {
            "type": "compression_status",
            "session_id": session_id,
            "message_count": compression_info.get("message_count", 0),
            "token_count": compression_info.get("token_count", 0),
            "threshold_rounds": compression_info.get("threshold_rounds"),
            "threshold_tokens": compression_info.get("threshold_tokens"),
            "needs_compression": compression_info.get("needs_compression", False),
            "compressed": compression_info.get("compressed", False),
        }
        
        # Step 5: ReAct Loop
        final_response = ""
        
        try:
            async for event in self._react_loop.run_streaming(
                messages,
                tools=self._tool_manager.get_all_tools(),
                session_id=session_id,
                skill_context=self._current_skill_context,  # Phase 2 - Pass skill context for tool restrictions
            ):
                event_type = event.get("type")
                
                # Debug: log all events
                logger.info(
                    "Processing event in engine",
                    extra={
                        "event_type": event_type,
                        "event_keys": list(event.keys()),
                        "tool_call_id_in_event": event.get("tool_call_id"),
                    }
                )
                
                if event_type == REACT_EVENT_THINKING:
                    yield {
                        "type": ORCH_EVENT_THINKING,
                        "content": event.get("content", ""),
                    }
                elif event_type == "tool_call":
                    tool_call_id = event.get("tool_call_id")
                    tool_name = event.get("name")
                    
                    # ===== StructuredPlan v2.0: Tool Constraint Validation =====
                    if self._tool_validator and hasattr(self._tool_validator, 'plan'):
                        is_allowed, reason = self._tool_validator.is_tool_allowed(tool_name)
                        
                        if not is_allowed:
                            logger.warning(
                                "Tool constraint violation detected",
                                extra={
                                    "session_id": session_id,
                                    "tool_name": tool_name,
                                    "reason": reason,
                                    "violation_count": self._tool_validator.violation_count,
                                }
                            )
                            
                            # Emit error event to inform LLM
                            yield {
                                "type": ORCH_EVENT_ERROR,
                                "error": f"工具使用限制：{reason}",
                            }
                            
                            # Check if we should trigger replan
                            if self._tool_validator.should_trigger_replan():
                                logger.info(
                                    "Replan triggered due to repeated tool constraint violations",
                                    extra={
                                        "session_id": session_id,
                                        "violation_count": self._tool_validator.violation_count,
                                    }
                                )
                                yield {
                                    "type": ORCH_EVENT_PLAN_ADJUSTMENT,
                                    "reason": f"LLM 多次违反工具约束（{self._tool_validator.violation_count}次违规）",
                                }
                            
                            # Skip this tool call - continue to next iteration
                            continue
                    
                    logger.info(
                        "Emitting tool_call event",
                        extra={
                            "tool_call_id": tool_call_id,
                            "name": tool_name,
                            "raw_event_keys": list(event.keys()),
                        }
                    )
                    yield {
                        "type": ORCH_EVENT_TOOL_CALL,
                        "tool_call_id": tool_call_id,
                        "name": tool_name,
                        "arguments": event.get("arguments"),
                    }
                elif event_type == "tool_result":
                    result = event.get("result", {})
                    tool_call_id = event.get("tool_call_id")
                    tool_name = event.get("tool_name")
                    success = event.get("success")
                    output = event.get("output", "")
                    
                    # Update plan state if we have a plan
                    if plan_state:
                        self._plan_context.update_from_tool_result(
                            plan_state,
                            tool_name=tool_name,
                            success=success,
                            output=output,
                        )
                        
                        # ===== StructuredPlan v2.0: Milestone Validation =====
                        if self._milestone_validator and hasattr(self._milestone_validator, 'plan'):
                            try:
                                # Use new MilestoneValidator for structured plans
                                validation_passed, validation_msg = self._milestone_validator.check_and_advance(
                                    tool_name=tool_name,
                                    success=success,
                                    output=output,
                                )
                                
                                if validation_passed:
                                    logger.info(
                                        "Milestone validation passed",
                                        extra={
                                            "session_id": session_id,
                                            "message": validation_msg,
                                            "current_step": self._milestone_validator.current_step_index + 1,
                                            "total_steps": len(self._milestone_validator.plan.steps),
                                        }
                                    )
                                else:
                                    logger.warning(
                                        "Milestone validation failed",
                                        extra={
                                            "session_id": session_id,
                                            "reason": validation_msg,
                                        }
                                    )
                                    plan_state.failed_count += 1
                            except Exception as e:
                                logger.warning(
                                    "MilestoneValidator error, falling back to PlanContext validation",
                                    extra={"error": str(e)}
                                )
                                # Fallback to old PlanContext validation
                                current_step_desc = self._get_current_step_description(plan_state)
                                if current_step_desc and self._plan_context.should_validate_milestone(current_step_desc):
                                    validation_context = self._build_validation_context(tool_name, output)
                                    passed, msg = self._plan_context.validate_milestone(
                                        plan_state,
                                        milestone_name=current_step_desc,
                                        context=validation_context,
                                    )
                                    
                                    if not passed:
                                        logger.warning(
                                            "Milestone validation failed (fallback)",
                                            extra={
                                                "session_id": session_id,
                                                "milestone": current_step_desc,
                                                "reason": msg,
                                            }
                                        )
                                        plan_state.failed_count += 1
                        else:
                            # Fallback to old PlanContext validation for v1.0 plans
                            current_step_desc = self._get_current_step_description(plan_state)
                            if current_step_desc and self._plan_context.should_validate_milestone(current_step_desc):
                                validation_context = self._build_validation_context(tool_name, output)
                                passed, msg = self._plan_context.validate_milestone(
                                    plan_state,
                                    milestone_name=current_step_desc,
                                    context=validation_context,
                                )
                                
                                if not passed:
                                    logger.warning(
                                        "Milestone validation failed",
                                        extra={
                                            "session_id": session_id,
                                            "milestone": current_step_desc,
                                            "reason": msg,
                                        }
                                    )
                                    # Mark as failure to trigger replan if needed
                                    plan_state.failed_count += 1
                        
                        # Check if we need to re-plan
                        need_replan, reason = self._plan_context.should_replan(plan_state)
                        if need_replan:
                            # Record the replan and check if we can still replan
                            self._plan_context.record_replan(plan_state, reason)
                            
                            if plan_state.replan_count > self._plan_context.MAX_REPLAN_COUNT:
                                logger.warning(
                                    "Replan limit exceeded",
                                    extra={
                                        "session_id": session_id,
                                        "replan_count": plan_state.replan_count,
                                    }
                                )
                            else:
                                logger.info(
                                    "Plan adjustment triggered",
                                    extra={
                                        "session_id": session_id,
                                        "reason": reason,
                                        "replan_count": plan_state.replan_count,
                                    }
                                )
                                yield {
                                    "type": ORCH_EVENT_PLAN_ADJUSTMENT,
                                    "reason": reason,
                                }
                    
                    logger.info(
                        "Emitting tool_result event",
                        extra={
                            "tool_call_id": tool_call_id,
                            "tool_name": tool_name,
                            "success": success,
                            "has_result": bool(result),
                            "result_requires_confirmation": result.get("requires_confirmation") if result else None,
                        }
                    )
                    yield {
                        "type": ORCH_EVENT_TOOL_RESULT,
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "success": success,
                        "output": output,
                        "result": result,
                    }
                elif event_type == REACT_EVENT_FINAL:
                    final_response = event.get("content", "")
                    final_response = self.response_guard.process(
                        final_response,
                        policy.soft_guidelines,
                    )
                    yield {
                        "type": ORCH_EVENT_FINAL,
                        "content": final_response,
                    }
                elif event_type == "awaiting_confirmation":
                    # Forward the awaiting confirmation event to frontend
                    yield {
                        "type": "awaiting_confirmation",
                        "tool_call_id": event.get("tool_call_id"),
                        "confirmation_id": event.get("confirmation_id"),
                        "command": event.get("command"),
                    }
                elif event_type == REACT_EVENT_ERROR:
                    error_msg = event.get("error", "Unknown error")
                    
                    # Check if max iterations reached - trigger Plan Mode
                    if "Maximum iterations" in error_msg:
                        # Check if we've already replanned too many times
                        if plan_state and plan_state.replan_count >= self._plan_context.MAX_REPLAN_COUNT:
                            logger.warning(
                                "Max iterations reached but replan limit exceeded",
                                extra={
                                    "session_id": session_id,
                                    "replan_count": plan_state.replan_count,
                                }
                            )
                            yield {
                                "type": ORCH_EVENT_ERROR,
                                "error": f"{error_msg} (已尝试重规划 {plan_state.replan_count} 次，请尝试简化任务或提供更多信息)",
                            }
                            continue
                        
                        logger.info(
                            "Max iterations reached, switching to Plan Mode",
                            extra={"session_id": session_id}
                        )
                        yield {
                            "type": ORCH_EVENT_PLAN_ADJUSTMENT,
                            "reason": "max_iterations_reached",
                        }
                        # Generate plan and continue execution with plan injection
                        try:
                            light_planner = self._get_light_planner()
                            plan_text = await light_planner.generate(
                                goal=user_message,
                                tools=[t.name for t in self._tool_manager.get_all_tools()],
                            )
                            
                            # Create or update plan state
                            if plan_state:
                                self._plan_context.record_replan(plan_state, "max_iterations_reached")
                                plan_state.original_plan = plan_text
                                plan_state.total_steps = plan_text.count("\n") + 1
                            else:
                                plan_state = PlanState(
                                    original_plan=plan_text,
                                    current_step=1,
                                    total_steps=plan_text.count("\n") + 1,
                                    completed_steps=[],
                                    failed_count=0,
                                    last_adjustment=None,
                                    replan_count=0,
                                )
                            
                            logger.info(
                                "Plan generated after max iterations",
                                extra={
                                    "session_id": session_id,
                                    "plan_steps": plan_state.total_steps,
                                    "replan_count": plan_state.replan_count,
                                }
                            )
                            yield {
                                "type": ORCH_EVENT_PLAN_GENERATED,
                                "plan": plan_text,
                            }
                            
                            # Continue execution with plan injected into system prompt
                            logger.info(
                                "Continuing execution with plan injection",
                                extra={
                                    "session_id": session_id,
                                    "current_step": plan_state.current_step,
                                }
                            )
                            
                            # Build messages with plan state (plan will be injected into system prompt)
                            messages, debug_info = await self._build_messages(
                                context=context,
                                user_message=user_message,
                                policy=policy,
                                relevant_memories=relevant_memories,
                                session_id=session_id,
                                plan_state=plan_state,
                                skill_context_msg=skill_context_msg,
                            )
                            
                            # Temporarily increase max_iterations for Plan Mode execution
                            original_max_iterations = self._react_loop.max_iterations
                            self._react_loop.max_iterations = 10  # More iterations for complex plan execution
                            
                            try:
                                # Call LLM again with plan-injected system prompt and run ReAct loop
                                async for event in self._react_loop.run_streaming(
                                    messages,
                                    tools=self._tool_manager.get_all_tools(),
                                    session_id=session_id,
                                    skill_context=self._current_skill_context,  # Phase 2
                                ):
                                    event_type = event.get("type")
                                    
                                    if event_type == REACT_EVENT_THINKING:
                                        yield {
                                            "type": ORCH_EVENT_THINKING,
                                            "content": event.get("content", ""),
                                        }
                                    elif event_type == "tool_call":
                                        tool_call_id = event.get("tool_call_id")
                                        yield {
                                            "type": ORCH_EVENT_TOOL_CALL,
                                            "tool_call_id": tool_call_id,
                                            "name": event.get("name"),
                                            "arguments": event.get("arguments"),
                                        }
                                    elif event_type == "tool_result":
                                        yield {
                                            "type": ORCH_EVENT_TOOL_RESULT,
                                            "tool_call_id": event.get("tool_call_id"),
                                            "success": event.get("success"),
                                            "output": event.get("output", ""),
                                            "error": event.get("error"),
                                        }
                                
                                # Update final response (empty since we streamed events)
                                final_response = ""
                            
                            finally:
                                # Restore original max_iterations after Plan Mode execution
                                self._react_loop.max_iterations = original_max_iterations
                                logger.info(
                                    "Restored max_iterations after Plan Mode execution",
                                    extra={
                                        "session_id": session_id,
                                        "max_iterations": self._react_loop.max_iterations,
                                    }
                                )
                        
                        except Exception as e:
                            logger.warning(
                                "Failed to generate plan after max iterations",
                                extra={"session_id": session_id, "error": str(e)}
                            )
                            yield {
                                "type": ORCH_EVENT_ERROR,
                                "error": f"计划生成失败：{str(e)}",
                            }
                    else:
                        yield {
                            "type": ORCH_EVENT_ERROR,
                            "error": error_msg,
                        }
        
        except Exception as e:
            yield {
                "type": ORCH_EVENT_ERROR,
                "error": str(e),
            }
            return
        
        # Step 6: Memory Writing
        if final_response:
            await self._write_memory(user_message, final_response, session_id)
        
        # ===== SCHEME 3: Post-execution validation =====
        # Check if user request required file operations but none were detected
        if self._request_requires_file_creation(user_message):
            logger.info(
                "Post-execution validation: checking for file operations",
                extra={"session_id": session_id}
            )
            # Note: This is a placeholder for future implementation
            # In a full implementation, we would check the conversation history
            # to verify that appropriate tools were called
        
        # Log request completion with iteration statistics
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Request completed",
            extra={
                "session_id": session_id,
                "duration_ms": duration_ms,
                "trace_id": None,  # Will be filled by logging middleware if available
            }
        )
    
    def _request_requires_file_creation(self, user_message: str) -> bool:
        """Check if user message requires file creation operations.
        
        This is a helper method for post-execution validation.
        
        Args:
            user_message: Original user message
            
        Returns:
            True if the request likely requires file operations
        """
        import re
        
        # Patterns indicating file creation needs
        file_creation_patterns = [
            r'创建.*文件|create.*file|make.*file',
            r'创建.*PPT|create.*PPT|make.*presentation',
            r'创建.*文档 | create.*document',
            r'生成.*报告 | generate.*report',
            r'保存.*文件|save.*file',
        ]
        
        message_lower = user_message.lower()
        for pattern in file_creation_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
    def _load_context(self, session_type: SessionType, session_rules: dict) -> Any:
        """Load context from memory system."""
        context_builder = self._get_context_builder()
        context = context_builder.build_context()
        
        if not session_rules.get("load_memory_md", True):
            context.long_term_memory = ""
        
        return context
    
    async def _build_messages(
        self,
        context: Any,
        user_message: str,
        policy: Any,
        relevant_memories: list[str] | None = None,
        session_id: str | None = None,
        plan_state: PlanState | None = None,
        skill_context_msg: dict | None = None,  # Phase 2 - Skill invocation context
    ) -> tuple[list, dict]:
        """Build message list for LLM with session history and compression.

        Args:
            context: Loaded context bundle
            user_message: User's message
            policy: Policy bundle
            relevant_memories: Retrieved relevant memories (from hybrid search)
            session_id: Session ID for loading conversation history
            plan_state: Current plan state (for plan mode)
            skill_context_msg: Skill invocation context message (Phase 2)

        Returns:
            Tuple of (messages list for LLM, compression info dict)
        """
        # ===== CRITICAL DEBUG LOGS =====
        logger.info(f"[BUILD_MESSAGES_START] context type={type(context).__name__}, skill_context_msg type={type(skill_context_msg).__name__ if skill_context_msg else None}")
        if skill_context_msg:
            logger.info(f"[BUILD_MESSAGES] skill_context_msg content preview: {skill_context_msg.get('content', '')[:100]}...")
        
        messages = []
        system_parts = []
        
        # Compression info to return for debugging
        compression_info = {
            "message_count": 0,
            "token_count": 0,
            "threshold_rounds": None,
            "threshold_tokens": None,
            "needs_compression": False,
            "compressed": False,
        }

        # Add soft guidelines from PolicyEngine (optimized version)
        # This avoids loading the entire AGENTS.md file in system prompt
        guidelines = self.policy_engine.build_system_prompt_guidelines()
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

        # Add tools
        tools = self._tool_manager.get_all_tools()
        if tools:
            tool_names = [t.name for t in tools]
            system_parts.append(f"\n# 可用工具\n你可以使用以下工具：{', '.join(tool_names)}")
            
            # ===== Add workspace path for file operations =====
            system_parts.append(
                f"\n\n# 工作目录与文件分类存储（极其重要）\n"
                f"**你的工作目录是：** `{self.workspace_path}`\n\n"
                f"**文件分类存储规则（必须遵守）：**\n"
                f"| 文件类型 | 存储目录 | 示例路径 |\n"
                f"|---------|---------|--------|\n"
                f"| Python/JS 脚本 | `scripts/` | `{self.workspace_path}/scripts/demo.py` |\n"
                f"| PPT 演示文稿 | `presentations/` | `{self.workspace_path}/presentations/demo.pptx` |\n"
                f"| 文档（Word/PDF） | `documents/` | `{self.workspace_path}/documents/report.docx` |\n"
                f"| Excel 表格 | `spreadsheets/` | `{self.workspace_path}/spreadsheets/data.xlsx` |\n"
                f"| 图片资源 | `images/` | `{self.workspace_path}/images/logo.png` |\n"
                f"| PDF 文件 | `pdfs/` | `{self.workspace_path}/pdfs/report.pdf` |\n\n"
                f"**核心规则：**\n"
                f"1. ❌ **禁止**将文件保存到工作目录根目录（如 `{self.workspace_path}/demo.py`）\n"
                f"2. ✅ **必须**保存到对应的分类子目录（如 `{self.workspace_path}/scripts/demo.py`）\n"
                f"3. 脚本中的输出文件路径也必须使用分类子目录\n"
                f"4. **run_in_terminal 执行脚本时，working_dir 必须设为工作目录**\n\n"
                f"**正确示例：**\n"
                f"```json\n"
                f'{{"file_path": "{self.workspace_path}/scripts/demo.py", "content": "..."}}\n'
                f"```\n\n"
                f"**错误示例（禁止）：**\n"
                f"```json\n"
                f'{{"file_path": "{self.workspace_path}/demo.py", "content": "..."}}  // 错误！未使用子目录\n'
                f'{{"file_path": "/path/to/backend/demo.py", "content": "..."}}  // 错误！不是工作目录\n'
                f"```"
            )
            
            # Add explicit instruction for tool usage
            system_parts.append("\n# 工具使用规则\n**重要：当用户要求执行任何操作时，你必须立即调用相应的工具，而不是用文字询问用户确认。**\n例如：\n- 用户要求删除文件 → 直接调用 run_in_terminal 工具执行 rm 命令\n- 用户要求创建目录 → 直接调用 run_in_terminal 工具执行 mkdir 命令\n- 用户要求移动文件 → 直接调用 run_in_terminal 工具执行 mv 命令\n\n不要用文字询问用户是否确认。如果操作需要用户确认，系统会自动处理确认流程。")
            
            # ===== CRITICAL: Time awareness requirement =====
            system_parts.append(
                "\n\n# ⏰ **关键规则：时间敏感性查询的强制要求**\n"
                "**当用户问题中包含以下时间词时：**\n"
                "- \"今天\"、\"今日\"、\"此刻\"、\"现在\"\n"
                "- \"明天\"、\"明日\"、\"后天\"\n"
                "- \"昨天\"、\"昨日\"、\"前天\"\n"
                "- \"本周\"、\"本周 X\"、\"下周\"\n"
                "- \"当前\"、\"目前\"、\"最近\"\n"
                "- \"早上\"、\"下午\"、\"晚上\"（指当天）\n\n"
                "**你必须严格遵守以下步骤：**\n"
                "1️⃣ **第一步：必须立即调用 `get_current_time` 工具获取准确的当前日期和时间**\n"
                "2️⃣ **第二步：基于获取到的实际日期，再进行后续查询（如天气、新闻等）**\n"
                "3️⃣ **绝对禁止假设自己知道当前日期** - 你没有内置的时间概念\n"
                "4️⃣ **绝对禁止跳过时间确认步骤** - 这是强制性要求，不是可选项\n\n"
                "**错误示例（严禁出现）：**\n"
                "❌ 用户：'今天杭州天气怎么样'\n"
                "❌ AI：[直接调用 web_search 查询\"今天杭州天气\"] ← **没有先获取日期！**\n\n"
                "**正确示例：**\n"
                "✅ 用户：'今天杭州天气怎么样'\n"
                "✅ AI：[调用 get_current_time] → 获取到\"2026-02-23\" → [调用 web_search 查询\"2026 年 2 月 23 日杭州天气\"]"
            )
            
            # ===== SCHEME 2: Enhanced tool call enforcement =====
            system_parts.append(
                "\n\n# 关键规则：杜绝幻觉性完成声明\n"
                "**极其重要：**当用户要求创建/生成/制作任何具体产物（如 PPT、文件、代码、报告等）时：\n"
                "1. **必须立即调用实际的工具**（read_file, write_file, run_in_terminal 等）来执行真实操作\n"
                "2. **绝不能用文字声称'已经完成'而不实际调用工具** - 这是被严格禁止的\n"
                "3. **只有在工具真正执行成功后才能告知用户完成**\n"
                "4. **不要编造虚假的文件路径** - 只有通过工具实际创建的文件才是真实的\n\n"
                "错误示例（绝对禁止）：\n"
                "❌ 用户：'帮我创建一个 PPT'\n"
                "❌ AI：'好的，PPT 已创建完成，保存在 /path/to/file.pptx'（但实际没有调用任何工具）\n\n"
                "正确做法：\n"
                "✅ 用户：'帮我创建一个 PPT'\n"
                "✅ AI：[思考后调用 read_file 读取技能文档] → [调用 write_file 创建脚本] → [调用 run_in_terminal 执行脚本] → 'PPT 已创建完成，保存在 /path/to/file.pptx'"
            )
            
            # ===== SPECIAL EMPHASIS FOR PPT GENERATION =====
            system_parts.append(
                "\n\n# ⚠️ 特别警告：PPT 生成的常见错误\n"
                "**当用户说'制作 PPT'、'创建演示文稿'、'生成幻灯片'时：**\n"
                "1. ❌ **绝对不要**使用 `fs.writeFileSync('xxx.txt', content)` 创建 .txt 文件\n"
                "2. ✅ **必须**使用 PptxGenJS 的 `pptx.writeFile()` 方法生成 .pptx 文件\n"
                "3. ❌ **不要**只创建\"内容大纲\"或\"脚本文件\"就声称完成了 PPT\n"
                "4. ✅ **必须**生成实际的 .pptx 二进制文件（可以在 PowerPoint 中打开）\n\n"
                "**判断标准：**\n"
                "- 如果生成的文件不能在 PowerPoint/Keynote 中直接打开 = ❌ 失败\n"
                "- 如果生成的文件是 .pptx 格式且可以在 PowerPoint 中打开 = ✅ 成功\n\n"
                "**正确示例：**\n"
                "```javascript\n"
                "const pptx = new PptxGenJS();\n"
                "pptx.addSlide().addText('标题', { fontSize: 36 });\n"
                "await pptx.writeFile({ fileName: 'presentations/demo.pptx' }); // 生成真正的 PPTX 文件\n"
                "```\n\n"
                "**错误示例（严禁出现）：**\n"
                "```javascript\n"
                "fs.writeFileSync('presentation-outline.txt', '第 1 页：标题...'); // 这只是文本文件，不是 PPT！\n"
                "console.log('PPT 已创建'); // 错误的声明！\n"
                "```"
            )
        
        # ===== Inject Skills (after tools) =====
        # Optimization: If a specific skill is already being invoked via skill_context_msg,
        # skip injecting all skills to avoid redundancy and save tokens
        logger.info(f"[SKILL_INJECT_START] skill_context_msg exists={bool(skill_context_msg)}")
        if not skill_context_msg:  # Only inject all skills if no specific skill is being invoked
            logger.info(f"[SKILL_LIST_START] Getting all skills from registry")
            try:
                skills = self._skill_registry.list_all_skills()
                logger.info(f"[SKILL_LIST_RESULT] Found {len(skills)} skills total")
            except Exception as e:
                logger.error(f"[SKILL_LIST_ERROR] Failed to list skills: {e}", exc_info=True)
                raise
            
            if skills:
                # Filter skills that LLM can auto-trigger
                llm_callable_skills = [
                    s for s in skills 
                    if not s.disable_model_invocation and s.user_invocable
                ]
                        
                if llm_callable_skills:
                    # Limit to prevent token overflow
                    MAX_SKILLS = 20
                    MAX_DESC_LENGTH = 100
                        
                    display_skills = llm_callable_skills[:MAX_SKILLS]
                    skill_descriptions = []
                        
                    logger.info(f"[SKILL_ITER_START] Iterating over {len(display_skills)} skills")
                    for idx, skill in enumerate(display_skills):
                        # Debug each skill's attributes
                        logger.info(f"[SKILL_{idx}] name={skill.name}, description type={type(skill.description).__name__}, description len={len(skill.description) if skill.description else 0}")
                        desc = skill.description[:MAX_DESC_LENGTH] if skill.description else ""
                        # Only include skill name and description (path removed to save tokens)
                        # LLM can still access skill files via read_file with skill name
                        skill_desc = f"{skill.name}({desc})"
                        skill_descriptions.append(skill_desc)
                        
                    system_parts.append(
                        f"\n# 可用技能\n你还可以使用以下技能：{', '.join(skill_descriptions)}"
                    )
                        
                    # Add usage instructions (simplified, without path examples)
                    system_parts.append(
                        "\n\n**技能使用说明**："
                        "技能是以目录形式组织的知识包。每个技能包含："
                        "\n- SKILL.md：详细的使用指南和工作流程（通过 read_file 读取）"
                        "\n- scripts/：可直接运行的示例代码（通过 run_in_terminal 执行）"
                        "\n- references/：参考资料和文档（按需加载）"
                        "\n- assets/：模板和资源文件（直接使用）"
                        "\n\n你可以通过 read_file 工具读取任何技能的文件来学习如何使用它。"
                        "当需要执行脚本时，使用 run_in_terminal 工具。"
                    )
                    
                    # ===== SPECIAL BINDINGS: Skill-specific CLI commands =====
                    # Inject explicit CLI binding instructions for skills that require specific tools
                    
                    # 1. pptx → web-artifacts-builder skill (if exists)
                    pptx_skill = next((s for s in display_skills if s.name == "pptx"), None)
                    if pptx_skill:
                        system_parts.append(
                            "\n\n# ⚠️ 关键规则：pptx 技能专用工具\n"
                            "**当用户要求制作 PPT、创建演示文稿时：**\n"
                            "1. **必须使用 `write_file` 创建 Node.js 脚本**\n"
                            "2. **必须使用 PptxGenJS 库的 `pptx.writeFile()` 方法**\n"
                            "3. **生成的文件必须是 .pptx 格式**（能在 PowerPoint 中打开）\n"
                            "4. **绝对不要只创建 .txt 文本文件就声称完成了 PPT**\n\n"
                            "**错误示例（绝对禁止）**：\n"
                            "❌ `fs.writeFileSync('outline.txt', '第 1 页：标题...')` - 这只是文本文件\n"
                            "❌ 声称'PPT 已创建'但生成的是 .txt 文件\n\n"
                            "**正确示例**：\n"
                            "✅ 使用 PptxGenJS：`await pptx.writeFile({ fileName: 'demo.pptx' })`"
                        )
                        
                    logger.info(
                        f"Injected {len(display_skills)} skills into system prompt",
                        extra={
                            "session_id": session_id,
                            "skill_names": [s.name for s in display_skills],
                            "total_skills": len(skills),
                        }
                    )
        
        # Inject plan context (for complex tasks)
        if plan_state:
            # Check if we have a structured plan v2.0
            if hasattr(plan_state, 'structured_plan') and plan_state.structured_plan:
                structured_plan = plan_state.structured_plan
                
                # Inject structured plan with skill binding and tool constraints
                plan_prompt = structured_plan.to_prompt()
                system_parts.append(f"\n# 📋 结构化执行计划 v{structured_plan.version}\n{plan_prompt}")
                
                # Add explicit tool constraint instructions
                if structured_plan.tool_constraints:
                    if structured_plan.tool_constraints.allowed:
                        allowed_tools = ', '.join(structured_plan.tool_constraints.allowed)
                        system_parts.append(f"\n\n# ⚠️ **工具限制（必须遵守）**\n你**只能**使用以下工具：{allowed_tools}\n**禁止使用其他任何工具！**")
                    
                    if structured_plan.tool_constraints.forbidden:
                        forbidden_tools = ', '.join(structured_plan.tool_constraints.forbidden)
                        system_parts.append(f"\n\n# ❌ **禁止工具（绝对不可使用）**\n你**绝对不能**使用以下工具：{forbidden_tools}\n**违反此规则将导致任务失败！**")
                
                # Add skill-specific CLI binding instructions for pptx skill
                if structured_plan.skill_binding == 'pptx':
                    system_parts.append(
                        "\n\n# 🔧 **技能绑定：pptx**\n"
                        "**你必须使用 `write_file` 创建 Node.js 脚本，并使用 PptxGenJS 库：**\n"
                        "- ✅ 使用 `PptxGenJS`的`pptx.writeFile()` 方法生成.pptx 文件\n"
                        "- ❌ **禁止只创建.txt 文本文件就声称完成了 PPT** - 必须生成真正的.pptx 二进制文件\n"
                    )
                
                logger.info(
                    "StructuredPlan v2.0 injected into ReAct",
                    extra={
                        "session_id": session_id,
                        "skill_binding": structured_plan.skill_binding,
                        "tool_constraints": structured_plan.tool_constraints,
                        "steps_count": len(structured_plan.steps),
                    }
                )
            else:
                # Fallback to v1.0 plan context
                plan_context_text = self._plan_context.build_react_context(plan_state)
                system_parts.append(f"\n# 执行计划\n{plan_context_text}")
                system_parts.append("\n# 规划提示\n按计划逐步执行，如遇到困难可灵活调整。完成一步后在思考中说明进度。")
                system_parts.append("\n# 效率优化提示\n**重要：**为提升执行效率，你可以在一轮思考中并行调用多个独立的工具（例如同时搜索多个关键词、同时读取多个文件），而不是逐一执行。只有当工具之间有依赖关系时才需要顺序执行。")
                logger.info(
                    "LightPlan v1.0 injected into ReAct",
                    extra={
                        "session_id": session_id,
                        "current_step": plan_state.current_step,
                        "total_steps": plan_state.total_steps,
                    }
                )

        # Add relevant memories (from hybrid search) - more precise than loading all
        if relevant_memories:
            memory_text = "\n".join(relevant_memories)
            system_parts.append(f"\n# 相关记忆\n{memory_text}")
        # Fallback to long-term memory if no relevant memories found
        elif context.long_term_memory:
            system_parts.append(f"\n# 长期记忆\n{context.long_term_memory[:800]}")

        # Build system message
        system_message = "\n".join(system_parts) if system_parts else ""
        
        # Phase 2: Add skill invocation context (if any) as the FIRST system message
        if skill_context_msg:
            messages.append(skill_context_msg)
        
        # Add the main system message with behavior guidelines, tools, skills, etc.
        # Note: Only add once to avoid duplication
        if system_message:
            messages.append({
                "role": "system",
                "content": system_message,
            })
        
        # Load conversation history from session
        history_messages = []
        if session_id:
            try:
                session_manager = self._get_session_manager()
                history_messages = await session_manager.get_messages_as_dict(session_id)
                
                logger.info(
                    "Loaded conversation history",
                    extra={
                        "session_id": session_id,
                        "history_count": len(history_messages),
                    }
                )
            except Exception as e:
                logger.warning(
                    "Failed to load conversation history",
                    extra={"session_id": session_id, "error": str(e)}
                )
        
        # Build full message list: system + history
        # Note: user_message is NOT appended here because it's already saved
        # in the database by Agent._chat_with_orchestrator_streaming before
        # calling Orchestrator.process_request
        # Note: system_message has already been added above, do NOT add it again
        
        # ===== CRITICAL FIX: Prevent context pollution from previous tasks =====
        # If there are many history messages, add a clear separator to indicate
        # this is a new request, preventing LLM from confusing with old tasks
        if history_messages and len(history_messages) > 4:
            # Add a system reminder to clarify this is a new task
            messages.append({
                "role": "system",
                "content": "\n---\n📌 **注意：这是一个新的请求，请忽略之前对话中的具体任务内容。**\n请专注于当前用户请求，不要受历史对话中提到的具体产物（如 PPT、文件等）影响。\n---\n"
            })
        
        messages.extend(history_messages)
        
        # Safety check: if history is empty (new session), add user message
        if not history_messages and user_message:
            messages.append({"role": "user", "content": user_message})
        
        # Update compression info with current state
        compression_info["message_count"] = len(messages)
        
        # Apply context compression if needed
        if len(messages) > 1 and session_id:
            try:
                compression_manager = self._get_compression_manager()
                
                # Update compression info with thresholds
                compression_info["threshold_rounds"] = compression_manager.config.threshold_rounds
                compression_info["threshold_tokens"] = compression_manager.config.threshold_tokens
                
                logger.info(
                    "Applying context compression",
                    extra={
                        "session_id": session_id,
                        "message_count": len(messages),
                        "compression_config": {
                            "threshold_rounds": compression_manager.config.threshold_rounds,
                            "threshold_tokens": compression_manager.config.threshold_tokens,
                            "retention_count": compression_manager.config.retention_count,
                        },
                    }
                )
                
                prepared = await compression_manager.prepare_context(
                    session_id=session_id,
                    current_messages=messages,
                    system_prompt=system_message
                )
                messages = prepared.messages
                
                # Update compression info with results
                compression_info["token_count"] = prepared.total_tokens
                compression_info["needs_compression"] = prepared.summary is not None or len(messages) != compression_info["message_count"]
                compression_info["compressed"] = prepared.summary is not None
                
                if prepared.summary:
                    logger.info(
                        "Context compression applied",
                        extra={
                            "session_id": session_id,
                            "total_tokens": prepared.total_tokens,
                            "has_summary": True,
                            "summary_preview": prepared.summary[:100] if prepared.summary else None,
                        }
                    )
                else:
                    logger.info(
                        "No compression applied (below threshold)",
                        extra={
                            "session_id": session_id,
                            "total_tokens": prepared.total_tokens,
                        }
                    )
            except Exception as e:
                logger.warning(
                    "Context compression failed, using original messages",
                    extra={"session_id": session_id, "error": str(e)}
                )
        
        return messages, compression_info
    
    def _get_current_step_description(self, plan_state: PlanState) -> str | None:
        """Get description of current step from plan
        
        Args:
            plan_state: Current plan state
            
        Returns:
            Step description or None if not available
        """
        steps = self._plan_context._parse_plan_steps(plan_state.original_plan)
        if 0 < plan_state.current_step <= len(steps):
            return steps[plan_state.current_step - 1]
        return None
    
    def _build_validation_context(
        self,
        tool_name: str,
        output: str,
    ) -> dict:
        """Build validation context from tool result
        
        Args:
            tool_name: Tool that was executed
            output: Tool output
            
        Returns:
            Context dict for milestone validation
        """
        context = {}
        
        # Extract file paths from output
        if tool_name in ["write_file", "create_file"]:
            # Try to parse file path from output
            import re
            match = re.search(r'(/[\w/.-]+\.\w+)', output)
            if match:
                context["file_path"] = match.group(0)
        
        # Extract module names from file paths
        if "file_path" in context:
            file_path = context["file_path"]
            # Convert file path to module name
            if file_path.endswith(".py"):
                module_name = file_path.replace("/", ".").replace(".py", "").split(".")[-1]
                context["module_name"] = module_name
        
        return context
    
    async def _write_memory(self, user_message: str, assistant_message: str, session_id: str) -> None:
        """Write conversation to memory."""
        try:
            from ..memory.md_sync import get_md_sync
            
            md_sync = get_md_sync(str(self.workspace_path))
            smart_memory = get_smart_memory_service(self._llm_router, str(self.workspace_path))
            
            await smart_memory.analyze_and_record(
                user_message=user_message,
                assistant_message=assistant_message,
                session_id=session_id,
                md_sync=md_sync,
            )
        except Exception as e:
            logger.warning(f"Failed to write memory: {e}")


# Global orchestrator instance
_orchestrator: Orchestrator | None = None


def get_orchestrator(workspace_path: str | None = None) -> Orchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    
    if _orchestrator is None:
        if workspace_path is None:
            config = ConfigManager().config
            # Handle ~ expansion and absolute/relative paths correctly
            raw_path = config.workspace.path
            expanded_path = Path(raw_path).expanduser()  # Expand ~ to user home
            
            if expanded_path.is_absolute():
                # Use absolute path directly
                workspace_path = str(expanded_path.resolve())
            else:
                # Relative path: resolve from backend directory
                backend_dir = Path(__file__).parent.parent.parent
                workspace_path = str((backend_dir / raw_path).resolve())
        _orchestrator = Orchestrator(workspace_path)
    
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the global orchestrator instance."""
    global _orchestrator
    _orchestrator = None


async def _execute_skill_directly(
    tool_manager,
    skill,
    arguments: str,
    session_id: str
) -> AsyncGenerator[dict, None]:
    """Execute skill's CLI command directly without ReAct loop.
    
    Args:
        tool_manager: ToolManager instance
        skill: SkillMetadata object
        arguments: Skill arguments string (will be used as CLI command arguments)
        session_id: Session ID for logging
        
    Yields:
        Event dictionaries
    """
    from src.models.skill import SkillMetadata
    
    logger.info(
        "Direct skill execution started",
        extra={
            "skill_name": skill.name,
            "arguments": arguments,
        }
    )
    
    # Build CLI command from skill name and arguments
    # The CLI command format depends on the specific skill
    # Example: "input.pdf output.docx" → "pdftotext input.pdf output.docx"
    cli_command = f"{skill.name}-cli {arguments}"  # Placeholder - actual command depends on skill
    
    logger.info(
        "Executing CLI command",
        extra={
            "command": cli_command,
            "skill_name": skill.name,
        }
    )
    
    try:
        # Execute CLI command directly
        result = await tool_manager.execute(
            "run_in_terminal",
            {"command": cli_command},
            skill_context=skill,
        )
        
        # Yield tool call event
        yield {
            "type": ORCH_EVENT_TOOL_CALL,
            "tool_call_id": f"direct_{skill.name}",
            "name": "run_in_terminal",
            "arguments": {"command": cli_command},
        }
        
        # Yield tool result event
        yield {
            "type": ORCH_EVENT_TOOL_RESULT,
            "tool_call_id": f"direct_{skill.name}",
            "tool_name": "run_in_terminal",
            "success": result.success,
            "output": result.output,
            "error": result.error,
        }
        
        # Yield final answer
        if result.success:
            yield {
                "type": ORCH_EVENT_FINAL,
                "content": f"✅ 技能 '{skill.name}' 执行成功:\n\n{result.output}",
            }
        else:
            yield {
                "type": ORCH_EVENT_FINAL,
                "content": f"❌ 技能 '{skill.name}' 执行失败:\n\n{result.error or result.output}",
            }
            
    except Exception as e:
        logger.error(
            "Direct skill execution failed",
            extra={
                "skill_name": skill.name,
                "error": str(e),
            }
        )
        yield {
            "type": ORCH_EVENT_ERROR,
            "error": f"技能执行失败：{str(e)}",
        }
