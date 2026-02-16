"""Agent core logic with streaming support."""

from pathlib import Path
from collections.abc import AsyncGenerator
from typing import Any, TYPE_CHECKING

from ..config.manager import ConfigManager
from ..services.llm.router import LLMRouter
from ..services.storage import StorageService
from ..utils.logger import get_logger, log_execution
from .session import SessionManager

if TYPE_CHECKING:
    from ..memory.context_builder import ContextBuilder
    from ..orchestrator.engine import Orchestrator

logger = get_logger(__name__)


class Agent:
    """X-Agent core logic.
    
    Orchestrates:
    - Session management
    - LLM routing with failover
    - Streaming responses
    - Message persistence
    - Context loading from memory system
    - Orchestrator for ReAct loop and tools (new)
    """
    
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        llm_router: LLMRouter | None = None,
        context_builder: "ContextBuilder | None" = None,
        use_orchestrator: bool = True,
    ) -> None:
        """Initialize agent.
        
        Args:
            session_manager: Session manager instance
            llm_router: LLM router instance
            context_builder: Context builder for memory system
            use_orchestrator: Whether to use the new Orchestrator (default: True)
        """
        self._session_manager = session_manager or SessionManager()
        self._llm_router = llm_router or LLMRouter()
        self._use_orchestrator = use_orchestrator
        self._orchestrator: "Orchestrator | None" = None
        
        # Get workspace path from config
        config_manager = ConfigManager()
        workspace_path = config_manager.config.workspace.path
        backend_dir = Path(__file__).parent.parent.parent
        self._resolved_workspace_path = str((backend_dir / workspace_path).resolve())
        
        if context_builder:
            self._context_builder = context_builder
        else:
            from ..memory.context_builder import get_context_builder
            self._context_builder = get_context_builder(self._resolved_workspace_path)
            logger.info(
                "Agent initialized with workspace",
                extra={"workspace_path": self._resolved_workspace_path}
            )
        
        # Initialize Orchestrator if enabled
        if self._use_orchestrator:
            from ..orchestrator.engine import Orchestrator
            self._orchestrator = Orchestrator(
                workspace_path=self._resolved_workspace_path,
                llm_router=self._llm_router,
            )
            logger.info("Agent initialized with Orchestrator")
    
    def _get_orchestrator(self) -> "Orchestrator":
        """Get or create orchestrator instance."""
        if self._orchestrator is None:
            from ..orchestrator.engine import Orchestrator
            self._orchestrator = Orchestrator(
                workspace_path=self._resolved_workspace_path,
                llm_router=self._llm_router,
            )
        return self._orchestrator
    
    @log_execution
    async def chat(
        self,
        session_id: str,
        user_message: str,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """Process a chat message and get AI response.
        
        Args:
            session_id: Session UUID
            user_message: User's message
            stream: Whether to stream the response
            
        Returns:
            Response dict (non-streaming) or AsyncGenerator (streaming)
        """
        # Use Orchestrator if available and enabled
        if self._use_orchestrator and self._orchestrator:
            if stream:
                return self._chat_with_orchestrator_streaming(session_id, user_message)
            else:
                return await self._chat_with_orchestrator(session_id, user_message)
        
        # Legacy path (without Orchestrator)
        # Save user message
        await self._session_manager.add_message(
            session_id=session_id,
            role="user",
            content=user_message,
        )
        
        # Get conversation history
        messages = await self._session_manager.get_messages_as_dict(session_id)
        
        # Load context from memory system and inject as system message
        context = self._context_builder.build_context()
        system_prompt = self._context_builder.get_system_prompt(context)
        
        # Prepend system prompt if we have identity context
        if context.spirit or context.owner:
            messages = [
                {"role": "system", "content": system_prompt}
            ] + messages
            logger.info(
                "Context injected into conversation",
                extra={
                    "session_id": session_id,
                    "has_spirit": context.spirit is not None,
                    "has_owner": context.owner is not None,
                    "message_count": len(messages),
                }
            )
        
        if stream:
            return self._chat_streaming(session_id, messages)
        else:
            return await self._chat_non_streaming(session_id, messages)
    
    async def _chat_with_orchestrator(
        self,
        session_id: str,
        user_message: str,
    ) -> dict[str, Any]:
        """Chat using the new Orchestrator (non-streaming)."""
        try:
            # Save user message
            await self._session_manager.add_message(
                session_id=session_id,
                role="user",
                content=user_message,
            )
            
            final_content = ""
            
            # Process through Orchestrator
            async for event in self._orchestrator.process_request(
                session_id=session_id,
                user_message=user_message,
                stream=False,
            ):
                if event.get("type") == "final_answer":
                    final_content = event.get("content", "")
            
            # Save assistant message
            if final_content:
                await self._session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=final_content,
                )
            
            return {
                "type": "message",
                "role": "assistant",
                "content": final_content,
                "session_id": session_id,
            }
            
        except Exception as e:
            logger.error(
                "Orchestrator chat failed",
                extra={"session_id": session_id, "error": str(e)}
            )
            return {
                "type": "error",
                "error": str(e),
                "session_id": session_id,
            }
    
    async def _chat_with_orchestrator_streaming(
        self,
        session_id: str,
        user_message: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Chat using the new Orchestrator (streaming)."""
        try:
            # Save user message
            await self._session_manager.add_message(
                session_id=session_id,
                role="user",
                content=user_message,
            )
            
            full_content = ""
            
            # Process through Orchestrator
            async for event in self._orchestrator.process_request(
                session_id=session_id,
                user_message=user_message,
                stream=True,
            ):
                event_type = event.get("type")
                
                # Forward events to client
                if event_type == "thinking":
                    yield {
                        "type": "thinking",
                        "content": event.get("content", ""),
                        "session_id": session_id,
                    }
                elif event_type == "tool_call":
                    yield {
                        "type": "tool_call",
                        "name": event.get("name"),
                        "arguments": event.get("arguments"),
                        "session_id": session_id,
                    }
                elif event_type == "tool_result":
                    yield {
                        "type": "tool_result",
                        "tool_name": event.get("tool_name"),
                        "success": event.get("success"),
                        "output": event.get("output"),
                        "session_id": session_id,
                    }
                elif event_type == "final_answer":
                    full_content = event.get("content", "")
                    yield {
                        "type": "message",
                        "role": "assistant",
                        "content": full_content,
                        "session_id": session_id,
                        "is_finished": True,
                    }
                elif event_type == "error":
                    yield {
                        "type": "error",
                        "error": event.get("error"),
                        "session_id": session_id,
                    }
            
            # Save assistant message
            if full_content:
                await self._session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=full_content,
                )
            
        except Exception as e:
            logger.error(
                "Orchestrator streaming chat failed",
                extra={"session_id": session_id, "error": str(e)}
            )
            yield {
                "type": "error",
                "error": str(e),
                "session_id": session_id,
            }
    
    async def _chat_non_streaming(
        self,
        session_id: str,
        messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        """Non-streaming chat completion."""
        try:
            # Get user message from the last user message in messages
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break
            
            # Get response from LLM (with session_id for stats)
            response = await self._llm_router.chat(messages, stream=False, session_id=session_id)
            
            # Save assistant message
            await self._session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=response.content,
                metadata={
                    "model": response.model,
                    "usage": response.usage,
                }
            )
            
            # NOTE: Memory recording is handled by websocket.py smart_record_conversation
            
            return {
                "type": "message",
                "role": "assistant",
                "content": response.content,
                "session_id": session_id,
                "model": response.model,
            }
            
        except Exception as e:
            logger.error(
                "Chat failed",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return {
                "type": "error",
                "error": str(e),
                "session_id": session_id,
            }
    
    async def _chat_streaming(
        self,
        session_id: str,
        messages: list[dict[str, str]]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming chat completion."""
        full_content = ""
        model = "unknown"
        
        # Get user message from the last user message in messages
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        try:
            # Get streaming response from LLM (with session_id for stats)
            stream = await self._llm_router.chat(messages, stream=True, session_id=session_id)
            
            async for chunk in stream:
                full_content += chunk.content
                model = chunk.model or model
                
                yield {
                    "type": "chunk",
                    "content": chunk.content,
                    "is_finished": chunk.is_finished,
                    "session_id": session_id,
                    "model": chunk.model,
                }
            
            # Save complete assistant message
            await self._session_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=full_content,
                metadata={"model": model}
            )
            
            # NOTE: Memory recording is handled by websocket.py smart_record_conversation
            # to avoid duplicate writes and use LLM-based analysis
            
            # Send final message
            yield {
                "type": "message",
                "role": "assistant",
                "content": full_content,
                "session_id": session_id,
                "model": model,
                "is_finished": True,
            }
            
        except Exception as e:
            logger.error(
                "Streaming chat failed",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            yield {
                "type": "error",
                "error": str(e),
                "session_id": session_id,
            }
    
    async def create_session(self, title: str | None = None) -> dict[str, Any]:
        """Create a new chat session.
        
        Args:
            title: Optional session title
            
        Returns:
            Session info dict
        """
        session = await self._session_manager.create_session(title)
        return session.to_dict()
    
    async def get_session_history(self, session_id: str) -> list[dict[str, Any]]:
        """Get session message history.
        
        Args:
            session_id: Session UUID
            
        Returns:
            List of message dicts
        """
        messages = await self._session_manager.get_messages(session_id)
        return [msg.to_dict() for msg in messages]

