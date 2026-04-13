"""Registry for text-to-speech providers."""

from __future__ import annotations

from .base import TTSProvider
from .edge_tts import EdgeTTSProvider
from .gpt_sovits import GPTSoVITSTTSProvider
from .openai_tts import OpenAITTSProvider


class TTSProviderRegistry:
    """Registry for named TTS providers."""

    def __init__(self) -> None:
        self._providers: dict[str, TTSProvider] = {}

    def register(self, provider: TTSProvider) -> None:
        provider_name = provider.provider_name
        if not provider_name:
            raise ValueError("TTS provider must declare provider_name")
        if provider_name in self._providers:
            raise ValueError(f"TTS provider already registered: {provider_name}")
        self._providers[provider_name] = provider

    def get(self, provider_name: str) -> TTSProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise LookupError(f"Unknown TTS provider: {provider_name}") from exc

    def list_provider_names(self) -> list[str]:
        return sorted(self._providers)


def create_default_tts_registry() -> TTSProviderRegistry:
    """Create the default registry with builtin TTS providers."""
    registry = TTSProviderRegistry()
    registry.register(EdgeTTSProvider())
    registry.register(OpenAITTSProvider())
    registry.register(GPTSoVITSTTSProvider())
    return registry
