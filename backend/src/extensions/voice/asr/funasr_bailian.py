"""Alibaba Bailian FunASR provider."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import websockets

from ....config.manager import get_config
from ....utils.logger import get_logger
from ..schemas import AudioTranscriptionRequest, AudioTranscriptionResult
from .base import ASRProvider

logger = get_logger(__name__)


class FunASRBailianASRProvider(ASRProvider):
    """Builtin ASR provider backed by Alibaba Bailian Fun-ASR."""

    provider_name = "funasr-bailian"
    _REALTIME_MODEL_FALLBACK = "fun-asr-realtime-2026-02-28"
    _DIRECT_FORMATS = {"mp3", "wav", "aac", "amr"}

    async def transcribe(self, request: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        provider_config = get_config().voice.funasr_bailian
        api_key = provider_config.api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("FunASR Bailian provider requires an API key")
        model_name = self._resolve_model_name(str(provider_config.model))
        audio_bytes, audio_format, sample_rate_hz = await asyncio.to_thread(
            self._load_audio_payload,
            request,
            provider_config,
        )
        task_id = uuid4().hex
        run_task_payload = {
            "header": {
                "action": "run-task",
                "task_id": task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": model_name,
                "input": {},
                "parameters": {
                    "format": audio_format,
                    "sample_rate": sample_rate_hz,
                },
            },
        }

        transcript_texts: list[str] = []
        segments: list[dict[str, object]] = []
        latest_partial_text = ""
        usage: dict[str, object] | None = None

        async with websockets.connect(
            provider_config.websocket_url,
            additional_headers={"Authorization": f"bearer {api_key}"},
            proxy=None,
            open_timeout=provider_config.timeout,
            close_timeout=provider_config.timeout,
            max_size=None,
        ) as websocket:
            await websocket.send(json.dumps(run_task_payload, ensure_ascii=False))
            await self._wait_for_task_started(websocket, provider_config.timeout)

            chunk_size_bytes = int(provider_config.chunk_size_bytes)
            chunk_interval_ms = int(provider_config.chunk_interval_ms)
            for offset in range(0, len(audio_bytes), chunk_size_bytes):
                await websocket.send(audio_bytes[offset : offset + chunk_size_bytes])
                if chunk_interval_ms > 0:
                    await asyncio.sleep(chunk_interval_ms / 1000)

            await websocket.send(
                json.dumps(
                    {
                        "header": {
                            "action": "finish-task",
                            "task_id": task_id,
                            "streaming": "duplex",
                        },
                        "payload": {"input": {}},
                    },
                    ensure_ascii=False,
                )
            )

            while True:
                raw_message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=provider_config.timeout,
                )
                message = json.loads(raw_message)
                event = str(message.get("header", {}).get("event", ""))
                if event == "task-finished":
                    usage_payload = message.get("payload", {}).get("usage")
                    if isinstance(usage_payload, dict):
                        usage = dict(usage_payload)
                    break
                if event == "task-failed":
                    raise RuntimeError(self._format_task_failed_message(message))
                if event != "result-generated":
                    continue

                sentence = message.get("payload", {}).get("output", {}).get("sentence", {})
                if not isinstance(sentence, dict):
                    continue
                if sentence.get("heartbeat"):
                    continue

                text = str(sentence.get("text", "")).strip()
                if text:
                    latest_partial_text = text
                    if sentence.get("sentence_end"):
                        transcript_texts.append(text)
                if "begin_time" in sentence or "end_time" in sentence or "words" in sentence:
                    segments.append(dict(sentence))

        combined_text = "\n".join(text for text in transcript_texts if text).strip()
        if not combined_text:
            combined_text = latest_partial_text.strip()
        if not combined_text:
            logger.warning(
                "FunASR returned no transcript text",
                extra={
                    "provider": self.provider_name,
                    "task_id": task_id,
                    "asset_id": request.asset.asset_id,
                    "format": audio_format,
                },
            )
            raise RuntimeError("FunASR returned no transcript text")

        return AudioTranscriptionResult(
            provider=self.provider_name,
            text=combined_text,
            language=request.language_hint or self._default_language_hint(provider_config),
            asset=request.asset,
            segments=segments,
            metadata={
                "task_id": task_id,
                "model": model_name,
                "audio_format": audio_format,
                "sample_rate_hz": sample_rate_hz,
                "usage": usage or {},
            },
        )

    def _default_language_hint(self, provider_config: object) -> str | None:
        hints = list(getattr(provider_config, "language_hints", []) or [])
        return str(hints[0]) if hints else None

    def _resolve_model_name(self, configured_model: str) -> str:
        normalized = configured_model.strip()
        if not normalized or "realtime" not in normalized:
            return self._REALTIME_MODEL_FALLBACK
        return normalized

    def _load_audio_payload(
        self,
        request: AudioTranscriptionRequest,
        provider_config: object,
    ) -> tuple[bytes, str, int]:
        source_path = request.asset.storage_path
        probe = self._probe_audio(source_path)
        target_sample_rate = int(getattr(provider_config, "sample_rate_hz", 16000))
        audio_format = self._resolve_audio_format(request, probe)
        sample_rate = int(probe.get("sample_rate") or 0)
        if audio_format in self._DIRECT_FORMATS and sample_rate == target_sample_rate:
            return source_path.read_bytes(), audio_format, target_sample_rate
        return self._transcode_to_wav(source_path, target_sample_rate), "wav", target_sample_rate

    def _resolve_audio_format(
        self,
        request: AudioTranscriptionRequest,
        probe: dict[str, int | str],
    ) -> str:
        format_candidates = [
            str(request.asset.format or "").lower(),
            str(probe.get("format") or "").lower(),
            request.asset.mime_type.lower().split("/", 1)[-1].split(";", 1)[0].strip(),
        ]
        for candidate in format_candidates:
            if candidate in self._DIRECT_FORMATS:
                return candidate
        return "wav"

    def _probe_audio(self, source_path: Path) -> dict[str, int | str]:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
        payload = json.loads(result.stdout)
        streams = list(payload.get("streams", []) or [])
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            {},
        )
        format_name = str(payload.get("format", {}).get("format_name", "")).split(",", 1)[0]
        sample_rate = int(audio_stream.get("sample_rate") or 0)
        channels = int(audio_stream.get("channels") or 0)
        return {
            "format": format_name,
            "sample_rate": sample_rate,
            "channels": channels,
        }

    def _transcode_to_wav(self, source_path: Path, sample_rate_hz: int) -> bytes:
        try:
            with tempfile.TemporaryDirectory(prefix="funasr-realtime-") as temp_dir:
                output_path = Path(temp_dir) / "normalized.wav"
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(source_path),
                        "-ac",
                        "1",
                        "-ar",
                        str(sample_rate_hz),
                        "-f",
                        "wav",
                        str(output_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        f"ffmpeg transcode failed: {result.stderr.strip() or result.stdout.strip()}"
                    )
                return output_path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is required to normalize unsupported audio formats") from exc

    async def _wait_for_task_started(self, websocket, timeout: int) -> None:  # type: ignore[no-untyped-def]
        while True:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            message = json.loads(raw_message)
            event = str(message.get("header", {}).get("event", ""))
            if event == "task-started":
                return
            if event == "task-failed":
                raise RuntimeError(self._format_task_failed_message(message))

    @staticmethod
    def _format_task_failed_message(message: dict[str, object]) -> str:
        header = message.get("header", {})
        payload = message.get("payload", {})
        error_code = ""
        error_message = ""
        if isinstance(header, dict):
            error_code = str(header.get("error_code", "") or "")
            error_message = str(header.get("error_message", "") or "")
        details = payload if isinstance(payload, dict) else {}
        parts = ["FunASR realtime task failed"]
        if error_code:
            parts.append(f"[{error_code}]")
        if error_message:
            parts.append(error_message)
        if details:
            parts.append(str(details))
        return " ".join(parts)
