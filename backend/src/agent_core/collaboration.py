"""多 Agent 协同模式定义.

定义协同模式的协议和数据结构，具体的执行逻辑由上层 Adapter 实现。

支持的协同模式：
- Leader-Worker: 主从模式，Leader 分配任务给多个 Worker
- Pipeline: 管道模式，数据按阶段顺序处理
- Discussion: 讨论模式，多个 Agent 就某个主题达成共识

设计原则：
- 零外部依赖，仅使用 Python 标准库
- 使用 dataclass 定义数据结构
- 使用 Protocol 定义执行端口
- 不包含具体执行逻辑

Example:
    # Leader-Worker 模式
    plan = LeaderWorkerPlan(
        plan_id="plan-001",
        leader_agent_id="leader-001",
        tasks=[
            WorkerTask(
                task_id="task-1",
                agent_id="worker-001",
                description="分析需求",
            ),
            WorkerTask(
                task_id="task-2",
                agent_id="worker-002",
                description="编写代码",
            ),
        ],
        parallel=True,
    )

    # Pipeline 模式
    pipeline = PipelinePlan(
        plan_id="pipeline-001",
        stages=[
            PipelineStage(stage_id="stage-1", agent_id="agent-001", description="数据清洗"),
            PipelineStage(stage_id="stage-2", agent_id="agent-002", description="数据分析"),
            PipelineStage(stage_id="stage-3", agent_id="agent-003", description="生成报告"),
        ],
    )

    # Discussion 模式
    discussion = DiscussionPlan(
        plan_id="discussion-001",
        topic="如何选择最佳架构方案",
        participant_agent_ids=["agent-001", "agent-002", "agent-003"],
        moderator_agent_id="agent-000",
        max_rounds=3,
        consensus_threshold=0.7,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class CollaborationMode(StrEnum):
    """协同模式类型"""

    LEADER_WORKER = "leader_worker"  # 主从模式
    PIPELINE = "pipeline"  # 管道模式
    DISCUSSION = "discussion"  # 讨论模式


class CollaborationStatus(StrEnum):
    """协同任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# === Leader-Worker 模式 ===


@dataclass
class WorkerTask:
    """分配给 Worker 的子任务"""

    task_id: str
    agent_id: str  # 目标 Worker Agent
    description: str  # 任务描述
    payload: dict[str, Any] = field(default_factory=dict)
    timeout: float = 120.0
    priority: int = 0

    # 结果
    status: CollaborationStatus = CollaborationStatus.PENDING
    result: Any = None
    error: str | None = None
    completed_at: datetime | None = None


@dataclass
class LeaderWorkerPlan:
    """Leader-Worker 协作计划"""

    plan_id: str
    leader_agent_id: str
    tasks: list[WorkerTask]
    aggregate_strategy: str = "merge"  # "merge" | "select_best" | "custom"
    parallel: bool = True  # 是否并行执行
    shared_context_id: str | None = None

    @property
    def all_completed(self) -> bool:
        """检查所有任务是否已完成（成功或失败）"""
        return all(
            t.status in (CollaborationStatus.COMPLETED, CollaborationStatus.FAILED)
            for t in self.tasks
        )

    @property
    def successful_tasks(self) -> list[WorkerTask]:
        """获取成功完成的任务列表"""
        return [t for t in self.tasks if t.status == CollaborationStatus.COMPLETED]

    @property
    def failed_tasks(self) -> list[WorkerTask]:
        """获取失败的任务列表"""
        return [t for t in self.tasks if t.status == CollaborationStatus.FAILED]

    @property
    def completion_rate(self) -> float:
        """获取完成率（0.0-1.0）"""
        if not self.tasks:
            return 0.0
        completed = len(
            [
                t
                for t in self.tasks
                if t.status in (CollaborationStatus.COMPLETED, CollaborationStatus.FAILED)
            ]
        )
        return completed / len(self.tasks)


# === Pipeline 模式 ===


