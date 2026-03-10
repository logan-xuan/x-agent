"""XAgentSystemPromptAdapter - 适配 conversation 模块的 SystemPromptBuilder 到 SystemPromptPort.

将 system prompt 的构建逻辑委托给 conversation.SystemPromptBuilder，
使 agent_core 不直接依赖 workspace 文件加载细节。

Example:
    from conversation.system_prompt_builder import SystemPromptBuilder
    from agent_core.adapters.system_prompt_adapter import XAgentSystemPromptAdapter

    builder = SystemPromptBuilder()
    adapter = XAgentSystemPromptAdapter(builder)

    config = AgentCoreConfig(system_prompt_port=adapter)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..ports.system_prompt_port import IdentityInfo

if TYPE_CHECKING:
    from ..ports.system_prompt_port import SystemPromptPort


class XAgentSystemPromptAdapter:
    """SystemPromptPort 适配器.

    包装 conversation.SystemPromptBuilder（或任何实现了相同接口的对象），
    提供给 agent_core 使用。

    Attributes:
        _builder: 实际的系统提示词构建器实例
    """

    def __init__(self, builder: "SystemPromptPort") -> None:
        """初始化适配器.

        Args:
            builder: 实现了 SystemPromptPort 接口的构建器实例
        """
        self._builder = builder

    def build_system_prompt(self) -> str:
        """构建完整的系统提示词.

        委托给内部的 builder 实例。

        Returns:
            组装好的系统提示词字符串
        """
        return self._builder.build_system_prompt()

    def load_identity(self) -> IdentityInfo:
        """加载 AI 身份信息.

        委托给内部的 builder 实例。

        Returns:
            IdentityInfo 数据对象
        """
        return self._builder.load_identity()


def create_system_prompt_adapter(
    workspace_path: str | None = None,
) -> XAgentSystemPromptAdapter:
    """创建 SystemPrompt 适配器的工厂函数.

    自动实例化 conversation.SystemPromptBuilder 并包装为适配器。

    Args:
        workspace_path: workspace 目录路径。为 None 时由 SystemPromptBuilder
            从全局配置读取默认路径（单 Agent 场景）。多 Agent 场景下应传入
            对应 Agent 的 workspace 路径，确保加载正确的 Bootstrap 文件。

    Returns:
        XAgentSystemPromptAdapter 实例
    """
    from ...conversation.system_prompt_builder import SystemPromptBuilder

    builder = SystemPromptBuilder(workspace_path=workspace_path)
    return XAgentSystemPromptAdapter(builder)
