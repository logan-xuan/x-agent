"""Developer mode API endpoints for debugging and prompt testing."""

import asyncio
import json
import subprocess
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from ...config.manager import ConfigManager
from ...conversation.context import get_current_context, set_current_context as set_context, AgentContext
from ...conversation.identity import ChannelProtocol, ChannelType
from ...gateway.dispatcher import GatewayDispatcher
from ...gateway.envelope import Envelope
from ...runtime.types import TurnResult
from ...services.llm.router import LLMRouter
from ...tools.builtin import AliyunWebSearchTool
from ...utils.logger import get_logger

router = APIRouter(prefix="/dev", tags=["developer"])
logger = get_logger(__name__)

# Path to prompt log file
PROMPT_LOG_PATH = Path(__file__).parent.parent.parent.parent / "logs" / "prompt-llm.log"

# Path to backend root (for running tests)
BACKEND_ROOT = Path(__file__).parent.parent.parent.parent


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


class RuntimeTurnDebugRequest(BaseModel):
    """Debug request for exercising the runtime turn bridge over HTTP."""

    content: str
    session_id: str = "dev-runtime-session"
    channel_type: str = "web_chat"
    channel_protocol: str = "rest_api"
    agent_id: str | None = None
    agent_name: str | None = None
    runtime_timeout_ms: int | None = Field(default=30000, ge=1)
    runtime_max_tokens: int | None = Field(default=None, ge=1)
    runtime_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    runtime_force_non_streaming: bool = False
    timeout_fallback_mode: Literal["abort", "final"] = "abort"
    disable_tools: bool = False
    disable_skills: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeTurnDebugResponse(BaseModel):
    """Debug response for the runtime turn bridge endpoint."""

    session_id: str
    kind: str
    finish_reason: str | None = None
    output_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMStreamProbeRequest(BaseModel):
    """Debug request for measuring provider streaming latency."""

    content: str
    system_prompt: str | None = None
    base_url_override: str | None = None
    max_tokens: int = Field(default=64, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_ms: int = Field(default=10000, ge=1)
    attempts: int = Field(default=1, ge=1, le=5)


class LLMStreamProbeResponse(BaseModel):
    """Measured provider streaming timings for a single probe."""

    create_stream_ms: int
    first_chunk_ms: int | None = None
    done_ms: int | None = None
    timed_out: bool = False
    chunk_count: int = 0
    content_preview: str = ""
    error: str | None = None
    samples: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _get_shared_llm_router() -> LLMRouter:
    """Resolve the application-scoped LLMRouter when available."""
    from ...main import get_llm_router

    return get_llm_router()


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
                # Parse the outer JSON object
                outer_entry = json.loads(line)

                # Extract the actual log data from the 'message' field which contains JSON string
                message_content = outer_entry.get("message", "")

                # Parse the inner JSON string to get the actual log data
                if isinstance(message_content, str) and message_content.startswith('{'):
                    try:
                        inner_entry = json.loads(message_content)

                        # Combine the outer and inner entries, with inner taking precedence for core fields
                        # Keep outer metadata but prioritize inner log data
                        combined_entry = {**outer_entry, **inner_entry}

                        # Remove the original 'message' field since we've parsed its contents
                        if 'message' in combined_entry:
                            del combined_entry['message']

                        logs.append(combined_entry)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse inner JSON from message field",
                                     extra={"line_start": line[:100]})
                        # If we can't parse the inner JSON, use the outer object as fallback
                        logs.append(outer_entry)
                else:
                    # If message field is not a JSON string, use the outer object
                    logs.append(outer_entry)

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


def _parse_channel_type(value: str) -> ChannelType:
    try:
        return ChannelType(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported channel_type: {value}",
        ) from exc


def _parse_channel_protocol(value: str) -> ChannelProtocol:
    try:
        return ChannelProtocol(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported channel_protocol: {value}",
        ) from exc


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


