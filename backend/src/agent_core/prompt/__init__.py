"""Prompt 组装管道模块.

提供插件式 prompt 组装功能，支持动态片段注入和条件控制。

主要组件:
- PromptSection: Prompt 片段数据类
- PromptPipeline: Prompt 组装管道

Example:
    from agent_core.prompt import PromptSection, PromptPipeline

    # 创建管道
    pipeline = PromptPipeline()

    # 添加片段
    pipeline.add_section(PromptSection(
        name="identity",
        priority=10,
        content_fn=lambda ctx: "You are a helpful assistant.",
    ))

    # 构建 prompt
    prompt = await pipeline.build(context={"user_id": "123"})
"""

from .pipeline import AfterBuildCallback, BeforeBuildCallback, PromptPipeline, SectionRenderCallback
from .section import ConditionFunction, ContentFunction, PromptSection

__all__ = [
    # 核心类
    "PromptSection",
    "PromptPipeline",
    # 类型别名
    "ContentFunction",
    "ConditionFunction",
    "BeforeBuildCallback",
    "SectionRenderCallback",
    "AfterBuildCallback",
]
