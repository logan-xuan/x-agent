"""Abstract base class for ASR providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import AudioTranscriptionRequest, AudioTranscriptionResult


class ASRProvider(ABC):
    """Common interface for all speech-to-text providers."""

    provider_name: str = ""

    @abstractmethod
    async def transcribe(self, request: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        """Transcribe the given audio asset."""
        raise NotImplementedError
