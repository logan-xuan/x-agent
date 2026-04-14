"""OpenAI-compatible LLM provider implementation."""

import os
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI

from ...utils.logger import get_logger
from .provider import LLMProvider, LLMResponse, StreamingLLMResponse

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible provider.

    Supports OpenAI API and any OpenAI-compatible endpoints
    (e.g., local models, custom providers).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize OpenAI provider."""
        super().__init__(config)
        self._client: AsyncOpenAI | None = None
        self._api_key = self._get_api_key()
        self._base_url = config.get("base_url", "https://api.openai.com/v1")

    def _get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        # Get from config (could be encrypted in production)
        api_key = self.config.get("api_key")
        if api_key:
            # Handle SecretStr or plain string
            if hasattr(api_key, "get_secret_value"):
                return api_key.get_secret_value()
            return str(api_key)

        # Fallback to environment variable
        return os.getenv("OPENAI_API_KEY")

    @property
    def is_available(self) -> bool:
        """Check if provider has valid configuration."""
        return bool(self._api_key and self._base_url)

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client with structured HTTP logging."""
        if self._client is None:
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                event_hooks={
                    "request": [self._on_http_request],
                    "response": [self._on_http_response],
                },
            )
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                max_retries=self.max_retries,
                http_client=http_client,
            )
        return self._client

    async def _on_http_request(self, request: httpx.Request) -> None:
        """Record HTTP request start time."""
        request.extensions["start_time"] = time.time()

    async def _on_http_response(self, response: httpx.Response) -> None:
        """Log structured HTTP response with timing."""
        start_time = response.request.extensions.get("start_time")
        elapsed_ms = round((time.time() - start_time) * 1000, 2) if start_time else None
        logger.info(
            "HTTP request completed",
            extra={
                "scene": "http_request",
                "provider": self.name,
                "method": response.request.method,
                "url": str(response.request.url),
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "response_bytes": int(response.headers.get("content-length", 0)),
            },
        )

    async def chat(
        self, messages: list[dict[str, str]], stream: bool = False, **kwargs: Any
    ) -> LLMResponse | AsyncGenerator[StreamingLLMResponse, None]:
        """Send chat completion request."""
        if not self.is_available:
            raise RuntimeError(f"Provider {self.name} is not available")

        client = self._get_client()

        # Merge default and custom parameters
        params = {"model": self.model_id, "messages": messages, "stream": stream, **kwargs}

        if stream:
            return self._chat_streaming(client, params)
        else:
            return await self._chat_non_streaming(client, params)

    async def _chat_non_streaming(self, client: AsyncOpenAI, params: dict[str, Any]) -> LLMResponse:
        """Non-streaming chat completion."""
        response = await client.chat.completions.create(**params)
        choice = response.choices[0]
        message = choice.message
        usage = self._extract_usage(response)
        tool_calls = self._extract_tool_calls(message)
        content = message.content or ""

        # 某些 OpenAI 兼容网关在非流式 chat.completions 中会丢失正文，
        # 但同请求的流式增量仍然正常；此时做一次受限回退恢复文本。
        if self._should_recover_empty_content(content=content, tool_calls=tool_calls, usage=usage):
            recovered_content = await self._recover_content_via_stream(client, params)
            if recovered_content:
                logger.warning(
                    "Recovered empty non-streaming content via streaming fallback",
                    extra={
                        "provider": self.name,
                        "model_id": self.model_id,
                        "base_url": self._base_url,
                    },
                )
                content = recovered_content

        return LLMResponse(
            content=content,
            model=response.model,
            usage=usage,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
        )

    def _extract_usage(self, response: Any) -> dict[str, int] | None:
        """Extract usage from an OpenAI-style response."""
        if not response.usage:
            return None
        return {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    def _extract_tool_calls(self, message: Any) -> list[dict[str, Any]] | None:
        """Extract OpenAI function calls from a message."""
        raw_tool_calls = getattr(message, "tool_calls", None)
        if not raw_tool_calls:
            return None

        return [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in raw_tool_calls
        ]

    def _should_recover_empty_content(
        self,
        *,
        content: str,
        tool_calls: list[dict[str, Any]] | None,
        usage: dict[str, int] | None,
    ) -> bool:
        """Return whether an empty non-streaming response should retry via stream."""
        if content or tool_calls:
            return False
        if not usage:
            return False
        return usage.get("completion_tokens", 0) > 0

    async def _recover_content_via_stream(
        self,
        client: AsyncOpenAI,
        params: dict[str, Any],
    ) -> str:
        """Reconstruct content from streaming deltas for buggy compatible gateways."""
        stream_params = {**params, "stream": True}
        response = await client.chat.completions.create(**stream_params)
        chunks: list[str] = []

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            chunks.append(delta.content or "")

        return "".join(chunks)

    async def _chat_streaming(
        self, client: AsyncOpenAI, params: dict[str, Any]
    ) -> AsyncGenerator[StreamingLLMResponse, None]:
        """Streaming chat completion."""
        params["stream"] = True
        response = await client.chat.completions.create(**params)

        async for chunk in response:
            if chunk.choices:
                delta = chunk.choices[0].delta
                is_finished = chunk.choices[0].finish_reason is not None

                yield StreamingLLMResponse(
                    content=delta.content or "",
                    is_finished=is_finished,
                    model=chunk.model,
                )

    async def health_check(self) -> bool:
        """Check if provider is healthy."""
        if not self.is_available:
            return False

        try:
            client = self._get_client()
            # Try a simple models list request
            await client.models.list()
            return True
        except Exception:
            return False
