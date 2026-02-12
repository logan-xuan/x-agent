"""
API response and error handling utilities for the x-agent2 AI assistant system.

This module provides standardized API responses and comprehensive error handling
across all system components.
"""

from typing import Any, Dict, Optional, Union
from enum import Enum
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from datetime import datetime
import traceback
import logging

# Set up logging for this module
logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Enumeration of standard error codes for the system."""

    # Generic errors
    GENERAL_ERROR = "GENERAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"

    # System-specific errors
    SESSION_EXPIRED = "SESSION_EXPIRED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    LLM_CONNECTION_FAILED = "LLM_CONNECTION_FAILED"
    DATABASE_CONNECTION_FAILED = "DATABASE_CONNECTION_FAILED"
    MEMORY_RETRIEVAL_FAILED = "MEMORY_RETRIEVAL_FAILED"

    # Input/output errors
    INVALID_INPUT_FORMAT = "INVALID_INPUT_FORMAT"
    FILE_UPLOAD_FAILED = "FILE_UPLOAD_FAILED"
    FILE_DOWNLOAD_FAILED = "FILE_DOWNLOAD_FAILED"


class APIResponse:
    """Standardized API response builder."""

    @staticmethod
    def success(
        data: Any = None,
        message: str = "Success",
        status_code: int = 200,
        metadata: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Create a success response.

        Args:
            data: Response data
            message: Success message
            status_code: HTTP status code
            metadata: Additional metadata

        Returns:
            JSONResponse with success structure
        """
        response_body = {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": status_code
        }

        if metadata:
            response_body["metadata"] = metadata

        return JSONResponse(content=response_body, status_code=status_code)

    @staticmethod
    def error(
        message: str = "An error occurred",
        error_code: Optional[ErrorCode] = None,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """
        Create an error response.

        Args:
            message: Error message
            error_code: Standard error code
            status_code: HTTP status code
            details: Additional error details
            metadata: Additional metadata

        Returns:
            JSONResponse with error structure
        """
        response_body = {
            "success": False,
            "message": message,
            "error_code": error_code.value if error_code else "UNKNOWN_ERROR",
            "timestamp": datetime.utcnow().isoformat(),
            "status_code": status_code
        }

        if details:
            response_body["details"] = details
        if metadata:
            response_body["metadata"] = metadata

        return JSONResponse(content=response_body, status_code=status_code)


class APIExceptionHandler:
    """Centralized exception handler for API endpoints."""

    @staticmethod
    def handle_validation_error(exc: Exception, field: str = None) -> JSONResponse:
        """Handle validation errors."""
        error_details = {
            "type": "ValidationError",
            "message": str(exc),
            "field": field or "unknown"
        }

        logger.warning(f"Validation error: {str(exc)}", extra={"field": field})

        return APIResponse.error(
            message="Validation failed",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=error_details
        )

    @staticmethod
    def handle_not_found(resource_type: str, resource_id: str = None) -> JSONResponse:
        """Handle resource not found errors."""
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} with ID '{resource_id}' not found"

        error_details = {
            "resource_type": resource_type,
            "resource_id": resource_id
        }

        logger.info(f"Resource not found: {message}")

        return APIResponse.error(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details=error_details
        )

    @staticmethod
    def handle_conflict(message: str, resource_type: str = None) -> JSONResponse:
        """Handle resource conflict errors."""
        error_details = {
            "type": "ConflictError",
            "message": message,
            "resource_type": resource_type
        }

        logger.warning(f"Resource conflict: {message}")

        return APIResponse.error(
            message=message,
            error_code=ErrorCode.RESOURCE_CONFLICT,
            status_code=status.HTTP_409_CONFLICT,
            details=error_details
        )

    @staticmethod
    def handle_authentication_failed(message: str = "Authentication failed") -> JSONResponse:
        """Handle authentication errors."""
        error_details = {
            "type": "AuthenticationError",
            "message": message
        }

        logger.warning(f"Authentication failed: {message}")

        return APIResponse.error(
            message=message,
            error_code=ErrorCode.AUTHENTICATION_FAILED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=error_details
        )

    @staticmethod
    def handle_authorization_failed(message: str = "Authorization failed") -> JSONResponse:
        """Handle authorization errors."""
        error_details = {
            "type": "AuthorizationError",
            "message": message
        }

        logger.warning(f"Authorization failed: {message}")

        return APIResponse.error(
            message=message,
            error_code=ErrorCode.AUTHORIZATION_FAILED,
            status_code=status.HTTP_403_FORBIDDEN,
            details=error_details
        )

    @staticmethod
    def handle_general_error(
        exc: Exception,
        message: str = "An unexpected error occurred",
        include_traceback: bool = False
    ) -> JSONResponse:
        """Handle general errors."""
        error_details = {
            "type": type(exc).__name__,
            "message": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }

        if include_traceback:
            error_details["traceback"] = traceback.format_exc()

        logger.error(f"General error: {str(exc)}", exc_info=True)

        return APIResponse.error(
            message=message,
            error_code=ErrorCode.GENERAL_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=error_details
        )


