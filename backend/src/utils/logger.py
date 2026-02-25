"""Structured JSON logging configuration with automatic Trace ID injection.

LOGGING BEST PRACTICES (P2 Improvement):
========================================

1. Log Level Guidelines:
   - ERROR: Critical failures that require immediate attention
   - WARNING: Unexpected behavior or configuration issues (e.g., retries, fallbacks)
   - INFO: Important business events (e.g., task start/completion, major decisions)
   - DEBUG: Routine operations and detailed execution flow (e.g., iterations, tool calls)

2. When to Use DEBUG vs INFO:
   - Use DEBUG for:
     * ReAct loop iterations
     * Tool call/result events (unless errors occur)
     * Cache hits/misses
     * Routine initialization
   
   - Use INFO for:
     * Task start/completion
     * User interactions (messages sent/received)
     * Strategy changes or adjustments
     * Final answers generated

3. Structured Logging:
   Always use the `extra` parameter for contextual data:
   
   # Good: Structured
   logger.info(
       "Task completed",
       extra={
           "task_id": task_id,
           "duration_ms": duration,
           "iterations": 5,
       }
   )
   
   # Bad: Unstructured string interpolation
   logger.info(f"Task {task_id} completed in {duration}ms after 5 iterations")

4. Avoid Logging PII/Secrets:
   Never log passwords, API keys, or personally identifiable information.
   
5. Context Propagation:
   Use trace_id for distributed tracing (automatically injected by this module).

Example:
    from ..utils.logger import get_logger
    
    logger = get_logger(__name__)
    
    # Routine event → DEBUG
    logger.debug("ReAct iteration started", extra={"iteration": 1})
    
    # Important decision → INFO
    logger.info("Switching to fallback LLM", extra={"reason": "rate_limit"})
    
    # Unexpected issue → WARNING
    logger.warning("Tool execution timeout", extra={"tool": "web_search", "timeout_s": 30})
"""

import functools
import inspect
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import structlog
from pythonjsonlogger import jsonlogger

try:
    from ..config.models import LoggingConfig
except (ImportError, ValueError):
    from config.models import LoggingConfig


