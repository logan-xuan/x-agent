"""Trace system for X-Agent execution monitoring.

This module provides:
1. Call chain tracing across components (Orchestrator → ReAct Loop → Tools)
2. Span-based timing for performance analysis
3. Structured trace storage for debugging
4. Correlation with logs via trace_id

Based on OpenTelemetry concepts but simplified for X-Agent's needs.

Usage:
    from .trace import get_tracer, Span
    
    tracer = get_tracer(__name__)
    
    # Start a span
    with tracer.start_span("task_execution") as span:
        span.set_attribute("task_id", task_id)
        
        # Nested span
        with tracer.start_span("tool_call", parent=span) as tool_span:
            tool_span.set_attribute("tool_name", "web_search")
            result = execute_tool()
            tool_span.set_attribute("result_size", len(result))
    
    # Or manually
    span = tracer.start_span("manual_span")
    try:
        do_work()
    finally:
        span.end()
"""

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterator

from ..utils.logger import get_logger

logger = get_logger(__name__)


class SpanKind(str, Enum):
    """Type of span."""
    INTERNAL = "internal"       # Internal operation
    CLIENT = "client"           # Outgoing request (e.g., LLM call)
    SERVER = "server"           # Incoming request (e.g., API endpoint)
    PRODUCER = "producer"       # Message producer
    CONSUMER = "consumer"       # Message consumer


class SpanStatus(str, Enum):
    """Status of span execution."""
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class Span:
    """A single span in a trace representing an operation.
    
    Attributes:
        span_id: Unique span identifier
        trace_id: Trace identifier (groups related spans)
        parent_id: Parent span ID (for nested operations)
        name: Operation name (e.g., "react_loop", "tool_call")
        kind: Type of span
        start_time: Start timestamp
        end_time: End timestamp (None if still running)
        attributes: Key-value metadata
        status: Execution status
        error: Error message if failed
    """
    
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    parent_id: str | None = None
    name: str = ""
    kind: SpanKind = SpanKind.INTERNAL
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: SpanStatus = SpanStatus.UNSET
    error: str | None = None
    
    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value
    
    def set_status(self, status: SpanStatus, error: str | None = None) -> None:
        """Set span status."""
        self.status = status
        self.error = error
    
    def end(self) -> None:
        """Mark span as ended."""
        if self.end_time is None:
            self.end_time = time.time()
            
            # Auto-set status if unset
            if self.status == SpanStatus.UNSET:
                self.status = SpanStatus.OK if not self.error else SpanStatus.ERROR
            
            # Log span completion
            duration_ms = (self.end_time - self.start_time) * 1000
            logger.debug(
                f"Span completed: {self.name}",
                extra={
                    "trace_id": self.trace_id,
                    "span_id": self.span_id,
                    "parent_id": self.parent_id,
                    "duration_ms": round(duration_ms, 2),
                    "status": self.status.value,
                    "attributes": self.attributes,
                }
            )
    
    def duration_ms(self) -> float | None:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000
    
    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "kind": self.kind.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "attributes": self.attributes,
            "status": self.status.value,
            "error": self.error,
        }


class Tracer:
    """Tracer for creating and managing spans.
    
    Each component gets its own tracer instance.
    """
    
    def __init__(self, name: str):
        """Initialize tracer.
        
        Args:
            name: Tracer name (usually module name)
        """
        self.name = name
        self._current_trace_id: str | None = None
        self._span_stack: list[Span] = []  # Stack of active spans
    
    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span.
        
        Args:
            name: Span name
            kind: Span kind
            parent: Parent span (for nested operations)
            attributes: Initial attributes
            
        Returns:
            New span instance
        """
        # Determine trace_id and parent_id
        if parent:
            trace_id = parent.trace_id
            parent_id = parent.span_id
        elif self._span_stack:
            # Use current span as parent
            current = self._span_stack[-1]
            trace_id = current.trace_id
            parent_id = current.span_id
        else:
            # New trace
            trace_id = str(uuid.uuid4())[:16]
            parent_id = None
            self._current_trace_id = trace_id
        
        span = Span(
            trace_id=trace_id,
            parent_id=parent_id,
            name=name,
            kind=kind,
            attributes=attributes or {},
        )
        
        self._span_stack.append(span)
        
        logger.debug(
            f"Span started: {name}",
            extra={
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_id": span.parent_id,
            }
        )
        
        return span
    
    def end_span(self, span: Span) -> None:
        """End a span.
        
        Args:
            span: Span to end
        """
        span.end()
        
        # Remove from stack if present
        if self._span_stack and self._span_stack[-1].span_id == span.span_id:
            self._span_stack.pop()
    
    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[Span]:
        """Context manager for creating a span.
        
        Args:
            name: Span name
            kind: Span kind
            attributes: Initial attributes
            
        Yields:
            Span instance
            
        Example:
            with tracer.span("process_request") as span:
                span.set_attribute("user_id", user_id)
                result = do_work()
        """
        span = self.start_span(name, kind, attributes=attributes)
        try:
            yield span
        except Exception as e:
            span.set_status(SpanStatus.ERROR, str(e))
            raise
        finally:
            self.end_span(span)
    
    def get_current_trace_id(self) -> str | None:
        """Get current trace ID."""
        if self._span_stack:
            return self._span_stack[0].trace_id
        return self._current_trace_id


# Global tracer registry
_tracers: dict[str, Tracer] = {}


def get_tracer(name: str) -> Tracer:
    """Get or create a tracer for a component.
    
    Args:
        name: Tracer name (usually __name__)
        
    Returns:
        Tracer instance
    """
    if name not in _tracers:
        _tracers[name] = Tracer(name)
    return _tracers[name]


# Future: Export traces to external systems (Jaeger, Zipkin, etc.)
# For now, traces are only logged via logger with trace_id correlation
