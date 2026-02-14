"""Error handling middleware with unified response format.

Provides consistent error responses across all API endpoints.
"""

import traceback
from typing import Any, Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ...core.context import get_current_context
from ...utils.logger import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base API error with status code and details."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or f"ERR_{status_code}"
        self.details = details or {}


class BadRequestError(APIError):
    """400 Bad Request error."""
    
    def __init__(self, message: str = "Bad request", details: Optional[dict] = None) -> None:
        super().__init__(message, status_code=400, error_code="ERR_BAD_REQUEST", details=details)


class NotFoundError(APIError):
    """404 Not Found error."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None) -> None:
        super().__init__(message, status_code=404, error_code="ERR_NOT_FOUND", details=details)


class InternalServerError(APIError):
    """500 Internal Server Error."""
    
    def __init__(self, message: str = "Internal server error", details: Optional[dict] = None) -> None:
        super().__init__(message, status_code=500, error_code="ERR_INTERNAL", details=details)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Middleware that catches exceptions and returns unified error responses.
    
    Response format:
    {
        "success": false,
        "error": {
            "code": "ERR_XXX",
            "message": "Error description",
            "details": {...}
        },
        "trace_id": "xxx"
    }
    """
    
    def __init__(
        self,
        app: ASGIApp,
        *,
        include_traceback: bool = False,
    ) -> None:
        super().__init__(app)
        self.include_traceback = include_traceback
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with error handling."""
        try:
            return await call_next(request)
        
        except APIError as e:
            return self._create_error_response(e)
        
        except ValidationError as e:
            # Pydantic validation errors
            error = BadRequestError(
                message="Validation error",
                details={"errors": e.errors()},
            )
            return self._create_error_response(error)
        
        except Exception as e:
            # Unexpected errors
            ctx = get_current_context()
            trace_id = ctx.trace_id if ctx else None
            
            logger.exception(
                "Unhandled exception",
                extra={"trace_id": trace_id, "error_type": type(e).__name__},
            )
            
            details = {"type": type(e).__name__}
            if self.include_traceback:
                details["traceback"] = traceback.format_exc()
            
            error = InternalServerError(
                message=str(e) if self.include_traceback else "An unexpected error occurred",
                details=details,
            )
            error.trace_id = trace_id  # type: ignore
            return self._create_error_response(error)
    
    def _create_error_response(self, error: APIError) -> JSONResponse:
        """Create a standardized error response."""
        ctx = get_current_context()
        trace_id = getattr(error, "trace_id", None) or (ctx.trace_id if ctx else None)
        
        response_body: dict[str, Any] = {
            "success": False,
            "error": {
                "code": error.error_code,
                "message": error.message,
            },
        }
        
        if error.details:
            response_body["error"]["details"] = error.details
        
        if trace_id:
            response_body["trace_id"] = trace_id
        
        return JSONResponse(
            status_code=error.status_code,
            content=response_body,
        )


# Success response helper
def success_response(
    data: Any,
    message: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """Create a standardized success response.
    
    Response format:
    {
        "success": true,
        "data": {...},
        "message": "...",  // optional
        "metadata": {...}  // optional
    }
    """
    response: dict[str, Any] = {
        "success": True,
        "data": data,
    }
    
    if message:
        response["message"] = message
    
    if metadata:
        response["metadata"] = metadata
    
    return response
