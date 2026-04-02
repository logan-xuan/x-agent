"""上下文管理接口定义.

ContextPort 定义了 agent_core 与上下文管理系统交互的接口。
agent_loop 在每次 LLM 调用前通过此接口准备上下文，
实现者决定是否需要压缩以及如何压缩。

扩展点说明:
    实现者可以接入不同的上下文策略：
    - 滑动窗口
    - 摘要压缩
    - 向量化检索
    - 外部记忆系统

设计原则:
    - 接口操作 list[dict] (LLM 格式)，因为调用点在 convert_messages_to_llm() 之后
    - 压缩判断逻辑由实现者内部决定，接口不暴露 should_compress
    - prepare_context 是幂等的：不需要压缩时原样返回
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PreparedContext:
    """上下文准备结果.

    由 ContextPort.prepare_context() 返回，
    包含（可能经过压缩的）消息列表和元信息。

    Attributes:
        messages: 准备好的消息列表 (LLM 格式 list[dict])
        was_compressed: 本次是否执行了压缩
        original_tokens: 原始 token 数
        final_tokens: 最终 token 数
        summary: 压缩摘要（仅压缩时有值）
    """

    messages: list[dict] = field(default_factory=list)
    was_compressed: bool = False
    original_tokens: int = 0
    final_tokens: int = 0
    summary: str = ""


class ContextPort(Protocol):
    """上下文管理接口.

    agent_core 通过此接口在 LLM 调用前准备上下文。
    实现者内部决定是否需要压缩，对调用方透明。

    Example:
        class MyContextManager:
            async def prepare_context(self, session_id, messages, system_prompt):
                if len(messages) < 50:
                    return PreparedContext(messages=messages)
                compressed = self._compress(messages)
                return PreparedContext(
                    messages=compressed,
                    was_compressed=True,
                )

            def estimate_tokens(self, messages):
                return sum(len(str(m)) // 4 for m in messages)
    """

    async def prepare_context(
        self,
        session_id: str,
        messages: list[dict],
        system_prompt: str = "",
    ) -> PreparedContext:
        """准备 LLM 调用上下文.

        内部判断是否需要压缩，需要时执行压缩并返回压缩后的消息。
        不需要压缩时原样返回。

        Args:
            session_id: 会话标识符
            messages: LLM 格式的消息列表 (不含 system prompt)
            system_prompt: 系统提示词

        Returns:
            PreparedContext: 准备好的上下文
        """
        ...

    def estimate_tokens(self, messages: list[dict]) -> int:
        """估算消息列表的 token 数量.

        Args:
            messages: LLM 格式的消息列表

        Returns:
            int: 估算的 token 数
        """
        ...
