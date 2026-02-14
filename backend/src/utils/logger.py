"""Structured JSON logging configuration with automatic Trace ID injection."""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger

from ..config.models import LoggingConfig


class TraceIDFilter(logging.Filter):
    """Filter that automatically injects trace_id and module info into log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Import here to avoid circular dependency
        try:
            from ..core.context import get_current_context
            ctx = get_current_context()
            record.trace_id = ctx.trace_id if ctx else None
            record.request_id = ctx.request_id if ctx else None
            record.session_id = ctx.session_id if ctx else None
        except Exception:
            record.trace_id = None
            record.request_id = None
            record.session_id = None
        
        # Extract module and class info from logger name
        # name format: src.api.websocket or src.core.agent.Agent
        parts = record.name.split('.')
        record.module_path = record.name
        
        # Try to extract class name if present in the message or from logger name
        record.class_name = getattr(record, 'class_name', None)
        
        return True


class ModuleInfoProcessor:
    """Structlog processor that adds module and class information."""
    
    def __call__(self, logger: Any, method_name: str, event_dict: dict) -> dict:
        # Add trace info from context
        try:
            from ..core.context import get_current_context
            ctx = get_current_context()
            if ctx:
                event_dict['trace_id'] = ctx.trace_id
                event_dict['request_id'] = ctx.request_id
                event_dict['session_id'] = ctx.session_id
        except Exception:
            pass
        
        # Add module info
        event_dict['module'] = event_dict.get('logger', 'unknown')
        
        return event_dict


def setup_logging(config: LoggingConfig) -> None:
    """Setup structured logging with JSON format and automatic Trace ID injection.
    
    Args:
        config: Logging configuration
    """
    # Ensure log directory exists
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create trace ID filter
    trace_filter = TraceIDFilter()
    
    # Configure standard library logging
    handlers: list[logging.Handler] = []
    
    # File handler with JSON format
    file_handler = logging.FileHandler(config.file)
    file_handler.addFilter(trace_filter)
    
    if config.format == "json":
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s %(trace_id)s %(request_id)s %(session_id)s",
            rename_fields={
                "timestamp": "timestamp", 
                "level": "level", 
                "name": "module",
                "trace_id": "trace_id",
                "request_id": "request_id",
                "session_id": "session_id",
            },
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-30s | trace_id=%(trace_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    # Console handler
    if config.console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.addFilter(trace_filter)
        if config.format == "json":
            console_handler.setFormatter(formatter)
        else:
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)-30s | trace_id=%(trace_id)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            )
        handlers.append(console_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, config.level.upper()),
        handlers=handlers,
        force=True,
    )
    
    # Configure structlog with module info processor
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f", utc=False),  # Local time
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        ModuleInfoProcessor(),  # Add module and trace info
    ]
    
    if config.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str, **kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance with automatic context injection.
    
    Args:
        name: Logger name (typically __name__)
        **kwargs: Additional context to bind to the logger
        
    Returns:
        Structured logger instance with automatic trace_id injection
    """
    logger = structlog.get_logger(name)
    if kwargs:
        logger = logger.bind(**kwargs)
    return logger
