"""PromptPipelineAdapter - 适配 PromptPipeline 到 SystemPromptPort.

将 agent_core 的 PromptPipeline 接入 agent_loop 的 prompt 构建流程。
支持:
- 动态 prompt 片段注入
- 条件控制和优先级排序
- Hook 系统集成
- 向后兼容（未启用时走原有逻辑）

Example:
    from agent_core.adapters.prompt_pipeline_adapter import (
        PromptPipelineAdapter,
        create_prompt_pipeline_adapter,
    )
    
    # 使用工厂函数创建
    adapter = create_prompt_pipeline_adapter(
        workspace_path="/path/to/workspace",
        enable_memory_section=True,
    )
    
    # 构建 prompt
    prompt = await adapter.build_system_prompt(context)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..prompt.pipeline import PromptPipeline
from ..prompt.section import PromptSection
from ..ports.system_prompt_port import IdentityInfo

if TYPE_CHECKING:
    from ..hooks import HookRegistry

try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# === 默认 Section 优先级 ===
PRIORITY_SYSTEM = 10       # 系统级别
PRIORITY_IDENTITY = 20     # 身份信息
PRIORITY_MEMORY = 30       # 记忆信息
PRIORITY_CONTEXT = 40      # 上下文
PRIORITY_TOOL = 50         # 工具描述
PRIORITY_SKILL = 60        # 技能描述
PRIORITY_CUSTOM = 100      # 自定义


class PromptPipelineAdapter:
    """PromptPipeline 适配器.
    
    桥接 PromptPipeline 到 agent_loop 的 prompt 构建流程。
    
    职责:
    1. 实现 SystemPromptPort 接口
    2. 管理 PromptPipeline 实例
    3. 注册默认的 PromptSection
    4. 将 Hook 系统与 pipeline 回调桥接
    
    Attributes:
        _pipeline: 内部的 PromptPipeline 实例
        _hooks: 可选的 HookRegistry 引用
        _base_system_prompt: 原始 system prompt（用于向后兼容）
    """
    
    def __init__(
        self,
        pipeline: PromptPipeline | None = None,
        base_system_prompt: str = "",
        hooks: HookRegistry | None = None,
    ) -> None:
        """初始化适配器.
        
        Args:
            pipeline: PromptPipeline 实例，为 None 时自动创建
            base_system_prompt: 基础 system prompt（兼容原有逻辑）
            hooks: Hook 注册中心（可选）
        """
        self._pipeline = pipeline or PromptPipeline()
        self._base_system_prompt = base_system_prompt
        self._hooks = hooks
        
        # 如果有基础 prompt，注册为一个 section
        if base_system_prompt:
            self._pipeline.add_section(PromptSection(
                name="base_system",
                priority=PRIORITY_SYSTEM,
                content_fn=lambda _: base_system_prompt,
            ))
    
    @property
    def pipeline(self) -> PromptPipeline:
        """获取内部的 PromptPipeline 实例."""
        return self._pipeline
    
    def add_section(self, section: PromptSection) -> None:
        """添加 prompt 片段.
        
        Args:
            section: PromptSection 实例
        """
        self._pipeline.add_section(section)
    
    def remove_section(self, name: str) -> bool:
        """移除 prompt 片段.
        
        Args:
            name: 片段名称
            
        Returns:
            是否成功移除
        """
        return self._pipeline.remove_section(name)
    
    def get_section(self, name: str) -> PromptSection | None:
        """获取 prompt 片段.
        
        Args:
            name: 片段名称
            
        Returns:
            PromptSection 或 None
        """
        return self._pipeline.get_section(name)
    
    async def build(self, context: Any = None, token_budget: int | None = None) -> str:
        """构建完整的 system prompt.
        
        整合 PromptPipeline 的输出，支持 Hook 系统回调。
        
        Args:
            context: 构建上下文
            token_budget: Token 预算限制
            
        Returns:
            组装好的 system prompt 字符串
        """
        # 桥接 Hook 系统到 pipeline 回调
        on_before_build = None
        on_section_render = None
        on_after_build = None
        
        if self._hooks:
            on_before_build = self._create_before_build_hook()
            on_section_render = self._create_section_render_hook()
            on_after_build = self._create_after_build_hook()
        
        prompt = await self._pipeline.build(
            context=context,
            token_budget=token_budget,
            on_before_build=on_before_build,
            on_section_render=on_section_render,
            on_after_build=on_after_build,
        )
        
        return prompt
    
    def build_system_prompt(self) -> str:
        """同步构建 system prompt（实现 SystemPromptPort 接口）.
        
        注意: 此方法为同步方法，不支持异步 section。
        如果需要异步 section，请使用 build() 方法。
        
        Returns:
            system prompt 字符串
        """
        # 如果没有注册任何 section，返回基础 prompt
        if len(self._pipeline) == 0:
            return self._base_system_prompt
        
        # 对于同步场景，使用同步执行（简化版）
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 没有运行中的事件循环
            loop = None
        
        if loop is not None:
            # 在已有事件循环中，创建一个 task
            # 这种情况下应该使用 build() 异步方法
            logger.warning(
                "build_system_prompt called in async context, "
                "consider using build() for full async support"
            )
            # 返回基础 prompt 作为 fallback
            return self._base_system_prompt
        
        # 没有事件循环，可以安全运行
        return asyncio.run(self.build())
    
    def load_identity(self) -> IdentityInfo:
        """加载身份信息（实现 SystemPromptPort 接口）.
        
        从 pipeline 的 identity section 中提取身份信息。
        如果没有 identity section，返回默认值。
        
        Returns:
            IdentityInfo 数据对象
        """
        identity_section = self._pipeline.get_section("identity")
        
        if identity_section and identity_section.metadata:
            return IdentityInfo(
                name=identity_section.metadata.get("name", "Assistant"),
                form=identity_section.metadata.get("form", ""),
                style=identity_section.metadata.get("style", ""),
                emoji=identity_section.metadata.get("emoji", ""),
            )
        
        return IdentityInfo(
            name="Assistant",
            form="",
            style="",
            emoji="",
        )
    
    def clone(self) -> PromptPipelineAdapter:
        """深拷贝适配器.
        
        用于每次请求独立修改，避免影响原始实例。
        
        Returns:
            新的 PromptPipelineAdapter 实例
        """
        return PromptPipelineAdapter(
            pipeline=self._pipeline.clone(),
            base_system_prompt=self._base_system_prompt,
            hooks=self._hooks,
        )
    
    # === 内部方法: Hook 桥接 ===
    
    def _create_before_build_hook(self):
        """创建 before_build 回调（桥接到 HookPoint.BEFORE_PROMPT_BUILD）."""
        async def callback(pipeline: PromptPipeline, context: Any) -> None:
            from ..hooks import HookContext, HookPoint
            
            if self._hooks is None:
                return
            
            hook_ctx = HookContext(
                point=HookPoint.BEFORE_PROMPT_BUILD,
                data={
                    "pipeline": pipeline,
                    "section_names": [s.name for s in pipeline.list_sections()],
                },
                metadata={"context": context},
            )
            await self._hooks.trigger(hook_ctx)
        
        return callback
    
    def _create_section_render_hook(self):
        """创建 section_render 回调（桥接到 HookPoint.ON_SECTION_RENDER）."""
        async def callback(section_name: str, rendered_content: str, context: Any) -> str | None:
            from ..hooks import HookContext, HookPoint
            
            if self._hooks is None:
                return None
            
            hook_ctx = HookContext(
                point=HookPoint.ON_SECTION_RENDER,
                data={
                    "section_name": section_name,
                    "content": rendered_content,
                },
                metadata={"context": context},
            )
            result_ctx = await self._hooks.trigger(hook_ctx)
            
            # 如果 Hook 修改了 content，返回修改后的值
            modified_content = result_ctx.data.get("content")
            if modified_content != rendered_content:
                return modified_content
            
            return None
        
        return callback
    
    def _create_after_build_hook(self):
        """创建 after_build 回调（桥接到 HookPoint.AFTER_PROMPT_BUILD）."""
        async def callback(final_prompt: str, context: Any) -> str | None:
            from ..hooks import HookContext, HookPoint
            
            if self._hooks is None:
                return None
            
            hook_ctx = HookContext(
                point=HookPoint.AFTER_PROMPT_BUILD,
                data={"prompt": final_prompt},
                metadata={"context": context},
            )
            result_ctx = await self._hooks.trigger(hook_ctx)
            
            # 如果 Hook 修改了 prompt，返回修改后的值
            modified_prompt = result_ctx.data.get("prompt")
            if modified_prompt != final_prompt:
                return modified_prompt
            
            return None
        
        return callback


# === Section 注册辅助函数 ===

def register_identity_section(
    adapter: PromptPipelineAdapter,
    name: str = "Assistant",
    form: str = "",
    style: str = "",
    emoji: str = "",
) -> None:
    """注册身份信息 section.
    
    Args:
        adapter: PromptPipelineAdapter 实例
        name: AI 名称
        form: 存在形态（如"猫咪"、"机器人"）
        style: 气质风格
        emoji: 标志性 emoji
    """
    content = f"You are {name}."
    if form:
        content += f" You are a {form}."
    if style:
        content += f" Your style is {style}."
    if emoji:
        content += f" Your signature emoji is {emoji}."
    
    adapter.add_section(PromptSection(
        name="identity",
        priority=PRIORITY_IDENTITY,
        content_fn=lambda _: content,
        metadata={"name": name, "form": form, "style": style, "emoji": emoji},
    ))


def register_memory_section(
    adapter: PromptPipelineAdapter,
    memory_port: Any,
) -> None:
    """注册记忆 section.
    
    Args:
        adapter: PromptPipelineAdapter 实例
        memory_port: MemoryPort 实例
    """
    async def get_memory_context(context: Any) -> str:
        if memory_port is None:
            return ""
        
        try:
            # 假设 context 中有 session_id
            session_id = getattr(context, "session_id", None)
            if not session_id:
                return ""
            
            memories = await memory_port.search(
                query="",
                session_id=session_id,
                limit=5,
            )
            
            if not memories:
                return ""
            
            return "\n\n# Relevant Memories\n" + "\n".join(
                f"- {m.content}" for m in memories
            )
        except Exception as e:
            logger.warning(f"Failed to load memory: {e}")
            return ""
    
    adapter.add_section(PromptSection(
        name="memory",
        priority=PRIORITY_MEMORY,
        content_fn=get_memory_context,
        condition_fn=lambda ctx: memory_port is not None,
    ))


def register_tool_section(
    adapter: PromptPipelineAdapter,
    tool_port: Any,
) -> None:
    """注册工具描述 section.
    
    Args:
        adapter: PromptPipelineAdapter 实例
        tool_port: ToolPort 实例
    """
    def get_tool_descriptions(context: Any) -> str:
        if tool_port is None:
            return ""
        
        try:
            tools = tool_port.get_tools()
            if not tools:
                return ""
            
            lines = ["# Available Tools"]
            for tool in tools:
                lines.append(f"- **{tool.name}**: {tool.description}")
            
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to load tools: {e}")
            return ""
    
    adapter.add_section(PromptSection(
        name="tools",
        priority=PRIORITY_TOOL,
        content_fn=get_tool_descriptions,
        condition_fn=lambda ctx: tool_port is not None,
    ))


# === 工厂函数 ===

def create_prompt_pipeline_adapter(
    workspace_path: str | None = None,
    hooks: HookRegistry | None = None,
    enable_identity: bool = True,
    identity_name: str = "Assistant",
    identity_form: str = "",
    identity_style: str = "",
    identity_emoji: str = "",
) -> PromptPipelineAdapter:
    """创建 PromptPipelineAdapter 的工厂函数.
    
    自动注册默认的 PromptSection 并返回配置好的适配器。
    
    Args:
        workspace_path: workspace 路径（可选，用于加载 Bootstrap 文件）
        hooks: Hook 注册中心（可选）
        enable_identity: 是否启用身份 section
        identity_name: AI 名称
        identity_form: 存在形态（如"猫咪"、"机器人"）
        identity_style: 气质风格
        identity_emoji: 标志性 emoji
        
    Returns:
        PromptPipelineAdapter 实例
    """
    # 尝试加载现有的 system prompt
    base_system_prompt = ""
    if workspace_path:
        try:
            from ...conversation.system_prompt_builder import SystemPromptBuilder
            builder = SystemPromptBuilder(workspace_path=workspace_path)
            base_system_prompt = builder.build_system_prompt()
        except Exception as e:
            logger.warning(f"Failed to load base system prompt: {e}")
    
    adapter = PromptPipelineAdapter(
        base_system_prompt=base_system_prompt,
        hooks=hooks,
    )
    
    # 注册身份 section（如果基础 prompt 为空）
    if enable_identity and not base_system_prompt:
        register_identity_section(
            adapter,
            name=identity_name,
            form=identity_form,
            style=identity_style,
            emoji=identity_emoji,
        )
    
    logger.info(
        "PromptPipelineAdapter created",
        extra={
            "has_base_prompt": bool(base_system_prompt),
            "section_count": len(adapter.pipeline),
        },
    )
    
    return adapter
