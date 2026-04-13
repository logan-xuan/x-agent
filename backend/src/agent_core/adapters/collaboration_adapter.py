"""CollaborationAdapter - 实现 CollaborationPort Protocol.

基于 DelegateAdapter 和 SharedContext 实现多 Agent 协同模式。
支持三种协同模式:
- Leader-Worker: 主从模式，Leader 分配任务给多个 Worker
- Pipeline: 管道模式，数据按阶段顺序处理
- Discussion: 讨论模式，多个 Agent 就某个主题达成共识

Example:
    from agent_core.adapters.collaboration_adapter import (
        CollaborationAdapter,
        create_collaboration_adapter,
    )

    # 使用工厂函数创建
    adapter = create_collaboration_adapter(
        leader_agent_id="leader-001",
    )

    # Leader-Worker 协作
    plan = LeaderWorkerPlan(
        plan_id="plan-001",
        leader_agent_id="leader-001",
        tasks=[
            WorkerTask(task_id="t1", agent_id="worker-001", description="任务1"),
            WorkerTask(task_id="t2", agent_id="worker-002", description="任务2"),
        ],
        parallel=True,
    )
    result = await adapter.execute_leader_worker(plan)

    # Pipeline 协作
    pipeline = PipelinePlan(
        plan_id="pipeline-001",
        stages=[
            PipelineStage(stage_id="s1", agent_id="agent-001", description="阶段1"),
            PipelineStage(stage_id="s2", agent_id="agent-002", description="阶段2"),
        ],
    )
    output = await adapter.execute_pipeline(pipeline)

    # Discussion 协作
    discussion = DiscussionPlan(
        plan_id="discussion-001",
        topic="选择最佳方案",
        participant_agent_ids=["agent-001", "agent-002", "agent-003"],
        moderator_agent_id="moderator-001",
        max_rounds=3,
    )
    consensus = await adapter.execute_discussion(discussion)
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..collaboration import (
    CollaborationMode,
    CollaborationStatus,
    DiscussionPlan,
    LeaderWorkerPlan,
    PipelinePlan,
)
from ..ports.delegate_port import DelegateTask
from ..shared_context import SharedContext

if TYPE_CHECKING:
    from ..hooks import HookRegistry
    from .delegate_adapter import DelegateAdapter

try:
    from ...utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


# === 共享上下文管理器 ===


class SharedContextManager:
    """管理多个 SharedContext 实例."""

    def __init__(self):
        self._contexts: dict[str, SharedContext] = {}

    def create_context(
        self, context_id: str | None = None, creator_agent_id: str = ""
    ) -> SharedContext:
        """创建新的共享上下文."""
        context = SharedContext(context_id=context_id, creator_agent_id=creator_agent_id)
        self._contexts[context.context_id] = context
        return context

    def get_context(self, context_id: str) -> SharedContext | None:
        """获取共享上下文."""
        return self._contexts.get(context_id)

    def delete_context(self, context_id: str) -> bool:
        """删除共享上下文."""
        if context_id in self._contexts:
            del self._contexts[context_id]
            return True
        return False

    def list_contexts(self) -> list[str]:
        """列出所有上下文 ID."""
        return list(self._contexts.keys())


# 全局共享上下文管理器
_global_context_manager: SharedContextManager | None = None


def get_shared_context_manager() -> SharedContextManager:
    """获取全局共享上下文管理器."""
    global _global_context_manager
    if _global_context_manager is None:
        _global_context_manager = SharedContextManager()
    return _global_context_manager


# === CollaborationAdapter ===


class CollaborationAdapter:
    """CollaborationPort 适配器.

    基于 DelegateAdapter 和 SharedContext 实现多 Agent 协同模式。

    职责:
    1. 实现 CollaborationPort Protocol
    2. 管理协同任务的生命周期
    3. 协调多个 Agent 的执行
    4. 管理共享上下文
    5. 触发协同相关的 Hook

    Attributes:
        _leader_agent_id: 协同任务发起者的 Agent ID
        _delegate_adapter: DelegateAdapter 实例
        _context_manager: SharedContextManager 实例
        _hooks: HookRegistry 实例（可选）
    """

    def __init__(
        self,
        leader_agent_id: str,
        delegate_adapter: DelegateAdapter,
        context_manager: SharedContextManager | None = None,
        hooks: HookRegistry | None = None,
    ) -> None:
        """初始化适配器.

        Args:
            leader_agent_id: 协同任务发起者的 Agent ID
            delegate_adapter: DelegateAdapter 实例
            context_manager: SharedContextManager 实例
            hooks: Hook 注册中心（可选）
        """
        self._leader_agent_id = leader_agent_id
        self._delegate_adapter = delegate_adapter
        self._context_manager = context_manager or get_shared_context_manager()
        self._hooks = hooks

    @property
    def leader_agent_id(self) -> str:
        """获取协同任务发起者的 Agent ID."""
        return self._leader_agent_id

    # === Leader-Worker 模式 ===

    async def execute_leader_worker(self, plan: LeaderWorkerPlan) -> dict[str, Any]:
        """执行 Leader-Worker 协作.

        流程:
        1. 创建共享上下文（如果指定）
        2. 触发 ON_COLLABORATION_START Hook
        3. 根据 parallel 设置，并行或串行执行任务
        4. 收集所有结果
        5. 根据 aggregate_strategy 聚合结果
        6. 触发 ON_COLLABORATION_END Hook

        Args:
            plan: Leader-Worker 协作计划

        Returns:
            dict: 执行结果
        """
        start_time = time.time()

        logger.info(
            "Starting Leader-Worker collaboration",
            extra={
                "plan_id": plan.plan_id,
                "leader_agent_id": plan.leader_agent_id,
                "task_count": len(plan.tasks),
                "parallel": plan.parallel,
            },
        )

        # 创建共享上下文
        shared_context = None
        if plan.shared_context_id:
            shared_context = self._context_manager.create_context(
                context_id=plan.shared_context_id,
                creator_agent_id=plan.leader_agent_id,
            )
            # 添加所有参与者
            for task in plan.tasks:
                shared_context.add_participant(task.agent_id)

        # 触发开始 Hook
        await self._trigger_collaboration_start_hook(
            plan_id=plan.plan_id,
            mode=CollaborationMode.LEADER_WORKER,
            participants=[t.agent_id for t in plan.tasks],
        )

        try:
            # 执行任务
            if plan.parallel:
                await self._execute_worker_tasks_parallel(plan, shared_context)
            else:
                await self._execute_worker_tasks_serial(plan, shared_context)

            # 聚合结果
            aggregated = self._aggregate_results(plan)

            execution_time = (time.time() - start_time) * 1000

            result = {
                "plan_id": plan.plan_id,
                "success": len(plan.failed_tasks) == 0,
                "total_tasks": len(plan.tasks),
                "successful_tasks": len(plan.successful_tasks),
                "failed_tasks": len(plan.failed_tasks),
                "aggregated_result": aggregated,
                "execution_time_ms": execution_time,
                "task_results": [
                    {
                        "task_id": t.task_id,
                        "agent_id": t.agent_id,
                        "status": t.status.value,
                        "result": t.result,
                        "error": t.error,
                    }
                    for t in plan.tasks
                ],
            }

            logger.info(
                "Leader-Worker collaboration completed",
                extra={
                    "plan_id": plan.plan_id,
                    "success_count": len(plan.successful_tasks),
                    "failure_count": len(plan.failed_tasks),
                    "execution_time_ms": execution_time,
                },
            )

            return result

        finally:
            # 触发结束 Hook
            await self._trigger_collaboration_end_hook(
                plan_id=plan.plan_id,
                mode=CollaborationMode.LEADER_WORKER,
                success=len(plan.failed_tasks) == 0,
            )

    async def _execute_worker_tasks_parallel(
        self,
        plan: LeaderWorkerPlan,
        shared_context: SharedContext | None,
    ) -> None:
        """并行执行 Worker 任务."""
        # 创建所有委派任务
        delegate_tasks = []
        for task in plan.tasks:
            task.status = CollaborationStatus.RUNNING

            delegate_task = DelegateTask.create(
                task_type=f"leader-worker:{task.task_id}",
                description=task.description,
                payload={
                    **task.payload,
                    "shared_context_id": shared_context.context_id if shared_context else None,
                },
                timeout=task.timeout,
            )
            delegate_tasks.append((task.agent_id, delegate_task))

        # 并行委派
        results = await self._delegate_adapter.delegate_parallel(delegate_tasks)

        # 更新任务状态
        for task, result in zip(plan.tasks, results, strict=False):
            task.completed_at = datetime.now()
            if result.success:
                task.status = CollaborationStatus.COMPLETED
                task.result = result.result
            else:
                task.status = CollaborationStatus.FAILED
                task.error = result.error

    async def _execute_worker_tasks_serial(
        self,
        plan: LeaderWorkerPlan,
        shared_context: SharedContext | None,
    ) -> None:
        """串行执行 Worker 任务."""
        for task in plan.tasks:
            task.status = CollaborationStatus.RUNNING

            delegate_task = DelegateTask.create(
                task_type=f"leader-worker:{task.task_id}",
                description=task.description,
                payload={
                    **task.payload,
                    "shared_context_id": shared_context.context_id if shared_context else None,
                },
                timeout=task.timeout,
            )

            result = await self._delegate_adapter.delegate(task.agent_id, delegate_task)

            task.completed_at = datetime.now()
            if result.success:
                task.status = CollaborationStatus.COMPLETED
                task.result = result.result
            else:
                task.status = CollaborationStatus.FAILED
                task.error = result.error

    def _aggregate_results(self, plan: LeaderWorkerPlan) -> Any:
        """聚合 Worker 结果."""
        results = [t.result for t in plan.successful_tasks]

        if plan.aggregate_strategy == "merge":
            # 合并所有结果到一个列表
            return results

        elif plan.aggregate_strategy == "select_best":
            # 选择第一个成功的结果（简单实现）
            return results[0] if results else None

        else:
            # 默认返回所有结果
            return results

    # === Pipeline 模式 ===

    async def execute_pipeline(self, plan: PipelinePlan) -> Any:
        """执行 Pipeline 协作.

        流程:
        1. 创建共享上下文（如果指定）
        2. 触发 ON_COLLABORATION_START Hook
        3. 按顺序执行每个阶段，前一阶段输出作为下一阶段输入
        4. 如果任何阶段失败，终止管道
        5. 触发 ON_COLLABORATION_END Hook

        Args:
            plan: 管道协作计划

        Returns:
            Any: 管道最终输出
        """
        start_time = time.time()

        logger.info(
            "Starting Pipeline collaboration",
            extra={
                "plan_id": plan.plan_id,
                "stage_count": len(plan.stages),
            },
        )

        # 创建共享上下文
        shared_context = None
        if plan.shared_context_id:
            shared_context = self._context_manager.create_context(
                context_id=plan.shared_context_id,
                creator_agent_id=self._leader_agent_id,
            )
            for stage in plan.stages:
                shared_context.add_participant(stage.agent_id)

        # 触发开始 Hook
        await self._trigger_collaboration_start_hook(
            plan_id=plan.plan_id,
            mode=CollaborationMode.PIPELINE,
            participants=[s.agent_id for s in plan.stages],
        )

        current_input: Any = None

        try:
            for i, stage in enumerate(plan.stages):
                stage.status = CollaborationStatus.RUNNING
                stage.started_at = datetime.now()
                stage.input_data = current_input

                logger.debug(
                    f"Executing pipeline stage {i + 1}/{len(plan.stages)}",
                    extra={
                        "stage_id": stage.stage_id,
                        "agent_id": stage.agent_id,
                    },
                )

                # 创建委派任务
                delegate_task = DelegateTask.create(
                    task_type=f"pipeline:{stage.stage_id}",
                    description=stage.description,
                    payload={
                        "input": current_input,
                        "stage_index": i,
                        "total_stages": len(plan.stages),
                        "shared_context_id": shared_context.context_id if shared_context else None,
                    },
                    timeout=stage.timeout,
                )

                result = await self._delegate_adapter.delegate(stage.agent_id, delegate_task)
                stage.completed_at = datetime.now()

                if result.success:
                    stage.status = CollaborationStatus.COMPLETED
                    stage.output_data = result.result
                    current_input = result.result  # 传递给下一阶段

                    # 更新共享上下文
                    if shared_context:
                        await shared_context.set(
                            f"stage_{stage.stage_id}_output",
                            result.result,
                            agent_id=stage.agent_id,
                        )
                else:
                    stage.status = CollaborationStatus.FAILED
                    stage.error = result.error

                    logger.error(
                        "Pipeline stage failed",
                        extra={
                            "stage_id": stage.stage_id,
                            "error": result.error,
                        },
                    )
                    break

            execution_time = (time.time() - start_time) * 1000

            if plan.is_completed:
                logger.info(
                    "Pipeline collaboration completed successfully",
                    extra={
                        "plan_id": plan.plan_id,
                        "execution_time_ms": execution_time,
                    },
                )
                return plan.final_output
            else:
                logger.warning(
                    "Pipeline collaboration failed",
                    extra={
                        "plan_id": plan.plan_id,
                        "progress": plan.progress,
                    },
                )
                return None

        finally:
            # 触发结束 Hook
            await self._trigger_collaboration_end_hook(
                plan_id=plan.plan_id,
                mode=CollaborationMode.PIPELINE,
                success=plan.is_completed,
            )

    # === Discussion 模式 ===

    async def execute_discussion(self, plan: DiscussionPlan) -> str:
        """执行 Discussion 协作，返回共识内容.

        流程:
        1. 创建共享上下文（如果指定）
        2. 触发 ON_COLLABORATION_START Hook
        3. 多轮收集观点：
           a. 向所有参与者请求观点
           b. 发布到消息板
           c. 重复直到达到最大轮次或达成共识
        4. 请求主持人生成总结共识
        5. 触发 ON_COLLABORATION_END Hook

        Args:
            plan: 讨论协作计划

        Returns:
            str: 达成的共识内容
        """
        start_time = time.time()
        plan.status = CollaborationStatus.RUNNING

        logger.info(
            "Starting Discussion collaboration",
            extra={
                "plan_id": plan.plan_id,
                "topic": plan.topic,
                "participant_count": len(plan.participant_agent_ids),
                "max_rounds": plan.max_rounds,
            },
        )

        # 创建共享上下文
        shared_context = None
        if plan.shared_context_id:
            shared_context = self._context_manager.create_context(
                context_id=plan.shared_context_id,
                creator_agent_id=plan.moderator_agent_id,
            )
            for agent_id in plan.participant_agent_ids:
                shared_context.add_participant(agent_id)
            shared_context.add_participant(plan.moderator_agent_id)

        # 触发开始 Hook
        await self._trigger_collaboration_start_hook(
            plan_id=plan.plan_id,
            mode=CollaborationMode.DISCUSSION,
            participants=plan.participant_agent_ids + [plan.moderator_agent_id],
        )

        try:
            # 多轮讨论
            for round_num in range(plan.max_rounds):
                plan.current_round = round_num + 1

                logger.debug(
                    f"Discussion round {plan.current_round}/{plan.max_rounds}",
                    extra={"plan_id": plan.plan_id},
                )

                # 收集观点
                await self._collect_round_contributions(plan, shared_context)

                # 检查是否可以达成共识（简单实现：检查是否有足够相似的观点）
                if await self._check_consensus(plan):
                    break

            # 请求主持人生成共识
            consensus = await self._generate_consensus(plan, shared_context)
            plan.set_consensus(consensus)

            execution_time = (time.time() - start_time) * 1000

            logger.info(
                "Discussion collaboration completed",
                extra={
                    "plan_id": plan.plan_id,
                    "rounds_used": plan.current_round,
                    "contribution_count": len(plan.contributions),
                    "execution_time_ms": execution_time,
                },
            )

            return consensus

        finally:
            # 触发结束 Hook
            await self._trigger_collaboration_end_hook(
                plan_id=plan.plan_id,
                mode=CollaborationMode.DISCUSSION,
                success=plan.is_consensus_reached,
            )

    async def _collect_round_contributions(
        self,
        plan: DiscussionPlan,
        shared_context: SharedContext | None,
    ) -> None:
        """收集一轮讨论的观点."""
        # 并行请求所有参与者的观点
        tasks = []
        for agent_id in plan.participant_agent_ids:
            delegate_task = DelegateTask.create(
                task_type="discussion:contribute",
                description=f"请就以下主题发表你的观点: {plan.topic}",
                payload={
                    "topic": plan.topic,
                    "round_number": plan.current_round,
                    "previous_contributions": [
                        {"agent_id": c.agent_id, "viewpoint": c.viewpoint}
                        for c in plan.contributions
                        if c.round_number == plan.current_round - 1
                    ],
                    "shared_context_id": shared_context.context_id if shared_context else None,
                },
                timeout=60.0,
            )
            tasks.append((agent_id, delegate_task))

        results = await self._delegate_adapter.delegate_parallel(tasks)

        # 处理结果
        for i, result in enumerate(results):
            agent_id = plan.participant_agent_ids[i]

            if result.success and isinstance(result.result, dict):
                contribution = plan.add_contribution(
                    agent_id=agent_id,
                    viewpoint=result.result.get("viewpoint", ""),
                    reasoning=result.result.get("reasoning", ""),
                    confidence=result.result.get("confidence", 0.5),
                )

                # 发布到消息板
                if shared_context:
                    await shared_context.post_message(
                        agent_id=agent_id,
                        content=contribution.viewpoint,
                        tags=["contribution", f"round-{plan.current_round}"],
                    )

    async def _check_consensus(self, plan: DiscussionPlan) -> bool:
        """检查是否达成共识（简单实现）.

        在实际场景中，这可能需要更复杂的逻辑，如语义相似度计算。
        """
        # 获取当前轮的观点
        current_contributions = [
            c for c in plan.contributions if c.round_number == plan.current_round
        ]

        if not current_contributions:
            return False

        # 简单实现：如果所有观点的置信度都超过阈值，认为达成共识
        avg_confidence = sum(c.confidence for c in current_contributions) / len(
            current_contributions
        )
        return avg_confidence >= plan.consensus_threshold

    async def _generate_consensus(
        self,
        plan: DiscussionPlan,
        shared_context: SharedContext | None,
    ) -> str:
        """请求主持人生成共识总结."""
        # 收集所有观点
        all_viewpoints = [
            {
                "agent_id": c.agent_id,
                "viewpoint": c.viewpoint,
                "reasoning": c.reasoning,
                "confidence": c.confidence,
                "round": c.round_number,
            }
            for c in plan.contributions
        ]

        delegate_task = DelegateTask.create(
            task_type="discussion:summarize",
            description=f"请作为主持人，总结以下讨论并形成共识: {plan.topic}",
            payload={
                "topic": plan.topic,
                "viewpoints": all_viewpoints,
                "rounds": plan.current_round,
                "shared_context_id": shared_context.context_id if shared_context else None,
            },
            timeout=60.0,
        )

        result = await self._delegate_adapter.delegate(
            plan.moderator_agent_id,
            delegate_task,
        )

        if result.success and isinstance(result.result, dict):
            return result.result.get("consensus", "无法达成共识")

        return "讨论未能达成共识"

    # === Hook 触发 ===

    async def _trigger_collaboration_start_hook(
        self,
        plan_id: str,
        mode: CollaborationMode,
        participants: list[str],
    ) -> None:
        """触发 ON_COLLABORATION_START Hook."""
        from ..hooks import HookContext, HookPoint

        if self._hooks is None:
            return

        hook_ctx = HookContext(
            point=HookPoint.ON_COLLABORATION_START,
            data={
                "plan_id": plan_id,
                "mode": mode.value,
                "leader_agent_id": self._leader_agent_id,
                "participants": participants,
            },
        )
        await self._hooks.trigger(hook_ctx)

    async def _trigger_collaboration_end_hook(
        self,
        plan_id: str,
        mode: CollaborationMode,
        success: bool,
    ) -> None:
        """触发 ON_COLLABORATION_END Hook."""
        from ..hooks import HookContext, HookPoint

        if self._hooks is None:
            return

        hook_ctx = HookContext(
            point=HookPoint.ON_COLLABORATION_END,
            data={
                "plan_id": plan_id,
                "mode": mode.value,
                "leader_agent_id": self._leader_agent_id,
                "success": success,
            },
        )
        await self._hooks.trigger(hook_ctx)


# === 工厂函数 ===


def create_collaboration_adapter(
    leader_agent_id: str,
    delegate_adapter: DelegateAdapter | None = None,
    context_manager: SharedContextManager | None = None,
    hooks: HookRegistry | None = None,
) -> CollaborationAdapter:
    """创建 CollaborationAdapter 的工厂函数.

    Args:
        leader_agent_id: 协同任务发起者的 Agent ID
        delegate_adapter: DelegateAdapter 实例，为 None 时自动创建
        context_manager: SharedContextManager 实例
        hooks: Hook 注册中心（可选）

    Returns:
        CollaborationAdapter 实例
    """
    # 如果没有提供 delegate_adapter，创建一个
    if delegate_adapter is None:
        from .delegate_adapter import create_delegate_adapter

        delegate_adapter = create_delegate_adapter(
            source_agent_id=leader_agent_id,
            hooks=hooks,
        )

    adapter = CollaborationAdapter(
        leader_agent_id=leader_agent_id,
        delegate_adapter=delegate_adapter,
        context_manager=context_manager,
        hooks=hooks,
    )

    logger.info(
        "CollaborationAdapter created",
        extra={
            "leader_agent_id": leader_agent_id,
        },
    )

    return adapter
