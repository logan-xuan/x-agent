"""Whisper-compatible ASR provider placeholder."""

from __future__ import annotations

import httpx

from ....config.manager import get_config
from ..schemas import AudioTranscriptionRequest, AudioTranscriptionResult
from .base import ASRProvider


class WhisperCompatibleASRProvider(ASRProvider):
    """Builtin Whisper-compatible ASR provider."""

    provider_name = "whisper-compatible"

    async def transcribe(self, request: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        provider_config = get_config().voice.whisper_compatible
        headers: dict[str, str] = {}
        auth_token = provider_config.auth_token.get_secret_value()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        with request.asset.storage_path.open("rb") as audio_file:
            files = {
                "file": (
                    request.asset.storage_path.name,
                    audio_file,
                    request.asset.mime_type,
                )
            }
            data: dict[str, object] = {
                "model": provider_config.default_model,
                "response_format": provider_config.response_format,
            }
            if request.language_hint:
                data["language"] = request.language_hint
            if request.prompt:
                data["prompt"] = request.prompt

            async with httpx.AsyncClient(timeout=provider_config.timeout) as client:
                response = await client.post(
                    str(provider_config.endpoint),
                    data=data,
                    files=files,
                    headers=headers,
                )
                response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type == "application/json":
            payload = response.json()
            text = str(payload.get("text", ""))
            language = payload.get("language")
            segments = list(payload.get("segments", []) or [])
        else:
            text = response.text
            language = request.language_hint
            segments = []

        return AudioTranscriptionResult(
            provider=self.provider_name,
            text=text,
            language=str(language) if language is not None else None,
            asset=request.asset,
            segments=segments,
            metadata={"endpoint": str(provider_config.endpoint)},
        )
