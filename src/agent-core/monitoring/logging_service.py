"""
Logging and monitoring infrastructure for the x-agent2 AI assistant system.

This module provides centralized logging, metrics collection, and monitoring
capabilities across all system components.
"""

import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import json
import traceback
from pathlib import Path
import os

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogFormatter(logging.Formatter):
    """Custom formatter for structured logging."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry)


class Logger:
    """Centralized logger for the system."""

    def __init__(self, name: str = "x-agent2", level: LogLevel = LogLevel.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level.value)

        # Prevent adding handlers multiple times
        if not self.logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(LogFormatter())
            self.logger.addHandler(console_handler)

            # File handler for general logs
            file_handler = logging.FileHandler(LOGS_DIR / f"{name}.log")
            file_handler.setFormatter(LogFormatter())
            self.logger.addHandler(file_handler)

            # Error file handler
            error_handler = logging.FileHandler(LOGS_DIR / f"{name}_errors.log")
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(LogFormatter())
            self.logger.addHandler(error_handler)

    def debug(self, message: str, **kwargs):
        self.logger.debug(message, extra={"extra_fields": kwargs})

    def info(self, message: str, **kwargs):
        self.logger.info(message, extra={"extra_fields": kwargs})

    def warning(self, message: str, **kwargs):
        self.logger.warning(message, extra={"extra_fields": kwargs})

    def error(self, message: str, **kwargs):
        self.logger.error(message, extra={"extra_fields": kwargs})

    def critical(self, message: str, **kwargs):
        self.logger.critical(message, extra={"extra_fields": kwargs})

    def exception(self, message: str, **kwargs):
        self.logger.exception(message, extra={"extra_fields": kwargs})


class MetricsCollector:
    """Collects and manages system metrics."""

    def __init__(self):
        self.metrics: Dict[str, Any] = {}
        self.counters: Dict[str, int] = {}
        self.timers: Dict[str, float] = {}

    def increment_counter(self, name: str, value: int = 1) -> int:
        """Increment a counter metric."""
        if name not in self.counters:
            self.counters[name] = 0
        self.counters[name] += value
        return self.counters[name]

    def record_timer(self, name: str, value: float) -> float:
        """Record a timer metric."""
        self.timers[name] = value
        return value

    def set_gauge(self, name: str, value: Any) -> Any:
        """Set a gauge metric."""
        self.metrics[name] = value
        return value

    def get_metric(self, name: str) -> Any:
        """Get a specific metric value."""
        if name in self.counters:
            return self.counters[name]
        elif name in self.timers:
            return self.timers[name]
        elif name in self.metrics:
            return self.metrics[name]
        return None

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        all_metrics = {}
        all_metrics.update(self.metrics)
        all_metrics.update(self.counters)
        all_metrics.update(self.timers)
        return all_metrics

    def reset_counter(self, name: str) -> None:
        """Reset a counter to zero."""
        if name in self.counters:
            self.counters[name] = 0

    def reset_all_counters(self) -> None:
        """Reset all counters to zero."""
        for key in self.counters:
            self.counters[key] = 0


class SystemMonitor:
    """Main monitoring interface for the system."""

    def __init__(self):
        self.logger = Logger()
        self.metrics_collector = MetricsCollector()
        self.uptime_start = datetime.utcnow()

    def log_debug(self, message: str, **kwargs):
        """Log a debug message."""
        self.logger.debug(message, **kwargs)

    def log_info(self, message: str, **kwargs):
        """Log an info message."""
        self.logger.info(message, **kwargs)

    def log_warning(self, message: str, **kwargs):
        """Log a warning message."""
        self.logger.warning(message, **kwargs)

    def log_error(self, message: str, **kwargs):
        """Log an error message."""
        self.logger.error(message, **kwargs)

    def log_critical(self, message: str, **kwargs):
        """Log a critical message."""
        self.logger.critical(message, **kwargs)

    def log_exception(self, message: str, **kwargs):
        """Log an exception with traceback."""
        self.logger.exception(message, **kwargs)

    def increment_counter(self, name: str, value: int = 1) -> int:
        """Increment a counter metric."""
        return self.metrics_collector.increment_counter(name, value)

    def record_timer(self, name: str, value: float) -> float:
        """Record a timer metric."""
        return self.metrics_collector.record_timer(name, value)

    def set_gauge(self, name: str, value: Any) -> Any:
        """Set a gauge metric."""
        return self.metrics_collector.set_gauge(name, value)

    def get_metrics(self) -> Dict[str, Any]:
        """Get all system metrics."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": (datetime.utcnow() - self.uptime_start).total_seconds(),
            "metrics": self.metrics_collector.get_all_metrics()
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform a basic health check."""
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": (datetime.utcnow() - self.uptime_start).total_seconds(),
            "disk_space_available": self._check_disk_space(),
            "log_directory_exists": LOGS_DIR.exists()
        }

    def _check_disk_space(self) -> float:
        """Check available disk space in MB."""
        try:
            statvfs = os.statvfs(".")
            available_bytes = statvfs.f_frsize * statvfs.f_bavail
            return available_bytes / (1024 * 1024)  # Convert to MB
        except:
            return -1  # Unable to determine

    def get_component_logger(self, component_name: str) -> Logger:
        """Get a logger for a specific component."""
        return Logger(f"x-agent2.{component_name}")


# Global monitor instance
monitor = SystemMonitor()

# Convenience functions
def get_logger(component_name: str) -> Logger:
    """Get a logger for a specific component."""
    return monitor.get_component_logger(component_name)

def log_debug(message: str, **kwargs):
    """Global debug logging function."""
    monitor.log_debug(message, **kwargs)

def log_info(message: str, **kwargs):
    """Global info logging function."""
    monitor.log_info(message, **kwargs)

def log_warning(message: str, **kwargs):
    """Global warning logging function."""
    monitor.log_warning(message, **kwargs)

def log_error(message: str, **kwargs):
    """Global error logging function."""
    monitor.log_error(message, **kwargs)

def log_exception(message: str, **kwargs):
    """Global exception logging function."""
    monitor.log_exception(message, **kwargs)

def increment_counter(name: str, value: int = 1) -> int:
    """Global counter increment function."""
    return monitor.increment_counter(name, value)

def record_timer(name: str, value: float) -> float:
    """Global timer recording function."""
    return monitor.record_timer(name, value)

def set_gauge(name: str, value: Any) -> Any:
    """Global gauge setting function."""
    return monitor.set_gauge(name, value)

def get_metrics() -> Dict[str, Any]:
    """Global metrics getter function."""
    return monitor.get_metrics()

def health_check() -> Dict[str, Any]:
    """Global health check function."""
    return monitor.health_check()