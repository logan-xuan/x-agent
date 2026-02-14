"""Failover logic for LLM providers."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ...utils.logger import get_logger
from .provider import LLMProvider

logger = get_logger(__name__)


@dataclass
class ProviderHealth:
    """Health status for a provider."""
    provider_name: str
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    total_requests: int = 0
    failed_requests: int = 0
    
    # Circuit breaker settings
    failure_threshold: int = 3
    recovery_timeout: float = 60.0  # seconds
    
    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open (provider considered down)."""
        if self.consecutive_failures < self.failure_threshold:
            return False
        
        # Check if enough time has passed for recovery
        if self.last_failure_time is None:
            return False
            
        import time
        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure < self.recovery_timeout
    
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests
    
    def record_success(self) -> None:
        """Record a successful request."""
        import time
        self.total_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = time.time()
        self.is_healthy = True
    
    def record_failure(self) -> None:
        """Record a failed request."""
        import time
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        
        if self.consecutive_failures >= self.failure_threshold:
            self.is_healthy = False
            logger.warning(
                "Provider circuit breaker opened after consecutive failures",
                extra={
                    "provider_name": self.provider_name,
                    "consecutive_failures": self.consecutive_failures,
                    "failure_threshold": self.failure_threshold,
                    "failure_rate": self.failure_rate,
                }
            )


class FailoverManager:
    """Manages failover logic with circuit breaker pattern."""
    
    def __init__(self) -> None:
        """Initialize failover manager."""
        self._health: dict[str, ProviderHealth] = {}
    
    def register_provider(self, provider: LLMProvider) -> None:
        """Register a provider for health tracking."""
        if provider.name not in self._health:
            self._health[provider.name] = ProviderHealth(
                provider_name=provider.name,
                failure_threshold=provider.config.get("max_retries", 3)
            )
    
    def is_provider_available(self, provider_name: str) -> bool:
        """Check if provider is available (circuit closed)."""
        if provider_name not in self._health:
            return True  # Unknown providers are assumed available
        
        health = self._health[provider_name]
        return not health.is_circuit_open
    
    def record_success(self, provider_name: str) -> None:
        """Record successful request."""
        if provider_name in self._health:
            self._health[provider_name].record_success()
    
    def record_failure(self, provider_name: str) -> None:
        """Record failed request."""
        if provider_name in self._health:
            self._health[provider_name].record_failure()
    
    def get_health_status(self) -> dict[str, dict[str, Any]]:
        """Get health status for all providers."""
        return {
            name: {
                "is_healthy": h.is_healthy,
                "is_circuit_open": h.is_circuit_open,
                "consecutive_failures": h.consecutive_failures,
                "failure_rate": h.failure_rate,
                "total_requests": h.total_requests,
            }
            for name, h in self._health.items()
        }
