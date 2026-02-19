"""Rate limiting middleware."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ...utils.errors import RateLimitError
from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 300  # Increased for development (was 60)
    requests_per_hour: int = 5000   # Increased for development (was 1000)
    burst_size: int = 50            # Increased for development (was 10)
    burst_window_seconds: float = 1.0


@dataclass
class ClientState:
    """State for a single client."""
    minute_count: int = 0
    hour_count: int = 0
    burst_timestamps: list[float] = field(default_factory=list)
    last_reset: datetime = field(default_factory=datetime.utcnow)
    blocked_until: Optional[datetime] = None


class InMemoryRateLimiter:
    """In-memory rate limiter."""
    
    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self.config = config or RateLimitConfig()
        self._clients: dict[str, ClientState] = defaultdict(ClientState)
        self._lock = asyncio.Lock()
    
    def _get_client_key(self, request: Request) -> str:
        """Get client identifier from request."""
        # Try X-Forwarded-For first (for reverse proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Fall back to client host
        if request.client:
            return request.client.host
        
        return "unknown"
    
    async def check_rate_limit(self, request: Request) -> Optional[float]:
        """Check if request should be rate limited.
        
        Args:
            request: FastAPI request
            
        Returns:
            None if allowed, retry_after seconds if blocked
        """
        async with self._lock:
            client_key = self._get_client_key(request)
            state = self._clients[client_key]
            now = datetime.utcnow()
            
            # Check if currently blocked
            if state.blocked_until and now < state.blocked_until:
                remaining = (state.blocked_until - now).total_seconds()
                return remaining
            
            # Reset counters if time window passed
            if now - state.last_reset >= timedelta(hours=1):
                state.minute_count = 0
                state.hour_count = 0
                state.last_reset = now
            elif now - state.last_reset >= timedelta(minutes=1):
                state.minute_count = 0
            
            # Check burst rate
            current_time = time.time()
            state.burst_timestamps = [
                ts for ts in state.burst_timestamps
                if current_time - ts < self.config.burst_window_seconds
            ]
            
            if len(state.burst_timestamps) >= self.config.burst_size:
                return self.config.burst_window_seconds
            
            # Check minute rate
            if state.minute_count >= self.config.requests_per_minute:
                return 60.0
            
            # Check hour rate
            if state.hour_count >= self.config.requests_per_hour:
                return 3600.0
            
            # Record request
            state.minute_count += 1
            state.hour_count += 1
            state.burst_timestamps.append(current_time)
            
            return None
    
    def cleanup_old_clients(self, max_age_hours: int = 24) -> None:
        """Remove old client states to prevent memory leak."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=max_age_hours)
        
        to_remove = [
            key for key, state in self._clients.items()
            if state.last_reset < cutoff
        ]
        
        for key in to_remove:
            del self._clients[key]
        
        if to_remove:
            logger.debug(
                "Cleaned up old client rate limit states",
                extra={
                    "cleaned_count": len(to_remove),
                    "max_age_hours": max_age_hours,
                }
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for FastAPI."""
    
    def __init__(
        self,
        app,
        config: Optional[RateLimitConfig] = None,
        exclude_paths: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        self.limiter = InMemoryRateLimiter(config)
        self.exclude_paths = exclude_paths or ["/health", "/api/v1/health"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through rate limiter."""
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Check rate limit
        retry_after = await self.limiter.check_rate_limit(request)
        
        if retry_after is not None:
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_host": request.client.host if request.client else "unknown",
                    "path": request.url.path,
                    "retry_after": retry_after,
                }
            )
            return Response(
                content='{"success":false,"error":{"code":"ERR_RATE_LIMITED","message":"Rate limit exceeded","details":{"retry_after":%d}}}' % int(retry_after),
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(int(retry_after)),
                },
            )
        
        return await call_next(request)


# Global rate limiter
rate_limiter = InMemoryRateLimiter()
