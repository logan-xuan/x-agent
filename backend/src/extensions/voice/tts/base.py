"""Abstract base class for TTS providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import SpeechSynthesisRequest, SpeechSynthesisResult


class TTSProvider(ABC):
    """Common interface for all text-to-speech providers."""

    provider_name: str = ""

    @abstractmethod
    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        """Synthesize an audio asset from text."""
        raise NotImplementedError