@router.post("/runtime-turn", response_model=RuntimeTurnDebugResponse)
async def debug_runtime_turn(request: RuntimeTurnDebugRequest) -> RuntimeTurnDebugResponse:
    """Execute the experimental runtime bridge over HTTP without changing the default chat path."""
    channel_type = _parse_channel_type(request.channel_type)
    channel_protocol = _parse_channel_protocol(request.channel_protocol)
    metadata = dict(request.metadata)
    if request.runtime_timeout_ms is not None:
        metadata["runtime_timeout_ms"] = request.runtime_timeout_ms
    if request.runtime_max_tokens is not None:
        metadata["runtime_max_tokens"] = request.runtime_max_tokens
    if request.runtime_temperature is not None:
        metadata["runtime_temperature"] = request.runtime_temperature
    if request.runtime_force_non_streaming:
        metadata["runtime_force_non_streaming"] = True
    metadata["runtime_timeout_fallback_mode"] = request.timeout_fallback_mode
    if request.disable_tools:
        metadata["runtime_disable_tools"] = True
        metadata["runtime_disable_skills"] = True
        metadata["runtime_skip_history_load"] = True
        metadata["persist_user_message"] = False
    if request.disable_skills:
        metadata["runtime_disable_skills"] = True
    envelope = Envelope.create_chat(
        content=request.content,
        session_id=request.session_id,
        channel_type=channel_type,
        channel_protocol=channel_protocol,
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        metadata=metadata,
    )
    dispatcher = GatewayDispatcher()
    result: TurnResult = await dispatcher.execute_runtime_turn(
        envelope,
        metadata=metadata,
    )
    return RuntimeTurnDebugResponse(
        session_id=request.session_id,
        kind=result.kind,
        finish_reason=result.finish_reason,
        output_text=result.output_text,
        metadata=dict(result.metadata),
    )


@router.post("/llm-stream-probe", response_model=LLMStreamProbeResponse)
async def debug_llm_stream_probe(request: LLMStreamProbeRequest) -> LLMStreamProbeResponse:
    """Measure shared-provider streaming timings without going through the full agent loop."""
    messages: list[dict[str, str]] = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.content})

    samples: list[dict[str, Any]] = []
    for _ in range(request.attempts):
        samples.append(
            await _run_llm_stream_probe_once(
                router=_get_shared_llm_router() if request.base_url_override is None else None,
                messages=messages,
                base_url_override=request.base_url_override,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                timeout_ms=request.timeout_ms,
            )
        )

    last = samples[-1]

    return LLMStreamProbeResponse(
        create_stream_ms=last["create_stream_ms"],
        first_chunk_ms=last["first_chunk_ms"],
        done_ms=last["done_ms"],
        timed_out=last["timed_out"],
        chunk_count=last["chunk_count"],
        content_preview=last["content_preview"],
        error=last["error"],
        samples=samples,
        metadata={
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "base_url_override": request.base_url_override,
            "message_count": len(messages),
            "attempts": request.attempts,
        },
    )


