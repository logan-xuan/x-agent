"""Internal logger for memory module.

This module provides a simple logger that doesn't depend on external utils.
Allows memory component to be used independently.
"""

import logging
import sys
from typing import Any


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger


class LoggerAdapter:
    """Adapter to provide structured logging interface."""
    
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
    
    def debug(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        """Log debug message."""
        self._logger.debug(self._format_msg(msg, extra))
    
    def info(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        """Log info message."""
        self._logger.info(self._format_msg(msg, extra))
    
    def warning(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        """Log warning message."""
        self._logger.warning(self._format_msg(msg, extra))
    
    def error(self, msg: str, extra: dict[str, Any] | None = None) -> None:
        """Log error message."""
        self._logger.error(self._format_msg(msg, extra))
    
    def _format_msg(self, msg: str, extra: dict[str, Any] | None = None) -> str:
        """Format message with extra data."""
        if extra:
            extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
            return f"{msg} | {extra_str}"
        return msg


def get_memory_logger(name: str) -> LoggerAdapter:
    """Get a memory module logger with adapter interface.
    
    Args:
        name: Logger name
        
    Returns:
        LoggerAdapter instance
    """
    return LoggerAdapter(get_logger(name))
