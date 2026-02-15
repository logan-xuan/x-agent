"""Agent core logic with streaming support."""

from pathlib import Path
from collections.abc import AsyncGenerator
from typing import Any

from ..config.manager import ConfigManager
from ..memory.context_builder import ContextBuilder
from ..memory.importance_detector import get_importance_detector
from ..memory.md_sync import get_md_sync
from ..memory.models import MemoryEntry, MemoryContentType
from ..services.llm.router import LLMRouter
from ..services.storage import StorageService
from ..utils.logger import get_logger, log_execution
from .session import SessionManager

logger = get_logger(__name__)


class Agent:
    """X-Agent core logic.
    
    Orchestrates:
    - Session management
    - LLM routing with failover
    - Streaming responses
    - Message persistence
    - Context loading from memory system
    - Automatic memory recording for important content
    """
    
    def __init__(
        self,
        session_manager: SessionManager | None = None,
        llm_router: LLMRouter | None = None,
        context_builder: ContextBuilder | None = None,
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
            config_manager = ConfigManager()
            workspace_path = config_manager.config.workspace.path
            # Resolve relative path from backend directory
            backend_dir = Path(__file__).parent.parent.parent
            resolved_path = (backend_dir / workspace_path).resolve()
            self._context_builder = ContextBuilder(str(resolved_path))
            logger.info(
                "Agent initialized with workspace",
                extra={"workspace_path": str(resolved_path)}
            )
        
        # Initialize memory components
        self._importance_detector = get_importance_detector()
        self._md_sync = get_md_sync(str(resolved_path))
    
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
            
            # Check for important content and record memory
            self._record_if_important(user_message, response.content)
            
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
            
            # Check for important content and record memory
            self._record_if_important(user_message, full_content)
            
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
    
    def _record_if_important(self, user_message: str, assistant_message: str) -> None:
        """Check if conversation contains important content and record to memory.
        
        Only records extracted important content, not the full message.
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
        """
        try:
            # Analyze the conversation turn
            analysis = self._importance_detector.analyze_conversation_turn(
                user_message=user_message,
                assistant_message=assistant_message,
            )
            
            if analysis["is_important"]:
                user_analysis = analysis.get("user_analysis", {})
                assistant_analysis = analysis.get("assistant_analysis", {})
                
                # Extract important content - NOT the full message
                content_to_record = None
                
                # Check user message for extracted entities
                user_entities = user_analysis.get("extracted_entities", [])
                if user_entities:
                    content_to_record = user_entities[0].get("content", "")
                
                # Check assistant message for extracted entities
                if not content_to_record:
                    assistant_entities = assistant_analysis.get("extracted_entities", [])
                    if assistant_entities:
                        content_to_record = assistant_entities[0].get("content", "")
                
                # Skip if no extractable content
                if not content_to_record or len(content_to_record.strip()) < 2:
                    logger.debug(
                        "Important detected but no extractable content, skipping",
                        extra={
                            "matched_keywords": user_analysis.get("matched_keywords", []),
                            "user_message_preview": user_message[:50],
                        }
                    )
                    return
                
                # Create memory entry
                content_type_str = analysis.get("content_type", "conversation")
                try:
                    content_type = MemoryContentType(content_type_str)
                except ValueError:
                    content_type = MemoryContentType.CONVERSATION
                
                entry = MemoryEntry(
                    content=content_to_record,
                    content_type=content_type,
                )
                
                # Save to markdown
                self._md_sync.append_memory_entry(entry)
                
                logger.info(
                    "Important content extracted and recorded",
                    extra={
                        "recorded_content": content_to_record[:50],
                        "content_type": content_type.value,
                        "matched_patterns": user_analysis.get("matched_patterns", []),
                    }
                )
            else:
                logger.debug(
                    "Content not important, skipping memory recording",
                    extra={"user_message_preview": user_message[:50]}
                )
                
        except Exception as e:
            # Don't fail the chat if memory recording fails
            logger.error(
                "Failed to record memory",
                extra={"error": str(e)}
            )
