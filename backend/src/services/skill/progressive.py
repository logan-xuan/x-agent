"""ProgressiveExecutor - 多阶段渐进式技能执行。

实现渐进式执行阶段:
DRY_RUN -> PLAN -> CONFIRM -> COMMIT -> ROLLBACK

支持预览、计划生成、确认和回滚能力。
"""

from dataclasses import dataclass, field
from typing import Any

from ...models.skill import (
    ExecutionStage,
    SkillExecutionContext,
    SkillManifest,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class StageResult:
    """单阶段执行结果。"""

    stage: ExecutionStage
    success: bool
    committed: bool = False

    # 预览/计划输出
    preview: str = ""
    steps: list[str] = field(default_factory=list)

    # 执行输出
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    # 回滚
    rollback_available: bool = False
    rollback_data: dict[str, Any] = field(default_factory=dict)

    # 错误
    error: str = ""


# 有效的阶段转换（当前阶段 -> 允许的下一阶段集合）
VALID_TRANSITIONS: dict[ExecutionStage, set[ExecutionStage]] = {
    ExecutionStage.DRY_RUN: {ExecutionStage.PLAN, ExecutionStage.CONFIRM, ExecutionStage.COMMIT},
    ExecutionStage.PLAN: {ExecutionStage.CONFIRM, ExecutionStage.COMMIT},
    ExecutionStage.CONFIRM: {ExecutionStage.COMMIT, ExecutionStage.ROLLBACK},
    ExecutionStage.COMMIT: {ExecutionStage.ROLLBACK},
    ExecutionStage.ROLLBACK: set(),  # 终态
}


class ProgressiveExecutor:
    """多阶段渐进式执行引擎。

    支持按阶段逐步执行技能:
    - DRY_RUN: 预览执行效果，无副作用
    - PLAN: 生成执行计划和步骤
    - CONFIRM: 等待用户确认
    - COMMIT: 执行实际操作
    - ROLLBACK: 撤销操作

    示例:
        progressive = ProgressiveExecutor()

        # 先预览
        ctx.stage = ExecutionStage.DRY_RUN
        preview = await progressive.execute_stage(manifest, ctx)

        # 再提交
        ctx.stage = ExecutionStage.COMMIT
        result = await progressive.execute_stage(manifest, ctx)
    """

    def is_valid_transition(
        self,
        from_stage: ExecutionStage,
        to_stage: ExecutionStage,
    ) -> bool:
        """检查阶段转换是否有效。

        Args:
            from_stage: 当前阶段
            to_stage: 目标阶段

        Returns:
            转换有效时返回 True
        """
        allowed = VALID_TRANSITIONS.get(from_stage, set())
        return to_stage in allowed

    async def execute_stage(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行技能的指定阶段。

        Args:
            manifest: 待执行的技能
            context: 包含目标阶段的执行上下文

        Returns:
            当前阶段的 StageResult
        """
        stage = context.stage

        logger.info(
            f"执行阶段 {stage.value}，技能 {manifest.skill_id}",
            extra={
                "skill_id": manifest.skill_id,
                "stage": stage.value,
                "session_id": context.session_id,
            },
        )

        if stage == ExecutionStage.DRY_RUN:
            return await self._execute_dry_run(manifest, context)
        elif stage == ExecutionStage.PLAN:
            return await self._execute_plan(manifest, context)
        elif stage == ExecutionStage.CONFIRM:
            return await self._execute_confirm(manifest, context)
        elif stage == ExecutionStage.COMMIT:
            return await self._execute_commit(manifest, context)
        elif stage == ExecutionStage.ROLLBACK:
            return await self._execute_rollback(manifest, context)
        else:
            return StageResult(
                stage=stage,
                success=False,
                error=f"Unknown stage: {stage.value}",
            )

    async def _execute_dry_run(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行试运行 - 预览效果，无副作用。"""
        if not manifest.supports_dry_run:
            return StageResult(
                stage=ExecutionStage.DRY_RUN,
                success=False,
                error=f"Skill '{manifest.skill_id}' does not support dry run",
            )

        preview = self._generate_preview(manifest, context)

        return StageResult(
            stage=ExecutionStage.DRY_RUN,
            success=True,
            committed=False,
            preview=preview,
        )

    async def _execute_plan(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行计划阶段 - 生成执行步骤。"""
        steps = self._generate_plan_steps(manifest, context)

        return StageResult(
            stage=ExecutionStage.PLAN,
            success=True,
            committed=False,
            steps=steps,
            preview=f"计划: 共 {len(steps)} 个步骤待执行",
        )

    async def _execute_confirm(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行确认阶段 - 返回确认请求。"""
        return StageResult(
            stage=ExecutionStage.CONFIRM,
            success=True,
            committed=False,
            preview=f"等待确认执行 '{manifest.skill_id}'",
        )

    async def _execute_commit(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行提交阶段 - 执行实际操作。"""
        logger.info(f"提交执行技能: {manifest.skill_id}", extra={"skill_id": manifest.skill_id})

        # 如果支持回滚，保存回滚数据
        rollback_data: dict[str, Any] = {}
        if manifest.supports_rollback:
            rollback_data = {
                "skill_id": manifest.skill_id,
                "params": dict(context.params),
                "timestamp": context.session_id,
            }

        # TODO: 实际执行分发逻辑
        return StageResult(
            stage=ExecutionStage.COMMIT,
            success=True,
            committed=True,
            output=f"技能 {manifest.skill_id} 提交执行成功",
            rollback_available=manifest.supports_rollback,
            rollback_data=rollback_data,
        )

    async def _execute_rollback(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> StageResult:
        """执行回滚阶段 - 撤销操作。"""
        if not manifest.supports_rollback:
            return StageResult(
                stage=ExecutionStage.ROLLBACK,
                success=False,
                error=f"Skill '{manifest.skill_id}' does not support rollback",
            )

        rollback_data = context.state.get("rollback_data")
        if not rollback_data:
            return StageResult(
                stage=ExecutionStage.ROLLBACK,
                success=False,
                error="No rollback state available",
            )

        logger.info(f"回滚技能: {manifest.skill_id}", extra={"skill_id": manifest.skill_id})

        # TODO: 实际回滚逻辑
        return StageResult(
            stage=ExecutionStage.ROLLBACK,
            success=True,
            committed=False,
            output=f"技能 {manifest.skill_id} 回滚成功",
        )

    def _generate_preview(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> str:
        """生成执行预览。"""
        parts = [
            f"[试运行] 技能: {manifest.name}",
            f"操作: {manifest.description}",
        ]

        if context.params:
            param_str = ", ".join(f"{k}={v}" for k, v in context.params.items())
            parts.append(f"参数: {param_str}")

        if manifest.side_effect:
            parts.append("警告: 此技能有副作用")

        return "\n".join(parts)

    def _generate_plan_steps(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> list[str]:
        """生成执行计划步骤。"""
        steps = [
            f"验证 '{manifest.skill_id}' 的参数",
        ]

        if manifest.preconditions:
            steps.append(f"检查前置条件: {', '.join(manifest.preconditions)}")

        steps.append(f"执行: {manifest.description}")

        if manifest.supports_rollback:
            steps.append("保存回滚状态")

        steps.append("返回结果")

        return steps
