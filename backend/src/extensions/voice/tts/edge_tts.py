"""Edge TTS provider placeholder."""

from __future__ import annotations

import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

from ....config.manager import get_config
from ....utils.logger import get_logger
from ..assets.storage import AudioAssetStore, get_audio_asset_store
from ..schemas import SpeechSynthesisRequest, SpeechSynthesisResult
from .base import TTSProvider

logger = get_logger(__name__)


_EDGE_TTS_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


def _normalize_text_for_edge_tts(text: str) -> str:
    """Remove markdown and symbols that commonly break edge-tts synthesis."""
    normalized = text
    normalized = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", normalized)
    normalized = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", normalized)
    normalized = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", normalized)
    normalized = re.sub(r"[*_~#>]+", " ", normalized)
    normalized = _EDGE_TTS_EMOJI_PATTERN.sub(" ", normalized)
    normalized = normalized.replace("\uFE0F", " ")
    normalized = normalized.replace("°C", "摄氏度")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _plain_text_fallback_for_edge_tts(text: str) -> str:
    """Convert text into a punctuation-light plain sentence for last-resort synthesis."""
    plain = _normalize_text_for_edge_tts(text)
    plain = re.sub(r"[^\w\u4e00-\u9fff]+", " ", plain, flags=re.UNICODE)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


class EdgeTTSProvider(TTSProvider):
    """Builtin Edge TTS provider."""

    provider_name = "edge"

    def __init__(self, *, asset_store: AudioAssetStore | None = None) -> None:
        self._asset_store = asset_store or get_audio_asset_store()

    @staticmethod
    def _run_edge_tts(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

    async def synthesize(self, request: SpeechSynthesisRequest) -> SpeechSynthesisResult:
        if request.response_format != "mp3":
            raise ValueError("Edge TTS currently only supports mp3 output")

        voice = request.voice or get_config().voice.edge_default_voice
        rate_percent = 0 if request.speech_rate is None else int((request.speech_rate - 1.0) * 100)
        normalized_text = _normalize_text_for_edge_tts(request.text)
        plain_text = _plain_text_fallback_for_edge_tts(request.text)

        with tempfile.TemporaryDirectory(prefix="edge-tts-") as tmp_dir:
            output_path = Path(tmp_dir) / "speech.mp3"
            def build_cmd(text: str) -> list[str]:
                return [
                    "edge-tts",
                    "--voice",
                    voice,
                    "--rate",
                    f"{rate_percent:+d}%",
                    "--write-media",
                    str(output_path),
                    "--text",
                    text,
                ]

            try:
                result = await asyncio.to_thread(self._run_edge_tts, build_cmd(request.text))
            except FileNotFoundError as exc:
                raise RuntimeError("edge-tts command is not installed") from exc

            should_retry_with_normalized = (
                result.returncode != 0
                and normalized_text
                and normalized_text != request.text
                and "NoAudioReceived" in (result.stderr or "")
            )
            if should_retry_with_normalized:
                logger.warning(
                    "edge-tts failed for original text, retrying with normalized plain text",
                    extra={
                        "voice": voice,
                        "original_length": len(request.text),
                        "normalized_length": len(normalized_text),
                    },
                )
                result = await asyncio.to_thread(self._run_edge_tts, build_cmd(normalized_text))

            should_retry_with_plain = (
                result.returncode != 0
                and plain_text
                and plain_text not in {request.text, normalized_text}
                and "NoAudioReceived" in (result.stderr or "")
            )
            if should_retry_with_plain:
                logger.warning(
                    "edge-tts failed after normalization, retrying with punctuation-stripped plain text",
                    extra={
                        "voice": voice,
                        "plain_length": len(plain_text),
                    },
                )
                result = await asyncio.to_thread(self._run_edge_tts, build_cmd(plain_text))

            if result.returncode != 0:
                raise RuntimeError(f"edge-tts failed: {result.stderr}")

            audio_bytes = output_path.read_bytes()

        stored = await self._asset_store.save_generated_audio(
            agent_id=str(request.metadata.get("agent_id") or "main-agent"),
            session_id=str(request.metadata.get("session_id") or "voice-session"),
            provider=self.provider_name,
            voice=voice,
            audio_bytes=audio_bytes,
            mime_type="audio/mpeg",
            audio_format="mp3",
        )
        return SpeechSynthesisResult(
            provider=self.provider_name,
            voice=voice,
            asset=stored.to_ref(source="generated"),
        )
