"""基于模型配置推导 runtime token 预算。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..config.models import ModelConfig
from .context.compression_pipeline import CompressionProfile
from .types import TurnBudgetProfile

_OUTPUT_RESERVE_RATIO = 0.12
_PROTOCOL_BUFFER_RATIO = 0.06
_MIN_OUTPUT_RESERVE_TOKENS = 4000
_MAX_OUTPUT_RESERVE_TOKENS = 32000
_MIN_PROTOCOL_BUFFER_TOKENS = 4000
_MAX_PROTOCOL_BUFFER_TOKENS = 16000


@dataclass(frozen=True)
class ModelBudgetHints:
    """模型上下文预算推导结果。"""

    max_context_tokens: int
    max_output_tokens: int
    reserved_output_tokens: int
    protocol_buffer_tokens: int
    usable_context_tokens: int
    discounted_context_window: int

    def to_metadata(self) -> dict[str, int]:
        return asdict(self)


def derive_model_budget_hints(model_config: ModelConfig | None) -> ModelBudgetHints | None:
    """按模型能力计算 runtime 可安全使用的上下文窗口。"""
    if model_config is None or model_config.max_context_tokens is None:
        return None

    max_context_tokens = max(int(model_config.max_context_tokens), 1)
    configured_output_tokens = int(
        model_config.max_output_tokens
        if model_config.max_output_tokens is not None
        else max_context_tokens * _OUTPUT_RESERVE_RATIO
    )
    output_cap_tokens = max(int(max_context_tokens * _OUTPUT_RESERVE_RATIO), 1)
    reserved_output_tokens = min(configured_output_tokens, output_cap_tokens)
    reserved_output_tokens = min(
        max(reserved_output_tokens, _dynamic_floor(max_context_tokens, _MIN_OUTPUT_RESERVE_TOKENS)),
        _MAX_OUTPUT_RESERVE_TOKENS,
    )

    protocol_buffer_tokens = min(
        max(
            int(max_context_tokens * _PROTOCOL_BUFFER_RATIO),
            _dynamic_floor(max_context_tokens, _MIN_PROTOCOL_BUFFER_TOKENS),
        ),
        _MAX_PROTOCOL_BUFFER_TOKENS,
    )
    usable_context_tokens = max(
        max_context_tokens - reserved_output_tokens - protocol_buffer_tokens,
        1,
    )
    discounted_context_window = max((usable_context_tokens * 7) // 10, 1)

    return ModelBudgetHints(
        max_context_tokens=max_context_tokens,
        max_output_tokens=configured_output_tokens,
        reserved_output_tokens=reserved_output_tokens,
        protocol_buffer_tokens=protocol_buffer_tokens,
        usable_context_tokens=usable_context_tokens,
        discounted_context_window=discounted_context_window,
    )


def derive_model_aware_turn_budget_profile(
    *,
    base_profile: TurnBudgetProfile,
    compression_profile: CompressionProfile,
    model_config: ModelConfig | None,
) -> tuple[TurnBudgetProfile, ModelBudgetHints | None]:
    """用模型能力折扣结果重写 turn token 预算，保持 controller 与 compression 一致。"""
    hints = derive_model_budget_hints(model_config)
    if hints is None:
        return _copy_turn_budget_profile(base_profile), None

    base_window = max(int(base_profile.max_total_tokens), 1)
    effective_window = min(base_window, hints.discounted_context_window)

    return (
        TurnBudgetProfile(
            max_turns=base_profile.max_turns,
            max_wall_time_ms=base_profile.max_wall_time_ms,
            max_total_tokens=effective_window,
            max_cost_usd=base_profile.max_cost_usd,
            max_tool_calls=base_profile.max_tool_calls,
            max_parallel_tools=base_profile.max_parallel_tools,
            max_spawns=base_profile.max_spawns,
            compact_trigger_tokens=max(
                int(effective_window * compression_profile.pressure.orange_pct),
                1,
            ),
            collapse_trigger_tokens=max(
                int(effective_window * compression_profile.pressure.yellow_pct),
                1,
            ),
            tool_result_single_chars=min(
                base_profile.tool_result_single_chars,
                compression_profile.persist.single_result_chars,
            ),
            tool_result_per_message_chars=min(
                base_profile.tool_result_per_message_chars,
                compression_profile.persist.aggregate_result_chars,
            ),
            max_tool_calls_by_name=dict(base_profile.max_tool_calls_by_name),
        ),
        hints,
    )


def _copy_turn_budget_profile(profile: TurnBudgetProfile) -> TurnBudgetProfile:
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


def _dynamic_floor(max_context_tokens: int, minimum_tokens: int) -> int:
    return max(min(max_context_tokens // 10, minimum_tokens), 1)
