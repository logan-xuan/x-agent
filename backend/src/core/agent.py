"""Agent core logic with streaming support."""

from pathlib import Path
from collections.abc import AsyncGenerator
from typing import Any, TYPE_CHECKING

from ..config.manager import ConfigManager
from ..services.compression import ContextCompressionManager
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
    - Tool confirmation for high-risk commands
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

        # Tool confirmation tracking for high-risk commands
        self._tool_confirmations: dict[str, bool] = {}

        # Get workspace path from config with proper ~ expansion
        config_manager = ConfigManager()
        raw_workspace_path = config_manager.config.workspace.path
        backend_dir = Path(__file__).parent.parent.parent
        
        # Handle ~ expansion and absolute/relative paths correctly
        expanded_path = Path(raw_workspace_path).expanduser()  # Expand ~ to user home
        if expanded_path.is_absolute():
            self._resolved_workspace_path = str(expanded_path.resolve())
        else:
            self._resolved_workspace_path = str((backend_dir / raw_workspace_path).resolve())

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
            # Lazy import to avoid circular dependency
            try:
                from ..orchestrator.engine import Orchestrator
                self._orchestrator = Orchestrator(
                    workspace_path=self._resolved_workspace_path,
                    llm_router=self._llm_router,
                    session_manager=self._session_manager,
                )
                logger.info("Agent initialized with Orchestrator")
            except Exception as e:
                logger.error(
                    "Failed to initialize Orchestrator",
                    extra={"error": str(e), "exc_info": True}
                )
                raise
        
        # Initialize context compression manager
        self._compression_manager = ContextCompressionManager(
            config=config_manager.config.compression,
            workspace_path=self._resolved_workspace_path,
            llm_service=self._llm_router if hasattr(self._llm_router, 'complete') else None
        )
        logger.info("Agent initialized with ContextCompressionManager")

    def set_tool_confirmation(self, tool_call_id: str, confirmed: bool) -> None:
        """Set confirmation status for a high-risk tool call.

        Args:
            tool_call_id: The tool call ID to confirm
            confirmed: Whether the tool call is confirmed
        """
        self._tool_confirmations[tool_call_id] = confirmed
        logger.info(
            f"Tool confirmation set: {tool_call_id} = {confirmed}",
            extra={"tool_call_id": tool_call_id, "confirmed": confirmed}
        )

    def is_tool_confirmed(self, tool_call_id: str) -> bool:
        """Check if a tool call has been confirmed.

        Args:
            tool_call_id: The tool call ID to check

        Returns:
            True if confirmed, False otherwise
        """
        return self._tool_confirmations.get(tool_call_id, False)

    def clear_tool_confirmation(self, tool_call_id: str) -> None:
        """Clear confirmation status for a tool call.

        Args:
            tool_call_id: The tool call ID to clear
        """
        if tool_call_id in self._tool_confirmations:
            del self._tool_confirmations[tool_call_id]
    
    def _get_orchestrator(self) -> "Orchestrator":
        """Get or create orchestrator instance."""
        if self._orchestrator is None:
            from ..orchestrator.engine import Orchestrator
            self._orchestrator = Orchestrator(
                workspace_path=self._resolved_workspace_path,
                llm_router=self._llm_router,
                session_manager=self._session_manager,
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
        
        # Apply context compression if needed
        prepared = await self._compression_manager.prepare_context(
            session_id=session_id,
            current_messages=messages,
            system_prompt=system_prompt
        )
        messages = prepared.messages
        
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
                        "tool_call_id": event.get("tool_call_id"),
                        "name": event.get("name"),
                        "arguments": event.get("arguments"),
                        "session_id": session_id,
                    }
                elif event_type == "tool_result":
                    yield {
                        "type": "tool_result",
                        "tool_call_id": event.get("tool_call_id"),
                        "tool_name": event.get("tool_name"),
                        "success": event.get("success"),
                        "output": event.get("output"),
                        "result": event.get("result"),
                        "session_id": session_id,
                    }
                elif event_type == "awaiting_confirmation":
                    yield {
                        "type": "awaiting_confirmation",
                        "tool_call_id": event.get("tool_call_id"),
                        "confirmation_id": event.get("confirmation_id"),
                        "command": event.get("command"),
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

