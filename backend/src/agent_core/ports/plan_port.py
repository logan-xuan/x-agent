"""计划管理接口定义.

PlanPort 定义了 agent_core 与计划系统交互的接口。
支持任务规划、进度追踪、动态调整等能力。

扩展点说明:
    实现者可以接入不同的计划系统：
    - 简单文本计划（默认）
    - DAG依赖图计划
    - 外部任务调度系统
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..types import AgentContext


class PlanStatus(Enum):
    """计划状态."""

    PENDING = "pending"  # 待执行
    IN_PROGRESS = "in_progress"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class StepStatus(Enum):
    """步骤状态."""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过


@dataclass
class PlanStep:
    """计划步骤.

    Attributes:
        step_id: 步骤唯一标识
        description: 步骤描述
        tool_name: 推荐使用的工具（可选）
        status: 当前状态
        dependencies: 依赖的步骤ID列表
        result: 执行结果（可选）
        error: 错误信息（可选）
    """

    step_id: str
    description: str
    tool_name: str = ""
    status: StepStatus = StepStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    result: str = ""
    error: str = ""


@dataclass
class Plan:
    """执行计划.

    Attributes:
        plan_id: 计划唯一标识
        goal: 目标描述
        steps: 步骤列表
        current_step: 当前步骤索引
        status: 计划状态
        metadata: 元数据
    """

    plan_id: str = ""
    goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    status: PlanStatus = PlanStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_current_step(self) -> PlanStep | None:
        """获取当前步骤."""
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def get_progress(self) -> tuple[int, int]:
        """获取进度 (已完成, 总数)."""
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed, len(self.steps)


class PlanPort(Protocol):
    """计划管理接口.

    agent_core 通过此接口进行任务规划和管理。
    实现者需要提供计划生成、更新、查询等能力。

    Example:
        class SimplePlanner:
            async def generate_plan(self, goal, context):
                # 基于目标生成简单文本计划
                steps = [
                    PlanStep(step_id="1", description="分析需求"),
                    PlanStep(step_id="2", description="执行操作"),
                    PlanStep(step_id="3", description="验证结果"),
                ]
                return Plan(goal=goal, steps=steps)
    """

    async def generate_plan(
        self,
        goal: str,
        context: AgentContext,
    ) -> Plan:
        """生成执行计划.

        Args:
            goal: 用户目标描述
            context: Agent 上下文，包含工具列表等信息

        Returns:
            Plan: 生成的执行计划

        Raises:
            Exception: 生成失败时抛出异常
        """
        ...

    async def update_step(
        self,
        plan_id: str,
        step_id: str,
        status: StepStatus,
        result: str | None = None,
        error: str | None = None,
    ) -> bool:
        """更新步骤状态.

        Args:
            plan_id: 计划ID
            step_id: 步骤ID
            status: 新状态
            result: 执行结果（可选）
            error: 错误信息（可选）

        Returns:
            bool: 是否更新成功
        """
        ...

    async def get_plan(self, plan_id: str) -> Plan | None:
        """获取计划详情.

        Args:
            plan_id: 计划ID

        Returns:
            Plan | None: 计划详情，不存在返回 None
        """
        ...

    async def should_replan(
        self,
        plan: Plan,
        context: AgentContext,
    ) -> tuple[bool, str]:
        """判断是否需要重新规划.

        Args:
            plan: 当前计划
            context: 当前上下文

        Returns:
            tuple[bool, str]: (是否需要重规划, 原因说明)
        """
        ...

    async def replan(
        self,
        plan: Plan,
        reason: str,
        context: AgentContext,
    ) -> Plan:
        """重新规划.

        Args:
            plan: 原计划
            reason: 重规划原因
            context: 当前上下文

        Returns:
            Plan: 新计划
        """
        ...
