"""Comprehensive error handling for X-Agent."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standard error codes for X-Agent."""
    # Configuration errors (1xxx)
    CONFIG_NOT_FOUND = "ERR_CONFIG_NOT_FOUND"
    CONFIG_INVALID = "ERR_CONFIG_INVALID"
    CONFIG_RELOAD_FAILED = "ERR_CONFIG_RELOAD_FAILED"
    
    # Model/LLM errors (2xxx)
    MODEL_NOT_FOUND = "ERR_MODEL_NOT_FOUND"
    MODEL_UNAVAILABLE = "ERR_MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "ERR_MODEL_TIMEOUT"
    MODEL_RATE_LIMITED = "ERR_MODEL_RATE_LIMITED"
    MODEL_AUTH_FAILED = "ERR_MODEL_AUTH_FAILED"
    
    # Session errors (3xxx)
    SESSION_NOT_FOUND = "ERR_SESSION_NOT_FOUND"
    SESSION_EXPIRED = "ERR_SESSION_EXPIRED"
    SESSION_INVALID = "ERR_SESSION_INVALID"
    
    # Message errors (4xxx)
    MESSAGE_EMPTY = "ERR_MESSAGE_EMPTY"
    MESSAGE_TOO_LONG = "ERR_MESSAGE_TOO_LONG"
    MESSAGE_INVALID = "ERR_MESSAGE_INVALID"
    
    # WebSocket errors (5xxx)
    WS_CONNECTION_FAILED = "ERR_WS_CONNECTION_FAILED"
    WS_NOT_CONNECTED = "ERR_WS_NOT_CONNECTED"
    WS_MESSAGE_INVALID = "ERR_WS_MESSAGE_INVALID"
    
    # General errors (9xxx)
    INTERNAL = "ERR_INTERNAL"
    VALIDATION = "ERR_VALIDATION"
    NOT_FOUND = "ERR_NOT_FOUND"
    RATE_LIMITED = "ERR_RATE_LIMITED"
    TIMEOUT = "ERR_TIMEOUT"


class XAgentError(Exception):
    """Base exception for X-Agent errors."""
    
    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)
    
    def to_dict(self) -> dict:
        """Convert error to dictionary for API response."""
        return {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            },
        }


class ConfigError(XAgentError):
    """Configuration-related errors."""
    pass


class ModelError(XAgentError):
    """Model/LLM-related errors."""
    pass


class SessionError(XAgentError):
    """Session-related errors."""
    pass


class MessageError(XAgentError):
    """Message-related errors."""
    pass


class WebSocketError(XAgentError):
    """WebSocket-related errors."""
    pass


class ValidationError(XAgentError):
    """Validation errors."""
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
    ) -> None:
        details = {}
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate for safety
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION,
            details=details,
        )


class RateLimitError(XAgentError):
    """Rate limit errors."""
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
    ) -> None:
        details = {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(
            message=message,
            code=ErrorCode.RATE_LIMITED,
            details=details,
        )


class TimeoutError(XAgentError):
    """Timeout errors."""
    def __init__(
        self,
        message: str = "Request timed out",
        timeout_seconds: Optional[float] = None,
    ) -> None:
        details = {}
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=message,
            code=ErrorCode.TIMEOUT,
            details=details,
        )


class ErrorResponse(BaseModel):
    """Standard error response model."""
    success: bool = False
    error: dict[str, Any]
    trace_id: Optional[str] = None
