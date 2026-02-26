"""WebSocket endpoint for real-time chat with distributed tracing.

Supports event types:
- chunk: Streaming text chunk
- message: Complete message
- thinking: LLM reasoning step (new)
- tool_call: Tool being called (new)
- tool_result: Tool execution result (new)
- error: Error occurred
- pong: Heartbeat response
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..core.agent import Agent
from ..core.context import AgentContext, ContextSource, set_current_context, clear_current_context, get_current_context
from ..memory.md_sync import get_md_sync
from ..services.smart_memory import get_smart_memory_service
from ..tools.manager import ToolManager
from ..utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# Global agent instance
_agent: Agent | None = None


async def send_system_message(
    websocket: WebSocket,
    session_id: str,
    trace_id: str,
    log_type: str,
    log_data: dict,
) -> None:
    """Send a system log message to the client.
    
    System messages are used for CLI commands, tool executions, errors, etc.
    They are displayed separately from user and assistant messages.
    
    Args:
        websocket: WebSocket connection
        session_id: Session ID
        trace_id: Trace ID for distributed tracing
        log_type: Type of log (cli_command, tool_execution, error, info)
        log_data: Log data including command, output, error, duration, etc.
    """
    try:
        await websocket.send_json({
            "type": "system",
            "session_id": session_id,
            "trace_id": trace_id,
            "log_type": log_type,
            "log_data": log_data,
        })
    except Exception as e:
        logger.error(
            f"Failed to send system message: {e}",
            extra={"trace_id": trace_id, "session_id": session_id}
        )


def get_agent() -> Agent:
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


async def smart_record_conversation(
    user_message: str,
    assistant_message: str,
    session_id: str,
) -> dict:
    """Use LLM to analyze and record conversation if important.
    
    This is the unified entry point for memory recording that:
    - Uses LLM to determine if content should be recorded
    - Extracts and updates identity information
    - Avoids duplicate processing
    
    Args:
        user_message: User's message
        assistant_message: Assistant's response
        session_id: Session ID
        
    Returns:
        Dict with recording results
    """
    try:
        from pathlib import Path
        from ..services.llm.router import LLMRouter
        from ..config.manager import ConfigManager
        
        config = ConfigManager().config
        
        # Resolve workspace path to absolute path
        backend_dir = Path(__file__).parent.parent.parent
        workspace_path = (backend_dir / config.workspace.path).resolve()
        
        llm_router = LLMRouter(config.models)
        md_sync = get_md_sync(str(workspace_path))
        
        service = get_smart_memory_service(llm_router, str(workspace_path))
        
        result = await service.analyze_and_record(
            user_message=user_message,
            assistant_message=assistant_message,
            session_id=session_id,
            md_sync=md_sync
        )
        
        return result
        
    except Exception as e:
        logger.warning(
            "Failed to smart record conversation",
            extra={"error": str(e), "session_id": session_id}
        )
        return {"recorded": False, "skip_reason": str(e)}


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

            # Handle tool confirmation from client
            if message.get("type") == "tool_confirm":
                tool_call_id = message.get("tool_call_id")
                confirmation_id = message.get("confirmation_id")
                command = message.get("command")
                
                if tool_call_id or confirmation_id:
                    # Set confirmation in the terminal tool module
                    from ..tools.builtin.terminal import set_confirmation_confirmed
                    if confirmation_id:
                        set_confirmation_confirmed(confirmation_id)
                    
                    # Also store in agent context for backwards compatibility
                    if tool_call_id:
                        agent.set_tool_confirmation(tool_call_id, True)
                    
                    logger.info(
                        f"Tool confirmation received: confirmation_id={confirmation_id}, tool_call_id={tool_call_id}",
                        extra={
                            "trace_id": message_context.trace_id,
                            "tool_call_id": tool_call_id,
                            "confirmation_id": confirmation_id,
                        }
                    )
                    
                    # If command is provided, re-execute it with confirmation
                    if command and confirmation_id:
                        logger.info(
                            f"Re-executing confirmed command: {command}",
                            extra={
                                "trace_id": message_context.trace_id,
                                "confirmation_id": confirmation_id,
                                "command": command,
                            }
                        )
                        
                        # Execute the command with confirmation
                        try:
                            from ..tools.builtin import get_builtin_tools
                            tool_manager = ToolManager()
                            # Register built-in tools
                            for tool in get_builtin_tools():
                                tool_manager.register(tool)
                            
                            # Execute with confirmation
                            result = await tool_manager.execute("run_in_terminal", {
                                "command": command,
                                "confirmed": True,
                                "confirmation_id": confirmation_id,
                            })
                            
                            # Send tool_call event
                            await websocket.send_json({
                                "type": "tool_call",
                                "tool_call_id": f"confirmed_{confirmation_id}",
                                "name": "run_in_terminal",
                                "arguments": {"command": command},
                                "trace_id": message_context.trace_id,
                            })
                            
                            # Send tool_result event
                            await websocket.send_json({
                                "type": "tool_result",
                                "tool_call_id": f"confirmed_{confirmation_id}",
                                "tool_name": "run_in_terminal",
                                "success": result.success,
                                "output": result.output[:500] if result.output else "",
                                "error": result.error,
                                "result": {
                                    "success": result.success,
                                    "output": result.output,
                                    "error": result.error,
                                },
                                "trace_id": message_context.trace_id,
                            })
                            
                            # Now pass the result to LLM for continued processing
                            # Build a context message about what was executed
                            context_message = f"[用户已确认执行高危命令]\n命令: {command}\n执行结果: {'成功' if result.success else '失败'}"
                            if result.output:
                                context_message += f"\n输出: {result.output[:1000]}"
                            if result.error:
                                context_message += f"\n错误: {result.error}"
                            
                            # Call agent to process the confirmed command result
                            logger.info(
                                "Passing confirmed command result to LLM",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "command": command,
                                    "success": result.success,
                                }
                            )
                            
                            stream = await agent.chat(
                                session_id=session_id,
                                user_message=context_message,
                                stream=True
                            )
                            
                            # Stream LLM response
                            async for chunk in stream:
                                if isinstance(chunk, dict):
                                    chunk["trace_id"] = message_context.trace_id
                                    await websocket.send_json(chunk)
                                    await asyncio.sleep(0.01)
                            
                        except Exception as e:
                            logger.error(
                                f"Failed to execute confirmed command: {e}",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "command": command,
                                }
                            )
                            await websocket.send_json({
                                "type": "error",
                                "error": f"执行确认命令失败: {str(e)}",
                                "session_id": session_id,
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
                        
                        # 🔍 DEBUG: Log ALL chunks received from engine
                        chunk_type_debug = chunk.get("type")
                        if chunk_type_debug in ("problem_guidance", "error"):
                            logger.info(
                                "📥 WebSocket stream received chunk type",
                                extra={
                                    "chunk_type": chunk_type_debug,
                                    "chunk_keys": list(chunk.keys()),
                                    "has_session_id": "session_id" in chunk,
                                }
                            )
                        
                        # Debug: log the full chunk before sending
                        chunk_type = chunk.get("type")
                        
                        # Debug: log the full chunk before sending
                        chunk_type = chunk.get("type")
                        if chunk_type in ("tool_call", "tool_result", "awaiting_confirmation", "problem_guidance"):
                            logger.info(
                                "🚀 Sending chunk to frontend",
                                extra={
                                    "type": chunk_type,
                                    "tool_call_id": chunk.get("tool_call_id"),
                                    "tool_name": chunk.get("name") or chunk.get("tool_name"),
                                    "guidance_type": chunk.get("data", {}).get("type") if chunk_type == "problem_guidance" else None,
                                    "has_data": "data" in chunk if chunk_type == "problem_guidance" else None,
                                }
                            )
                        # Handle different event types
                        chunk_type = chunk.get("type")
                        
                        if chunk_type in ("chunk", "message") and "content" in chunk:
                            # Standard text response
                            assistant_response += chunk.get("content", "")
                        
                        elif chunk_type == "thinking":
                            # LLM reasoning - log and forward
                            logger.debug(
                                "LLM thinking",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "content": chunk.get("content", "")[:100],
                                }
                            )
                            
                            # Forward thinking event to frontend for UI feedback
                            await websocket.send_json(chunk)
                        
                        elif chunk_type == "tool_call":
                            # Tool call - log and forward
                            logger.info(
                                "Tool call",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "tool_name": chunk.get("name"),
                                    "tool_call_id": chunk.get("tool_call_id"),
                                    "arguments": chunk.get("arguments"),
                                }
                            )
                            
                            # Send system message for CLI command execution
                            tool_name = chunk.get("name")
                            tool_args = chunk.get("arguments", {})
                            if tool_name == "run_in_terminal":
                                command = tool_args.get("command", "")
                                await send_system_message(
                                    websocket=websocket,
                                    session_id=session_id,
                                    trace_id=message_context.trace_id,
                                    log_type="cli_command",
                                    log_data={
                                        "command": command,
                                        "status": "executing",
                                        "tool_call_id": chunk.get("tool_call_id"),
                                    }
                                )
                        
                        elif chunk_type == "tool_result":
                            # Tool result - log and forward
                            logger.info(
                                "Tool result",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "tool_name": chunk.get("tool_name"),
                                    "tool_call_id": chunk.get("tool_call_id"),
                                    "success": chunk.get("success"),
                                    "has_result": "result" in chunk,
                                    "result_requires_confirmation": chunk.get("result", {}).get("requires_confirmation") if chunk.get("result") else None,
                                }
                            )
                            
                            # Send system message for tool execution result
                            tool_call_id = chunk.get("tool_call_id")
                            success = chunk.get("success")
                            output = chunk.get("output", "")
                            error = chunk.get("error")
                            
                            await send_system_message(
                                websocket=websocket,
                                session_id=session_id,
                                trace_id=message_context.trace_id,
                                log_type="tool_execution",
                                log_data={
                                    "tool_call_id": tool_call_id,
                                    "success": success,
                                    "output": output[:1000] if output else None,
                                    "error": error,
                                    "duration_ms": None,  # TODO: Add timing info,
                                }
                            )
                        
                        
                        # 🔥 NEW: Handle problem_guidance events
                        elif chunk_type == "problem_guidance":
                            logger.info(
                                "🚀 WebSocket: Sending problem_guidance to frontend",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "guidance_type": chunk.get("data", {}).get("type"),
                                    "has_data": "data" in chunk,
                                    "session_id": session_id,
                                }
                            )
                            logger.info(
                                "🔍 DEBUG: About to send problem_guidance chunk",
                                extra={"chunk_keys": list(chunk.keys()), "chunk_type": chunk_type}
                            )
                            # Forward guidance event to frontend
                            await websocket.send_json(chunk)
                            logger.info(
                                "✅ DEBUG: problem_guidance sent successfully"
                            )
                        
                        elif chunk_type == "final_answer":
                            # Final answer from engine - this is the main response
                            logger.info(
                                "🚀 Sending final_answer to frontend",
                                extra={
                                    "trace_id": message_context.trace_id,
                                    "content_preview": str(chunk.get("content", ""))[:100],
                                    "session_id": session_id,
                                }
                            )
                            # Forward final answer to frontend
                            await websocket.send_json(chunk)
                            logger.info(
                                "✅ Final answer sent successfully"
                            )
                        
                        else:
                            # Default: forward any other dict chunks (only once!)
                            logger.debug(
                                "Forwarding default chunk",
                                extra={"chunk_type": chunk_type}
                            )
                            await websocket.send_json(chunk)
                    
                    else:
                        # Non-dict chunks are sent as-is
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
