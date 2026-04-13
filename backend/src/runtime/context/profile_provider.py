"""Compression profile provider for runtime context management."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from .compression_pipeline import (
    CompressionAutocompactConfig,
    CompressionCollapseConfig,
    CompressionMemoryFlushConfig,
    CompressionMicrocompactConfig,
    CompressionPersistConfig,
    CompressionPressureConfig,
    CompressionProfile,
    CompressionPruningConfig,
    CompressionQualityConfig,
)


def build_default_compression_profiles() -> dict[str, CompressionProfile]:
    """Return the built-in compression profiles used by the runtime."""
    return {
        "balanced": CompressionProfile(mode="balanced"),
        "aggressive": CompressionProfile(
            mode="aggressive",
            pressure=CompressionPressureConfig(
                yellow_pct=0.45, orange_pct=0.60, red_pct=0.72, hard_stop_pct=0.85
            ),
            persist=CompressionPersistConfig(
                single_result_chars=30000,
                aggregate_result_chars=120000,
                artifact_preview_chars=1600,
                artifact_preview_head_chars=700,
                artifact_preview_tail_chars=500,
            ),
            pruning=CompressionPruningConfig(
                ttl_ms=180000,
                preserve_recent_assistants=2,
                soft_trim_max_chars=2500,
                soft_trim_head_chars=900,
                soft_trim_tail_chars=900,
            ),
            microcompact=CompressionMicrocompactConfig(trigger_pct=0.45, max_units_per_pass=12),
            collapse=CompressionCollapseConfig(trigger_pct=0.60, max_segment_tokens=8000),
            autocompact=CompressionAutocompactConfig(
                trigger_pct=0.72,
                reserve_tokens_floor=12000,
                max_history_share=0.40,
                fallback_summary_max_chars=5000,
            ),
            memory_flush=CompressionMemoryFlushConfig(soft_threshold_tokens=2500),
            quality=CompressionQualityConfig(min_compression_gain_tokens=500),
            retain_recent_messages=8,
        ),
        "conservative": CompressionProfile(
            mode="conservative",
            pressure=CompressionPressureConfig(
                yellow_pct=0.55, orange_pct=0.75, red_pct=0.88, hard_stop_pct=0.94
            ),
            persist=CompressionPersistConfig(
                single_result_chars=80000,
                aggregate_result_chars=260000,
                artifact_preview_chars=2600,
                artifact_preview_head_chars=1100,
                artifact_preview_tail_chars=900,
            ),
            pruning=CompressionPruningConfig(
                ttl_ms=600000,
                preserve_recent_assistants=5,
                soft_trim_max_chars=5000,
                soft_trim_head_chars=1800,
                soft_trim_tail_chars=1800,
                hard_clear_enabled=False,
            ),
            microcompact=CompressionMicrocompactConfig(trigger_pct=0.60, max_units_per_pass=4),
            collapse=CompressionCollapseConfig(trigger_pct=0.75, max_segment_tokens=18000),
            autocompact=CompressionAutocompactConfig(
                trigger_pct=0.88,
                reserve_tokens_floor=28000,
                max_history_share=0.60,
                fallback_summary_max_chars=10000,
            ),
            memory_flush=CompressionMemoryFlushConfig(soft_threshold_tokens=5000),
            quality=CompressionQualityConfig(min_compression_gain_tokens=1500),
            retain_recent_messages=16,
        ),
    }


@dataclass
class CompressionProfileProvider:
    """Resolve named runtime compression profiles with validation."""

    profiles: dict[str, CompressionProfile] = field(
        default_factory=build_default_compression_profiles
    )
    default_profile_name: str = "balanced"

    def __post_init__(self) -> None:
        if self.default_profile_name not in self.profiles:
            raise ValueError(f"unknown default compression profile: {self.default_profile_name}")
        for name, profile in self.profiles.items():
            self._validate_profile(name, profile)

    def get(self, name: str | None = None) -> CompressionProfile:
        """Return a defensive copy of the selected compression profile."""
        selected = name or self.default_profile_name
        if selected not in self.profiles:
            raise KeyError(f"compression profile not found: {selected}")
        return deepcopy(self.profiles[selected])

    def names(self) -> list[str]:
        """List available profile names."""
        return sorted(self.profiles.keys())

    def _validate_profile(self, name: str, profile: CompressionProfile) -> None:
        if profile.persist.single_result_chars > profile.persist.aggregate_result_chars:
            raise ValueError(
                f"compression profile {name} has single_result_chars > aggregate_result_chars"
            )
        if profile.pruning.preserve_recent_assistants < 1:
            raise ValueError(
                f"compression profile {name} must preserve at least one recent assistant"
            )
        if not 0 < profile.autocompact.max_history_share < 1:
            raise ValueError(f"compression profile {name} has invalid max_history_share")
        if not (
            0
            < profile.pressure.yellow_pct
            < profile.pressure.orange_pct
            < profile.pressure.red_pct
            < profile.pressure.hard_stop_pct
            < 1
        ):
            raise ValueError(f"compression profile {name} has invalid pressure thresholds")
        if profile.quality.min_compression_gain_tokens < 0:
            raise ValueError(f"compression profile {name} has invalid min_compression_gain_tokens")