class TimedSizeRotatingFileHandler(logging.Handler):
    """Custom log handler that rotates logs by both time and size.
    
    Features:
    - Rotates logs at specified time intervals (daily by default)
    - Rotates logs when they exceed max size
    - Names files with date and sequence: x-agent-2026-02-17-01.log
    - Compresses old backup files
    """
    
    def __init__(
        self,
        filename: str,
        when: str = 'D',
        interval: int = 1,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB default
        backup_count: int = 5,
        encoding: str = 'utf-8'
    ):
        """Initialize the handler.
        
        Args:
            filename: Base log file path
            when: Time interval (S=seconds, M=minutes, H=hours, D=days, W=weekday)
            interval: Rotation interval multiplier
            max_bytes: Maximum file size in bytes before rotation
            backup_count: Number of backup files to keep
            encoding: File encoding
        """
        super().__init__()
        self.base_filename = filename
        self.when = when.upper()
        self.interval = interval
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.encoding = encoding
        self.stream = None  # Initialize stream attribute
        
        # Calculate rollover time
        self.rollover_time = self._compute_rollover_time()
        
        # Open the base file
        self.open()
    
    def _compute_rollover_time(self) -> float:
        """Compute the next rollover time based on the interval."""
        from logging.handlers import TimedRotatingFileHandler
        # Use TimedRotatingFileHandler's logic to compute rollover
        t = TimedRotatingFileHandler(
            filename=self.base_filename,
            when=self.when,
            interval=self.interval,
            backupCount=self.backup_count
        )
        rollover = t.computeRollover(time.time())
        return rollover
    
    def open(self):
        """Open the current log file for writing."""
        if self.stream is None:
            self.stream = open(self.base_filename, 'a', encoding=self.encoding)
    
    def should_rollover(self, record: logging.LogRecord) -> bool:
        """Determine if rollover should occur."""
        # Check if time-based rollover is needed
        if time.time() >= self.rollover_time:
            return True
        
        # Check if size-based rollover is needed
        if self.stream is not None:
            self.stream.seek(0, 2)  # Seek to end
            if self.stream.tell() >= self.max_bytes:
                return True
        
        return False
    
    def do_rollover(self):
        """Perform the rollover operation."""
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # Generate new filename with date and sequence
        current_time = datetime.now()
        date_suffix = current_time.strftime('%Y-%m-%d')
        
        # Find the next available sequence number
        seq = 1
        while True:
            dir_name = os.path.dirname(self.base_filename)
            base_name = os.path.basename(self.base_filename)
            name_parts = os.path.splitext(base_name)
            
            if len(name_parts) == 2:
                new_filename = os.path.join(
                    dir_name, 
                    f"{name_parts[0]}-{date_suffix}-{seq:02d}{name_parts[1]}"
                )
            else:
                new_filename = os.path.join(
                    dir_name,
                    f"{base_name}-{date_suffix}-{seq:02d}"
                )
            
            if not os.path.exists(new_filename):
                break
            seq += 1
        
        # Rename the current file
        try:
            os.rename(self.base_filename, new_filename)
        except OSError:
            pass
        
        # Clean up old backups
        self._delete_old_backups()
        
        # Compute next rollover time
        self.rollover_time = self._compute_rollover_time()
        
        # Open new base file
        self.open()
    
    def _delete_old_backups(self):
        """Delete old backup files exceeding backup_count."""
        dir_name = os.path.dirname(self.base_filename)
        base_name = os.path.basename(self.base_filename)
        name_parts = os.path.splitext(base_name)
        
        if len(name_parts) != 2:
            return
        
        prefix = name_parts[0]
        suffix = name_parts[1]
        
        # Find all backup files
        backup_files = []
        try:
            for filename in os.listdir(dir_name):
                # Match pattern: prefix-YYYY-MM-DD-NN.suffix
                if filename.startswith(prefix + '-') and filename.endswith(suffix):
                    full_path = os.path.join(dir_name, filename)
                    if os.path.isfile(full_path):
                        backup_files.append((full_path, os.path.getmtime(full_path)))
        except OSError:
            return
        
        # Sort by modification time (newest first)
        backup_files.sort(key=lambda x: x[1], reverse=True)
        
        # Delete excess backups
        for filepath, _ in backup_files[self.backup_count:]:
            try:
                os.remove(filepath)
            except OSError:
                pass
    
    def emit(self, record: logging.LogRecord):
        """Emit a log record."""
        try:
            if self.should_rollover(record):
                self.do_rollover()
            
            msg = self.format(record)
            if self.stream is None:
                self.open()
            self.stream.write(msg + '\n')
            self.flush()
        except Exception:
            self.handleError(record)

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
    
    # Parse max size (e.g., "10MB" -> bytes)
    max_size_str = config.max_size.upper()
    if max_size_str.endswith('MB'):
        max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024)
    elif max_size_str.endswith('KB'):
        max_bytes = int(float(max_size_str[:-2]) * 1024)
    elif max_size_str.endswith('GB'):
        max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024 * 1024)
    else:
        try:
            max_bytes = int(max_size_str)
        except ValueError:
            max_bytes = 10 * 1024 * 1024  # Default to 10MB
    
    # Configure standard library logging
    handlers: list[logging.Handler] = []
    
    # File handler with custom timed+size rotation and JSON format
    file_handler = TimedSizeRotatingFileHandler(
        filename=config.file,
        when=config.when,
        interval=config.interval,
        max_bytes=max_bytes,
        backup_count=config.backup_count,
        encoding='utf-8'
    )
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
    
    # Initialize LLM prompt logger with rotation
    try:
        llm_logger = get_llm_prompt_logger(config)
    except Exception as e:
        logger = get_logger(__name__)
        logger.warning(f"Failed to initialize LLM prompt logger: {e}")
    
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
    _file_handler: TimedSizeRotatingFileHandler | None = None
    _initialized: bool = False
    
    def __new__(cls) -> "LLMPromptLogger":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def initialize(
        self, 
        log_dir: str = "logs",
        max_size: str = "50MB",
        backup_count: int = 5,
        when: str = "D",
        interval: int = 1
    ) -> None:
        """Initialize the LLM prompt logger with rotation support.
        
        Args:
            log_dir: Directory to store log files
            max_size: Max file size before rotation
            backup_count: Number of backup files to keep
            when: Time interval for rotation (D=days, H=hours, etc.)
            interval: Rotation interval multiplier
        """
        if self._initialized:
            return
        
        self._log_file = Path(log_dir) / "prompt-llm.log"
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Parse max size
        max_size_str = max_size.upper()
        if max_size_str.endswith('MB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024)
        elif max_size_str.endswith('KB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024)
        elif max_size_str.endswith('GB'):
            max_bytes = int(float(max_size_str[:-2]) * 1024 * 1024 * 1024)
        else:
            try:
                max_bytes = int(max_size_str)
            except ValueError:
                max_bytes = 50 * 1024 * 1024  # Default to 50MB
        
        # Create rotating file handler
        self._file_handler = TimedSizeRotatingFileHandler(
            filename=str(self._log_file),
            when=when,
            interval=interval,
            max_bytes=max_bytes,
            backup_count=backup_count,
            encoding='utf-8'
        )
        
        # Set JSON formatter
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
        self._file_handler.setFormatter(formatter)
        
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
        
        # Write using rotating handler
        assert self._file_handler is not None
        log_record = logging.LogRecord(
            name='llm_prompt',
            level=logging.INFO,
            pathname=str(self._log_file),
            lineno=0,
            msg=json.dumps(entry, ensure_ascii=False),
            args=(),
            exc_info=None
        )
        self._file_handler.emit(log_record)


# Global instance
_llm_prompt_logger = LLMPromptLogger()


def get_llm_prompt_logger(config: LoggingConfig | None = None) -> LLMPromptLogger:
    """Get the global LLM prompt logger instance.
    
    Args:
        config: Optional logging configuration (uses defaults if not provided)
        
    Returns:
        LLMPromptLogger instance
    """
    if not _llm_prompt_logger._initialized:
        if config:
            _llm_prompt_logger.initialize(
                log_dir=str(Path(config.prompt_llm_file).parent),
                max_size=config.prompt_llm_max_size,
                backup_count=config.prompt_llm_backup_count,
                when=config.when,
                interval=config.interval
            )
        else:
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
