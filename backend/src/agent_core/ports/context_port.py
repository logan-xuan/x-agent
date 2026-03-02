"""上下文管理接口定义.

ContextPort 定义了 agent_core 与上下文管理系统交互的接口。
支持上下文压缩、Token估算、优先级管理等能力。

扩展点说明:
    实现者可以接入不同的上下文策略：
    - 滑动窗口（默认）
    - 摘要压缩
    - 向量化检索
    - 外部记忆系统
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Any
from enum import Enum
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ..types import AgentMessage


class CompressionStrategy(Enum):
    """压缩策略."""
    
    SLIDING_WINDOW = "sliding_window"  # 滑动窗口
    SUMMARY = "summary"                # 摘要压缩
    SEMANTIC = "semantic"              # 语义压缩
    HYBRID = "hybrid"                  # 混合策略


@dataclass
class CompressionResult:
    """压缩结果.
    
    Attributes:
        messages: 压缩后的消息列表
        original_tokens: 原始 token 数
        compressed_tokens: 压缩后 token 数
        compression_ratio: 压缩比率
        summary: 压缩摘要（可选）
    """
    
    messages: list["AgentMessage"] = field(default_factory=list)
    original_tokens: int = 0
    compressed_tokens: int = 0
    compression_ratio: float = 0.0
    summary: str = ""


@dataclass
class ContextConfig:
    """上下文配置.
    
    Attributes:
        max_tokens: 最大 token 数
        strategy: 压缩策略
        preserve_recent: 保留最近 N 条消息
        enable_summary: 是否启用摘要
        summary_threshold: 触发摘要的消息数量阈值
    """
    
    max_tokens: int = 4000
    strategy: CompressionStrategy = CompressionStrategy.SLIDING_WINDOW
    preserve_recent: int = 4  # 保留最近 N 轮对话
    enable_summary: bool = True
    summary_threshold: int = 20  # 超过 N 条消息触发摘要


class ContextPort(Protocol):
    """上下文管理接口.
    
    agent_core 通过此接口管理对话上下文。
    实现者需要提供压缩、估算、优化等能力。
    
    Example:
        class SimpleContextManager:
            async def compress(self, messages, config):
                # 滑动窗口压缩
                preserved = messages[-config.preserve_recent * 2:]
                return CompressionResult(
                    messages=preserved,
                    original_tokens=self.estimate_tokens(messages),
                    compressed_tokens=self.estimate_tokens(preserved),
                )
    """
    
    async def compress(
        self,
        messages: list["AgentMessage"],
        config: ContextConfig | None = None,
    ) -> CompressionResult:
        """压缩上下文.
        
        Args:
            messages: 原始消息列表
            config: 压缩配置（可选）
        
        Returns:
            CompressionResult: 压缩结果
        
        Raises:
            Exception: 压缩失败时抛出异常
        """
        ...
    
    async def estimate_tokens(
        self,
        messages: list["AgentMessage"],
    ) -> int:
        """估算 token 数量.
        
        Args:
            messages: 消息列表
        
        Returns:
            int: 估算的 token 数
        """
        ...
    
    async def prioritize(
        self,
        messages: list["AgentMessage"],
        query: str,
    ) -> list["AgentMessage"]:
        """按相关性排序消息.
        
        Args:
            messages: 消息列表
            query: 当前查询
        
        Returns:
            list[AgentMessage]: 排序后的消息列表
        """
        ...
    
    async def summarize(
        self,
        messages: list["AgentMessage"],
    ) -> str:
        """生成消息摘要.
        
        Args:
            messages: 消息列表
        
        Returns:
            str: 摘要文本
        """
        ...
    
    async def should_compress(
        self,
        messages: list["AgentMessage"],
        config: ContextConfig | None = None,
    ) -> tuple[bool, str]:
        """判断是否需要压缩.
        
        Args:
            messages: 消息列表
            config: 配置（可选）
        
        Returns:
            tuple[bool, str]: (是否需要压缩, 原因说明)
        """
        ...
