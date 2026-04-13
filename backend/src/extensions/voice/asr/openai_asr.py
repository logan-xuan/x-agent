"""OpenAI ASR provider placeholder."""

from __future__ import annotations

import asyncio

from openai import OpenAI

from ....config.manager import get_config
from ..schemas import AudioTranscriptionRequest, AudioTranscriptionResult
from .base import ASRProvider


class OpenAIASRProvider(ASRProvider):
    """Builtin OpenAI ASR provider."""

    provider_name = "openai"

    async def transcribe(self, request: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        provider_config = get_config().voice.openai
        api_key = provider_config.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("OpenAI voice provider requires an API key")

        client = OpenAI(
            api_key=api_key,
            base_url=str(provider_config.base_url),
            timeout=provider_config.timeout,
        )

        def _transcribe() -> object:
            with request.asset.storage_path.open("rb") as audio_file:
                kwargs: dict[str, object] = {
                    "file": audio_file,
                    "model": provider_config.asr_model,
                }
                if request.language_hint:
                    kwargs["language"] = request.language_hint
                if request.prompt:
                    kwargs["prompt"] = request.prompt
                return client.audio.transcriptions.create(**kwargs)

        response = await asyncio.to_thread(_transcribe)
        return AudioTranscriptionResult(
            provider=self.provider_name,
            text=response.text,
            language=getattr(response, "language", request.language_hint),
            asset=request.asset,
            segments=list(getattr(response, "segments", []) or []),
            metadata={"model": provider_config.asr_model},
        )
