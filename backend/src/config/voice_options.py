"""Voice-related configuration options."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

EDGE_VOICE_OPTIONS: tuple[str, ...] = (
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunxiaNeural",
    "zh-CN-YunyangNeural",
    "zh-CN-liaoning-XiaobeiNeural",
    "zh-CN-shaanxi-XiaoniNeural",
    "zh-HK-HiuGaaiNeural",
    "zh-HK-HiuMaanNeural",
    "zh-HK-WanLungNeural",
    "zh-TW-HsiaoChenNeural",
    "zh-TW-HsiaoYuNeural",
    "zh-TW-YunJheNeural",
)

DEFAULT_TTS_PROVIDER = "edge"
DEFAULT_OPENAI_TTS_VOICE = "alloy"
OPENAI_TTS_VOICE_OPTIONS: tuple[str, ...] = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
)
DEFAULT_TTS_VOICE_CATALOG: dict[str, dict[str, Any]] = {
    "edge": {
        "default": "zh-CN-YunxiNeural",
        "options": list(EDGE_VOICE_OPTIONS),
    },
    "openai": {
        "default": DEFAULT_OPENAI_TTS_VOICE,
        "options": list(OPENAI_TTS_VOICE_OPTIONS),
    },
    "gpt-sovits": {
        "default": None,
        "options": [],
    },
}


def is_valid_edge_voice(value: str | None) -> bool:
    """Return whether the given voice id is a supported Edge voice."""
    if value is None:
        return False
    return value in EDGE_VOICE_OPTIONS


def build_default_tts_voice_catalog() -> dict[str, dict[str, Any]]:
    """Return a mutable copy of the default TTS voice catalog."""
    return deepcopy(DEFAULT_TTS_VOICE_CATALOG)
