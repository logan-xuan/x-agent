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

logger = get_logger(__name__)


class Agent:
    """X-Agent core logic.
    
    Orchestrates:
    - Session management
    - LLM routing with failover
    - Streaming responses
    - Message persistence
    - Context loading from memory system
    """
    
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        llm_router: LLMRouter | None = None,
        context_builder: "ContextBuilder | None" = None,
    ) -> None:
        """Initialize agent.
        
        Args:
            session_manager: Session manager instance
            llm_router: LLM router instance
            context_builder: Context builder for memory system
        """
        self._session_manager = session_manager or SessionManager()
        self._llm_router = llm_router or LLMRouter()
        
        # Get workspace path from config
        if context_builder:
            self._context_builder = context_builder
        else:
            from ..memory.context_builder import get_context_builder
            config_manager = ConfigManager()
            workspace_path = config_manager.config.workspace.path
            # Resolve relative path from backend directory
            backend_dir = Path(__file__).parent.parent.parent
            resolved_path = (backend_dir / workspace_path).resolve()
            # Use global singleton to ensure cache is shared and can be cleared
            self._context_builder = get_context_builder(str(resolved_path))
            logger.info(
                "Agent initialized with workspace",
                extra={"workspace_path": str(resolved_path)}
            )
    
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

