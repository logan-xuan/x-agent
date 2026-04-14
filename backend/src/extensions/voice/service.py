"""Voice service facade for TTS and ASR orchestration."""

from __future__ import annotations

from .asr.registry import ASRProviderRegistry, create_default_asr_registry
from .schemas import (
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
)
from .speech_rewriter import SpeechTextRewriter
from .tts.registry import TTSProviderRegistry, create_default_tts_registry


class VoiceService:
    """Lightweight facade over TTS and ASR provider registries."""

    def __init__(
        self,
        *,
        tts_registry: TTSProviderRegistry | None = None,
        asr_registry: ASRProviderRegistry | None = None,
        speech_rewriter: SpeechTextRewriter | None = None,
    ) -> None:
        self._tts_registry = tts_registry or create_default_tts_registry()
        self._asr_registry = asr_registry or create_default_asr_registry()
        self._speech_rewriter = speech_rewriter or SpeechTextRewriter()

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        provider = self._tts_registry.get(request.provider)
        normalized_text = await self._speech_rewriter.rewrite(
            request.text,
            metadata=request.metadata,
        ) or request.text.strip()
        normalized_request = request.model_copy(
            update={
                "text": normalized_text,
                "metadata": {
                    **request.metadata,
                    "tts_original_text": request.text,
                },
            }
        )
        return await provider.synthesize(normalized_request)

    async def transcribe(self, request: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        provider = self._asr_registry.get(request.provider)
        return await provider.transcribe(request)


_voice_service: VoiceService | None = None


def get_voice_service() -> VoiceService:
    """Return the shared voice service instance."""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service
