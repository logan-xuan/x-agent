"""LLM Router for primary/backup model routing with failover."""

import asyncio
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

from ...config.manager import ConfigManager
from ...utils.logger import get_llm_fallback_event_logger, get_logger, log_execution
from .bailian_provider import BailianProvider
from .circuit_breaker import circuit_breaker_manager
from .openai_provider import OpenAIProvider
from .provider import LLMProvider, LLMResponse, StreamingLLMResponse

logger = get_logger(__name__)


class LLMRouter:
    """Routes LLM requests to available providers with failover support.

    Implements primary/backup pattern:
    1. Try primary provider first
    2. On failure, fallback to backup providers by priority
    3. Track provider health and avoid unhealthy providers
    """

    def __init__(self, model_configs: list[Any] | None = None) -> None:
        """Initialize router with providers from configuration.

        Args:
            model_configs: Optional list of model configurations.
                          If not provided, loads from ConfigManager.
        """
        self._providers: dict[str, LLMProvider] = {}
        self._primary: LLMProvider | None = None
        self._backups: list[LLMProvider] = []
        self._model_configs = model_configs
        self._provider_health_cache: dict[str, tuple[float, bool]] = {}
        self._provider_health_locks: dict[str, asyncio.Lock] = {}
        self._provider_health_ttl_seconds = 30.0
        self._load_providers()

    def _health_lock_for(self, provider_name: str) -> asyncio.Lock:
        """Return a per-provider lock used to dedupe concurrent health probes."""
        lock = self._provider_health_locks.get(provider_name)
        if lock is None:
            lock = asyncio.Lock()
            self._provider_health_locks[provider_name] = lock
        return lock

    def _recent_provider_health(self, provider_name: str) -> bool | None:
        """Return cached provider health when still fresh."""
        cached = self._provider_health_cache.get(provider_name)
        if cached is None:
            return None
        checked_at, healthy = cached
        if time.monotonic() - checked_at >= self._provider_health_ttl_seconds:
            return None
        return healthy

    def _next_provider_name(
        self,
        providers_to_try: list[LLMProvider],
        current_index: int,
    ) -> str | None:
        """Return the next provider name for fallback logging."""
        for next_provider in providers_to_try[current_index + 1 :]:
            if next_provider is not None:
                return next_provider.name
        return None

    def _extract_provider_failure_details(self, error: Exception) -> dict[str, Any]:
        """Normalize provider failure details for structured fallback logs."""
        error_message = str(error)
        status_code = getattr(error, "status_code", None)
        request_id = getattr(error, "request_id", None)
        error_code = getattr(error, "code", None)

        response = getattr(error, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        if request_id is None and response is not None:
            request_id = getattr(response, "request_id", None)
            if request_id is None:
                headers = getattr(response, "headers", None)
                if headers is not None:
                    request_id = headers.get("x-request-id") or headers.get("request-id")

        if not error_code:
            match = re.search(r"[\"']code[\"']\s*:\s*[\"']([^\"']+)[\"']", error_message)
            if match:
                error_code = match.group(1)

        message_lower = error_message.lower()
        fallback_reason = "provider_exception"
        if error_code == "AllocationQuota.FreeTierOnly" or "allocationquota.freetieronly" in message_lower:
            fallback_reason = "allocation_quota_free_tier_only"
        elif status_code == 429 or "rate limit" in message_lower or "rate_limit" in message_lower:
            fallback_reason = "rate_limit"
        elif status_code == 401:
            fallback_reason = "auth_error"
        elif status_code == 403:
            fallback_reason = "permission_denied"
        elif "timeout" in message_lower:
            fallback_reason = "timeout"
        elif "connection" in message_lower or "connect" in message_lower:
            fallback_reason = "connection_error"

        return {
            "fallback_reason": fallback_reason,
            "error_code": error_code,
            "status_code": status_code,
            "request_id": request_id,
        }

    def _routing_context(
        self,
        *,
        original_primary_provider_name: str | None,
        preferred_provider_name: str | None,
        provider_attempt_order: list[str],
        provider_name: str | None = None,
        provider_attempt_index: int | None = None,
        fallback_from_provider_name: str | None = None,
        fallback_used: bool | None = None,
    ) -> dict[str, Any]:
        """Build shared structured logging context for provider routing."""
        context: dict[str, Any] = {
            "original_primary_provider_name": original_primary_provider_name,
            "preferred_provider_name": preferred_provider_name,
            "provider_attempt_order": provider_attempt_order,
        }
        if provider_name is not None:
            context["provider_name"] = provider_name
        if provider_attempt_index is not None:
            context["provider_attempt_index"] = provider_attempt_index
        if fallback_from_provider_name is not None:
            context["fallback_from_provider_name"] = fallback_from_provider_name
        if fallback_used is not None:
            context["fallback_used"] = fallback_used
        return context

    def _emit_fallback_event(
        self,
        *,
        session_id: str | None,
        original_primary_provider_name: str | None,
        provider_attempt_order: list[str],
        failed_provider_name: str,
        next_provider_name: str,
        provider_attempt_index: int,
        fallback_trigger: str,
        failure_details: dict[str, Any],
        error: Exception,
        error_type: str | None = None,
    ) -> None:
        """Emit a single dedicated fallback event entry."""
        try:
            fallback_logger = get_llm_fallback_event_logger()
            fallback_logger.log_event(
                session_id=session_id,
                original_primary_provider_name=original_primary_provider_name,
                failed_provider_name=failed_provider_name,
                next_provider_name=next_provider_name,
                provider_attempt_order=provider_attempt_order,
                provider_attempt_index=provider_attempt_index,
                fallback_trigger=fallback_trigger,
                fallback_reason=failure_details.get("fallback_reason"),
                error_code=failure_details.get("error_code"),
                status_code=failure_details.get("status_code"),
                request_id=failure_details.get("request_id"),
                error_type=error_type or type(error).__name__,
                error=str(error),
            )
        except Exception as log_error:
            logger.warning(
                "Failed to emit dedicated fallback event",
                extra={
                    "provider_name": failed_provider_name,
                    "next_provider_name": next_provider_name,
                    "session_id": session_id,
                    "error": str(log_error),
                    "error_type": type(log_error).__name__,
                },
            )

    async def _check_provider_health(
        self,
        provider: LLMProvider,
        *,
        use_cache: bool = True,
    ) -> bool:
        """Run or reuse a recent provider health probe."""
        provider_name = provider.name
        now = time.monotonic()
        cached = self._provider_health_cache.get(provider_name)
        if use_cache and cached is not None and now - cached[0] < self._provider_health_ttl_seconds:
            logger.info(
                "Using cached provider health result",
                extra={
                    "provider_name": provider_name,
                    "healthy": cached[1],
                    "cache_age_ms": int((now - cached[0]) * 1000),
                },
            )
            return cached[1]

        lock = self._health_lock_for(provider_name)
        async with lock:
            now = time.monotonic()
            cached = self._provider_health_cache.get(provider_name)
            if (
                use_cache
                and cached is not None
                and now - cached[0] < self._provider_health_ttl_seconds
            ):
                logger.info(
                    "Using cached provider health result",
                    extra={
                        "provider_name": provider_name,
                        "healthy": cached[1],
                        "cache_age_ms": int((now - cached[0]) * 1000),
                    },
                )
                return cached[1]

            started = time.monotonic()
            logger.info(
                "Running provider health probe",
                extra={
                    "provider_name": provider_name,
                    "use_cache": use_cache,
                },
            )
            try:
                healthy = await provider.health_check()
            except Exception as exc:
                healthy = False
                logger.warning(
                    "Provider health probe raised an exception",
                    extra={
                        "provider_name": provider_name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )

            completed_at = time.monotonic()
            self._provider_health_cache[provider_name] = (completed_at, healthy)
            logger.info(
                "Provider health probe completed",
                extra={
                    "provider_name": provider_name,
                    "healthy": healthy,
                    "elapsed_ms": int((completed_at - started) * 1000),
                },
            )
            return healthy

    def _load_providers(self) -> None:
        """Load providers from configuration."""
        if self._model_configs:
            model_configs = self._model_configs
        else:
            config_manager = ConfigManager()
            config = config_manager.config
            model_configs = config.models

        for model_config in model_configs:
            provider = self._create_provider(model_config)
            if provider:
                self._providers[model_config.name] = provider

                if model_config.is_primary:
                    self._primary = provider
                    logger.info(
                        "Set primary provider",
                        extra={
                            "provider_name": model_config.name,
                            "provider_type": model_config.provider,
                            "model_id": model_config.model_id,
                        },
                    )
                else:
                    self._backups.append(provider)
                    logger.info(
                        "Added backup provider",
                        extra={
                            "provider_name": model_config.name,
                            "provider_type": model_config.provider,
                            "model_id": model_config.model_id,
                            "priority": getattr(model_config, "priority", 0),
                        },
                    )

        # Sort backups by priority (lower number = higher priority)
        self._backups.sort(key=lambda p: p.config.get("priority", 0))

        if not self._primary and self._backups:
            # If no primary set, use first backup as primary
            self._primary = self._backups.pop(0)
            logger.warning(
                "No primary provider configured, using first backup as primary",
                extra={
                    "backup_provider": self._primary.name if self._primary else None,
                    "backup_count": len(self._backups),
                },
            )

    def _create_provider(self, config: Any) -> LLMProvider | None:
        """Create provider instance based on configuration."""
        provider_type = config.provider
        config_dict = {
            "name": config.name,
            "model_id": config.model_id,
            "api_key": config.api_key,
            "base_url": str(config.base_url) if config.base_url else None,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
            "priority": getattr(config, "priority", 0),
            "is_primary": config.is_primary,
            "max_context_tokens": getattr(config, "max_context_tokens", None),
            "max_output_tokens": getattr(config, "max_output_tokens", None),
        }

        try:
            if provider_type == "openai":
                provider = OpenAIProvider(config_dict)
            elif provider_type == "bailian":
                provider = BailianProvider(config_dict)
            else:
                logger.warning(
                    "Unknown provider type",
                    extra={
                        "provider_type": provider_type,
                        "provider_name": config.name,
                    },
                )
                return None

            if provider.is_available:
                return provider
            else:
                logger.warning(
                    "Provider is not available (missing configuration)",
                    extra={
                        "provider_name": config.name,
                        "provider_type": provider_type,
                    },
                )
                return None

        except Exception as e:
            logger.error(
                "Failed to create provider",
                extra={
                    "provider_name": config.name,
                    "provider_type": provider_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return None

    @property
    def primary(self) -> LLMProvider | None:
        """Get primary provider."""
        return self._primary

    @property
    def primary_model(self) -> LLMProvider | None:
        """Get primary provider (alias for primary)."""
        return self._primary

    @property
    def backup_models(self) -> list[LLMProvider]:
        """Get backup providers sorted by priority."""
        return self._backups

    @property
    def backups(self) -> list[LLMProvider]:
        """Get backup providers sorted by priority (alias for backup_models)."""
        return self._backups

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                try:
                    await provider.close()
                except Exception as e:
                    logger.warning(
                        "Error closing provider",
                        extra={
                            "provider_name": provider.name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )
        logger.info(
            "LLM router closed",
            extra={
                "provider_count": len(self._providers),
            },
        )

    @log_execution
    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse | AsyncGenerator[StreamingLLMResponse, None]:
        """Send chat request with automatic failover and circuit breaker.

        Args:
            messages: List of messages in OpenAI format
            stream: Whether to stream the response
            session_id: Optional session ID for statistics correlation
            **kwargs: Additional parameters

        Returns:
            LLM response (streaming or non-streaming)

        Raises:
            RuntimeError: If no provider is available
        """
        preferred_provider = kwargs.pop("preferred_provider", None)

        providers_to_try = [self._primary] + self._backups if self._primary else self._backups
        providers_to_try = [p for p in providers_to_try if p is not None]

        if isinstance(preferred_provider, str) and preferred_provider:
            providers_to_try.sort(
                key=lambda provider: 0 if provider.name == preferred_provider else 1
            )

        if not providers_to_try:
            raise RuntimeError("No LLM providers available")

        original_primary_provider_name = self._primary.name if self._primary else None
        preferred_provider_name = preferred_provider if isinstance(preferred_provider, str) else None
        provider_attempt_order = [provider.name for provider in providers_to_try]
        logger.info(
            "Provider routing plan created",
            extra={
                "session_id": session_id,
                **self._routing_context(
                    original_primary_provider_name=original_primary_provider_name,
                    preferred_provider_name=preferred_provider_name,
                    provider_attempt_order=provider_attempt_order,
                ),
            },
        )

        last_error = None

        for index, provider in enumerate(providers_to_try):
            # Get circuit breaker for this provider
            breaker = circuit_breaker_manager.get_breaker(provider.name)
            next_provider_name = self._next_provider_name(providers_to_try, index)
            provider_attempt_index = index + 1
            fallback_from_provider_name = providers_to_try[index - 1].name if index > 0 else None
            fallback_used = index > 0

            # Check if circuit breaker allows this request
            if not await breaker.can_execute():
                logger.warning(
                    "Circuit breaker open, skipping provider",
                    extra={
                        "circuit_state": "open",
                        "fallback_trigger": "circuit_breaker_open",
                        "fallback_reason": "circuit_breaker_open",
                        "next_provider_name": next_provider_name,
                        "session_id": session_id,
                        **self._routing_context(
                            original_primary_provider_name=original_primary_provider_name,
                            preferred_provider_name=preferred_provider_name,
                            provider_attempt_order=provider_attempt_order,
                            provider_name=provider.name,
                            provider_attempt_index=provider_attempt_index,
                            fallback_from_provider_name=fallback_from_provider_name,
                            fallback_used=fallback_used,
                        ),
                    },
                )
                if next_provider_name is not None:
                    self._emit_fallback_event(
                        session_id=session_id,
                        original_primary_provider_name=original_primary_provider_name,
                        provider_attempt_order=provider_attempt_order,
                        failed_provider_name=provider.name,
                        next_provider_name=next_provider_name,
                        provider_attempt_index=provider_attempt_index,
                        fallback_trigger="circuit_breaker_open",
                        failure_details={
                            "fallback_reason": "circuit_breaker_open",
                            "error_code": None,
                            "status_code": None,
                            "request_id": None,
                        },
                        error=RuntimeError("Circuit breaker open"),
                        error_type="CircuitBreakerOpen",
                    )
                continue

            try:
                logger.info(
                    "Trying provider",
                    extra={
                        "session_id": session_id,
                        "stream": stream,
                        **self._routing_context(
                            original_primary_provider_name=original_primary_provider_name,
                            preferred_provider_name=preferred_provider_name,
                            provider_attempt_order=provider_attempt_order,
                            provider_name=provider.name,
                            provider_attempt_index=provider_attempt_index,
                            fallback_from_provider_name=fallback_from_provider_name,
                            fallback_used=fallback_used,
                        ),
                    },
                )

                recent_health = self._recent_provider_health(provider.name)
                if recent_health is False:
                    logger.warning(
                        "Skipping provider due to recent failed health probe",
                        extra={
                            "fallback_trigger": "recent_failed_health_probe",
                            "fallback_reason": "recent_failed_health_probe",
                            "next_provider_name": next_provider_name,
                            "session_id": session_id,
                            **self._routing_context(
                                original_primary_provider_name=original_primary_provider_name,
                                preferred_provider_name=preferred_provider_name,
                                provider_attempt_order=provider_attempt_order,
                                provider_name=provider.name,
                                provider_attempt_index=provider_attempt_index,
                                fallback_from_provider_name=fallback_from_provider_name,
                                fallback_used=fallback_used,
                            ),
                        },
                    )
                    if next_provider_name is not None:
                        self._emit_fallback_event(
                            session_id=session_id,
                            original_primary_provider_name=original_primary_provider_name,
                            provider_attempt_order=provider_attempt_order,
                            failed_provider_name=provider.name,
                            next_provider_name=next_provider_name,
                            provider_attempt_index=provider_attempt_index,
                            fallback_trigger="recent_failed_health_probe",
                            failure_details={
                                "fallback_reason": "recent_failed_health_probe",
                                "error_code": None,
                                "status_code": None,
                                "request_id": None,
                            },
                            error=RuntimeError("Recent failed health probe cached for provider"),
                            error_type="RecentFailedHealthProbe",
                        )
                    continue

                start_time = time.time()
                result = await provider.chat(messages, stream=stream, **kwargs)
                latency_ms = int((time.time() - start_time) * 1000)

                # Log LLM interaction to dedicated prompt log
                try:
                    from ...conversation.context import get_current_context
                    from ...utils.logger import get_llm_prompt_logger

                    ctx = get_current_context()
                    prompt_logger = get_llm_prompt_logger()
                    stat_service = None
                    try:
                        from ..stat_service import get_stat_service

                        stat_service = get_stat_service()
                    except Exception as stat_error:
                        logger.warning(
                            "Failed to initialize stat service",
                            extra={
                                "provider_name": provider.name,
                                "error": str(stat_error),
                                "error_type": type(stat_error).__name__,
                            },
                        )

                    if stream:
                        # For streaming, wrap to capture response
                        return self._wrap_streaming_with_prompt_log(
                            result,
                            provider,
                            breaker,
                            session_id,
                            messages,
                            latency_ms,
                            ctx.trace_id if ctx else None,
                            prompt_logger,
                            stat_service=stat_service,
                            tools=kwargs.get("tools"),
                            call_id=str(kwargs.get("llm_call_id", "") or ""),
                        )
                    else:
                        self._provider_health_cache[provider.name] = (time.monotonic(), True)
                        await breaker.record_success()
                        logger.info(
                            "Successfully used provider",
                            extra={
                                "latency_ms": latency_ms,
                                "session_id": session_id,
                                **self._routing_context(
                                    original_primary_provider_name=original_primary_provider_name,
                                    preferred_provider_name=preferred_provider_name,
                                    provider_attempt_order=provider_attempt_order,
                                    provider_name=provider.name,
                                    provider_attempt_index=provider_attempt_index,
                                    fallback_from_provider_name=fallback_from_provider_name,
                                    fallback_used=fallback_used,
                                ),
                            },
                        )
                        # For non-streaming, log immediately
                        prompt_logger.log_interaction(
                            session_id=session_id,
                            trace_id=ctx.trace_id if ctx else None,
                            provider=provider.name,
                            model=provider.model_id,
                            messages=messages,
                            response=result.content,
                            latency_ms=latency_ms,
                            token_usage=result.usage,
                            success=True,
                            tools=kwargs.get("tools"),
                            call_id=str(kwargs.get("llm_call_id", "") or ""),
                            source="router",
                        )
                except Exception as prompt_log_error:
                    logger.warning(
                        "Failed to log prompt interaction",
                        extra={
                            "provider_name": provider.name,
                            "error": str(prompt_log_error),
                        },
                    )

                # Record statistics
                try:
                    from ..stat_service import get_stat_service

                    stat_service = get_stat_service()

                    if stream:
                        # For streaming, wrap the generator to capture stats
                        return self._wrap_streaming_response(
                            result,
                            provider,
                            breaker,
                            session_id,
                            latency_ms,
                            stat_service,
                            prompt_messages=messages,
                        )
                    else:
                        self._provider_health_cache[provider.name] = (time.monotonic(), True)
                        await breaker.record_success()
                        logger.info(
                            "Successfully used provider",
                            extra={
                                "latency_ms": latency_ms,
                                "session_id": session_id,
                                **self._routing_context(
                                    original_primary_provider_name=original_primary_provider_name,
                                    preferred_provider_name=preferred_provider_name,
                                    provider_attempt_order=provider_attempt_order,
                                    provider_name=provider.name,
                                    provider_attempt_index=provider_attempt_index,
                                    fallback_from_provider_name=fallback_from_provider_name,
                                    fallback_used=fallback_used,
                                ),
                            },
                        )
                        # For non-streaming, record immediately
                        await stat_service.record_request(
                            provider_name=provider.name,
                            model_id=provider.model_id,
                            success=True,
                            session_id=session_id,
                            prompt_tokens=result.usage.get("prompt_tokens", 0)
                            if result.usage
                            else 0,
                            completion_tokens=result.usage.get("completion_tokens", 0)
                            if result.usage
                            else 0,
                            latency_ms=latency_ms,
                        )
                except Exception as stat_error:
                    logger.warning(
                        "Failed to record stats",
                        extra={
                            "provider_name": provider.name,
                            "error": str(stat_error),
                            "error_type": type(stat_error).__name__,
                        },
                    )

                return result

            except Exception as e:
                failure_details = self._extract_provider_failure_details(e)
                logger.warning(
                    "Provider failed",
                    extra={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "session_id": session_id,
                        **self._routing_context(
                            original_primary_provider_name=original_primary_provider_name,
                            preferred_provider_name=preferred_provider_name,
                            provider_attempt_order=provider_attempt_order,
                            provider_name=provider.name,
                            provider_attempt_index=provider_attempt_index,
                            fallback_from_provider_name=fallback_from_provider_name,
                            fallback_used=fallback_used,
                        ),
                        **failure_details,
                    },
                )
                if next_provider_name is not None:
                    logger.warning(
                        "Provider failed, falling back to next provider",
                        extra={
                            "next_provider_name": next_provider_name,
                            "session_id": session_id,
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "fallback_trigger": "provider_exception",
                            **self._routing_context(
                                original_primary_provider_name=original_primary_provider_name,
                                preferred_provider_name=preferred_provider_name,
                                provider_attempt_order=provider_attempt_order,
                                provider_name=provider.name,
                                provider_attempt_index=provider_attempt_index,
                                fallback_from_provider_name=fallback_from_provider_name,
                                fallback_used=fallback_used,
                            ),
                            **failure_details,
                        },
                    )
                    self._emit_fallback_event(
                        session_id=session_id,
                        original_primary_provider_name=original_primary_provider_name,
                        provider_attempt_order=provider_attempt_order,
                        failed_provider_name=provider.name,
                        next_provider_name=next_provider_name,
                        provider_attempt_index=provider_attempt_index,
                        fallback_trigger="provider_exception",
                        failure_details=failure_details,
                        error=e,
                    )

                # Log failed prompt interaction
                try:
                    from ...conversation.context import get_current_context
                    from ...utils.logger import get_llm_prompt_logger

                    ctx = get_current_context()
                    prompt_logger = get_llm_prompt_logger()
                    prompt_logger.log_interaction(
                        session_id=session_id,
                        trace_id=ctx.trace_id if ctx else None,
                        provider=provider.name,
                        model=provider.model_id,
                        messages=messages,
                        response="",
                        latency_ms=0,
                        success=False,
                        error=str(e),
                        tools=kwargs.get("tools"),
                        call_id=str(kwargs.get("llm_call_id", "") or ""),
                        source="router",
                    )
                except Exception as prompt_log_error:
                    logger.warning(
                        "Failed to log failed prompt interaction",
                        extra={
                            "provider_name": provider.name,
                            "error": str(prompt_log_error),
                        },
                    )

                # Record failure
                await breaker.record_failure(e)

                # Record failed request stat
                try:
                    from ..stat_service import get_stat_service

                    stat_service = get_stat_service()
                    await stat_service.record_request(
                        provider_name=provider.name,
                        model_id=provider.model_id,
                        success=False,
                        session_id=session_id,
                        error_message=str(e),
                    )
                except Exception as stat_error:
                    logger.warning(
                        "Failed to record failure stats",
                        extra={
                            "provider_name": provider.name,
                            "error": str(stat_error),
                            "error_type": type(stat_error).__name__,
                        },
                    )

                last_error = e
                continue

        # All providers failed
        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count from text.

        Uses a simple heuristic: ~4 characters per token for mixed Chinese/English.
        This is a rough estimate but sufficient for statistics.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        if not text:
            return 0
        # Count Chinese characters (each is roughly 1-2 tokens)
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        # For English and other text, ~4 characters per token
        other_chars = len(text) - chinese_chars
        return chinese_chars * 2 + other_chars // 4

    async def _wrap_streaming_response(
        self,
        stream: AsyncGenerator[StreamingLLMResponse, None],
        provider: LLMProvider,
        breaker: Any,
        session_id: str | None,
        initial_latency_ms: int,
        stat_service: Any,
        prompt_messages: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[StreamingLLMResponse, None]:
        """Wrap streaming response to capture statistics.

        Args:
            stream: Original streaming response
            provider: Provider that generated the response
            session_id: Optional session ID
            initial_latency_ms: Initial latency before streaming started
            stat_service: Statistics service instance
            prompt_messages: Original prompt messages for token estimation

        Yields:
            Streaming response chunks
        """
        total_content = ""
        model = provider.model_id
        total_latency_ms = initial_latency_ms
        has_error = False
        completed = False
        error_message = None

        try:
            start_time = time.time()
            async for chunk in stream:
                total_content += chunk.content
                if chunk.model:
                    model = chunk.model
                yield chunk
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            completed = True

        except Exception as e:
            has_error = True
            error_message = str(e)
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            if total_content:
                logger.warning(
                    "Streaming provider ended with partial content; converting to best-effort completion",
                    extra={
                        "provider_name": provider.name,
                        "session_id": session_id,
                        "latency_ms": total_latency_ms,
                        "error": error_message,
                    },
                )
                completed = True
                yield StreamingLLMResponse(
                    content="",
                    is_finished=True,
                    model=provider.model_id,
                )
                return
            raise

        finally:
            if completed:
                self._provider_health_cache[provider.name] = (time.monotonic(), True)
                await breaker.record_success()
                logger.info(
                    "Successfully used provider",
                    extra={
                        "provider_name": provider.name,
                        "latency_ms": total_latency_ms,
                        "session_id": session_id,
                    },
                )
            elif has_error:
                await breaker.record_failure(Exception(error_message or "streaming_error"))

            # Record stats after streaming completes
            try:
                # Estimate prompt tokens from input messages
                prompt_tokens = 0
                if prompt_messages:
                    for msg in prompt_messages:
                        prompt_tokens += self._estimate_tokens(msg.get("content", ""))

                # Estimate completion tokens from output
                completion_tokens = self._estimate_tokens(total_content)

                await stat_service.record_request(
                    provider_name=provider.name,
                    model_id=model,
                    success=completed,
                    session_id=session_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=total_latency_ms,
                    error_message=error_message,
                )
            except Exception as stat_error:
                logger.warning(
                    "Failed to record streaming stats",
                    extra={
                        "provider_name": provider.name,
                        "error": str(stat_error),
                        "error_type": type(stat_error).__name__,
                    },
                )

    async def _wrap_streaming_with_prompt_log(
        self,
        stream: AsyncGenerator[StreamingLLMResponse, None],
        provider: LLMProvider,
        breaker: Any,
        session_id: str | None,
        prompt_messages: list[dict[str, str]],
        initial_latency_ms: int,
        trace_id: str | None,
        prompt_logger: Any,
        stat_service: Any | None = None,
        tools: list[dict] | None = None,
        call_id: str = "",
    ) -> AsyncGenerator[StreamingLLMResponse, None]:
        """Wrap streaming response to log prompt interaction.

        Args:
            stream: Original streaming response
            provider: Provider that generated the response
            session_id: Optional session ID
            prompt_messages: Original prompt messages
            initial_latency_ms: Initial latency before streaming started
            trace_id: Request trace ID
            prompt_logger: LLMPromptLogger instance
            tools: Tool definitions sent to LLM

        Yields:
            Streaming response chunks
        """
        total_content = ""
        total_latency_ms = initial_latency_ms
        has_error = False
        completed = False
        error_message = None
        first_content_chunk_logged = False

        try:
            start_time = time.time()
            async for chunk in stream:
                total_content += chunk.content
                if chunk.content and not first_content_chunk_logged:
                    first_content_chunk_logged = True
                    logger.info(
                        "Streaming provider emitted first content chunk",
                        extra={
                            "provider_name": provider.name,
                            "session_id": session_id,
                            "first_chunk_latency_ms": int((time.time() - start_time) * 1000)
                            + initial_latency_ms,
                            "chunk_chars": len(chunk.content),
                        },
                    )
                yield chunk
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            completed = True
            if not first_content_chunk_logged:
                logger.info(
                    "Streaming provider completed without content chunk",
                    extra={
                        "provider_name": provider.name,
                        "session_id": session_id,
                        "total_latency_ms": total_latency_ms,
                    },
                )

        except Exception as e:
            has_error = True
            error_message = str(e)
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            if total_content:
                logger.warning(
                    "Streaming provider ended with partial content; converting to best-effort completion",
                    extra={
                        "provider_name": provider.name,
                        "session_id": session_id,
                        "latency_ms": total_latency_ms,
                        "error": error_message,
                    },
                )
                completed = True
                yield StreamingLLMResponse(
                    content="",
                    is_finished=True,
                    model=provider.model_id,
                )
                return
            raise

        finally:
            if completed:
                self._provider_health_cache[provider.name] = (time.monotonic(), True)
                await breaker.record_success()
                logger.info(
                    "Successfully used provider",
                    extra={
                        "provider_name": provider.name,
                        "latency_ms": total_latency_ms,
                        "session_id": session_id,
                    },
                )
            elif has_error:
                await breaker.record_failure(Exception(error_message or "streaming_error"))

            # Log prompt interaction after streaming completes
            try:
                # Estimate tokens for streaming response
                prompt_tokens = 0
                for msg in prompt_messages:
                    prompt_tokens += self._estimate_tokens(msg.get("content", ""))
                completion_tokens = self._estimate_tokens(total_content)

                if stat_service is not None:
                    await stat_service.record_request(
                        provider_name=provider.name,
                        model_id=provider.model_id,
                        success=completed,
                        session_id=session_id,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        latency_ms=total_latency_ms,
                        error_message=error_message,
                    )

                prompt_logger.log_interaction(
                    session_id=session_id,
                    trace_id=trace_id,
                    provider=provider.name,
                    model=provider.model_id,
                    messages=prompt_messages,
                    response=total_content,
                    latency_ms=total_latency_ms,
                    token_usage={
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": prompt_tokens + completion_tokens,
                    },
                    success=completed,
                    error=error_message,
                    tools=tools,
                    call_id=call_id,
                    source="router",
                )
            except Exception as log_error:
                logger.warning(
                    "Failed to log streaming prompt interaction",
                    extra={
                        "provider_name": provider.name,
                        "error": str(log_error),
                    },
                )

    async def health_check(self) -> dict[str, bool]:
        """Check health of all providers.

        Returns:
            Dict mapping provider name to health status
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await self._check_provider_health(provider, use_cache=False)
            except Exception as e:
                logger.warning(
                    "Health check failed for provider",
                    extra={
                        "provider_name": name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                results[name] = False
        return results

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Complete a prompt (single message convenience method).

        This is a convenience method that wraps chat() for single-prompt completions.
        Used by compression service for summary generation.

        Args:
            prompt: The prompt text to complete
            **kwargs: Additional parameters passed to chat()

        Returns:
            LLM response
        """
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(messages, stream=False, **kwargs)
