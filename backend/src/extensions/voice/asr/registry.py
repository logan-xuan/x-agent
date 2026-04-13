"""Registry for speech-to-text providers."""

from __future__ import annotations

from .base import ASRProvider
from .funasr_bailian import FunASRBailianASRProvider
from .openai_asr import OpenAIASRProvider
from .whisper_compatible import WhisperCompatibleASRProvider


class ASRProviderRegistry:
    """Registry for named ASR providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ASRProvider] = {}

    def register(self, provider: ASRProvider) -> None:
        provider_name = provider.provider_name
        if not provider_name:
            raise ValueError("ASR provider must declare provider_name")
        if provider_name in self._providers:
            raise ValueError(f"ASR provider already registered: {provider_name}")
        self._providers[provider_name] = provider

    def get(self, provider_name: str) -> ASRProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise LookupError(f"Unknown ASR provider: {provider_name}") from exc

    def list_provider_names(self) -> list[str]:
        return sorted(self._providers)


def create_default_asr_registry() -> ASRProviderRegistry:
    """Create the default registry with builtin ASR providers."""
    registry = ASRProviderRegistry()
    registry.register(FunASRBailianASRProvider())
    registry.register(OpenAIASRProvider())
    registry.register(WhisperCompatibleASRProvider())
    return registry
