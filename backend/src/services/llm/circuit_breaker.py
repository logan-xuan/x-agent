"""Circuit breaker pattern for LLM providers.

Implements the circuit breaker pattern to prevent cascading failures
when a provider is experiencing issues.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
import asyncio

from ...utils.logger import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation, requests pass through
    OPEN = "open"          # Failing, requests are blocked
    HALF_OPEN = "half_open"  # Testing if provider recovered


@dataclass
class CircuitStats:
    """Statistics for circuit breaker."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changed_at: Optional[datetime] = None


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5        # Failures before opening
    success_threshold: int = 2        # Successes in half-open to close
    timeout_seconds: float = 30.0     # Time before retrying in open state
    half_open_max_calls: int = 3      # Max calls in half-open state


class CircuitBreaker:
    """Circuit breaker for a single provider.
    
    States:
    - CLOSED: Normal operation, all requests pass through
    - OPEN: Provider is failing, requests are blocked
    - HALF_OPEN: Testing if provider has recovered
    
    State transitions:
    - CLOSED -> OPEN: When consecutive failures >= threshold
    - OPEN -> HALF_OPEN: After timeout period
    - HALF_OPEN -> CLOSED: When enough successes
    - HALF_OPEN -> OPEN: When any failure occurs
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state
    
    @property
    def stats(self) -> CircuitStats:
        """Get circuit statistics."""
        return self._stats
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (allowing requests)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is in half-open state."""
        return self._state == CircuitState.HALF_OPEN
    
    async def can_execute(self) -> bool:
        """Check if a request can be executed.
        
        Returns:
            True if request should proceed, False if blocked
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                # Check if timeout has passed
                if self._should_attempt_recovery():
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True
                return False
            
            if self._state == CircuitState.HALF_OPEN:
                # Limit calls in half-open state
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            return False
    
    async def record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            self._stats.total_requests += 1
            self._stats.successful_requests += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = datetime.utcnow()
            
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit recorded success in half-open state",
                    extra={
                        "circuit_name": self.name,
                        "successful_requests": self._stats.successful_requests,
                        "success_threshold": self.config.success_threshold,
                    }
                )
                # Check if we should close
                if self._stats.successful_requests >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
    
    async def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record a failed request."""
        async with self._lock:
            self._stats.total_requests += 1
            self._stats.failed_requests += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = datetime.utcnow()
            
            error_msg = str(error) if error else "Unknown error"
            
            if self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    logger.warning(
                        "Circuit opening due to consecutive failures",
                        extra={
                            "circuit_name": self.name,
                            "consecutive_failures": self._stats.consecutive_failures,
                            "failure_threshold": self.config.failure_threshold,
                            "error": error_msg,
                        }
                    )
                    self._transition_to(CircuitState.OPEN)
            
            elif self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit reopening due to failure in half-open state",
                    extra={
                        "circuit_name": self.name,
                        "error": error_msg,
                    }
                )
                self._transition_to(CircuitState.OPEN)
    
    def _should_attempt_recovery(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._stats.state_changed_at is None:
            return True
        
        elapsed = datetime.utcnow() - self._stats.state_changed_at
        return elapsed >= timedelta(seconds=self.config.timeout_seconds)
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changed_at = datetime.utcnow()
        
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        
        if new_state == CircuitState.CLOSED:
            self._stats.consecutive_failures = 0
        
        logger.info(
            "Circuit state transitioned",
            extra={
                "circuit_name": self.name,
                "old_state": old_state.value,
                "new_state": new_state.value,
            }
        )
    
    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0
        logger.info(
            "Circuit reset to closed state",
            extra={
                "circuit_name": self.name,
            }
        )
    
    def to_dict(self) -> dict:
        """Get circuit breaker status as dictionary."""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": {
                "total_requests": self._stats.total_requests,
                "successful_requests": self._stats.successful_requests,
                "failed_requests": self._stats.failed_requests,
                "consecutive_failures": self._stats.consecutive_failures,
                "last_failure_time": self._stats.last_failure_time.isoformat() if self._stats.last_failure_time else None,
                "last_success_time": self._stats.last_success_time.isoformat() if self._stats.last_success_time else None,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout_seconds": self.config.timeout_seconds,
            },
        }


class CircuitBreakerManager:
    """Manages circuit breakers for multiple providers."""
    
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker for a provider.
        
        Args:
            name: Provider name
            config: Optional circuit breaker configuration
            
        Returns:
            CircuitBreaker for the provider
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]
    
    def get_all_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers."""
        return {name: breaker.to_dict() for name, breaker in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
    
    def remove(self, name: str) -> None:
        """Remove a circuit breaker."""
        if name in self._breakers:
            del self._breakers[name]


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()
