"""Shared runtime service factory for orchestrator/config integration."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from ..config.manager import get_config
from ..config.models import (
    RuntimeCompressionProfileConfig,
    RuntimeSessionProfileConfig,
    RuntimeToolPolicyConfig,
    RuntimeTurnProfileConfig,
)
from ..services.storage import get_storage_service
from .context import (
    CompressionAutocompactConfig,
    CompressionCollapseConfig,
    CompressionMemoryFlushConfig,
    CompressionMicrocompactConfig,
    CompressionPersistConfig,
    CompressionPressureConfig,
    CompressionProfile,
    CompressionProfileProvider,
    CompressionPruningConfig,
    CompressionQualityConfig,
)
from .repositories import (
    StorageArtifactRepository,
    StorageCompressionEventRepository,
    StorageSessionRepository,
    StorageStateSnapshotRepository,
    StorageSummaryRepository,
    StorageTranscriptRepository,
)
from .session import ChildSessionManager, ChildSessionPolicy, DefaultSessionOrchestrator, InMemoryLaneScheduler
from .types import ToolPolicy, TurnBudgetProfile


def _to_turn_budget_profile(profile: RuntimeTurnProfileConfig) -> TurnBudgetProfile:
    return TurnBudgetProfile(
        max_turns=profile.max_turns,
        max_wall_time_ms=profile.max_wall_time_ms,
        max_total_tokens=profile.max_total_tokens,
        max_cost_usd=profile.max_cost_usd,
        max_tool_calls=profile.max_tool_calls,
        max_parallel_tools=profile.max_parallel_tools,
        max_spawns=profile.max_spawns,
        compact_trigger_tokens=profile.compact_trigger_tokens,
        collapse_trigger_tokens=profile.collapse_trigger_tokens,
        tool_result_single_chars=profile.tool_result_single_chars,
        tool_result_per_message_chars=profile.tool_result_per_message_chars,
        max_tool_calls_by_name=dict(profile.max_tool_calls_by_name),
    )


def _to_tool_policy(policy: RuntimeToolPolicyConfig) -> ToolPolicy:
    return ToolPolicy(
        max_result_size_chars=policy.max_result_size_chars,
        max_uses_per_turn=policy.max_uses_per_turn,
        max_uses_per_session=policy.max_uses_per_session,
        max_parallelism=policy.max_parallelism,
        default_timeout_ms=policy.default_timeout_ms,
        compactable=policy.compactable,
        persist_large_output=policy.persist_large_output,
        allow_in_subagent=policy.allow_in_subagent,
        cost_weight=policy.cost_weight,
        repeat_signature_limit=policy.repeat_signature_limit,
    )


def _to_compression_profile(profile: RuntimeCompressionProfileConfig) -> CompressionProfile:
    return CompressionProfile(
        mode=profile.mode,
        pressure=CompressionPressureConfig(**profile.pressure.model_dump()),
        persist=CompressionPersistConfig(**profile.persist.model_dump()),
        pruning=CompressionPruningConfig(**profile.pruning.model_dump()),
        microcompact=CompressionMicrocompactConfig(**profile.microcompact.model_dump()),
        collapse=CompressionCollapseConfig(**profile.collapse.model_dump()),
        autocompact=CompressionAutocompactConfig(**profile.autocompact.model_dump()),
        memory_flush=CompressionMemoryFlushConfig(**profile.memory_flush.model_dump()),
        quality=CompressionQualityConfig(**profile.quality.model_dump()),
        retain_recent_messages=profile.retain_recent_messages,
    )


@dataclass
class RuntimeServices:
    """Runtime-wide shared services and profile adapters."""

    orchestrator: DefaultSessionOrchestrator
    compression_profiles: CompressionProfileProvider
    turn_profiles: dict[str, TurnBudgetProfile]
    tool_policies: dict[str, ToolPolicy]
    default_turn_profile: str
    default_compression_profile: str
    default_session_profile: str


def _build_runtime_services() -> RuntimeServices:
    config = get_config()
    runtime_config = config.runtime
    storage = get_storage_service()
    session_profile: RuntimeSessionProfileConfig = runtime_config.session_profiles[
        runtime_config.defaults.session_profile
    ]

    orchestrator = DefaultSessionOrchestrator(
        session_store=StorageSessionRepository(storage),
        transcript_repository=StorageTranscriptRepository(storage),
        summary_repository=StorageSummaryRepository(storage),
        artifact_repository=StorageArtifactRepository(storage),
        compression_event_repository=StorageCompressionEventRepository(storage),
        state_snapshot_repository=StorageStateSnapshotRepository(storage),
        lane_scheduler=InMemoryLaneScheduler(
            lane_limits={
                "main": session_profile.lane_limits.main,
                "followup": session_profile.lane_limits.followup,
                "subagent": session_profile.lane_limits.subagent,
                "cron": session_profile.lane_limits.cron,
                "background_tool": session_profile.lane_limits.background_tool,
            }
        ),
        child_session_manager=ChildSessionManager(
            policy=ChildSessionPolicy(
                prompt_mode=session_profile.child_prompt_mode,
                max_spawns=0 if session_profile.child_max_depth <= 0 else 1,
                allow_session_tools=False,
                auto_archive=True,
            )
        ),
    )

    compression_profiles = CompressionProfileProvider(
        profiles={
            name: _to_compression_profile(profile)
            for name, profile in runtime_config.compression_profiles.items()
        },
        default_profile_name=runtime_config.defaults.compression_profile,
    )
    turn_profiles = {
        name: _to_turn_budget_profile(profile)
        for name, profile in runtime_config.turn_profiles.items()
    }
    tool_policies = {
        name: _to_tool_policy(policy)
        for name, policy in runtime_config.tools.by_name.items()
    }
    tool_policies.setdefault("__default__", _to_tool_policy(runtime_config.tools.defaults))

    return RuntimeServices(
        orchestrator=orchestrator,
        compression_profiles=compression_profiles,
        turn_profiles=turn_profiles,
        tool_policies=tool_policies,
        default_turn_profile=runtime_config.defaults.turn_profile,
        default_compression_profile=runtime_config.defaults.compression_profile,
        default_session_profile=runtime_config.defaults.session_profile,
    )


_runtime_services: RuntimeServices | None = None
_runtime_services_lock = Lock()


def get_runtime_services() -> RuntimeServices:
    """Return shared runtime services for the current process."""
    global _runtime_services
    if _runtime_services is None:
        with _runtime_services_lock:
            if _runtime_services is None:
                _runtime_services = _build_runtime_services()
    return _runtime_services


def reset_runtime_services() -> None:
    """Reset the cached runtime services, primarily for tests."""
    global _runtime_services
    with _runtime_services_lock:
        _runtime_services = None
