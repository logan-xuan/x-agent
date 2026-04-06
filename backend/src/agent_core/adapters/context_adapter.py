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
        self._context_assembler = context_assembler

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

        Returns:
            PreparedContext: 准备好的上下文
        """
        try:
            # 清洗输入消息，确保 content 字段合法
            sanitized_messages = _truncate_tool_messages(
                _sanitize_messages(messages),
                max_chars=getattr(self._manager.config, "max_tool_message_chars", 4000),
            )

            mode = getattr(self._manager.config, "mode", "legacy")
            if self._context_assembler is not None and mode in {"hybrid", "stateful"}:
                from ...services.context.types import ContextBuildRequest

                bundle = await self._context_assembler.build(
                    ContextBuildRequest(
                        session_id=session_id,
                        agent_id="main-agent",
                        mode=mode,
                        current_messages=sanitized_messages,
                        max_prompt_tokens=getattr(self._manager.config, "max_context_tokens", 32000),
                    )
                )
                if mode == "stateful":
                    final_messages = _sanitize_messages(bundle.messages)
                    final_tokens = self._manager.token_counter.count_messages(final_messages)
                    return PreparedContext(
                        messages=final_messages,
                        was_compressed=True,
                        original_tokens=self._manager.token_counter.count_messages(messages),
                        final_tokens=final_tokens,
                        summary=bundle.session_state_text,
                    )
                sanitized_messages = _truncate_tool_messages(
                    _sanitize_messages(bundle.messages),
                    max_chars=getattr(self._manager.config, "max_tool_message_chars", 4000),
                )

            result = await self._manager.prepare_context(
                session_id=session_id,
                current_messages=sanitized_messages,
                system_prompt=system_prompt,
                tools=tools,
            )

            was_compressed = result.summary is not None and result.summary != ""

            # 清洗输出消息，确保压缩后的消息也合法
            final_messages = _sanitize_messages(result.messages)

            if was_compressed:
                logger.info(
                    "Context compressed via adapter",
                    extra={
                        "session_id": session_id,
                        "original_message_count": len(messages),
                        "compressed_message_count": len(final_messages),
                        "total_tokens": result.total_tokens,
                    }
                )

            return PreparedContext(
                messages=final_messages,
                was_compressed=was_compressed,
                original_tokens=self._manager.token_counter.count_messages(messages),
                final_tokens=result.total_tokens,
                summary=result.summary or "",
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


def _truncate_tool_messages(messages: list[dict], *, max_chars: int) -> list[dict]:
    """Truncate oversized tool messages before they go back into prompt assembly."""
    if max_chars <= 0:
        return messages

    truncated: list[dict] = []
    marker = "\n...[tool output truncated]..."
    for message in messages:
        content = str(message.get("content", ""))
        if message.get("role") == "tool" and len(content) > max_chars:
            head_budget = max(max_chars - len(marker), 0)
            truncated.append({**message, "content": content[:head_budget] + marker})
        else:
            truncated.append(message)
    return truncated


def create_context_adapter(
    llm_router: Any,
    compression_config: Any,
    workspace_path: str,
) -> XAgentContextAdapter:
    """创建 ContextPort adapter 的工厂函数.

    组装 ContextCompressionManager 并注入 summary_fn 回调。

    Args:
        llm_router: LLMRouter 实例，用于摘要生成
        compression_config: CompressionConfig 配置
        workspace_path: 工作区路径

    Returns:
        XAgentContextAdapter 实例
    """
    from ...services.compression import ContextCompressionManager

    async def summary_fn(prompt: str) -> str:
        """通过 LLMRouter 生成摘要的回调.

        使用非流式调用 (stream=False) 获取完整响应。
        """
        response = await llm_router.chat(
            messages=[{"role": "user", "content": prompt}],
            stream=False,
        )
        return response.content or ""

    manager = ContextCompressionManager(
        config=compression_config,
        workspace_path=workspace_path,
        summary_fn=summary_fn,
    )

    return XAgentContextAdapter(manager)
