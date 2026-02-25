"""Event type definitions for X-Agent streaming responses.

This module provides centralized type definitions for all event types
used in X-Agent's streaming communication protocol (WebSocket, SSE, etc.).

Event types are organized by category:
- Agent lifecycle events (thinking, tool calls, results)
- User interaction events (confirmations, input requests)
- System events (errors, compression status)
"""

from enum import Enum
from typing import Any, TypedDict


class EventType(str, Enum):
    """Standard event types for X-Agent streaming protocol.
    
    Categories:
    - Agent outputs: THINKING, TOOL_CALL, TOOL_RESULT, FINAL_ANSWER, MESSAGE
    - User interactions: AWAITING_CONFIRMATION, INPUT_REQUEST
    - System events: ERROR, COMPRESSION_STATUS
    - Special: REFLECTION (enhanced reasoning)
    """
    
    # Agent reasoning and actions
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINAL_ANSWER = "final_answer"
    MESSAGE = "message"
    
    # Enhanced agent features
    REFLECTION = "reflection"  # Self-reflection events
    ITERATION = "iteration"     # ReAct loop iteration boundary
    
    # User interaction
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    INPUT_REQUEST = "input_request"
    
    # System events
    ERROR = "error"
    COMPRESSION_STATUS = "compression_status"
    
    # Backend-only events (not sent to frontend)
    INTERNAL_STATE = "_internal_state"  # Prefix with _ to indicate internal


class ThinkingEvent(TypedDict):
    """Event when agent is thinking/reasoning."""
    type: str  # EventType.THINKING
    thinking: str


class ToolCallEvent(TypedDict):
    """Event when agent calls a tool."""
    type: str  # EventType.TOOL_CALL
    tool_name: str
    arguments: dict[str, Any]
    tool_call_id: str | None


class ToolResultEvent(TypedDict):
    """Event when tool execution completes."""
    type: str  # EventType.TOOL_RESULT
    tool_name: str
    result: str
    success: bool
    tool_call_id: str | None


class MessageEvent(TypedDict):
    """General message event (final answer or intermediate)."""
    type: str  # EventType.MESSAGE
    message: str
    role: str | None  # 'assistant', 'system', etc.


class ErrorEvent(TypedDict):
    """Error event."""
    type: str  # EventType.ERROR
    error: str
    details: dict[str, Any] | None


class CompressionStatusEvent(TypedDict):
    """Context compression status event."""
    type: str  # EventType.COMPRESSION_STATUS
    compressed: bool
    original_size: int | None
    compressed_size: int | None


class AwaitingConfirmationEvent(TypedDict):
    """Event requesting user confirmation."""
    type: str  # EventType.AWAITING_CONFIRMATION
    message: str
    action: str  # Description of what needs confirmation
    options: list[str] | None  # Available response options


class ReflectionEvent(TypedDict):
    """Self-reflection event for enhanced reasoning."""
    type: str  # EventType.REFLECTION
    reflection: str
    trigger: str  # What triggered reflection (e.g., "error", "uncertainty")


# Helper functions for creating events

def create_thinking_event(thinking: str) -> ThinkingEvent:
    """Create a thinking event."""
    return {"type": EventType.THINKING.value, "thinking": thinking}


def create_tool_call_event(
    tool_name: str,
    arguments: dict[str, Any],
    tool_call_id: str | None = None,
) -> ToolCallEvent:
    """Create a tool call event."""
    return {
        "type": EventType.TOOL_CALL.value,
        "tool_name": tool_name,
        "arguments": arguments,
        "tool_call_id": tool_call_id,
    }


def create_tool_result_event(
    tool_name: str,
    result: str,
    success: bool = True,
    tool_call_id: str | None = None,
) -> ToolResultEvent:
    """Create a tool result event."""
    return {
        "type": EventType.TOOL_RESULT.value,
        "tool_name": tool_name,
        "result": result,
        "success": success,
        "tool_call_id": tool_call_id,
    }


def create_message_event(message: str, role: str = "assistant") -> MessageEvent:
    """Create a message event."""
    return {
        "type": EventType.MESSAGE.value,
        "message": message,
        "role": role,
    }


def create_error_event(error: str, details: dict[str, Any] | None = None) -> ErrorEvent:
    """Create an error event."""
    return {
        "type": EventType.ERROR.value,
        "error": error,
        "details": details,
    }


def create_compression_event(
    compressed: bool,
    original_size: int | None = None,
    compressed_size: int | None = None,
) -> CompressionStatusEvent:
    """Create a compression status event."""
    return {
        "type": EventType.COMPRESSION_STATUS.value,
        "compressed": compressed,
        "original_size": original_size,
        "compressed_size": compressed_size,
    }


def create_awaiting_confirmation_event(
    message: str,
    action: str,
    options: list[str] | None = None,
) -> AwaitingConfirmationEvent:
    """Create an awaiting confirmation event."""
    return {
        "type": EventType.AWAITING_CONFIRMATION.value,
        "message": message,
        "action": action,
        "options": options,
    }


def create_reflection_event(reflection: str, trigger: str = "reasoning") -> ReflectionEvent:
    """Create a reflection event."""
    return {
        "type": EventType.REFLECTION.value,
        "reflection": reflection,
        "trigger": trigger,
    }
