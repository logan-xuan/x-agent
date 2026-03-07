"""Agent 类封装.

提供 Agent 的高级封装，管理状态、消息队列和事件订阅。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Callable, Any

from .types import (
    AgentContext,
    AgentState,
    AgentMessage,
    AgentEvent,
    AgentStartEvent,
    AgentEndEvent,
    MessageEndEvent,
    UserMessage,
    AssistantMessage,
    TextContent,
)
from .agent_loop import agent_loop
from .event_stream import EventStream, EventCollector

if TYPE_CHECKING:
    from .config import AgentCoreConfig


class Agent:
    """Agent 类.
    
    提供 Agent 的高级封装，包括:
    - 状态管理
    - 消息队列 (steering, follow-up)
    - 事件订阅
    - 便捷方法
    
    Example:
        agent = Agent(config)
        
        # 发送消息
        async for event in agent.prompt("Hello"):
            print(event.type)
        
        # 中断
        agent.abort()
        
        # 发送 steering 消息
        agent.steer("Please focus on...")
    """
    
    def __init__(
        self,
        config: "AgentCoreConfig",
        system_prompt: str = "",
    ) -> None:
        """初始化 Agent.
        
        Args:
            config: Agent Core 配置
            system_prompt: 系统提示词 (可选，会覆盖 config 中的)
        """
        self._config = config
        self._system_prompt = system_prompt or config.system_prompt
        # 保存原始 system prompt（含 SKILLS_INJECTION_MARKER），
        # 用于多轮对话中每次从原始模板重新注入 skills，避免重复追加
        self._original_system_prompt = self._system_prompt
        
        # 状态
        self._state = AgentState(
            system_prompt=self._system_prompt,
            model=config.model,
            provider=config.provider,
            thinking_level=config.thinking_level,
            tools=[],  # 从 tool_port 获取
        )
        
        # 消息队列
        self._steering_queue: list[AgentMessage] = []
        self._follow_up_queue: list[AgentMessage] = []
        
        # 中止事件
        self._abort_event: asyncio.Event | None = None
        
        # 事件订阅者
        self._event_callbacks: list[Callable[[AgentEvent], None]] = []
        
        # 加载工具
        if config.tools:
            self._state.tools = config.tools.get_tools()
    
    @property
    def state(self) -> AgentState:
        """获取当前状态."""
        return self._state
    
    @property
    def messages(self) -> list[AgentMessage]:
        """获取消息历史."""
        return self._state.messages
    
    @property
    def is_streaming(self) -> bool:
        """检查是否正在流式处理."""
        return self._state.is_streaming
    
    async def prompt(
        self,
        content: str,
        images: list[tuple[str, str]] | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """发送用户消息.
        
        Args:
            content: 消息内容
            images: 图片列表 (base64_data, mime_type)
        
        Yields:
            AgentEvent
        """
        # 创建用户消息
        user_message = UserMessage.from_text_and_images(content, images)
        
        # 创建上下文
        context = AgentContext(
            system_prompt=self._system_prompt,
            messages=self._state.messages.copy(),
            tools=self._state.tools,
        )
        
        # 创建中止事件
        self._abort_event = asyncio.Event()
        self._state.is_streaming = True
        self._state.error = None
        
        try:
            async for event in agent_loop(
                prompts=[user_message],
                context=context,
                config=self._config,
                abort_event=self._abort_event,
            ):
                # 更新状态
                self._update_state(event)
                
                # 通知订阅者
                for callback in self._event_callbacks:
                    try:
                        callback(event)
                    except Exception:
                        pass
                
                yield event
        
        finally:
            self._state.is_streaming = False
            self._abort_event = None
    
    def abort(self) -> None:
        """中止当前处理."""
        if self._abort_event:
            self._abort_event.set()
    
    def steer(self, content: str) -> None:
        """发送 steering 消息.
        
        Steering 消息会在当前工具调用后注入，用于中断和重定向。
        
        Args:
            content: 消息内容
        """
        self._steering_queue.append(UserMessage.from_text(content))
    
    def follow_up(self, content: str) -> None:
        """发送 follow-up 消息.
        
        Follow-up 消息会在当前 turn 结束后注入，用于追问。
        
        Args:
            content: 消息内容
        """
        self._follow_up_queue.append(UserMessage.from_text(content))
    
    def clear_messages(self) -> None:
        """清空消息历史."""
        self._state.messages.clear()
    
    def add_message(self, message: AgentMessage) -> None:
        """添加消息到历史.
        
        Args:
            message: 消息对象
        """
        self._state.messages.append(message)
    
    def subscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        """订阅事件.
        
        Args:
            callback: 事件回调函数
        """
        self._event_callbacks.append(callback)
    
    def unsubscribe(self, callback: Callable[[AgentEvent], None]) -> None:
        """取消订阅.
        
        Args:
            callback: 事件回调函数
        """
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)
    
    def _update_state(self, event: AgentEvent) -> None:
        """根据事件更新状态."""
        if isinstance(event, AgentStartEvent):
            self._state.current_trace_id = event.trace_id
        
        elif isinstance(event, AgentEndEvent):
            self._state.is_streaming = False
            self._state.stream_message = None
            self._state.pending_tool_calls.clear()
            # 更新消息历史
            for msg in event.messages:
                if msg not in self._state.messages:
                    self._state.messages.append(msg)
        
        elif isinstance(event, MessageEndEvent):
            if event.message:
                self._state.stream_message = None
    
    async def get_steering_messages(self) -> list[AgentMessage]:
        """获取 steering 消息队列.
        
        Returns:
            list[AgentMessage]: steering 消息列表
        """
        messages = self._steering_queue.copy()
        self._steering_queue.clear()
        return messages
    
    async def get_follow_up_messages(self) -> list[AgentMessage]:
        """获取 follow-up 消息队列.
        
        Returns:
            list[AgentMessage]: follow-up 消息列表
        """
        messages = self._follow_up_queue.copy()
        self._follow_up_queue.clear()
        return messages


async def run_agent_once(
    config: "AgentCoreConfig",
    prompt: str,
    system_prompt: str = "",
    messages: list[AgentMessage] | None = None,
) -> tuple[list[AgentMessage], list[AgentEvent]]:
    """运行一次 Agent 对话.
    
    便捷函数，用于简单的单轮对话。
    
    Args:
        config: Agent Core 配置
        prompt: 用户消息
        system_prompt: 系统提示词
        messages: 历史消息
    
    Returns:
        tuple[list[AgentMessage], list[AgentEvent]]: (新消息列表, 所有事件)
    
    Example:
        messages, events = await run_agent_once(
            config=config,
            prompt="What is 2 + 2?",
        )
        print(messages[-1].get_text())  # 输出答案
    """
    agent = Agent(config, system_prompt=system_prompt)
    
    if messages:
        for msg in messages:
            agent.add_message(msg)
    
    collector = EventCollector[AgentEvent]()
    
    async for event in agent.prompt(prompt):
        collector.add(event)
    
    # 提取新消息
    new_messages: list[AgentMessage] = []
    for event in collector.get_all():
        if isinstance(event, AgentEndEvent):
            new_messages = event.messages
            break
    
    return new_messages, collector.get_all()
