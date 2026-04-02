"""系统提示词构建接口定义.

SystemPromptPort 定义了 agent_core 与系统提示词构建系统交互的接口。
将 system prompt 的构造逻辑从 agent_core 中解耦，
由外部模块（如 conversation）提供具体实现。

扩展点说明:
    实现者可以接入不同的提示词构建策略：
    - 基于 Markdown 文件（SPIRIT.md / OWNER.md / IDENTITY.md）
    - 基于数据库配置
    - 基于远程配置中心
    - 多租户差异化提示词
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class IdentityInfo:
    """AI 身份信息.

    agent_core 内部使用的纯数据结构，不依赖外部 models。

    Attributes:
        name: AI 名字
        form: 存在形态（如"猫咪"、"机器人"）
        style: 气质风格
        emoji: 标志性 emoji
    """

    name: str = ""
    form: str = ""
    style: str = ""
    emoji: str = ""


class SystemPromptPort(Protocol):
    """系统提示词构建接口.

    agent_core 通过此接口获取系统提示词，
    而不需要知道提示词是如何构建的（从哪些文件加载、如何组装）。

    Example:
        class MyPromptBuilder:
            def build_system_prompt(self) -> str:
                return "你是一个 AI 助手。"

            def load_identity(self) -> IdentityInfo:
                return IdentityInfo(name="小助手")

        config = AgentCoreConfig(
            system_prompt_port=MyPromptBuilder(),
        )
    """

    def build_system_prompt(self) -> str:
        """构建完整的系统提示词.

        从各种来源（文件、配置、数据库等）加载并组装系统提示词。

        Returns:
            组装好的系统提示词字符串
        """
        ...

    def load_identity(self) -> IdentityInfo:
        """加载 AI 身份信息.

        Returns:
            IdentityInfo 数据对象
        """
        ...