async def _run_llm_stream_probe_once(
    *,
    router: LLMRouter | None,
    messages: list[dict[str, str]],
    base_url_override: str | None,
    max_tokens: int,
    temperature: float | None,
    timeout_ms: int,
) -> dict[str, Any]:
    """Run a single streaming probe attempt against the shared router."""
    started_at = time.monotonic()
    first_chunk_ms: int | None = None
    chunk_count = 0
    content_parts: list[str] = []
    timed_out = False
    done_ms: int | None = None
    error: str | None = None
    stream = None

    try:
        if base_url_override is not None:
            stream = await _probe_with_base_url_override(
                base_url_override=base_url_override,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            assert router is not None
            stream = await router.chat(
                messages,
                stream=True,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        create_stream_ms = int((time.monotonic() - started_at) * 1000)
    except Exception as exc:
        return {
            "create_stream_ms": int((time.monotonic() - started_at) * 1000),
            "first_chunk_ms": None,
            "done_ms": None,
            "timed_out": False,
            "chunk_count": 0,
            "content_preview": "",
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        async with asyncio.timeout(timeout_ms / 1000):
            async for chunk in stream:
                if chunk.content:
                    chunk_count += 1
                    content_parts.append(chunk.content)
                    if first_chunk_ms is None:
                        first_chunk_ms = int((time.monotonic() - started_at) * 1000)
                if chunk.is_finished:
                    done_ms = int((time.monotonic() - started_at) * 1000)
                    break
    except TimeoutError:
        timed_out = True
    finally:
        aclose = getattr(stream, "aclose", None) if stream is not None else None
        if callable(aclose):
            await aclose()

    if done_ms is None and not timed_out:
        done_ms = int((time.monotonic() - started_at) * 1000)

    return {
        "create_stream_ms": create_stream_ms,
        "first_chunk_ms": first_chunk_ms,
        "done_ms": done_ms,
        "timed_out": timed_out,
        "chunk_count": chunk_count,
        "content_preview": "".join(content_parts)[:200],
        "error": error,
    }


async def _probe_with_base_url_override(
    *,
    base_url_override: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float | None,
):
    """Create a temporary OpenAI-compatible client for direct base_url probing."""
    config = ConfigManager().config.models[0]
    api_key = (
        config.api_key.get_secret_value()
        if hasattr(config.api_key, "get_secret_value")
        else str(config.api_key)
    )
    client = AsyncOpenAI(api_key=api_key, base_url=base_url_override)
    return await client.chat.completions.create(
        model=config.model_id,
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature,
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


# =============================================================================
# Compression Test APIs
# =============================================================================

class CompressionTestRequest(BaseModel):
    """Compression test request model."""
    test_type: str  # "token_counter" | "compressor"


class CompressionTestResponse(BaseModel):
    """Compression test response model."""
    success: bool
    test_type: str
    output: str
    duration_ms: int
    error: str | None = None


@router.post("/compression-test", response_model=CompressionTestResponse)
async def run_compression_test(request: CompressionTestRequest) -> CompressionTestResponse:
    """Run compression-related unit tests.
    
    Args:
        request: Test request with test_type ("token_counter" or "compressor")
        
    Returns:
        Test execution results with output
    """
    start_time = time.time()
    
    # Validate test type
    valid_tests = ["token_counter", "compressor"]
    if request.test_type not in valid_tests:
        return CompressionTestResponse(
            success=False,
            test_type=request.test_type,
            output="",
            duration_ms=0,
            error=f"Invalid test type. Must be one of: {', '.join(valid_tests)}"
        )
    
    # Map test type to test file
    test_files = {
        "token_counter": "tests/unit/test_token_counter.py",
        "compressor": "tests/unit/test_compressor.py",
    }
    
    test_file = test_files[request.test_type]
    test_path = BACKEND_ROOT / test_file
    
    # Check if test file exists
    if not test_path.exists():
        return CompressionTestResponse(
            success=False,
            test_type=request.test_type,
            output="",
            duration_ms=0,
            error=f"Test file not found: {test_file}"
        )
    
    try:
        # Run pytest with verbose output
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_path), "-v"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\n\n=== STDERR ===\n" + result.stderr
        
        return CompressionTestResponse(
            success=result.returncode == 0,
            test_type=request.test_type,
            output=output,
            duration_ms=duration_ms,
            error=None if result.returncode == 0 else f"Tests failed with exit code {result.returncode}"
        )
        
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        return CompressionTestResponse(
            success=False,
            test_type=request.test_type,
            output="",
            duration_ms=duration_ms,
            error="Test execution timed out (60s)"
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Compression test failed", extra={"error": str(e), "test_type": request.test_type})
        return CompressionTestResponse(
            success=False,
            test_type=request.test_type,
            output="",
            duration_ms=duration_ms,
            error=f"Failed to run tests: {str(e)}"
        )


@router.get("/compression-test/list")
async def list_compression_tests() -> dict[str, Any]:
    """List available compression tests.

    Returns:
        List of available test types
    """
    return {
        "tests": [
            {
                "id": "token_counter",
                "name": "Token计数器测试",
                "description": "测试TokenCounter的计数准确性，包括中英文、边界条件",
                "file": "tests/unit/test_token_counter.py"
            },
            {
                "id": "compressor",
                "name": "压缩器测试",
                "description": "测试ContextCompressor的压缩逻辑、消息列表构建",
                "file": "tests/unit/test_compressor.py"
            }
        ]
    }


# =============================================================================
# Compression Record Query APIs
# =============================================================================

class CompressionRecordQueryResponse(BaseModel):
    """Compression record query response model."""
    records: list[dict]
    total: int


# =============================================================================
# Compression Record Query APIs
# =============================================================================

from typing import Any, Dict, List
from pydantic import BaseModel
from fastapi import Query
from sqlalchemy import select
import json
from datetime import datetime

from ...models.compression import CompressionEvent
from ...services.storage import get_storage_service


class CompressionRecord(BaseModel):
    """Individual compression record."""
    id: str
    sessionId: str
    originalMessageCount: int
    compressedMessageCount: int
    originalTokenCount: int
    compressedTokenCount: int
    compressionRatio: float
    compressionTime: str
    originalMessages: List[Dict[str, Any]]
    compressedMessages: List[Dict[str, Any]]


class CompressionRecordQueryResponse(BaseModel):
    """Compression record query response model."""
    records: List[CompressionRecord]
    total: int


@router.get("/compression-records", response_model=CompressionRecordQueryResponse)
async def query_compression_records(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> CompressionRecordQueryResponse:
    """Query compression history records.

    Args:
        limit: Maximum number of records to return (default: 20, max: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        List of compression records with pagination info
    """
    storage = get_storage_service()

    async with storage.session() as db:
        # Query compression events with pagination
        result = await db.execute(
            select(CompressionEvent)
            .order_by(CompressionEvent.compression_time.desc())
            .offset(offset)
            .limit(limit)
        )
        events = result.scalars().all()

        # Count total records for pagination
        count_result = await db.execute(select(CompressionEvent))
        total = len(count_result.scalars().all())

        # Convert to response format
        records = []
        for event in events:
            try:
                original_messages = json.loads(event.original_messages) if event.original_messages else []
                compressed_messages = json.loads(event.compressed_messages) if event.compressed_messages else []
            except json.JSONDecodeError:
                # If JSON parsing fails, use empty arrays
                original_messages = []
                compressed_messages = []

            record = CompressionRecord(
                id=event.id,
                sessionId=event.session_id,
                originalMessageCount=event.original_message_count,
                compressedMessageCount=event.compressed_message_count,
                originalTokenCount=event.original_token_count,
                compressedTokenCount=event.compressed_token_count,
                compressionRatio=event.compression_ratio,
                compressionTime=event.compression_time.isoformat() if event.compression_time else "",
                originalMessages=original_messages,
                compressedMessages=compressed_messages
            )
            records.append(record)

    return CompressionRecordQueryResponse(
        records=records,
        total=total
    )


# ============ Web Search Debugging Endpoint (Aliyun OpenSearch) ============


class WebSearchRequest(BaseModel):
    """Web search request model."""
    query: str
    max_results: int = 5


class WebSearchResult(BaseModel):
    """Web search result item."""
    title: str
    snippet: str
    url: str


class WebSearchResponse(BaseModel):
    """Web search response model."""
    success: bool
    query: str
    results: list[WebSearchResult]
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/web-search", response_model=WebSearchResponse)
async def web_search_debug(request: WebSearchRequest) -> WebSearchResponse:
    """Test web search functionality (Aliyun OpenSearch).
    
    Args:
        request: Web search request with query and max_results
        
    Returns:
        Web search results with raw and formatted output
    """
    try:
        # Create web search tool instance (Aliyun OpenSearch)
        tool = AliyunWebSearchTool()
        
        # Execute search
        result = await tool.execute(
            query=request.query,
            max_results=request.max_results
        )
        
        # Parse results from formatted output
        parsed_results = []
        if result.success and result.output:
            # Try to extract structured data from formatted output
            lines = result.output.split('\n')
            current_result = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    if current_result:
                        parsed_results.append(WebSearchResult(**current_result))
                        current_result = {}
                    continue
                
                if line.startswith('🔍') or line.startswith('Search results for:') or line.startswith('No results'):
                    continue
                
                # Parse numbered results
                if '.' in line and '**' in line:
                    # Title line
                    title = line.split('**')[1] if '**' in line else line
                    current_result['title'] = title.replace('**', '')
                elif line.startswith('🔗') or line.startswith('URL:'):
                    current_result['url'] = line.replace('🔗', '').replace('URL:', '').strip()
                elif not line.startswith(str(range(10))) and 'title' in current_result:
                    # Snippet line
                    current_result['snippet'] = line
            
            # Add last result if exists
            if current_result and 'title' in current_result:
                if 'snippet' not in current_result:
                    current_result['snippet'] = ''
                if 'url' not in current_result:
                    current_result['url'] = ''
                parsed_results.append(WebSearchResult(**current_result))
        
        return WebSearchResponse(
            success=result.success,
            query=request.query,
            results=parsed_results,
            output=result.output,
            error=result.error,
            metadata=result.metadata
        )
        
    except Exception as e:
        logger.error(
            "Web search debug failed",
            extra={"query": request.query, "error": str(e)}
        )
        return WebSearchResponse(
            success=False,
            query=request.query,
            results=[],
            error=str(e)
        )
