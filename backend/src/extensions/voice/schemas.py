"""Shared schemas for the voice extension."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

AudioFormat = Literal["mp3", "wav", "ogg", "webm", "m4a", "flac"]
AudioSource = Literal["upload", "generated", "reference"]


class AudioAssetRef(BaseModel):
    """Reference to an audio asset managed by the voice extension."""

    asset_id: str = Field(..., description="Stable audio asset identifier")
    storage_path: Path = Field(..., description="Local storage path")
    mime_type: str = Field(..., description="MIME type")
    format: AudioFormat = Field(..., description="Audio file format")
    source: AudioSource = Field(..., description="Where the asset came from")
    public_url: str | None = Field(default=None, description="Served URL when exposed externally")
    playback_url: str | None = Field(
        default=None,
        description="Browser-facing playback URL when different from public_url",
    )
    size_bytes: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechSynthesisRequest(BaseModel):
    """Normalized text-to-speech request."""

    text: str = Field(..., min_length=1, description="Text to synthesize")
    provider: str = Field(default="edge", description="Requested TTS provider")
    voice: str | None = Field(default=None, description="Voice or speaker identifier")
    response_format: AudioFormat = Field(default="mp3", description="Target audio format")
    language: str | None = Field(default=None, description="Language hint")
    speech_rate: float | None = Field(default=None, description="Optional speech rate multiplier")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeechSynthesisResult(BaseModel):
    """Normalized text-to-speech result."""

    provider: str = Field(..., description="TTS provider that produced the asset")
    voice: str | None = Field(default=None, description="Resolved voice identifier")
    asset: AudioAssetRef = Field(..., description="Generated audio asset")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioTranscriptionRequest(BaseModel):
    """Normalized speech-to-text request."""

    asset: AudioAssetRef = Field(..., description="Source audio asset")
    provider: str = Field(default="openai", description="Requested ASR provider")
    language_hint: str | None = Field(default=None, description="Optional language hint")
    prompt: str | None = Field(default=None, description="Optional transcription prompt")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioTranscriptionResult(BaseModel):
    """Normalized speech-to-text result."""

    provider: str = Field(..., description="ASR provider used for transcription")
    text: str = Field(..., description="Transcribed text")
    language: str | None = Field(default=None, description="Detected or fixed language")
    asset: AudioAssetRef = Field(..., description="Original source audio")
    segments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
