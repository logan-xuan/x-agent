"""Unit tests for runtime compression profile provider."""

import pytest

from src.runtime.context import CompressionProfile, CompressionProfileProvider, build_default_compression_profiles


def test_compression_profile_provider_exposes_default_profiles():
    provider = CompressionProfileProvider()

    assert provider.default_profile_name == "balanced"
    assert provider.names() == ["aggressive", "balanced", "conservative"]


def test_compression_profile_provider_returns_defensive_copy():
    provider = CompressionProfileProvider()

    profile = provider.get("balanced")
    profile.retain_recent_messages = 999

    fresh = provider.get("balanced")

    assert fresh.retain_recent_messages != 999


def test_compression_profile_provider_rejects_invalid_profile_constraints():
    broken = CompressionProfile()
    broken.persist.single_result_chars = 500
    broken.persist.aggregate_result_chars = 100

    with pytest.raises(ValueError, match="single_result_chars > aggregate_result_chars"):
        CompressionProfileProvider(profiles={"broken": broken}, default_profile_name="broken")


def test_build_default_compression_profiles_returns_named_profiles():
    profiles = build_default_compression_profiles()

    assert set(profiles) == {"balanced", "aggressive", "conservative"}
    assert profiles["aggressive"].mode == "aggressive"
    assert profiles["conservative"].mode == "conservative"
