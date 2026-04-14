"""OpenAI TTS provider placeholder."""

from __future__ import annotations

import asyncio

from openai import OpenAI

from ....config.manager import get_config
from ..assets.storage import AudioAssetStore, get_audio_asset_store
from ..schemas import SpeechSynthesisRequest, SpeechSynthesisResult
from .base import TTSProvider


class OpenAITTSProvider(TTSProvider):
    """Builtin OpenAI TTS provider."""

    provider_name = "openai"

    def __init__(self, *, asset_store: AudioAssetStore | None = None) -> None:
        self._asset_store = asset_store or get_audio_asset_store()

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        config = get_config().voice
        voice_config = config.openai
        api_key = voice_config.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("OpenAI voice provider requires an API key")

        client = OpenAI(
            api_key=api_key,
            base_url=str(voice_config.base_url),
            timeout=voice_config.timeout,
        )

        voice = request.voice or config.tts.get_default_voice(self.provider_name)

        def _create_speech() -> bytes:
            kwargs: dict[str, object] = {
                "input": request.text,
                "model": voice_config.tts_model,
                "voice": voice,
                "response_format": request.response_format,
            }
            if request.speech_rate is not None:
                kwargs["speed"] = request.speech_rate
            response = client.audio.speech.create(**kwargs)
            return response.read()

        audio_bytes = await asyncio.to_thread(_create_speech)
        mime_type = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "flac": "audio/flac",
            "aac": "audio/aac",
            "opus": "audio/ogg",
            "pcm": "audio/L16",
        }.get(request.response_format, "application/octet-stream")

        stored = await self._asset_store.save_generated_audio(
            agent_id=str(request.metadata.get("agent_id") or "main-agent"),
            session_id=str(request.metadata.get("session_id") or "voice-session"),
            provider=self.provider_name,
            voice=voice,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            audio_format=request.response_format,
        )
        return SpeechSynthesisResult(
            provider=self.provider_name,
            voice=voice,
            asset=stored.to_ref(source="generated"),
            metadata={"model": voice_config.tts_model},
        )
