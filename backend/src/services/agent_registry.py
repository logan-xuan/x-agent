"""Agent 注册中心实现.

管理 Agent 的注册、发现、能力匹配和健康检查。

提供:
- Agent 注册与注销
- 能力标签查找
- 负载均衡选择
- 心跳与健康检查
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class AgentStatus(StrEnum):
    """Agent 状态."""

    IDLE = "idle"  # 空闲，可接受任务
    BUSY = "busy"  # 繁忙，正在执行任务
    OFFLINE = "offline"  # 离线


@dataclass
class AgentCapability:
    """Agent 能力描述.

    Attributes:
        agent_id: Agent 唯一标识符
        name: Agent 名称
        capabilities: 能力标签列表（如 ["research", "code-analysis", "summarize"]）
        status: 当前状态
        load: 当前负载（0.0-1.0）
        max_concurrent_tasks: 最大并发任务数
        current_tasks: 当前执行任务数
        last_heartbeat: 最后心跳时间
        metadata: 额外元数据
    """

    agent_id: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    load: float = 0.0  # 当前负载 0.0-1.0
    max_concurrent_tasks: int = 1
    current_tasks: int = 0
    last_heartbeat: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_load(self) -> None:
        """根据当前任务数更新负载."""
        if self.max_concurrent_tasks > 0:
            self.load = self.current_tasks / self.max_concurrent_tasks
        else:
            self.load = 0.0

    def can_accept_task(self) -> bool:
        """检查是否可以接受新任务."""
        return self.status != AgentStatus.OFFLINE and self.current_tasks < self.max_concurrent_tasks

    def has_capability(self, capability: str) -> bool:
        """检查是否拥有指定能力."""
        return capability in self.capabilities

    def has_all_capabilities(self, capabilities: list[str]) -> bool:
        """检查是否拥有所有指定能力."""
        return all(self.has_capability(c) for c in capabilities)


class AgentRegistry:
    """Agent 注册中心.

    管理 Agent 的注册、发现、能力匹配和健康检查。

    Example:
        registry = AgentRegistry()

        # 注册 Agent
        registry.register(AgentCapability(
            agent_id="research-agent",
            name="Research Agent",
            capabilities=["research", "summarize"],
            max_concurrent_tasks=3,
        ))

        # 查找 Agent
        agents = registry.find_by_capability("research")

        # 根据能力选择最佳 Agent
        best = registry.find_best_match(["research", "summarize"])

        # 心跳
        registry.heartbeat("research-agent")

        # 健康检查
        health = registry.check_health()
    """

    def __init__(self, heartbeat_timeout_seconds: float = 60.0):
        """初始化注册中心.

        Args:
            heartbeat_timeout_seconds: 心跳超时时间（秒）
        """
        self._agents: dict[str, AgentCapability] = {}
        self._heartbeat_timeout_seconds: float = heartbeat_timeout_seconds

    def register(self, agent: AgentCapability) -> None:
        """注册 Agent.

        Args:
            agent: Agent 能力描述
        """
        agent.last_heartbeat = datetime.now()
        self._agents[agent.agent_id] = agent

        logger.info(
            "Agent registered",
            extra={
                "agent_id": agent.agent_id,
                "name": agent.name,
                "capabilities": agent.capabilities,
                "status": agent.status.value,
            },
        )

    def unregister(self, agent_id: str) -> None:
        """注销 Agent.

        Args:
            agent_id: Agent ID
        """
        agent = self._agents.pop(agent_id, None)
        if agent:
            logger.info(
                "Agent unregistered",
                extra={"agent_id": agent_id},
            )

    def get_agent(self, agent_id: str) -> AgentCapability | None:
        """获取 Agent 信息.

        Args:
            agent_id: Agent ID

        Returns:
            AgentCapability | None: Agent 信息，不存在返回 None
        """
        return self._agents.get(agent_id)

    def list_agents(self, status: AgentStatus | None = None) -> list[AgentCapability]:
        """列出所有 Agent（可按状态过滤）.

        Args:
            status: 状态过滤（可选）

        Returns:
            list[AgentCapability]: Agent 列表
        """
        if status is None:
            return list(self._agents.values())
        return [a for a in self._agents.values() if a.status == status]

    def find_by_capability(self, capability: str) -> list[AgentCapability]:
        """根据能力标签查找 Agent.

        Args:
            capability: 能力标签

        Returns:
            list[AgentCapability]: 拥有该能力的 Agent 列表
        """
        return [
            a
            for a in self._agents.values()
            if a.has_capability(capability) and a.status != AgentStatus.OFFLINE
        ]

    def find_best_match(self, required_capabilities: list[str]) -> AgentCapability | None:
        """找到最佳匹配的 Agent（能力匹配 + 负载均衡）.

        匹配策略：
        1. 必须拥有所有 required_capabilities
        2. 状态不能是 OFFLINE
        3. 按负载从低到高排序
        4. 返回第一个

        Args:
            required_capabilities: 所需能力列表

        Returns:
            AgentCapability | None: 最佳匹配的 Agent，无匹配返回 None
        """
        candidates = [
            a
            for a in self._agents.values()
            if a.has_all_capabilities(required_capabilities)
            and a.status != AgentStatus.OFFLINE
            and a.can_accept_task()
        ]

        if not candidates:
            return None

        # 按负载排序，选择负载最低的
        candidates.sort(key=lambda a: a.load)
        return candidates[0]

    def update_status(self, agent_id: str, status: AgentStatus) -> None:
        """更新 Agent 状态.

        Args:
            agent_id: Agent ID
            status: 新状态
        """
        agent = self._agents.get(agent_id)
        if agent:
            old_status = agent.status
            agent.status = status

            logger.debug(
                "Agent status updated",
                extra={
                    "agent_id": agent_id,
                    "old_status": old_status.value,
                    "new_status": status.value,
                },
            )

    def heartbeat(self, agent_id: str) -> None:
        """Agent 心跳.

        Args:
            agent_id: Agent ID
        """
        agent = self._agents.get(agent_id)
        if agent:
            agent.last_heartbeat = datetime.now()

    def update_load(self, agent_id: str, load: float) -> None:
        """更新 Agent 负载.

        Args:
            agent_id: Agent ID
            load: 新负载值（0.0-1.0）
        """
        agent = self._agents.get(agent_id)
        if agent:
            agent.load = max(0.0, min(1.0, load))

    def increment_tasks(self, agent_id: str) -> None:
        """增加 Agent 的当前任务数.

        Args:
            agent_id: Agent ID
        """
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_tasks += 1
            agent.update_load()
            agent.status = AgentStatus.BUSY if agent.current_tasks > 0 else AgentStatus.IDLE

    def decrement_tasks(self, agent_id: str) -> None:
        """减少 Agent 的当前任务数.

        Args:
            agent_id: Agent ID
        """
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_tasks = max(0, agent.current_tasks - 1)
            agent.update_load()
            agent.status = AgentStatus.BUSY if agent.current_tasks > 0 else AgentStatus.IDLE

    def check_health(self) -> dict[str, Any]:
        """检查所有 Agent 健康状态，标记超时的为 OFFLINE.

        Returns:
            dict: 健康检查结果
        """
        now = datetime.now()
        timeout = timedelta(seconds=self._heartbeat_timeout_seconds)

        healthy = 0
        unhealthy = 0
        offline = 0

        for agent in self._agents.values():
            if agent.last_heartbeat is None:
                # 安全措施：如果 last_heartbeat 为 None，设置为当前时间并保持 IDLE 状态
                # 正常流程中 register() 已经设置了 last_heartbeat = datetime.now()
                # 所以这里不应该出现 None，但作为安全措施处理
                agent.last_heartbeat = now
                if agent.status == AgentStatus.OFFLINE:
                    agent.status = AgentStatus.IDLE
                    logger.info(
                        "Agent heartbeat initialized, set to IDLE",
                        extra={"agent_id": agent.agent_id},
                    )
                healthy += 1
                continue

            time_since_heartbeat = now - agent.last_heartbeat
            if time_since_heartbeat > timeout:
                if agent.status != AgentStatus.OFFLINE:
                    logger.warning(
                        "Agent heartbeat timeout, marking offline",
                        extra={
                            "agent_id": agent.agent_id,
                            "last_heartbeat": agent.last_heartbeat.isoformat(),
                            "seconds_since_heartbeat": time_since_heartbeat.total_seconds(),
                        },
                    )
                    agent.status = AgentStatus.OFFLINE
                offline += 1
            else:
                if agent.status == AgentStatus.OFFLINE:
                    # 心跳恢复，重新上线
                    agent.status = AgentStatus.IDLE
                    logger.info(
                        "Agent heartbeat recovered, back online",
                        extra={"agent_id": agent.agent_id},
                    )
                if agent.status == AgentStatus.IDLE:
                    healthy += 1
                else:
                    unhealthy += 1

        return {
            "total": len(self._agents),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "offline": offline,
            "timestamp": now.isoformat(),
        }

    def get_statistics(self) -> dict[str, Any]:
        """获取注册中心统计信息.

        Returns:
            dict: 统计信息
        """
        status_counts = {}
        capability_counts: dict[str, int] = {}
        total_load = 0.0

        for agent in self._agents.values():
            # 状态统计
            status_key = agent.status.value
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            # 能力统计
            for cap in agent.capabilities:
                capability_counts[cap] = capability_counts.get(cap, 0) + 1

            # 负载统计
            total_load += agent.load

        avg_load = total_load / len(self._agents) if self._agents else 0.0

        return {
            "total_agents": len(self._agents),
            "status_distribution": status_counts,
            "capability_distribution": capability_counts,
            "average_load": round(avg_load, 3),
            "heartbeat_timeout_seconds": self._heartbeat_timeout_seconds,
        }

    def get_all_capabilities(self) -> list[str]:
        """获取所有已注册的能力标签.

        Returns:
            list[str]: 能力标签列表（去重）
        """
        capabilities: set[str] = set()
        for agent in self._agents.values():
            capabilities.update(agent.capabilities)
        return sorted(capabilities)


# 全局 AgentRegistry 实例
_global_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 实例.

    Returns:
        AgentRegistry: 全局注册中心实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = AgentRegistry()
    return _global_registry


def reset_agent_registry() -> None:
    """重置全局 AgentRegistry 实例（用于测试）."""
    global _global_registry
    _global_registry = None
