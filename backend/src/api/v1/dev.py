"""Developer mode API endpoints for debugging and prompt testing."""

import json
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...config.manager import ConfigManager
from ...core.context import get_current_context, set_current_context as set_context, AgentContext
from ...services.llm.router import LLMRouter
from ...utils.logger import get_logger

router = APIRouter(prefix="/dev", tags=["developer"])
logger = get_logger(__name__)

# Path to prompt log file
PROMPT_LOG_PATH = Path(__file__).parent.parent.parent.parent / "logs" / "prompt-llm.log"


class PromptTestRequest(BaseModel):
    """Prompt test request model."""
    messages: list[dict[str, str]]
    stream: bool = False
    system_prompt: str | None = None


class PromptTestResponse(BaseModel):
    """Prompt test response model."""
    content: str
    model: str
    provider: str
    latency_ms: int
    token_usage: dict[str, int] | None = None


class PromptLogEntry(BaseModel):
    """Prompt log entry model."""
    timestamp: str
    session_id: str | None
    trace_id: str | None
    provider: str
    model: str
    latency_ms: int
    success: bool
    request: dict[str, Any]
    response: str
    token_usage: dict[str, int] | None = None
    error: str | None = None


class PromptLogsResponse(BaseModel):
    """Prompt logs response model."""
    logs: list[PromptLogEntry]
    total: int


def _read_prompt_logs(limit: int = 20) -> list[dict[str, Any]]:
    """Read the last N lines from prompt log file.
    
    Args:
        limit: Maximum number of log entries to return
        
    Returns:
        List of parsed log entries
    """
    logs = []
    
    if not PROMPT_LOG_PATH.exists():
        logger.warning("Prompt log file not found", extra={"path": str(PROMPT_LOG_PATH)})
        return logs
    
    try:
        # Read all lines and parse JSON
        with open(PROMPT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Parse last N lines (most recent first)
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                logs.append(entry)
            except json.JSONDecodeError:
                logger.warning("Failed to parse log entry", extra={"line": line[:100]})
                continue
                
    except Exception as e:
        logger.error("Error reading prompt logs", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read prompt logs: {str(e)}"
        )
    
    return logs


@router.get("/prompt-logs", response_model=PromptLogsResponse)
async def get_prompt_logs(limit: int = 20) -> PromptLogsResponse:
    """Get recent prompt interaction logs.
    
    Args:
        limit: Maximum number of log entries to return (default: 20)
        
    Returns:
        List of prompt log entries
    """
    logs = _read_prompt_logs(limit=limit)
    
    # Convert to response model
    entries = []
    for log in logs:
        entry = PromptLogEntry(
            timestamp=log.get("timestamp", ""),
            session_id=log.get("session_id"),
            trace_id=log.get("trace_id"),
            provider=log.get("provider", "unknown"),
            model=log.get("model", "unknown"),
            latency_ms=log.get("latency_ms", 0),
            success=log.get("success", False),
            request=log.get("request", {}),
            response=log.get("response", ""),
            token_usage=log.get("token_usage"),
            error=log.get("error"),
        )
        entries.append(entry)
    
    return PromptLogsResponse(logs=entries, total=len(entries))


@router.post("/prompt-test", response_model=PromptTestResponse)
async def test_prompt(request: PromptTestRequest) -> PromptTestResponse:
    """Test a prompt directly with the primary LLM.
    
    Args:
        request: Prompt test request with messages and optional system prompt
        
    Returns:
        LLM response with metadata
    """
    start_time = time.time()
    
    try:
        # Initialize LLM router
        router = LLMRouter()
        
        if not router.primary:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No primary LLM provider available"
            )
        
        # Build messages
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)
        
        # Set up context for logging
        ctx = AgentContext()
        set_context(ctx)
        
        # Call LLM (non-streaming for simplicity)
        response = await router.chat(
            messages=messages,
            stream=False,
            session_id="dev-test",
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        return PromptTestResponse(
            content=response.content,
            model=router.primary.model_id,
            provider=router.primary.name,
            latency_ms=latency_ms,
            token_usage=response.usage,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Prompt test failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt test failed: {str(e)}"
        )


@router.post("/prompt-test/stream")
async def test_prompt_stream(request: PromptTestRequest) -> StreamingResponse:
    """Test a prompt with streaming response.
    
    Args:
        request: Prompt test request with messages and optional system prompt
        
    Returns:
        Streaming response with SSE format
    """
    async def generate() -> AsyncGenerator[str, None]:
        start_time = time.time()
        
        try:
            # Initialize LLM router
            router = LLMRouter()
            
            if not router.primary:
                yield f"data: {json.dumps({'error': 'No primary LLM provider available'})}\n\n"
                return
            
            # Build messages
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.extend(request.messages)
            
            # Set up context for logging
            ctx = AgentContext()
            set_context(ctx)
            
            # Call LLM with streaming
            stream = await router.chat(
                messages=messages,
                stream=True,
                session_id="dev-test",
            )
            
            full_content = ""
            async for chunk in stream:
                full_content += chunk.content
                data = {
                    "type": "chunk",
                    "content": chunk.content,
                    "model": chunk.model or router.primary.model_id,
                }
                yield f"data: {json.dumps(data)}\n\n"
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Send final message with metadata
            final_data = {
                "type": "done",
                "content": full_content,
                "model": router.primary.model_id,
                "provider": router.primary.name,
                "latency_ms": latency_ms,
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
        except Exception as e:
            logger.error("Streaming prompt test failed", extra={"error": str(e)})
            error_data = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
