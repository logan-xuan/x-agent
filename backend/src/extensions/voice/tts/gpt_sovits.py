"""GPT-SoVITS TTS provider placeholder."""

from __future__ import annotations

import httpx

from ....config.manager import get_config
from ..assets.storage import AudioAssetStore, get_audio_asset_store
from ..schemas import SpeechSynthesisRequest, SpeechSynthesisResult
from .base import TTSProvider


class GPTSoVITSTTSProvider(TTSProvider):
    """Builtin GPT-SoVITS TTS provider."""

    provider_name = "gpt-sovits"

    def __init__(self, *, asset_store: AudioAssetStore | None = None) -> None:
        self._asset_store = asset_store or get_audio_asset_store()

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        provider_config = get_config().voice.gpt_sovits
        if not provider_config.ref_audio_path or not provider_config.ref_text:
            raise RuntimeError("GPT-SoVITS requires ref_audio_path and ref_text to be configured")

        payload = {
            "text": request.text,
            "text_lang": provider_config.text_lang,
            "ref_audio_path": provider_config.ref_audio_path,
            "prompt_text": provider_config.ref_text,
            "prompt_lang": provider_config.prompt_lang,
            "top_k": 5,
            "top_p": 1.0,
            "temperature": 1.0,
            "text_split_method": "cut5",
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": True,
            "return_fragment": False,
        }

        async with httpx.AsyncClient(timeout=provider_config.timeout) as client:
            response = await client.post(str(provider_config.endpoint), json=payload)
            response.raise_for_status()
            audio_bytes = response.content
            mime_type = response.headers.get("content-type", "audio/wav").split(";", 1)[0]

        audio_format = "wav" if mime_type == "audio/wav" else request.response_format
        stored = await self._asset_store.save_generated_audio(
            agent_id=str(request.metadata.get("agent_id") or "main-agent"),
            session_id=str(request.metadata.get("session_id") or "voice-session"),
            provider=self.provider_name,
            voice=request.voice,
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            audio_format=audio_format,
        )
        return SpeechSynthesisResult(
            provider=self.provider_name,
            voice=request.voice,
            asset=stored.to_ref(source="generated"),
        )
