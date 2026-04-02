"""PromptSection 数据类定义.

定义 PromptSection 数据结构，用于表示 prompt 的一个片段。
每个片段包含名称、优先级、内容生成函数、条件触发函数等属性。

设计原则:
- 零外部依赖，仅使用 Python 标准库
- 使用 dataclass 定义
- 支持同步和异步内容生成函数
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# 内容生成函数类型
ContentFunction = Callable[[Any], str | Awaitable[str]]

# 条件触发函数类型
ConditionFunction = Callable[[Any], bool]


@dataclass
class PromptSection:
    """Prompt 片段数据类.

    表示 prompt 组装管道中的一个片段，支持动态内容生成和条件控制。

    Attributes:
        name: 片段名称（唯一标识）
        priority: 排序优先级（数字越小越靠前）
        content_fn: 动态生成内容的函数，接收 context 参数，返回 str 或 Awaitable[str]
        condition_fn: 条件触发函数（None=始终启用），接收 context 参数，返回 bool
        enabled: 全局启用/禁用开关
        max_tokens: 最大 token 数限制（None=不限制）
        metadata: 额外元数据（用于扩展）

    Example:
        # 同步内容生成
        section = PromptSection(
            name="identity",
            priority=10,
            content_fn=lambda ctx: "You are a helpful assistant.",
        )

        # 异步内容生成
        async def get_context(ctx):
            return await fetch_user_context(ctx.user_id)

        section = PromptSection(
            name="user_context",
            priority=20,
            content_fn=get_context,
            condition_fn=lambda ctx: ctx.has_user_context,
        )
    """

    name: str
    priority: int
    content_fn: ContentFunction
    condition_fn: ConditionFunction | None = None
    enabled: bool = True
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    async def render(self, context: Any) -> str:
        """渲染片段内容.

        调用 content_fn 生成内容，自动处理同步和异步函数。

        Args:
            context: 渲染上下文，传递给 content_fn

        Returns:
            渲染后的内容字符串
        """
        result = self.content_fn(context)

        # 检查是否为协程函数（异步）
        if inspect.isawaitable(result):
            return await result

        return result  # type: ignore

    def should_render(self, context: Any) -> bool:
        """检查是否应该渲染此片段.

        检查 enabled 开关和 condition_fn 条件。

        Args:
            context: 条件判断上下文，传递给 condition_fn

        Returns:
            是否应该渲染
        """
        if not self.enabled:
            return False

        if self.condition_fn is not None:
            return self.condition_fn(context)

        return True

    def clone(self) -> PromptSection:
        """深拷贝片段.

        Returns:
            新的 PromptSection 实例
        """
        return PromptSection(
            name=self.name,
            priority=self.priority,
            content_fn=self.content_fn,
            condition_fn=self.condition_fn,
            enabled=self.enabled,
            max_tokens=self.max_tokens,
            metadata=dict(self.metadata),  # 浅拷贝 metadata
        )