@dataclass
class PipelineStage:
    """管道中的一个阶段"""

    stage_id: str
    agent_id: str
    description: str
    transform_fn_name: str | None = None  # 可选的数据转换函数名
    timeout: float = 120.0

    # 运行状态
    status: CollaborationStatus = CollaborationStatus.PENDING
    input_data: Any = None
    output_data: Any = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class PipelinePlan:
    """管道协作计划"""

    plan_id: str
    stages: list[PipelineStage]  # 按顺序执行
    shared_context_id: str | None = None

    @property
    def current_stage(self) -> PipelineStage | None:
        """获取当前正在执行的阶段"""
        for stage in self.stages:
            if stage.status in (CollaborationStatus.PENDING, CollaborationStatus.RUNNING):
                return stage
        return None

    @property
    def is_completed(self) -> bool:
        """检查管道是否已完成"""
        return all(s.status == CollaborationStatus.COMPLETED for s in self.stages)

    @property
    def has_failed(self) -> bool:
        """检查管道是否有失败阶段"""
        return any(s.status == CollaborationStatus.FAILED for s in self.stages)

    @property
    def final_output(self) -> Any:
        """获取最终输出（如果管道已完成）"""
        if self.stages and self.stages[-1].status == CollaborationStatus.COMPLETED:
            return self.stages[-1].output_data
        return None

    @property
    def progress(self) -> float:
        """获取进度（0.0-1.0）"""
        if not self.stages:
            return 0.0
        completed = len([s for s in self.stages if s.status == CollaborationStatus.COMPLETED])
        return completed / len(self.stages)


# === Discussion 模式 ===


@dataclass
class DiscussionContribution:
    """讨论中的一个观点"""

    agent_id: str
    viewpoint: str  # 观点内容
    reasoning: str  # 推理过程
    confidence: float = 0.5  # 置信度 0.0-1.0
    timestamp: datetime | None = None
    round_number: int = 0  # 第几轮讨论


@dataclass
class DiscussionPlan:
    """讨论协作计划"""

    plan_id: str
    topic: str  # 讨论主题
    participant_agent_ids: list[str]  # 参与讨论的 Agent
    moderator_agent_id: str  # 主持人 Agent
    max_rounds: int = 3  # 最大讨论轮次
    consensus_threshold: float = 0.7  # 共识阈值
    shared_context_id: str | None = None

    # 讨论状态
    contributions: list[DiscussionContribution] = field(default_factory=list)
    current_round: int = 0
    consensus: str | None = None  # 达成的共识
    status: CollaborationStatus = CollaborationStatus.PENDING

    def add_contribution(
        self, agent_id: str, viewpoint: str, reasoning: str = "", confidence: float = 0.5
    ) -> DiscussionContribution:
        """添加一个观点"""
        contribution = DiscussionContribution(
            agent_id=agent_id,
            viewpoint=viewpoint,
            reasoning=reasoning,
            confidence=confidence,
            timestamp=datetime.now(),
            round_number=self.current_round,
        )
        self.contributions.append(contribution)
        return contribution

    def advance_round(self) -> None:
        """进入下一轮讨论"""
        self.current_round += 1

    def set_consensus(self, consensus_text: str) -> None:
        """设置共识内容"""
        self.consensus = consensus_text
        self.status = CollaborationStatus.COMPLETED

    @property
    def is_consensus_reached(self) -> bool:
        """检查是否已达成共识"""
        return self.consensus is not None

    @property
    def contributions_by_round(self) -> dict[int, list[DiscussionContribution]]:
        """按轮次分组的观点"""
        result: dict[int, list[DiscussionContribution]] = {}
        for c in self.contributions:
            if c.round_number not in result:
                result[c.round_number] = []
            result[c.round_number].append(c)
        return result


# === 协同端口 (Protocol) ===


class CollaborationPort(Protocol):
    """协同模式的执行端口

    由上层 Adapter 实现具体的执行逻辑
    """

    async def execute_leader_worker(self, plan: LeaderWorkerPlan) -> dict[str, Any]:
        """执行 Leader-Worker 协作

        Args:
            plan: Leader-Worker 协作计划

        Returns:
            dict: 执行结果，包含聚合后的结果
        """
        ...

    async def execute_pipeline(self, plan: PipelinePlan) -> Any:
        """执行 Pipeline 协作

        Args:
            plan: 管道协作计划

        Returns:
            Any: 管道最终输出
        """
        ...

    async def execute_discussion(self, plan: DiscussionPlan) -> str:
        """执行 Discussion 协作，返回共识内容

        Args:
            plan: 讨论协作计划

        Returns:
            str: 达成的共识内容
        """
        ...
