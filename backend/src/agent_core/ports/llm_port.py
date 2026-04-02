"""LLM 调用接口定义.

LLMPort 定义了 agent_core 与 LLM 服务交互的接口。
实现者需要提供流式响应能力。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..types import AgentTool, StreamChunk


class LLMPort(Protocol):
    """LLM 调用接口.
    
    agent_core 通过此接口调用 LLM 服务，不关心具体实现。
    实现者需要将具体的 LLM 服务（如 OpenAI, Anthropic 等）适配到此接口。
    
    Example:
        class OpenAIAdapter:
            def __init__(self, client):
                self.client = client
            
            async def stream(
                self,
                system_prompt: str,
                messages: list[dict],
                tools: list[AgentTool] | None = None,
            ) -> AsyncIterator[StreamChunk]:
                # 调用 OpenAI API 并转换响应
                ...
    """

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[AgentTool] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成响应.
        
        Args:
            system_prompt: 系统提示词
            messages: 消息历史（已转换为 LLM 格式）
            tools: 可用工具列表（可选）
        
        Yields:
            StreamChunk: 流式数据块，包含以下类型：
                - text_delta: 文本增量
                - thinking_delta: 思考内容增量
                - tool_call: 工具调用
                - done: 完成
                - error: 错误
        
        Raises:
            Exception: LLM 调用失败时抛出异常
        """
        ...