class APIServiceHelper:
    """Helper class for common API operations."""

    @staticmethod
    def validate_required_fields(data: Dict[str, Any], required_fields: list) -> Dict[str, Any]:
        """
        Validate that required fields are present in the data.

        Args:
            data: Input data dictionary
            required_fields: List of required field names

        Returns:
            Dictionary with validation results
        """
        missing_fields = []

        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)

        return {
            "is_valid": len(missing_fields) == 0,
            "missing_fields": missing_fields
        }

    @staticmethod
    def sanitize_input(text: str, max_length: int = 10000) -> str:
        """
        Sanitize text input by removing potentially harmful content.

        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length]

        # Remove null bytes and control characters that aren't whitespace
        sanitized = "".join(char for char in text if ord(char) >= 32 or char in "\t\n\r")

        return sanitized

    @staticmethod
    def format_response_data(data: Any, include_metadata: bool = True) -> Dict[str, Any]:
        """
        Format data for API response with optional metadata.

        Args:
            data: Data to format
            include_metadata: Whether to include metadata

        Returns:
            Formatted data dictionary
        """
        result = {"data": data}

        if include_metadata:
            result["metadata"] = {
                "timestamp": datetime.utcnow().isoformat(),
                "format_version": "1.0"
            }

        return result


class CustomHTTPException(HTTPException):
    """Custom HTTP exception with extended error information."""

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: Optional[Dict[str, str]] = None,
        error_code: Optional[ErrorCode] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code
        self.additional_info = additional_info or {}


# Common response utility functions
def create_success_response(
    data: Any = None,
    message: str = "Success",
    metadata: Optional[Dict[str, Any]] = None
) -> JSONResponse:
    """Shorthand function to create success responses."""
    return APIResponse.success(data=data, message=message, metadata=metadata)


def create_error_response(
    message: str = "An error occurred",
    error_code: Optional[ErrorCode] = None,
    status_code: int = 500,
    details: Optional[Dict[str, Any]] = None
) -> JSONResponse:
    """Shorthand function to create error responses."""
    return APIResponse.error(
        message=message,
        error_code=error_code,
        status_code=status_code,
        details=details
    )


# FastAPI exception handler setup
def add_exception_handlers(app):
    """
    Add standardized exception handlers to a FastAPI application.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(500)
    async def general_exception_handler(request, exc):
        return APIExceptionHandler.handle_general_error(exc)

    @app.exception_handler(422)
    async def validation_exception_handler(request, exc):
        return APIExceptionHandler.handle_validation_error(exc)

    @app.exception_handler(404)
    async def not_found_exception_handler(request, exc):
        return APIExceptionHandler.handle_not_found("Resource")

    @app.exception_handler(401)
    async def auth_exception_handler(request, exc):
        return APIExceptionHandler.handle_authentication_failed()

    @app.exception_handler(403)
    async def forbidden_exception_handler(request, exc):
        return APIExceptionHandler.handle_authorization_failed()