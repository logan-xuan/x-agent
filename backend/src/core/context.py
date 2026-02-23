"""Context management for X-Agent.

Provides execution context that flows through the agent lifecycle,
including session state, tracing, and metadata management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid
from contextvars import ContextVar
from enum import Enum


class ContextSource(str, Enum):
    """Source of the context creation."""
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    CLI = "cli"
    INTERNAL = "internal"


# Context variable for request-scoped context
_current_context: ContextVar["AgentContext"] = ContextVar("agent_context")


def get_current_context() -> Optional["AgentContext"]:
    """Get the current request context if set."""
    try:
        return _current_context.get()
    except LookupError:
        return None


def set_current_context(ctx: "AgentContext") -> None:
    """Set the current request context."""
    _current_context.set(ctx)


def clear_current_context() -> None:
    """Clear the current request context."""
    try:
        _current_context.set(None)  # type: ignore
    except LookupError:
        pass


@dataclass
class AgentContext:
    """Execution context for a single agent request.
    
    This context flows through the entire request lifecycle:
    1. Created when a request arrives (WebSocket message or REST API call)
    2. Passed to all middleware and handlers
    3. Used for logging, tracing, and state management
    4. Cleaned up when the request completes
    
    Attributes:
        trace_id: Unique identifier for request tracing
        session_id: Session identifier (user conversation)
        request_id: Unique request identifier within the session
        source: Where this request originated from
        user_id: User identifier (for future multi-user support)
        metadata: Additional context-specific data
        created_at: When this context was created
        parent_trace_id: Parent trace ID for nested operations
    """
    
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    source: ContextSource = ContextSource.INTERNAL
    user_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    parent_trace_id: Optional[str] = None
    
    # Timing tracking
    _start_time: Optional[float] = field(default=None, repr=False)
    _end_time: Optional[float] = field(default=None, repr=False)
    
    def __post_init__(self) -> None:
        self._start_time = datetime.utcnow().timestamp()
    
    @property
    def elapsed_ms(self) -> Optional[float]:
        """Elapsed time in milliseconds since context creation."""
        if self._start_time is None:
            return None
        end = self._end_time or datetime.utcnow().timestamp()
        return (end - self._start_time) * 1000
    
    def complete(self) -> None:
        """Mark this context as complete."""
        self._end_time = datetime.utcnow().timestamp()
    
    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        # Fix: Ensure metadata is a dict before iterating
        metadata_dict = self.metadata if isinstance(self.metadata, dict) else {}
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "source": self.source.value,
            "user_id": self.user_id,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at.isoformat(),
            "metadata": {k: v for k, v in metadata_dict.items() if not k.startswith("_")},
        }
    
    def child(self, **overrides: Any) -> "AgentContext":
        """Create a child context for nested operations."""
        return AgentContext(
            trace_id=str(uuid.uuid4()),
            session_id=overrides.get("session_id", self.session_id),
            request_id=str(uuid.uuid4())[:8],
            source=overrides.get("source", self.source),
            user_id=overrides.get("user_id", self.user_id),
            metadata={**self.metadata, **overrides.get("metadata", {})},
            parent_trace_id=self.trace_id,
        )
    
    @classmethod
    def for_websocket(cls, session_id: str, **metadata: Any) -> "AgentContext":
        """Create context for a WebSocket message."""
        return cls(
            session_id=session_id,
            source=ContextSource.WEBSOCKET,
            metadata=metadata,
        )
    
    @classmethod
    def for_rest_api(cls, session_id: Optional[str] = None, **metadata: Any) -> "AgentContext":
        """Create context for a REST API request."""
        return cls(
            session_id=session_id,
            source=ContextSource.REST_API,
            metadata=metadata,
        )
    
    @classmethod
    def for_cli(cls, **metadata: Any) -> "AgentContext":
        """Create context for a CLI command."""
        return cls(
            source=ContextSource.CLI,
            metadata=metadata,
        )


class ContextManager:
    """Manages context lifecycle for requests.
    
    Usage:
        async with context_manager.request(session_id="abc") as ctx:
            # ctx is automatically set as current context
            # and available via get_current_context()
            ...
    """
    
    def __init__(self) -> None:
        self._active_contexts: dict[str, AgentContext] = {}
    
    def request(
        self,
        session_id: Optional[str] = None,
        source: ContextSource = ContextSource.INTERNAL,
        **metadata: Any
    ) -> "ContextGuard":
        """Create a request-scoped context.
        
        Args:
            session_id: Optional session identifier
            source: Where the request originated
            **metadata: Additional context metadata
            
        Returns:
            Context guard for use with 'async with'
        """
        ctx = AgentContext(
            session_id=session_id,
            source=source,
            metadata=metadata,
        )
        return ContextGuard(self, ctx)
    
    def register(self, ctx: AgentContext) -> None:
        """Register an active context."""
        self._active_contexts[ctx.trace_id] = ctx
        set_current_context(ctx)
    
    def unregister(self, ctx: AgentContext) -> None:
        """Unregister a context."""
        if ctx.trace_id in self._active_contexts:
            del self._active_contexts[ctx.trace_id]
        clear_current_context()
    
    def get_active_contexts(self) -> list[AgentContext]:
        """Get all active contexts."""
        return list(self._active_contexts.values())


class ContextGuard:
    """Context manager guard for request-scoped context."""
    
    def __init__(self, manager: ContextManager, ctx: AgentContext) -> None:
        self._manager = manager
        self._ctx = ctx
    
    def __enter__(self) -> AgentContext:
        self._manager.register(self._ctx)
        return self._ctx
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._ctx.complete()
        self._manager.unregister(self._ctx)
    
    async def __aenter__(self) -> AgentContext:
        return self.__enter__()
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


# Global context manager instance
context_manager = ContextManager()
