"""WebSocket endpoint for real-time chat with distributed tracing."""

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.agent import Agent
from ..core.context import AgentContext, ContextSource, set_current_context, clear_current_context, get_current_context
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
                
                async for chunk in stream:
                    # Add trace_id to each chunk
                    if isinstance(chunk, dict):
                        chunk["trace_id"] = message_context.trace_id
                    await websocket.send_json(chunk)
                    
                    # Small delay to prevent overwhelming the client
                    await asyncio.sleep(0.01)
                    
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
