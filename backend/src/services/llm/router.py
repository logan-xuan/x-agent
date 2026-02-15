"""LLM Router for primary/backup model routing with failover."""

import time
from collections.abc import AsyncGenerator
from typing import Any

from ...config.manager import ConfigManager
from ...utils.logger import get_logger, log_execution
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
        self._load_providers()
    
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
                        }
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
                        }
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
                }
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
                    }
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
                    }
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
                }
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
            if hasattr(provider, 'close'):
                try:
                    await provider.close()
                except Exception as e:
                    logger.warning(
                        "Error closing provider",
                        extra={
                            "provider_name": provider.name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    )
        logger.info(
            "LLM router closed",
            extra={
                "provider_count": len(self._providers),
            }
        )
    
    @log_execution
    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        session_id: str | None = None,
        **kwargs: Any
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
        providers_to_try = [self._primary] + self._backups if self._primary else self._backups
        providers_to_try = [p for p in providers_to_try if p is not None]
        
        if not providers_to_try:
            raise RuntimeError("No LLM providers available")
        
        last_error = None
        
        for provider in providers_to_try:
            # Get circuit breaker for this provider
            breaker = circuit_breaker_manager.get_breaker(provider.name)
            
            # Check if circuit breaker allows this request
            if not await breaker.can_execute():
                logger.warning(
                    "Circuit breaker open, skipping provider",
                    extra={
                        "provider_name": provider.name,
                        "circuit_state": "open",
                    }
                )
                continue
            
            try:
                logger.info(
                    "Trying provider",
                    extra={
                        "provider_name": provider.name,
                        "session_id": session_id,
                        "stream": stream,
                    }
                )
                
                # Check provider health before using
                if not await provider.health_check():
                    logger.warning(
                        "Provider health check failed, skipping",
                        extra={
                            "provider_name": provider.name,
                        }
                    )
                    await breaker.record_failure(Exception("Health check failed"))
                    continue
                
                start_time = time.time()
                result = await provider.chat(messages, stream=stream, **kwargs)
                latency_ms = int((time.time() - start_time) * 1000)
                
                # Record success
                await breaker.record_success()
                logger.info(
                    "Successfully used provider",
                    extra={
                        "provider_name": provider.name,
                        "latency_ms": latency_ms,
                        "session_id": session_id,
                    }
                )
                
                # Log LLM interaction to dedicated prompt log
                try:
                    from ...core.context import get_current_context
                    from ...utils.logger import get_llm_prompt_logger
                    
                    ctx = get_current_context()
                    prompt_logger = get_llm_prompt_logger()
                    
                    if stream:
                        # For streaming, wrap to capture response
                        return self._wrap_streaming_with_prompt_log(
                            result, provider, session_id, messages, latency_ms,
                            ctx.trace_id if ctx else None, prompt_logger,
                        )
                    else:
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
                        )
                except Exception as prompt_log_error:
                    logger.warning(
                        "Failed to log prompt interaction",
                        extra={
                            "provider_name": provider.name,
                            "error": str(prompt_log_error),
                        }
                    )
                
                # Record statistics
                try:
                    from ..stat_service import get_stat_service
                    stat_service = get_stat_service()
                    
                    if stream:
                        # For streaming, wrap the generator to capture stats
                        return self._wrap_streaming_response(
                            result, provider, session_id, latency_ms, stat_service,
                            prompt_messages=messages,
                        )
                    else:
                        # For non-streaming, record immediately
                        await stat_service.record_request(
                            provider_name=provider.name,
                            model_id=provider.model_id,
                            success=True,
                            session_id=session_id,
                            prompt_tokens=result.usage.get("prompt_tokens", 0) if result.usage else 0,
                            completion_tokens=result.usage.get("completion_tokens", 0) if result.usage else 0,
                            latency_ms=latency_ms,
                        )
                except Exception as stat_error:
                    logger.warning(
                        "Failed to record stats",
                        extra={
                            "provider_name": provider.name,
                            "error": str(stat_error),
                            "error_type": type(stat_error).__name__,
                        }
                    )
                
                return result
                
            except Exception as e:
                logger.warning(
                    "Provider failed",
                    extra={
                        "provider_name": provider.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "session_id": session_id,
                    }
                )
                
                # Log failed prompt interaction
                try:
                    from ...core.context import get_current_context
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
                    )
                except Exception as prompt_log_error:
                    logger.warning(
                        "Failed to log failed prompt interaction",
                        extra={
                            "provider_name": provider.name,
                            "error": str(prompt_log_error),
                        }
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
                        }
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
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # For English and other text, ~4 characters per token
        other_chars = len(text) - chinese_chars
        return chinese_chars * 2 + other_chars // 4
    
    async def _wrap_streaming_response(
        self,
        stream: AsyncGenerator[StreamingLLMResponse, None],
        provider: LLMProvider,
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
        error_message = None
        
        try:
            start_time = time.time()
            async for chunk in stream:
                total_content += chunk.content
                if chunk.model:
                    model = chunk.model
                yield chunk
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            
        except Exception as e:
            has_error = True
            error_message = str(e)
            raise
        
        finally:
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
                    success=not has_error,
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
                    }
                )
    
    async def _wrap_streaming_with_prompt_log(
        self,
        stream: AsyncGenerator[StreamingLLMResponse, None],
        provider: LLMProvider,
        session_id: str | None,
        prompt_messages: list[dict[str, str]],
        initial_latency_ms: int,
        trace_id: str | None,
        prompt_logger: Any,
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
            
        Yields:
            Streaming response chunks
        """
        total_content = ""
        total_latency_ms = initial_latency_ms
        has_error = False
        error_message = None
        
        try:
            start_time = time.time()
            async for chunk in stream:
                total_content += chunk.content
                yield chunk
            total_latency_ms = int((time.time() - start_time) * 1000) + initial_latency_ms
            
        except Exception as e:
            has_error = True
            error_message = str(e)
            raise
        
        finally:
            # Log prompt interaction after streaming completes
            try:
                # Estimate tokens for streaming response
                prompt_tokens = 0
                for msg in prompt_messages:
                    prompt_tokens += self._estimate_tokens(msg.get("content", ""))
                completion_tokens = self._estimate_tokens(total_content)
                
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
                    success=not has_error,
                    error=error_message,
                )
            except Exception as log_error:
                logger.warning(
                    "Failed to log streaming prompt interaction",
                    extra={
                        "provider_name": provider.name,
                        "error": str(log_error),
                    }
                )
    
    async def health_check(self) -> dict[str, bool]:
        """Check health of all providers.
        
        Returns:
            Dict mapping provider name to health status
        """
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except Exception as e:
                logger.warning(
                    "Health check failed for provider",
                    extra={
                        "provider_name": name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                results[name] = False
        return results
