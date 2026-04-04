"""Agent 信息值对象。

AgentInfo 是 Gateway 层使用的轻量 Agent 信息载体，
从配置驱动的 Agent dataclass 转换而来。

Gateway 层通过 AgentInfo 获取 Agent 信息，
不直接依赖具体的 Agent 实现，保持层间解耦。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AgentInfo:
    """Agent 信息值对象（Gateway 层使用）。

    不可变值对象，封装 Agent 的核心属性。
    由 GatewayDispatcher 从配置加载的 Agent dataclass 转换构建。

    Attributes:
        agent_id:      Agent 唯一标识。
        agent_name:    Agent 显示名称。
        agent_type:    Agent 类型（"main" / "partner" / "sub"）。
        agent_persona: Agent 人设描述，用于构建 system_prompt。
    """

    agent_id: str
    agent_name: str
    agent_type: str = "main"
    agent_persona: str = ""
    workspace: str = ""
    feature: str = ""
    model_name: str = ""
    temperature: float | None = None
    max_tokens: int | None = None

    @classmethod
    def from_orm(cls, agent_orm: Any) -> AgentInfo:
        """从 Agent 模型创建 AgentInfo（支持 ORM 和 dataclass）。

        Args:
            agent_orm: conversation.dao.models.Agent 实例（ORM 或 dataclass）。

        Returns:
            AgentInfo 值对象。
        """
        # 支持 dataclass（通过属性访问）和 dict（通过 get 方法）
        if isinstance(agent_orm, dict):
            return cls(
                agent_id=agent_orm.get("agent_id", ""),
                agent_name=agent_orm.get("agent_name", ""),
                agent_type=agent_orm.get("agent_type", "main"),
                agent_persona=agent_orm.get("agent_persona", ""),
                workspace=agent_orm.get("workspace", ""),
                feature=agent_orm.get("feature", ""),
                model_name=(agent_orm.get("model_config", {}) or {}).get("name", ""),
                temperature=(agent_orm.get("model_config", {}) or {}).get("temperature"),
                max_tokens=(agent_orm.get("model_config", {}) or {}).get("max_tokens"),
            )
        # 支持 dataclass 和 ORM 模型（通过属性访问）
        model_config = getattr(agent_orm, "model_config", {}) or {}
        return cls(
            agent_id=getattr(agent_orm, "agent_id", ""),
            agent_name=getattr(agent_orm, "agent_name", ""),
            agent_type=getattr(agent_orm, "agent_type", "main"),
            agent_persona=getattr(agent_orm, "agent_persona", ""),
            workspace=getattr(agent_orm, "workspace", ""),
            feature=getattr(agent_orm, "feature", ""),
            model_name=model_config.get("name", ""),
            temperature=model_config.get("temperature"),
            max_tokens=model_config.get("max_tokens"),
        )

    @classmethod
    def default(cls) -> AgentInfo:
        """创建默认 Agent 信息。

        使用与 bootstrap.py 中一致的默认值。

        Returns:
            默认 AgentInfo 实例。
        """
        from ..conversation.dao.bootstrap import DEFAULT_AGENT_ID

        return cls(
            agent_id=DEFAULT_AGENT_ID,
            agent_name="X-Agent",
            agent_type="main",
            agent_persona="",
        )

    def to_dict(self) -> dict[str, str]:
        """序列化为字典。

        Returns:
            包含 Agent 核心属性的字典。
        """
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "workspace": self.workspace,
            "feature": self.feature,
            "model_name": self.model_name,
        }
