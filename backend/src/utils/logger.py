"""Structured JSON logging configuration with automatic Trace ID injection."""

import functools
import inspect
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import structlog
from pythonjsonlogger import jsonlogger

from ..config.models import LoggingConfig

# Type variable for generic function decoration
F = TypeVar('F', bound=Callable[..., Any])


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


class LLMPromptLogger:
    """Dedicated logger for LLM prompt/request/response tracking.
    
    Writes to a separate log file (logs/prompt-llm.log) for easy analysis.
    Each log entry contains:
    - timestamp: ISO format timestamp
    - session_id: Session identifier
    - trace_id: Request trace ID
    - provider: LLM provider name
    - model: Model ID
    - request: The messages array sent to LLM
    - response: The LLM response content
    - latency_ms: Request latency in milliseconds
    - token_usage: Token statistics (if available)
    """
    
    _instance: "LLMPromptLogger | None" = None
    _log_file: Path | None = None
    _initialized: bool = False
    
    def __new__(cls) -> "LLMPromptLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(self, log_dir: str = "logs") -> None:
        """Initialize the LLM prompt logger.
        
        Args:
            log_dir: Directory to store log files
        """
        if self._initialized:
            return
            
        self._log_file = Path(log_dir) / "prompt-llm.log"
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = True
    
    def log_interaction(
        self,
        session_id: str | None,
        trace_id: str | None,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        response: str,
        latency_ms: int,
        token_usage: dict[str, int] | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Log an LLM interaction to the dedicated log file.
        
        Args:
            session_id: Session identifier
            trace_id: Request trace ID
            provider: LLM provider name
            model: Model ID
            messages: The messages array sent to LLM
            response: The LLM response content
            latency_ms: Request latency in milliseconds
            token_usage: Token statistics (prompt_tokens, completion_tokens, total_tokens)
            success: Whether the request was successful
            error: Error message if request failed
        """
        if not self._initialized:
            self.initialize()
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "trace_id": trace_id,
            "provider": provider,
            "model": model,
            "latency_ms": latency_ms,
            "success": success,
            "request": {
                "message_count": len(messages),
                "messages": messages,
            },
            "response": response,
        }
        
        if token_usage:
            entry["token_usage"] = token_usage
        
        if error:
            entry["error"] = error
        
        # Append to log file
        assert self._log_file is not None
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# Global instance
_llm_prompt_logger = LLMPromptLogger()


def get_llm_prompt_logger() -> LLMPromptLogger:
    """Get the global LLM prompt logger instance.
    
    Returns:
        LLMPromptLogger instance
    """
    if not _llm_prompt_logger._initialized:
        _llm_prompt_logger.initialize()
    return _llm_prompt_logger


def log_execution(func: F) -> F:
    """Decorator to automatically log function entry, exit, and execution time.
    
    Logs:
    - Function entry with parameters (at DEBUG level)
    - Function exit with return value preview (at DEBUG level)
    - Execution duration (at INFO level if > 100ms, DEBUG otherwise)
    - Any exceptions raised (at ERROR level)
    
    Usage:
        @log_execution
        async def my_function(param1: str) -> dict:
            ...
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with automatic logging
    """
    logger = get_logger(func.__module__)
    func_name = f"{func.__qualname__}"
    
    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Log entry
        params_preview = {}
        if args:
            params_preview['args_count'] = len(args)
        if kwargs:
            # Limit parameter value length for logging
            params_preview['kwargs'] = {
                k: str(v)[:100] if isinstance(v, str) and len(str(v)) > 100 else v
                for k, v in kwargs.items()
            }
        
        logger.debug(
            f"Entering {func_name}",
            extra={
                'event': 'function_entry',
                'function': func_name,
                'params': params_preview,
            }
        )
        
        start_time = time.time()
        error_occurred = False
        result = None
        
        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            error_occurred = True
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Exception in {func_name}",
                extra={
                    'event': 'function_exception',
                    'function': func_name,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'duration_ms': round(elapsed_ms, 2),
                },
                exc_info=True,
            )
            raise
        finally:
            if not error_occurred:
                elapsed_ms = (time.time() - start_time) * 1000
                
                # Log result preview
                result_preview = None
                if result is not None:
                    if isinstance(result, dict):
                        result_preview = {k: type(v).__name__ for k, v in list(result.items())[:5]}
                    elif isinstance(result, (list, tuple)):
                        result_preview = f"{type(result).__name__}[{len(result)}]"
                    else:
                        result_preview = type(result).__name__
                
                # Use INFO level for slow operations (> 100ms), DEBUG otherwise
                log_level = 'info' if elapsed_ms > 100 else 'debug'
                log_method = getattr(logger, log_level)
                
                log_method(
                    f"Exiting {func_name}",
                    extra={
                        'event': 'function_exit',
                        'function': func_name,
                        'duration_ms': round(elapsed_ms, 2),
                        'result_type': result_preview,
                    }
                )
    
    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Log entry
        params_preview = {}
        if args:
            params_preview['args_count'] = len(args)
        if kwargs:
            params_preview['kwargs'] = {
                k: str(v)[:100] if isinstance(v, str) and len(str(v)) > 100 else v
                for k, v in kwargs.items()
            }
        
        logger.debug(
            f"Entering {func_name}",
            extra={
                'event': 'function_entry',
                'function': func_name,
                'params': params_preview,
            }
        )
        
        start_time = time.time()
        error_occurred = False
        result = None
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_occurred = True
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Exception in {func_name}",
                extra={
                    'event': 'function_exception',
                    'function': func_name,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'duration_ms': round(elapsed_ms, 2),
                },
                exc_info=True,
            )
            raise
        finally:
            if not error_occurred:
                elapsed_ms = (time.time() - start_time) * 1000
                
                # Log result preview
                result_preview = None
                if result is not None:
                    if isinstance(result, dict):
                        result_preview = {k: type(v).__name__ for k, v in list(result.items())[:5]}
                    elif isinstance(result, (list, tuple)):
                        result_preview = f"{type(result).__name__}[{len(result)}]"
                    else:
                        result_preview = type(result).__name__
                
                # Use INFO level for slow operations (> 100ms), DEBUG otherwise
                log_level = 'info' if elapsed_ms > 100 else 'debug'
                log_method = getattr(logger, log_level)
                
                log_method(
                    f"Exiting {func_name}",
                    extra={
                        'event': 'function_exit',
                        'function': func_name,
                        'duration_ms': round(elapsed_ms, 2),
                        'result_type': result_preview,
                    }
                )
    
    # Return appropriate wrapper based on whether function is async
    if inspect.iscoroutinefunction(func):
        return async_wrapper  # type: ignore
    else:
        return sync_wrapper  # type: ignore
