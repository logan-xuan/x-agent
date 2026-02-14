"""OpenAI-compatible LLM provider implementation."""

import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI

from .provider import LLMProvider, LLMResponse, StreamingLLMResponse


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
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        **kwargs: Any
    ) -> LLMResponse | AsyncGenerator[StreamingLLMResponse, None]:
        """Send chat completion request."""
        if not self.is_available:
            raise RuntimeError(f"Provider {self.name} is not available")
        
        client = self._get_client()
        
        # Merge default and custom parameters
        params = {
            "model": self.model_id,
            "messages": messages,
            "stream": stream,
            **kwargs
        }
        
        if stream:
            return self._chat_streaming(client, params)
        else:
            return await self._chat_non_streaming(client, params)
    
    async def _chat_non_streaming(
        self,
        client: AsyncOpenAI,
        params: dict[str, Any]
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        response = await client.chat.completions.create(**params)
        
        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else None,
        )
    
    async def _chat_streaming(
        self,
        client: AsyncOpenAI,
        params: dict[str, Any]
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
