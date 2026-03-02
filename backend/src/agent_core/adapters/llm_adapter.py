"""XAgentLLMAdapter - 适配 X-Agent LLMRouter 到 LLMPort.

将 X-Agent 的 LLMRouter (支持 failover、circuit breaker) 包装为
agent_core 的 LLMPort Protocol。

策略:
- 无工具时: stream=True, 真实流式传输
- 有工具时: stream=False, 获取完整响应后合成 StreamChunk 序列
  (因为现有 StreamingLLMResponse 不支持 tool_calls)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from ..types import StreamChunk, AgentTool

if TYPE_CHECKING:
    pass


# finish_reason 映射
_FINISH_REASON_MAP = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "content_filter": "end_turn",
}


def _map_finish_reason(reason: str | None) -> str:
    """将 OpenAI finish_reason 映射为 agent_core stop_reason."""
    if not reason:
        return "end_turn"
    return _FINISH_REASON_MAP.get(reason, "end_turn")


class XAgentLLMAdapter:
    """LLMPort 适配器，包装 X-Agent 的 LLMRouter.
    
    Example:
        from src.services.llm.router import LLMRouter
        
        router = LLMRouter()
        adapter = XAgentLLMAdapter(router)
        
        config = AgentCoreConfig(llm=adapter)
    """
    
    def __init__(self, router: Any) -> None:
        """初始化适配器.
        
        Args:
            router: X-Agent LLMRouter 实例
        """
        self._router = router
    
    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[AgentTool] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成 LLM 响应.
        
        Args:
            system_prompt: 系统提示词
            messages: LLM 格式消息列表
            tools: 可用工具列表
        
        Yields:
            StreamChunk 事件
        """
        # 构建完整消息列表: 注入 system_prompt
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        # 转换工具为 OpenAI 格式
        openai_tools = None
        if tools:
            openai_tools = [t.to_llm_tool() for t in tools]
        
        try:
            if openai_tools:
                # === 有工具: 非流式路径 ===
                async for chunk in self._non_streaming_with_tools(
                    full_messages, openai_tools
                ):
                    yield chunk
            else:
                # === 无工具: 流式路径 ===
                async for chunk in self._streaming_text(full_messages):
                    yield chunk
                    
        except Exception as e:
            yield StreamChunk.err(str(e))
    
    async def _streaming_text(
        self, messages: list[dict]
    ) -> AsyncIterator[StreamChunk]:
        """流式文本路径 (无工具).
        
        Args:
            messages: 消息列表
        
        Yields:
            StreamChunk
        """
        result = await self._router.chat(messages, stream=True)
        
        last_usage = None
        async for chunk in result:
            if chunk.content:
                yield StreamChunk.text(chunk.content)
            if chunk.usage:
                last_usage = chunk.usage
            if chunk.is_finished:
                yield StreamChunk.done("end_turn", last_usage or chunk.usage)
                return
        
        # 如果没有收到 is_finished，也发送 done
        yield StreamChunk.done("end_turn", last_usage)
    
    async def _non_streaming_with_tools(
        self, messages: list[dict], openai_tools: list[dict]
    ) -> AsyncIterator[StreamChunk]:
        """非流式路径 (有工具).
        
        Args:
            messages: 消息列表
            openai_tools: OpenAI 格式工具定义
        
        Yields:
            StreamChunk
        """
        response = await self._router.chat(
            messages, stream=False, tools=openai_tools
        )
        
        # 输出文本内容
        if response.content:
            yield StreamChunk.text(response.content)
        
        # 输出工具调用
        if response.tool_calls:
            for tc in response.tool_calls:
                tool_call_id = tc.get("id", "")
                function = tc.get("function", {})
                name = function.get("name", "")
                
                # arguments 可能是 JSON 字符串或 dict
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (json.JSONDecodeError, TypeError):
                        arguments = {"raw": arguments}
                
                yield StreamChunk.tool(tool_call_id, name, arguments)
        
        # 输出完成
        stop_reason = _map_finish_reason(response.finish_reason)
        yield StreamChunk.done(stop_reason, response.usage)
