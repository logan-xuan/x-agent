"""Voice extension public exports."""

from .schemas import (
    AudioAssetRef,
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
)
from .service import VoiceService, get_voice_service

__all__ = [
    "AudioAssetRef",
    "AudioTranscriptionRequest",
    "AudioTranscriptionResult",
    "SpeechSynthesisRequest",
    "SpeechSynthesisResult",
    "VoiceService",
    "get_voice_service",
]
