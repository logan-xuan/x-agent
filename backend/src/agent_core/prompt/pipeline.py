"""PromptPipeline 类实现.

实现插件式 prompt 组装管道，支持动态片段注入和条件控制。

设计原则:
- 零外部依赖，仅使用 Python 标准库
- 支持可选的回调函数集成（不直接依赖 hook 系统）
- 支持 token 预算管理和裁剪
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .section import PromptSection

# 回调函数类型定义
BeforeBuildCallback = Callable[["PromptPipeline", Any], Awaitable[None]]
SectionRenderCallback = Callable[[str, str, Any], Awaitable[str | None]]
AfterBuildCallback = Callable[[str, Any], Awaitable[str | None]]


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量.

    使用简单的启发式方法：平均每个 token 约 4 个字符。
    这是一个粗略估计，实际应使用 tokenizer。

    Args:
        text: 输入文本

    Returns:
        估算的 token 数量
    """
    return len(text) // 4


class PromptPipeline:
    """Prompt 组装管道.

    管理多个 PromptSection，支持动态组装最终 prompt。
    支持优先级排序、条件过滤、token 预算管理和回调集成。

    Example:
        pipeline = PromptPipeline()

        # 添加片段
        pipeline.add_section(PromptSection(
            name="identity",
            priority=10,
            content_fn=lambda ctx: "You are a helpful assistant.",
        ))

        # 构建 prompt
        prompt = await pipeline.build(context={"user_id": "123"})

        # 带 token 预算
        prompt = await pipeline.build(
            context={"user_id": "123"},
            token_budget=2000,
        )
    """

    def __init__(self) -> None:
        """初始化管道."""
        self._sections: list[PromptSection] = []

    def add_section(self, section: PromptSection) -> None:
        """添加 prompt 片段.

        如果已存在同名片段，会替换原有片段。

        Args:
            section: 要添加的 PromptSection
        """
        # 检查是否已存在同名片段
        for i, existing in enumerate(self._sections):
            if existing.name == section.name:
                self._sections[i] = section
                return

        self._sections.append(section)

    def remove_section(self, name: str) -> bool:
        """按名称移除片段.

        Args:
            name: 片段名称

        Returns:
            是否成功移除
        """
        for i, section in enumerate(self._sections):
            if section.name == name:
                self._sections.pop(i)
                return True
        return False

    def get_section(self, name: str) -> PromptSection | None:
        """获取指定名称的片段.

        Args:
            name: 片段名称

        Returns:
            PromptSection 或 None
        """
        for section in self._sections:
            if section.name == name:
                return section
        return None

    def list_sections(self) -> list[PromptSection]:
        """按 priority 排序返回所有片段.

        Returns:
            按优先级排序的 PromptSection 列表
        """
        return sorted(self._sections, key=lambda s: s.priority)

    async def build(
        self,
        context: Any,
        token_budget: int | None = None,
        on_before_build: BeforeBuildCallback | None = None,
        on_section_render: SectionRenderCallback | None = None,
        on_after_build: AfterBuildCallback | None = None,
    ) -> str:
        """构建最终 prompt.

        构建流程:
        1. 触发 on_before_build 回调
        2. 过滤 enabled=False 的片段
        3. 按 condition_fn 过滤不满足条件的片段
        4. 按 priority 排序
        5. 依次调用 content_fn 生成内容
        6. 触发 on_section_render 回调（每个片段渲染后）
        7. 如果有 token_budget，按优先级从低到高裁剪超出的片段
        8. 触发 on_after_build 回调
        9. 拼接所有内容，用 \n\n 分隔

        Args:
            context: 构建上下文，传递给 content_fn 和 condition_fn
            token_budget: 最大 token 数限制（None=不限制）
            on_before_build: build 开始前回调，接收 pipeline 和 context
            on_section_render: 每个 section 渲染后回调，接收 section_name、rendered_content、context
            on_after_build: build 完成后回调，接收 final_prompt 和 context，可返回修改后的 prompt

        Returns:
            组装好的 prompt 字符串
        """
        # 1. 触发 before build 回调
        if on_before_build is not None:
            await on_before_build(self, context)

        # 2-4. 过滤和排序
        active_sections = [
            section for section in self._sections
            if section.should_render(context)
        ]
        active_sections.sort(key=lambda s: s.priority)

        # 5-6. 渲染每个片段
        rendered_sections: list[tuple[PromptSection, str]] = []
        for section in active_sections:
            content = await section.render(context)

            # 触发 section render 回调
            if on_section_render is not None:
                modified = await on_section_render(section.name, content, context)
                if modified is not None:
                    content = modified

            rendered_sections.append((section, content))

        # 7. Token 预算裁剪
        if token_budget is not None and rendered_sections:
            rendered_sections = self._apply_token_budget(
                rendered_sections, token_budget
            )

        # 8. 拼接内容
        contents = [content for _, content in rendered_sections]
        final_prompt = "\n\n".join(contents)

        # 9. 触发 after build 回调
        if on_after_build is not None:
            modified = await on_after_build(final_prompt, context)
            if modified is not None:
                final_prompt = modified

        return final_prompt

    def _apply_token_budget(
        self,
        rendered_sections: list[tuple[PromptSection, str]],
        token_budget: int,
    ) -> list[tuple[PromptSection, str]]:
        """按 token 预算裁剪片段.

        按优先级从低到高裁剪，直到总 token 数在预算内。
        优先级相同的情况下，后出现的先被裁剪。

        Args:
            rendered_sections: 已渲染的片段列表（已按优先级排序）
            token_budget: token 预算

        Returns:
            裁剪后的片段列表
        """
        # 计算总 token 数
        total_tokens = sum(
            _estimate_tokens(content) for _, content in rendered_sections
        )

        if total_tokens <= token_budget:
            return rendered_sections

        # 按优先级从低到高裁剪（反转列表，优先级低的在后面）
        result = list(rendered_sections)

        # 创建按优先级降序排列的索引（优先级低的先被考虑裁剪）
        indices_by_priority = sorted(
            range(len(result)),
            key=lambda i: (-result[i][0].priority, -i),  # 优先级降序，同优先级后出现的先裁剪
        )

        for idx in indices_by_priority:
            if total_tokens <= token_budget:
                break

            section, content = result[idx]

            # 检查片段是否有自己的 max_tokens 限制
            if section.max_tokens is not None:
                content_tokens = _estimate_tokens(content)
                if content_tokens > section.max_tokens:
                    # 裁剪内容（简单截断）
                    max_chars = section.max_tokens * 4
                    content = content[:max_chars] + "..."
                    result[idx] = (section, content)
                    total_tokens = sum(
                        _estimate_tokens(c) for _, c in result
                    )
                    continue

            # 移除整个片段
            total_tokens -= _estimate_tokens(content)
            result[idx] = (section, "")  # 标记为空字符串

        # 过滤掉空内容
        return [(s, c) for s, c in result if c]

    def clone(self) -> PromptPipeline:
        """深拷贝管道.

        用于每次请求独立修改，避免影响原始管道。

        Returns:
            新的 PromptPipeline 实例
        """
        new_pipeline = PromptPipeline()
        for section in self._sections:
            new_pipeline.add_section(section.clone())
        return new_pipeline

    def __len__(self) -> int:
        """返回片段数量."""
        return len(self._sections)

    def __contains__(self, name: str) -> bool:
        """检查是否包含指定名称的片段."""
        return any(s.name == name for s in self._sections)
