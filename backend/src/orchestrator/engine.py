"""Orchestrator engine for X-Agent.

The Orchestrator is the central coordinator that:
- Loads and applies AGENTS.md policies
- Coordinates context loading
- Manages the ReAct loop
- Executes tools
- Handles memory writing

This is the main entry point for processing user requests.
"""

import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

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
from ..config.manager import ConfigManager
from ..memory.context_builder import ContextBuilder, get_context_builder
from ..memory.hybrid_search import HybridSearch, get_hybrid_search
from ..memory.md_sync import get_md_sync
from ..memory.models import SessionType
from ..memory.vector_store import get_vector_store
from ..memory.embedder import get_embedder
from ..services.llm.router import LLMRouter
from ..services.smart_memory import get_smart_memory_service
from ..tools.manager import ToolManager, get_tool_manager
from ..tools.builtin import get_builtin_tools
from ..utils.logger import get_logger

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


class Orchestrator:
    """Central orchestrator for X-Agent request processing."""
    
    def __init__(
        self,
        workspace_path: str,
        llm_router: LLMRouter | None = None,
    ) -> None:
        """Initialize the orchestrator."""
        self.workspace_path = Path(workspace_path).resolve()
        
        # Initialize components
        self.policy_engine = PolicyEngine(str(self.workspace_path))
        self.session_guard = SessionGuard()
        self.response_guard = ResponseGuard()
        
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
        
        # Tool manager with built-in tools
        self._tool_manager = get_tool_manager()
        self._register_builtin_tools()
        
        # ReAct loop
        self._react_loop = ReActLoop(
            llm_router=self._llm_router,
            tool_manager=self._tool_manager,
        )
        
        logger.info(
            "Orchestrator initialized",
            extra={
                "workspace_path": str(self.workspace_path),
                "tools_count": len(self._tool_manager.get_tool_names()),
            }
        )
    
    def _get_context_builder(self) -> ContextBuilder:
        """Get or create context builder."""
        if self._context_builder is None:
            self._context_builder = get_context_builder(str(self.workspace_path))
        return self._context_builder
    
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
            }
        )
        
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
        
        # Step 4: Build Messages
        messages = self._build_messages(context, user_message, policy, relevant_memories)
        
        # Step 5: ReAct Loop
        final_response = ""
        
        try:
            async for event in self._react_loop.run_streaming(
                messages,
                tools=self._tool_manager.get_all_tools(),
                session_id=session_id,
            ):
                event_type = event.get("type")
                
                if event_type == REACT_EVENT_THINKING:
                    yield {
                        "type": ORCH_EVENT_THINKING,
                        "content": event.get("content", ""),
                    }
                elif event_type == "tool_call":
                    yield {
                        "type": ORCH_EVENT_TOOL_CALL,
                        "name": event.get("name"),
                        "arguments": event.get("arguments"),
                    }
                elif event_type == "tool_result":
                    yield {
                        "type": ORCH_EVENT_TOOL_RESULT,
                        "tool_name": event.get("tool_name"),
                        "success": event.get("success"),
                        "output": event.get("output"),
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
                elif event_type == REACT_EVENT_ERROR:
                    yield {
                        "type": ORCH_EVENT_ERROR,
                        "error": event.get("error", "Unknown error"),
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
        
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Request completed",
            extra={
                "session_id": session_id,
                "duration_ms": duration_ms,
            }
        )
    
    def _load_context(self, session_type: SessionType, session_rules: dict) -> Any:
        """Load context from memory system."""
        context_builder = self._get_context_builder()
        context = context_builder.build_context()
        
        if not session_rules.get("load_memory_md", True):
            context.long_term_memory = ""
        
        return context
    
    def _build_messages(
        self,
        context: Any,
        user_message: str,
        policy: Any,
        relevant_memories: list[str] | None = None,
    ) -> list:
        """Build message list for LLM.
        
        Args:
            context: Loaded context bundle
            user_message: User's message
            policy: Policy bundle
            relevant_memories: Retrieved relevant memories (from hybrid search)
            
        Returns:
            List of messages for LLM
        """
        messages = []
        system_parts = []
        
        # Add soft guidelines
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
            system_parts.append(f"\n# 可用工具\n你可以使用以下工具: {', '.join(tool_names)}")
        
        # Add relevant memories (from hybrid search) - more precise than loading all
        if relevant_memories:
            memory_text = "\n".join(relevant_memories)
            system_parts.append(f"\n# 相关记忆\n{memory_text}")
        # Fallback to long-term memory if no relevant memories found
        elif context.long_term_memory:
            system_parts.append(f"\n# 长期记忆\n{context.long_term_memory[:800]}")
        
        if system_parts:
            messages.append({"role": "system", "content": "\n".join(system_parts)})
        
        messages.append({"role": "user", "content": user_message})
        return messages
    
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
            backend_dir = Path(__file__).parent.parent.parent
            workspace_path = str((backend_dir / config.workspace.path).resolve())
        _orchestrator = Orchestrator(workspace_path)
    
    return _orchestrator


def reset_orchestrator() -> None:
    """Reset the global orchestrator instance."""
    global _orchestrator
    _orchestrator = None
