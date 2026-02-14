"""Request/Response tracing middleware.

Adds trace IDs to all requests for distributed tracing and debugging.
"""

import time
import uuid
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...core.context import ContextSource, AgentContext, set_current_context, clear_current_context
from ...utils.logger import get_logger

logger = get_logger(__name__)

# Header names
TRACE_ID_HEADER = "X-Trace-ID"
REQUEST_ID_HEADER = "X-Request-ID"


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware that adds tracing headers and context to requests.
    
    - Generates or propagates trace IDs
    - Generates request IDs
    - Sets up request-scoped context
    - Logs request/response timing
    """
    
    def __init__(
        self,
        app: ASGIApp,
        *,
        trace_id_header: str = TRACE_ID_HEADER,
        request_id_header: str = REQUEST_ID_HEADER,
    ) -> None:
        super().__init__(app)
        self.trace_id_header = trace_id_header
        self.request_id_header = request_id_header
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with tracing."""
        # Get or generate trace ID
        trace_id = request.headers.get(self.trace_id_header) or str(uuid.uuid4())
        request_id = str(uuid.uuid4())[:8]
        
        # Get session ID from path params or query
        session_id: Optional[str] = None
        if "session_id" in request.path_params:
            session_id = request.path_params["session_id"]
        elif "session_id" in request.query_params:
            session_id = request.query_params["session_id"]
        
        # Create context
        context = AgentContext(
            trace_id=trace_id,
            request_id=request_id,
            session_id=session_id,
            source=ContextSource.REST_API,
            metadata={
                "method": request.method,
                "path": request.url.path,
                "client_host": request.client.host if request.client else None,
            },
        )
        
        # Set current context for logging
        set_current_context(context)
        
        # Log request start
        start_time = time.time()
        logger.info(
            "Request started",
            extra={
                "trace_id": trace_id,
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add tracing headers to response
            response.headers[self.trace_id_header] = trace_id
            response.headers[self.request_id_header] = request_id
            
            # Log request completion
            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "Request completed",
                extra={
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "elapsed_ms": round(elapsed_ms, 2),
                },
            )
            
            # Add timing header
            response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
            
            return response
            
        finally:
            context.complete()
            clear_current_context()
