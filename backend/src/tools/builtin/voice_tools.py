"""Built-in voice tools exposed to the agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config.manager import get_config
from ...conversation.context import get_current_context
from ...extensions.voice import (
    AudioAssetRef,
    AudioTranscriptionRequest,
    SpeechSynthesisRequest,
    get_voice_service,
)
from ...extensions.voice.assets import AudioAssetStore, get_audio_asset_store
from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult


def _resolve_agent_session() -> tuple[str, str, dict[str, Any]]:
    context = get_current_context()
    if context is None:
        return "main-agent", "", {}
    metadata = context.metadata if isinstance(context.metadata, dict) else {}
    return context.agent_id or "main-agent", context.session_id or "", dict(metadata)


def _resolve_agent_voice_defaults(agent_id: str) -> tuple[str, str | None, str]:
    config = get_config()
    global_default_provider = str(config.voice.tts.default_provider)
    global_default_voice = config.voice.tts.get_default_voice(global_default_provider)
    agent_cfg = config.multi_agent.get_agent(agent_id)
    if agent_cfg is None:
        return global_default_provider, global_default_voice, "openai"

    tts_provider = str(agent_cfg.voice.tts.provider or global_default_provider)
    tts_voice = agent_cfg.voice.tts.voice or config.voice.tts.get_default_voice(tts_provider)
    asr_provider = str(agent_cfg.voice.asr_provider or "openai")
    return tts_provider, tts_voice, asr_provider


def _audio_reply_payload(
    *,
    asset: AudioAssetRef,
    provider: str,
    voice: str | None,
) -> dict[str, Any]:
    return {
        "asset_id": asset.asset_id,
        "public_url": asset.public_url,
        "playback_url": asset.playback_url,
        "mime_type": asset.mime_type,
        "format": asset.format,
        "provider": provider,
        "voice": voice,
    }


def _guess_audio_mime_type(path: Path) -> tuple[str, str] | None:
    suffix = path.suffix.lower().lstrip(".")
    mapping = {
        "mp3": ("audio/mpeg", "mp3"),
        "wav": ("audio/wav", "wav"),
        "ogg": ("audio/ogg", "ogg"),
        "webm": ("audio/webm", "webm"),
        "m4a": ("audio/mp4", "m4a"),
        "flac": ("audio/flac", "flac"),
        "aac": ("audio/aac", "aac"),
        "amr": ("audio/amr", "amr"),
    }
    return mapping.get(suffix)


class SynthesizeSpeechTool(BaseTool):
    """Generate a speech asset from text."""

    def __init__(self, *, voice_service=None) -> None:
        self._voice_service = voice_service or get_voice_service()

    @property
    def name(self) -> str:
        return "synthesize_speech"

    @property
    def description(self) -> str:
        return (
            "把文本合成为可播放音频。"
            "当用户明确要求语音版、音频回复、播报版时使用。"
            "工具结果会被挂到最终 assistant 消息的 audio_reply。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="text",
                type=ToolParameterType.STRING,
                description="要合成的文本内容。",
                required=True,
                min_length=1,
            ),
            ToolParameter(
                name="provider",
                type=ToolParameterType.STRING,
                description="可选的 TTS provider，未指定时使用当前 Agent 默认值。",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="voice",
                type=ToolParameterType.STRING,
                description="可选的音色或 speaker，未指定时使用当前 provider 默认值。",
                required=False,
                default=None,
            ),
        ]

    async def execute(
        self,
        text: str,
        provider: str | None = None,
        voice: str | None = None,
    ) -> ToolResult:
        agent_id, session_id, _metadata = _resolve_agent_session()
        default_provider, default_voice, _default_asr = _resolve_agent_voice_defaults(agent_id)
        final_provider = provider or default_provider
        final_voice = voice or default_voice

        try:
            result = await self._voice_service.synthesize(
                SpeechSynthesisRequest(
                    text=text,
                    provider=final_provider,
                    voice=final_voice,
                    metadata={
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "tool_name": self.name,
                    },
                )
            )
        except Exception as exc:
            return ToolResult.error_result(f"Failed to synthesize speech: {exc}")

        audio_reply = _audio_reply_payload(
            asset=result.asset,
            provider=result.provider,
            voice=result.voice,
        )
        return ToolResult.ok(
            "\n".join(
                [
                    "已生成语音。",
                    f"Provider: {result.provider}",
                    f"Voice: {result.voice or ''}".rstrip(),
                    f"Playback: {result.asset.playback_url or result.asset.public_url or ''}".rstrip(),
                ]
            ).strip(),
            audio_reply=audio_reply,
            provider=result.provider,
            voice=result.voice,
            agent_id=agent_id,
            session_id=session_id,
        )


class TranscribeAudioTool(BaseTool):
    """Transcribe an audio asset to text."""

    def __init__(self, *, voice_service=None, asset_store: AudioAssetStore | None = None) -> None:
        self._voice_service = voice_service or get_voice_service()
        self._asset_store = asset_store or get_audio_asset_store()

    @property
    def name(self) -> str:
        return "transcribe_audio"

    @property
    def description(self) -> str:
        return (
            "把音频转写成文本。"
            "可处理当前请求中的语音输入、项目内已保存的 audio asset，或本地音频文件路径。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="asset_id",
                type=ToolParameterType.STRING,
                description="项目内已保存音频资产的 asset_id。未指定时优先使用当前请求音频。",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="file_path",
                type=ToolParameterType.STRING,
                description="本地音频文件路径。仅在无法提供 asset_id 时使用。",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="provider",
                type=ToolParameterType.STRING,
                description="可选的 ASR provider，未指定时使用当前 Agent 默认值。",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="language_hint",
                type=ToolParameterType.STRING,
                description="可选语言提示，如 zh、en、ja。",
                required=False,
                default=None,
            ),
            ToolParameter(
                name="prompt",
                type=ToolParameterType.STRING,
                description="可选 ASR prompt。",
                required=False,
                default=None,
            ),
        ]

    async def execute(
        self,
        asset_id: str | None = None,
        file_path: str | None = None,
        provider: str | None = None,
        language_hint: str | None = None,
        prompt: str | None = None,
    ) -> ToolResult:
        agent_id, session_id, metadata = _resolve_agent_session()
        _default_tts_provider, _default_tts_voice, default_asr_provider = _resolve_agent_voice_defaults(
            agent_id
        )
        resolved_asset = await self._resolve_asset_ref(
            asset_id=asset_id,
            file_path=file_path,
            metadata=metadata,
        )
        if resolved_asset is None:
            return ToolResult.error_result(
                "Missing audio reference. Provide asset_id or file_path, or call from a current audio request."
            )

        try:
            result = await self._voice_service.transcribe(
                AudioTranscriptionRequest(
                    asset=resolved_asset,
                    provider=provider or default_asr_provider,
                    language_hint=language_hint,
                    prompt=prompt,
                    metadata={
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "tool_name": self.name,
                    },
                )
            )
        except Exception as exc:
            return ToolResult.error_result(f"Failed to transcribe audio: {exc}")

        transcript = {
            "text": result.text,
            "language": result.language,
            "provider": result.provider,
        }
        audio = {
            "asset_id": result.asset.asset_id,
            "public_url": result.asset.public_url,
            "playback_url": result.asset.playback_url,
            "mime_type": result.asset.mime_type,
            "format": result.asset.format,
        }
        return ToolResult.ok(
            result.text,
            transcript=transcript,
            audio=audio,
            provider=result.provider,
            agent_id=agent_id,
            session_id=session_id,
        )

    async def _resolve_asset_ref(
        self,
        *,
        asset_id: str | None,
        file_path: str | None,
        metadata: dict[str, Any],
    ) -> AudioAssetRef | None:
        if asset_id:
            return await self._asset_store.get_asset_ref(asset_id)

        if file_path:
            path = Path(file_path).expanduser().resolve()
            if not path.exists() or not path.is_file():
                return None
            guessed = _guess_audio_mime_type(path)
            if guessed is None:
                return None
            mime_type, audio_format = guessed
            return AudioAssetRef(
                asset_id=f"adhoc-{path.stem}",
                storage_path=path,
                mime_type=mime_type,
                format=audio_format,
                source="upload",
            )

        audio = metadata.get("audio")
        if isinstance(audio, dict):
            current_asset_id = audio.get("asset_id")
            if current_asset_id:
                return await self._asset_store.get_asset_ref(str(current_asset_id))

        return None
