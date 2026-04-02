"""Agent Core 配置与依赖注入.

本模块定义了 AgentCoreConfig，用于配置 agent_core 的依赖项。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .hooks import HookRegistry
    from .middleware import MessageMiddleware, MiddlewareChain, ToolMiddleware
    from .ports.context_port import ContextPort
    from .ports.llm_port import LLMPort
    from .ports.logger_port import LoggerPort
    from .ports.memory_port import MemoryPort
    from .ports.plan_port import PlanPort
    from .ports.skill_port import SkillPort
    from .ports.system_prompt_port import SystemPromptPort
    from .ports.tool_port import ToolPort
    from .ports.delegate_port import DelegatePort
    from .collaboration import CollaborationPort
    from .prompt.pipeline import PromptPipeline
    from .tool_middleware import ToolMiddlewarePipeline


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
            plan=plan_adapter,
            context=context_adapter,
            skill=skill_adapter,
            model="gpt-4",
            thinking_level="medium",
            enable_memory=True,
            enable_plan=True,
        )
    
    Attributes:
        llm: LLM 调用端口（必需）
        tools: 工具执行端口（可选）
        memory: 记忆存储端口（可选）
        logger: 日志端口（可选，有默认实现）
        plan: 计划管理端口（可选）
        context: 上下文管理端口（可选）
        skill: 技能系统端口（可选）
        
        model: 模型名称
        provider: 提供商名称
        thinking_level: 思考级别
        temperature: 温度参数
        max_tokens: 最大 token 数
        
        enable_memory: 是否启用记忆存储
        enable_plan: 是否启用计划系统
        enable_context_compression: 是否启用上下文压缩
        enable_experience_learning: 是否启用经验学习
        
        system_prompt: 默认系统提示词
        
        hooks: Hook 注册中心
        message_middlewares: 消息处理中间件链
        tool_middlewares: 工具执行中间件链
    """

    # === 必需的端口 ===
    llm: LLMPort | None = None

    # === 可选的端口 ===
    tools: ToolPort | None = None
    memory: MemoryPort | None = None
    logger: LoggerPort | None = None

    # === 扩展端口 ===
    plan: PlanPort | None = None
    context: ContextPort | None = None
    skill: SkillPort | None = None
    system_prompt_port: SystemPromptPort | None = None

    # === 模型配置 ===
    model: str = ""
    provider: str = ""
    thinking_level: str = "off"  # "off" | "minimal" | "low" | "medium" | "high"
    temperature: float | None = None
    max_tokens: int | None = None

    # === 功能开关 ===
    enable_memory: bool = True
    enable_plan: bool = False
    enable_context_compression: bool = True
    enable_experience_learning: bool = True

    # === 默认配置 ===
    system_prompt: str = ""

    # === 性能配置 ===
    experience_search_timeout_ms: int = 200  # 经验检索超时
    memory_write_async: bool = True  # 异步写入记忆

    # === 上下文配置 ===
    # (上下文配置由 ContextPort 实现者内部管理)

    # === 扩展点 ===
    hooks: HookRegistry | None = None
    message_middlewares: MiddlewareChain | None = None
    tool_middlewares: MiddlewareChain | None = None

    # === 多 Agent 协同端口（新增） ===
    delegate_port: DelegatePort | None = None
    collaboration_port: CollaborationPort | None = None

    # === 动态 Prompt 组装（新增） ===
    prompt_pipeline: PromptPipeline | None = None  # 启用时使用 pipeline 构建 prompt

    # === 工具中间件管道（新增） ===
    tool_middleware_pipeline: ToolMiddlewarePipeline | None = None  # 启用时在工具执行前后插入中间件

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

        if self.enable_plan and self.plan is None:
            # 警告但不报错，plan 是可选的
            pass

    def with_llm(self, llm: LLMPort) -> AgentCoreConfig:
        """设置 LLM 端口.
        
        Args:
            llm: LLM 调用端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.llm = llm
        return self

    def with_tools(self, tools: ToolPort) -> AgentCoreConfig:
        """设置工具端口.
        
        Args:
            tools: 工具执行端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.tools = tools
        return self

    def with_memory(self, memory: MemoryPort) -> AgentCoreConfig:
        """设置记忆端口.
        
        Args:
            memory: 记忆存储端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.memory = memory
        return self

    def with_logger(self, logger: LoggerPort) -> AgentCoreConfig:
        """设置日志端口.
        
        Args:
            logger: 日志端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.logger = logger
        return self

    def with_plan(self, plan: PlanPort) -> AgentCoreConfig:
        """设置计划端口.
        
        Args:
            plan: 计划管理端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.plan = plan
        self.enable_plan = True
        return self

    def with_context(self, context: ContextPort) -> AgentCoreConfig:
        """设置上下文端口.
        
        Args:
            context: 上下文管理端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.context = context
        return self

    def with_system_prompt_port(
        self, system_prompt_port: SystemPromptPort
    ) -> AgentCoreConfig:
        """设置系统提示词端口.
        
        Args:
            system_prompt_port: 系统提示词构建端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.system_prompt_port = system_prompt_port
        return self

    def with_skill(self, skill: SkillPort) -> AgentCoreConfig:
        """设置技能端口.
        
        Args:
            skill: 技能系统端口
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.skill = skill
        return self

    def with_hooks(self, hooks: HookRegistry) -> AgentCoreConfig:
        """设置 Hook 注册中心.
        
        Args:
            hooks: Hook 注册中心
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.hooks = hooks
        return self

    def add_message_middleware(
        self,
        middleware: MessageMiddleware
    ) -> AgentCoreConfig:
        """添加消息处理中间件.
        
        Args:
            middleware: 消息中间件
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        if self.message_middlewares is None:
            from .middleware import MiddlewareChain
            self.message_middlewares = MiddlewareChain()
        self.message_middlewares.add(middleware)  # type: ignore
        return self

    def add_tool_middleware(
        self,
        middleware: ToolMiddleware
    ) -> AgentCoreConfig:
        """添加工具执行中间件.
        
        Args:
            middleware: 工具中间件
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        if self.tool_middlewares is None:
            from .middleware import MiddlewareChain
            self.tool_middlewares = MiddlewareChain()
        self.tool_middlewares.add(middleware)  # type: ignore
        return self

    def with_delegate_port(self, delegate_port: DelegatePort) -> AgentCoreConfig:
        """设置委派端口.
        
        Args:
            delegate_port: 委派端口实例
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.delegate_port = delegate_port
        return self

    def with_collaboration_port(self, collaboration_port: CollaborationPort) -> AgentCoreConfig:
        """设置协同端口.
        
        Args:
            collaboration_port: 协同端口实例
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.collaboration_port = collaboration_port
        return self

    def with_prompt_pipeline(self, prompt_pipeline: PromptPipeline) -> AgentCoreConfig:
        """设置 Prompt Pipeline.
        
        Args:
            prompt_pipeline: PromptPipeline 实例
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.prompt_pipeline = prompt_pipeline
        return self

    def with_tool_middleware_pipeline(self, pipeline: ToolMiddlewarePipeline) -> AgentCoreConfig:
        """设置工具中间件管道.
        
        Args:
            pipeline: ToolMiddlewarePipeline 实例
        
        Returns:
            AgentCoreConfig: 返回自身以支持链式调用
        """
        self.tool_middleware_pipeline = pipeline
        return self


# === 默认配置工厂 ===

def create_minimal_config(llm: LLMPort) -> AgentCoreConfig:
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
    llm: LLMPort,
    tools: ToolPort | None = None,
    memory: MemoryPort | None = None,
    logger: LoggerPort | None = None,
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
