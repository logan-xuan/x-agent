"""LLM Provider abstract base class."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Standard LLM response."""
    content: str | None
    model: str
    usage: dict[str, int] | None = None
    metadata: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None  # OpenAI function calls
    finish_reason: str | None = None  # "stop", "tool_calls", etc.


@dataclass
class StreamingLLMResponse:
    """Streaming LLM response chunk."""
    content: str
    is_finished: bool = False
    model: str | None = None
    usage: dict[str, int] | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM providers (OpenAI, Bailian, etc.) must implement this interface.
    """
    
    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize provider with configuration.
        
        Args:
            config: Provider configuration from x-agent.yaml
        """
        self.config = config
        self.name = config.get("name", "unknown")
        self.model_id = config.get("model_id", "unknown")
        self.timeout = config.get("timeout", 30.0)
        self.max_retries = config.get("max_retries", 2)
    
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
        **kwargs: Any
    ) -> LLMResponse | AsyncGenerator[StreamingLLMResponse, None]:
        """Send chat completion request.
        
        Args:
            messages: List of messages in OpenAI format
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters
            
        Returns:
            Either LLMResponse (non-streaming) or AsyncGenerator (streaming)
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy.
        
        Returns:
            True if provider is available and responding
        """
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available.
        
        Returns:
            True if provider has valid configuration
        """
        pass
