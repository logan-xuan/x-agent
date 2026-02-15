"""WebSocket endpoint for real-time chat with distributed tracing."""

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.agent import Agent
from ..core.context import AgentContext, ContextSource, set_current_context, clear_current_context, get_current_context
from ..memory.importance_detector import get_importance_detector
from ..memory.md_sync import get_md_sync
from ..memory.models import MemoryEntry
from ..utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Global agent instance
_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


async def record_if_important(
    user_message: str,
    assistant_message: str,
    session_id: str,
) -> bool:
    """Record conversation turn if it contains important information.
    
    Args:
        user_message: User's message
        assistant_message: Assistant's response
        session_id: Session ID for metadata
        
    Returns:
        True if recorded, False otherwise
    """
    try:
        detector = get_importance_detector()
        analysis = detector.analyze_conversation_turn(user_message, assistant_message)
        
        if analysis["is_important"]:
            md_sync = get_md_sync()
            
            # Create memory entry with the important content
            content_type = detector.detect_content_type(user_message)
            if content_type.value == "conversation":
                content_type = detector.detect_content_type(assistant_message)
            
            # Use user message as primary content
            entry = MemoryEntry(
                content=user_message,
                content_type=content_type,
                metadata={
                    "session_id": session_id,
                    "assistant_preview": assistant_message[:100] if assistant_message else "",
                    "matched_patterns": analysis["user_analysis"].get("matched_patterns", []),
                }
            )
            
            result = md_sync.append_memory_entry(entry)
            
            if result:
                logger.info(
                    "Important conversation recorded",
                    extra={
                        "session_id": session_id,
                        "content_type": content_type.value,
                        "patterns": analysis["user_analysis"].get("matched_patterns", []),
                    }
                )
            return result
            
        return False
        
    except Exception as e:
        logger.warning(
            "Failed to record important content",
            extra={"error": str(e), "session_id": session_id}
        )
        return False


@router.websocket("/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time chat with streaming and distributed tracing.
    
    Supports:
    - Chat messages: {"content": "message"}
    - Ping/Pong heartbeat: {"type": "ping"} -> {"type": "pong"}
    - Distributed tracing via X-Trace-ID header
    
    Args:
        websocket: WebSocket connection
        session_id: Session identifier
    """
    # Get trace ID from headers, query params, or generate new one
    trace_id = (
        websocket.headers.get("X-Trace-ID") 
        or websocket.query_params.get("trace_id")
        or str(uuid.uuid4())
    )
    request_id = str(uuid.uuid4())[:8]
    
    # Create WebSocket context
    context = AgentContext(
        trace_id=trace_id,
        request_id=request_id,
        session_id=session_id,
        source=ContextSource.WEBSOCKET,
        metadata={
            "client_host": websocket.client.host if websocket.client else None,
            "client_port": websocket.client.port if websocket.client else None,
        },
    )
    
    # Set context for this WebSocket connection
    set_current_context(context)
    
    await websocket.accept()
    logger.info(
        f"WebSocket connected: session={session_id}",
        extra={
            "trace_id": trace_id,
            "request_id": request_id,
            "session_id": session_id,
            "source": "websocket",
        }
    )
    
    try:
        agent = get_agent()
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            # Create child context for each message
            message_context = context.child(
                metadata={"message_type": "chat"}
            )
            set_current_context(message_context)
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON",
                    "session_id": session_id,
                    "trace_id": message_context.trace_id,
                })
                continue
            
            # Handle ping/pong heartbeat
            if message.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "trace_id": message_context.trace_id,
                })
                continue
            
            # Handle chat message
            user_content = message.get("content", "").strip()
            if not user_content:
                await websocket.send_json({
                    "type": "error",
                    "error": "Empty message",
                    "session_id": session_id,
                    "trace_id": message_context.trace_id,
                })
                continue
            
            logger.info(
                f"Received message in session {session_id}: {user_content[:50]}...",
                extra={
                    "trace_id": message_context.trace_id,
                    "session_id": session_id,
                    "message_length": len(user_content),
                }
            )
            
            # Stream AI response
            try:
                stream = await agent.chat(
                    session_id=session_id,
                    user_message=user_content,
                    stream=True
                )
                
                # Collect assistant response for memory recording
                assistant_response = ""
                
                async for chunk in stream:
                    # Add trace_id to each chunk
                    if isinstance(chunk, dict):
                        chunk["trace_id"] = message_context.trace_id
                        # Collect response content (type is "chunk" or "message")
                        if chunk.get("type") in ("chunk", "message") and "content" in chunk:
                            assistant_response += chunk.get("content", "")
                    await websocket.send_json(chunk)
                    
                    # Small delay to prevent overwhelming the client
                    await asyncio.sleep(0.01)
                
                # Record important conversation (async, non-blocking)
                if assistant_response:
                    asyncio.create_task(
                        record_if_important(user_content, assistant_response, session_id)
                    )
                    
            except Exception as e:
                logger.error(
                    f"Streaming error: {e}",
                    extra={
                        "trace_id": message_context.trace_id,
                        "session_id": session_id,
                        "error_type": type(e).__name__,
                    }
                )
                await websocket.send_json({
                    "type": "error",
                    "error": str(e),
                    "session_id": session_id,
                    "trace_id": message_context.trace_id,
                })
            finally:
                # Complete child context
                message_context.complete()
            
    except WebSocketDisconnect:
        logger.info(
            f"Client disconnected from session {session_id}",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "elapsed_ms": context.elapsed_ms,
            }
        )
    except Exception as e:
        logger.error(
            f"WebSocket error: {e}",
            extra={
                "trace_id": trace_id,
                "session_id": session_id,
                "error_type": type(e).__name__,
            }
        )
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        # Complete and clear context
        context.complete()
        clear_current_context()
