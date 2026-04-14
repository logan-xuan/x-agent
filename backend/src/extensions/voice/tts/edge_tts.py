"""Edge TTS provider placeholder."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path

from ....config.manager import get_config
from ....utils.logger import get_logger
from ..assets.storage import AudioAssetStore, get_audio_asset_store
from ..schemas import SpeechSynthesisRequest, SpeechSynthesisResult
from ..text_normalizer import normalize_text_for_tts, plain_text_fallback_for_tts
from .base import TTSProvider

logger = get_logger(__name__)


def _normalize_text_for_edge_tts(text: str) -> str:
    """Remove markdown and symbols that commonly break edge-tts synthesis."""
    return normalize_text_for_tts(text)


def _plain_text_fallback_for_edge_tts(text: str) -> str:
    """Convert text into a punctuation-light plain sentence for last-resort synthesis."""
    return plain_text_fallback_for_tts(text)


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

        config = get_config().voice
        voice = request.voice or config.tts.get_default_voice(self.provider_name)
        rate_percent = 0 if request.speech_rate is None else int((request.speech_rate - 1.0) * 100)
        original_source_text = str(request.metadata.get("tts_original_text") or "").strip()
        normalized_text = _normalize_text_for_edge_tts(request.text)
        plain_text = _plain_text_fallback_for_edge_tts(request.text)
        original_rule_text = _normalize_text_for_edge_tts(original_source_text) if original_source_text else ""
        synthesis_text = normalized_text or request.text

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
                result = await asyncio.to_thread(self._run_edge_tts, build_cmd(synthesis_text))
            except FileNotFoundError as exc:
                raise RuntimeError("edge-tts command is not installed") from exc

            should_retry_with_plain = (
                result.returncode != 0
                and plain_text
                and plain_text not in {request.text, synthesis_text}
                and "NoAudioReceived" in (result.stderr or "")
            )
            if should_retry_with_plain:
                logger.warning(
                    "edge-tts failed after text normalization, retrying with punctuation-stripped plain text",
                    extra={
                        "voice": voice,
                        "normalized_length": len(synthesis_text),
                        "plain_length": len(plain_text),
                    },
                )
                result = await asyncio.to_thread(self._run_edge_tts, build_cmd(plain_text))

            should_retry_with_original_rules = (
                result.returncode != 0
                and original_rule_text
                and original_rule_text not in {request.text, synthesis_text, plain_text}
                and "NoAudioReceived" in (result.stderr or "")
            )
            if should_retry_with_original_rules:
                logger.warning(
                    "edge-tts failed for rewritten text, retrying with rule-normalized original text",
                    extra={
                        "voice": voice,
                        "original_rule_length": len(original_rule_text),
                    },
                )
                result = await asyncio.to_thread(
                    self._run_edge_tts,
                    build_cmd(original_rule_text),
                )

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
