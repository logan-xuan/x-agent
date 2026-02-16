"""阿里云百炼 LLM provider implementation."""

import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from openai import AsyncOpenAI

from .provider import LLMProvider, LLMResponse, StreamingLLMResponse


class BailianProvider(LLMProvider):
    """阿里云百炼 (Bailian) provider.
    
    百炼平台提供 OpenAI 兼容的 API，因此复用 OpenAI SDK。
    文档: https://help.aliyun.com/document_detail/2589301.html
    """
    
    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize Bailian provider."""
        super().__init__(config)
        self._client: AsyncOpenAI | None = None
        self._api_key = self._get_api_key()
        self._base_url = config.get("base_url", self.DEFAULT_BASE_URL)
    
    def _get_api_key(self) -> str | None:
        """Get API key from config or environment."""
        # Get from config
        api_key = self.config.get("api_key")
        if api_key:
            if hasattr(api_key, "get_secret_value"):
                return api_key.get_secret_value()
            return str(api_key)
        
        # Fallback to environment variable
        return os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
    
    @property
    def is_available(self) -> bool:
        """Check if provider has valid configuration."""
        return bool(self._api_key and self._base_url)
    
    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI-compatible client for Bailian."""
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
        """Send chat completion request to Bailian."""
        if not self.is_available:
            raise RuntimeError(f"Provider {self.name} is not available")
        
        client = self._get_client()
        
        # Bailian-specific parameter handling
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
        
        choice = response.choices[0]
        message = choice.message
        
        # Extract tool calls if present
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        
        return LLMResponse(
            content=message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else None,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
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
        """Check if Bailian provider is healthy."""
        if not self.is_available:
            return False
        
        try:
            client = self._get_client()
            # Try a simple chat completion as health check
            # Some Bailian endpoints don't support /v1/models
            response = await client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False
