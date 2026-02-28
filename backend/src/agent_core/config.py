"""Agent Core 配置与依赖注入.

本模块定义了 AgentCoreConfig，用于配置 agent_core 的依赖项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ports.llm_port import LLMPort
    from .ports.tool_port import ToolPort
    from .ports.memory_port import MemoryPort
    from .ports.logger_port import LoggerPort


@dataclass
class AgentCoreConfig:
    """Agent Core 配置.
    
    通过依赖注入连接外部系统。
    
    Example:
        # 最小配置 - 仅需 LLM
        config = AgentCoreConfig(llm=my_llm_adapter)
        
        # 完整配置
        config = AgentCoreConfig(
            llm=my_llm_adapter,
            tools=my_tool_adapter,
            memory=my_memory_adapter,
            logger=my_logger_adapter,
            model="gpt-4",
            thinking_level="medium",
            enable_memory=True,
            enable_experience_learning=True,
        )
    
    Attributes:
        llm: LLM 调用端口（必需）
        tools: 工具执行端口（可选）
        memory: 记忆存储端口（可选）
        logger: 日志端口（可选，有默认实现）
        
        model: 模型名称
        provider: 提供商名称
        thinking_level: 思考级别
        temperature: 温度参数
        max_tokens: 最大 token 数
        
        enable_memory: 是否启用记忆存储
        enable_experience_learning: 是否启用经验学习
        
        system_prompt: 默认系统提示词
    """
    
    # === 必需的端口 ===
    llm: "LLMPort | None" = None
    
    # === 可选的端口 ===
    tools: "ToolPort | None" = None
    memory: "MemoryPort | None" = None
    logger: "LoggerPort | None" = None
    
    # === 模型配置 ===
    model: str = ""
    provider: str = ""
    thinking_level: str = "off"  # "off" | "minimal" | "low" | "medium" | "high"
    temperature: float | None = None
    max_tokens: int | None = None
    
    # === 功能开关 ===
    enable_memory: bool = True
    enable_experience_learning: bool = True
    
    # === 默认配置 ===
    system_prompt: str = ""
    
    # === 性能配置 ===
    experience_search_timeout_ms: int = 200  # 经验检索超时
    memory_write_async: bool = True  # 异步写入记忆
    
    def validate(self) -> None:
        """验证配置有效性.
        
        Raises:
            ValueError: 配置无效时抛出
        """
        if self.llm is None:
            raise ValueError("LLMPort is required. Please provide an LLM adapter.")
        
        if self.enable_memory and self.memory is None:
            # 警告但不报错，因为 memory 是可选的
            pass
        
        if self.enable_experience_learning and self.memory is None:
            # 经验学习依赖 memory
            pass
    
    def with_llm(self, llm: "LLMPort") -> "AgentCoreConfig":
        """设置 LLM 端口.
        
        Args:
            llm: LLM 调用端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.llm = llm
        return self
    
    def with_tools(self, tools: "ToolPort") -> "AgentCoreConfig":
        """设置工具端口.
        
        Args:
            tools: 工具执行端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.tools = tools
        return self
    
    def with_memory(self, memory: "MemoryPort") -> "AgentCoreConfig":
        """设置记忆端口.
        
        Args:
            memory: 记忆存储端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.memory = memory
        return self
    
    def with_logger(self, logger: "LoggerPort") -> "AgentCoreConfig":
        """设置日志端口.
        
        Args:
            logger: 日志端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.logger = logger
        return self


# === 默认配置工厂 ===

def create_minimal_config(llm: "LLMPort") -> AgentCoreConfig:
    """创建最小配置.
    
    Args:
        llm: LLM 调用端口
    
    Returns:
        AgentCoreConfig: 最小配置实例
    """
    return AgentCoreConfig(
        llm=llm,
        enable_memory=False,
        enable_experience_learning=False,
    )


def create_full_config(
    llm: "LLMPort",
    tools: "ToolPort | None" = None,
    memory: "MemoryPort | None" = None,
    logger: "LoggerPort | None" = None,
    **kwargs,
) -> AgentCoreConfig:
    """创建完整配置.
    
    Args:
        llm: LLM 调用端口
        tools: 工具执行端口
        memory: 记忆存储端口
        logger: 日志端口
        **kwargs: 其他配置项
    
    Returns:
        AgentCoreConfig: 完整配置实例
    """
    return AgentCoreConfig(
        llm=llm,
        tools=tools,
        memory=memory,
        logger=logger,
        **kwargs,
    )
