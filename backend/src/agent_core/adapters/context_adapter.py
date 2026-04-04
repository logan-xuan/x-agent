"""XAgentContextAdapter - 适配压缩模块到 ContextPort.

桥接 X-Agent 的 ContextCompressionManager 到 agent_core 的 ContextPort Protocol。
通过 LLMRouter 提供摘要生成能力，压缩模块本身不依赖任何 LLM 接口。

架构:
    agent_loop._call_llm()
        → ContextPort.prepare_context()
            → XAgentContextAdapter
                → ContextCompressionManager.prepare_context()
                    → ContextCompressor.compress()
                        → summary_fn (由本 adapter 提供)
                            → LLMRouter.chat(stream=False)
"""

from __future__ import annotations

from typing import Any

from ...services.context import ContextBuildRequest, get_context_assembler
from ...utils.logger import get_logger
from ..ports.context_port import PreparedContext

logger = get_logger(__name__)


class XAgentContextAdapter:
    """ContextPort 适配器，桥接 ContextCompressionManager 到 agent_core.

    职责:
    1. 实现 ContextPort Protocol (prepare_context / estimate_tokens)
    2. 提供 summary_fn 回调给 ContextCompressionManager
    3. 将 ContextCompressionManager 的 PreparedContext 转换为 agent_core 的 PreparedContext

    Example:
        from src.services.llm.router import LLMRouter
        from src.config.manager import get_config

        router = LLMRouter()
        config = get_config()
        adapter = create_context_adapter(router, config.compression, config.workspace.path)

        agent_config = AgentCoreConfig(context=adapter)
    """

    def __init__(self, compression_manager: Any, context_assembler: Any | None = None) -> None:
        """初始化适配器.

        Args:
            compression_manager: ContextCompressionManager 实例
        """
        self._manager = compression_manager
        self._assembler = context_assembler

    def _sanitize_messages(
        self,
        messages: list[dict],
    ) -> tuple[list[dict], dict[str, int]]:
        """清洗并裁剪消息，避免非法 content 和超长工具结果进入上下文."""
        max_tool_message_chars = self._manager.config.max_tool_message_chars
        sanitized = []
        truncated_count = 0
        truncated_chars = 0

        for msg in messages:
            content = msg.get("content")
            fixed_msg = msg

            if content is None:
                fixed_msg = {**fixed_msg, "content": ""}
                content = ""

            if (
                fixed_msg.get("role") == "tool"
                and isinstance(content, str)
                and len(content) > max_tool_message_chars
            ):
                truncated_count += 1
                truncated_chars += len(content) - max_tool_message_chars
                fixed_msg = {
                    **fixed_msg,
                    "content": _truncate_tool_content(content, max_tool_message_chars),
                }

            sanitized.append(fixed_msg)

        return sanitized, {
            "truncated_count": truncated_count,
            "truncated_chars": truncated_chars,
        }

    async def prepare_context(
        self,
        session_id: str,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
    ) -> PreparedContext:
        """准备 LLM 调用上下文，内部判断是否需要压缩.

        Args:
            session_id: 会话标识符
            messages: LLM 格式的消息列表 (不含 system prompt)
            system_prompt: 系统提示词
            tools: OpenAI function/tool schema 列表（可选）

        Returns:
            PreparedContext: 准备好的上下文
        """
        try:
            # 清洗输入消息，确保 content 字段合法，并限制超长工具结果。
            sanitized_messages, input_stats = self._sanitize_messages(messages)
            if input_stats["truncated_count"] > 0:
                logger.info(
                    "Tool messages truncated before context preparation",
                    extra={
                        "session_id": session_id,
                        "truncated_count": input_stats["truncated_count"],
                        "truncated_chars": input_stats["truncated_chars"],
                        "max_tool_message_chars": self._manager.config.max_tool_message_chars,
                    }
                )

            messages_for_manager = sanitized_messages
            assembled_bundle = None
            mode = getattr(self._manager.config, "mode", "legacy")

            if mode != "legacy" and self._assembler is not None:
                assembled_bundle = await self._assemble_stateful_context(
                    session_id=session_id,
                    messages=sanitized_messages,
                    tools=tools,
                )
                messages_for_manager = assembled_bundle.messages

            if mode == "stateful" and assembled_bundle is not None:
                final_messages, output_stats = self._sanitize_messages(messages_for_manager)
                if output_stats["truncated_count"] > 0:
                    logger.info(
                        "Tool messages truncated after stateful assembly",
                        extra={
                            "session_id": session_id,
                            "truncated_count": output_stats["truncated_count"],
                            "truncated_chars": output_stats["truncated_chars"],
                            "max_tool_message_chars": self._manager.config.max_tool_message_chars,
                        }
                    )

                final_tokens = (
                    self._manager.token_counter.count_messages(final_messages)
                    + self._manager.token_counter.count_tool_definitions(tools)
                    + self._manager.token_counter.count_text(system_prompt)
                )
                return PreparedContext(
                    messages=final_messages,
                    was_compressed=True,
                    original_tokens=(
                        self._manager.token_counter.count_messages(messages)
                        + self._manager.token_counter.count_tool_definitions(tools)
                        + self._manager.token_counter.count_text(system_prompt)
                    ),
                    final_tokens=final_tokens,
                    summary=assembled_bundle.session_state_text,
                    metadata={
                        "context_mode": mode,
                        "token_breakdown": assembled_bundle.token_breakdown,
                        "used_fallback": assembled_bundle.used_fallback,
                    },
                )

            result = await self._manager.prepare_context(
                session_id=session_id,
                current_messages=messages_for_manager,
                system_prompt=system_prompt,
                tools=tools,
            )

            was_compressed = result.summary is not None and result.summary != ""

            # 清洗输出消息，确保压缩后的消息也合法
            final_messages, output_stats = self._sanitize_messages(result.messages)
            if output_stats["truncated_count"] > 0:
                logger.info(
                    "Tool messages truncated after context preparation",
                    extra={
                        "session_id": session_id,
                        "truncated_count": output_stats["truncated_count"],
                        "truncated_chars": output_stats["truncated_chars"],
                        "max_tool_message_chars": self._manager.config.max_tool_message_chars,
                    }
                )

            if was_compressed:
                logger.info(
                    "Context compressed via adapter",
                    extra={
                        "session_id": session_id,
                        "original_message_count": len(messages_for_manager),
                        "compressed_message_count": len(final_messages),
                        "total_tokens": result.total_tokens,
                    }
                )

            return PreparedContext(
                messages=final_messages,
                was_compressed=was_compressed,
                original_tokens=(
                    self._manager.token_counter.count_messages(messages)
                    + self._manager.token_counter.count_tool_definitions(tools)
                    + self._manager.token_counter.count_text(system_prompt)
                ),
                final_tokens=result.total_tokens,
                summary=result.summary or "",
                metadata={
                    "context_mode": mode,
                    "quality_rejected": getattr(result, "quality_rejected", False),
                    "used_fallback": getattr(assembled_bundle, "used_fallback", False) if assembled_bundle else False,
                    "token_breakdown": getattr(assembled_bundle, "token_breakdown", {}) if assembled_bundle else {},
                },
            )

        except Exception as e:
            logger.error(
                "Context preparation failed, returning original messages",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return PreparedContext(
                messages=messages,
                was_compressed=False,
                original_tokens=0,
                final_tokens=0,
                summary="",
                metadata={},
            )

    async def _assemble_stateful_context(
        self,
        *,
        session_id: str,
        messages: list[dict],
        tools: list[dict] | None,
    ) -> Any:
        """Build stateful prompt fragments before legacy compression runs."""
        try:
            from ...conversation.context import get_current_context

            current = get_current_context()
            agent_id = current.agent_id if current and current.agent_id else "unknown-agent"
        except Exception:
            agent_id = "unknown-agent"

        budget_profile = self._manager._resolve_budget_profile()
        max_prompt_tokens = (
            budget_profile.hard_context_limit_tokens
            if budget_profile and budget_profile.hard_context_limit_tokens
            else self._manager.config.max_context_tokens
        )
        reserved_output_tokens = (
            budget_profile.reserved_output_tokens
            if budget_profile
            else 0
        )

        return await self._assembler.build(
            ContextBuildRequest(
                session_id=session_id,
                agent_id=agent_id,
                mode=getattr(self._manager.config, "mode", "hybrid"),
                current_messages=messages,
                max_prompt_tokens=max_prompt_tokens,
                reserved_output_tokens=reserved_output_tokens,
                tools=tools,
                session_state_budget_tokens=self._manager.config.session_state_budget_tokens,
                evidence_budget_tokens=self._manager.config.evidence_budget_tokens,
                episodic_budget_tokens=self._manager.config.episodic_budget_tokens,
                artifact_budget_tokens=self._manager.config.artifact_budget_tokens,
                max_working_set_messages=self._manager.config.stateful_max_working_set_messages,
            )
        )

    def estimate_tokens(self, messages: list[dict]) -> int:
        """估算消息列表的 token 数量.

        Args:
            messages: LLM 格式的消息列表

        Returns:
            int: 估算的 token 数
        """
        return self._manager.token_counter.count_messages(messages)


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """清洗消息列表，确保所有消息的 content 字段合法.

    某些 LLM API（如阿里云百炼）要求 content 字段不能为 None。
    AssistantMessage 在只有 tool_calls 没有文本时，content 会被设为 None，
    这在正常流程中没问题，但压缩后重新发送时会导致 API 400 错误。

    处理规则:
    - content 为 None 且有 tool_calls: 设为空字符串 ""
    - content 为 None 且无 tool_calls: 设为空字符串 ""
    - content 已有值: 保持不变

    Args:
        messages: LLM 格式的消息列表

    Returns:
        清洗后的消息列表（新列表，不修改原始数据）
    """
    sanitized = []
    for msg in messages:
        if msg.get("content") is None:
            fixed_msg = {**msg, "content": ""}
            sanitized.append(fixed_msg)
        else:
            sanitized.append(msg)
    return sanitized


def _truncate_tool_content(content: str, max_chars: int) -> str:
    """截断超长工具结果，避免原始正文持续膨胀后续 prompt."""
    if max_chars <= 0 or len(content) <= max_chars:
        return content

    note = (
        f"\n\n... [tool output truncated, {len(content)} total characters, "
        f"{len(content) - max_chars} omitted]"
    )
    if len(note) >= max_chars:
        return note[:max_chars]

    keep = max_chars - len(note)
    return content[:keep] + note


def create_context_adapter(
    llm_router: Any,
    compression_config: Any,
    workspace_path: str,
    active_model_name: str = "",
    requested_output_tokens: int | None = None,
) -> XAgentContextAdapter:
    """创建 ContextPort adapter 的工厂函数.

    组装 ContextCompressionManager 并注入 summary_fn 回调。

    Args:
        llm_router: LLMRouter 实例，用于摘要生成
        compression_config: CompressionConfig 配置
        workspace_path: 工作区路径
        active_model_name: 当前 agent 优先使用的模型配置名
        requested_output_tokens: 当前 agent 请求的最大输出 token 数

    Returns:
        XAgentContextAdapter 实例
    """
    from ...config.manager import ConfigManager
    from ...services.compression import ContextCompressionManager
    from ...services.compression.manager import CompressionBudgetProfile

    async def summary_fn(prompt: str) -> str:
        """通过 LLMRouter 生成摘要的回调.

        使用非流式调用 (stream=False) 获取完整响应。
        """
        response = await llm_router.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        return response.content or ""

    def budget_resolver() -> CompressionBudgetProfile | None:
        """Resolve a runtime budget profile from current config and selected model."""
        config = ConfigManager().config
        compression = config.compression

        model_config = None
        if active_model_name:
            model_config = config.get_model_by_name(active_model_name)
        if model_config is None:
            model_config = next((model for model in config.models if model.is_primary), None)
        if model_config is None and config.models:
            model_config = config.models[0]
        if model_config is None:
            return None

        model_context_limit = model_config.max_context_tokens
        model_output_limit = model_config.max_output_tokens

        default_output_reserve = max(
            compression.min_output_reserve_tokens,
            int(model_context_limit * compression.output_reserve_ratio),
        )
        reserved_output_tokens = requested_output_tokens or default_output_reserve
        reserved_output_tokens = min(max(1, reserved_output_tokens), model_output_limit)

        safety_margin_tokens = max(
            compression.min_safety_margin_tokens,
            int(model_context_limit * compression.safety_margin_ratio),
        )

        theoretical_hard_limit = max(
            1,
            model_context_limit - reserved_output_tokens - safety_margin_tokens,
        )
        hard_context_limit = min(
            compression.max_context_tokens,
            theoretical_hard_limit,
        ) if compression.max_context_tokens else theoretical_hard_limit
        trigger_tokens = min(
            hard_context_limit,
            max(
                compression.threshold_tokens,
                int(hard_context_limit * compression.trigger_ratio),
            ),
        )

        return CompressionBudgetProfile(
            provider_name=model_config.name,
            model_id=model_config.model_id,
            model_context_limit_tokens=model_context_limit,
            model_output_limit_tokens=model_output_limit,
            reserved_output_tokens=reserved_output_tokens,
            safety_margin_tokens=safety_margin_tokens,
            hard_context_limit_tokens=hard_context_limit,
            trigger_tokens=trigger_tokens,
        )

    manager = ContextCompressionManager(
        config=compression_config,
        workspace_path=workspace_path,
        summary_fn=summary_fn,
        budget_resolver=budget_resolver,
    )

    return XAgentContextAdapter(
        manager,
        context_assembler=get_context_assembler(),
    )
