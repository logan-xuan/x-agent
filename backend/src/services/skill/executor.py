"""SkillExecutor - 风险感知技能执行引擎。

实现基于风险的确认流程、权限验证、
前置条件检查和审批模式执行。

执行流程:
1. 验证权限 (required_auth 检查)
2. 验证前置条件 (必需参数检查)
3. 检查风险/审批要求
4. 执行或返回确认请求
"""

import importlib
import inspect
import time
from dataclasses import dataclass
from typing import Any

from ...models.skill import (
    ApprovalMode,
    ExecutionStage,
    RiskLevel,
    SkillExecutionContext,
    SkillExecutionResult,
    SkillManifest,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PermissionCheckResult:
    """权限验证结果。"""

    allowed: bool
    missing_permissions: list[str]


@dataclass
class PreconditionCheckResult:
    """前置条件验证结果。"""

    satisfied: bool
    missing_params: list[str]
    unsatisfied_conditions: list[str]


class SkillExecutor:
    """风险感知技能执行引擎。

    管理技能的完整执行生命周期，内置
    风险评估、权限检查和确认流程。

    示例:
        executor = SkillExecutor()
        result = await executor.execute(manifest, context)

        if result.confirmation_pending:
            # 向用户展示确认信息
            print(result.confirmation_message)
        elif result.success:
            print(result.output)
    """

    # 始终需要确认的风险等级
    HIGH_RISK_LEVELS = {RiskLevel.HIGH, RiskLevel.CRITICAL}

    # 需要确认的审批模式
    CONFIRM_MODES = {ApprovalMode.CONFIRM, ApprovalMode.APPROVAL, ApprovalMode.MANUAL}

    def needs_confirmation(self, manifest: SkillManifest) -> bool:
        """检查技能执行是否需要用户确认。

        Args:
            manifest: 待检查的技能清单

        Returns:
            需要确认时返回 True
        """
        # HIGH 和 CRITICAL 始终需要确认
        if manifest.risk_level in self.HIGH_RISK_LEVELS:
            return True

        # 检查审批模式
        return manifest.approval_mode in self.CONFIRM_MODES

    def validate_permissions(
        self,
        manifest: SkillManifest,
        user_permissions: list[str],
    ) -> PermissionCheckResult:
        """验证用户是否具备所需权限。

        Args:
            manifest: 包含 required_auth 的技能清单
            user_permissions: 用户可用权限列表

        Returns:
            包含允许状态和缺失列表的 PermissionCheckResult
        """
        if not manifest.required_auth:
            return PermissionCheckResult(allowed=True, missing_permissions=[])

        missing = [auth for auth in manifest.required_auth if auth not in user_permissions]

        return PermissionCheckResult(
            allowed=len(missing) == 0,
            missing_permissions=missing,
        )

    def validate_preconditions(
        self,
        manifest: SkillManifest,
        params: dict[str, Any],
    ) -> PreconditionCheckResult:
        """验证执行前置条件。

        检查 input_schema 中的必需参数。

        Args:
            manifest: 包含 input_schema 的技能清单
            params: 可用参数

        Returns:
            PreconditionCheckResult
        """
        missing_params = []

        if manifest.input_schema:
            required = manifest.input_schema.get("required", [])
            missing_params = [p for p in required if p not in params]

        return PreconditionCheckResult(
            satisfied=len(missing_params) == 0,
            missing_params=missing_params,
            unsatisfied_conditions=[],
        )

    async def execute(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        """执行技能（含风险感知流程）。

        执行流程:
        1. 检查权限
        2. 检查前置条件（必需参数）
        3. 如需确认且未自动确认，返回待确认状态
        4. 执行技能

        Args:
            manifest: 待执行的技能
            context: 执行上下文

        Returns:
            SkillExecutionResult
        """
        start_time = time.time()

        logger.info(
            f"执行技能: {manifest.skill_id}",
            extra={
                "skill_id": manifest.skill_id,
                "session_id": context.session_id,
                "risk_level": manifest.risk_level.value,
                "stage": context.stage.value,
            },
        )

        # 步骤 1: 权限检查
        perm_result = self.validate_permissions(manifest, context.user_permissions)
        if not perm_result.allowed:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                f"技能权限拒绝: {manifest.skill_id}",
                extra={
                    "missing_permissions": perm_result.missing_permissions,
                },
            )
            return SkillExecutionResult(
                success=False,
                stage=context.stage,
                error=f"Permission denied. Missing permissions: {', '.join(perm_result.missing_permissions)}",
                error_code="PERMISSION_DENIED",
                duration_ms=duration_ms,
            )

        # 步骤 2: 前置条件检查
        precond_result = self.validate_preconditions(manifest, context.params)
        if not precond_result.satisfied:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"技能前置条件未满足: {manifest.skill_id}",
                extra={
                    "missing_params": precond_result.missing_params,
                },
            )
            return SkillExecutionResult(
                success=False,
                stage=context.stage,
                error=f"Missing required parameters: {', '.join(precond_result.missing_params)}",
                error_code="MISSING_PARAMS",
                recoverable=True,
                duration_ms=duration_ms,
            )

        # 步骤 3: 确认检查
        if self.needs_confirmation(manifest) and not context.auto_confirm:
            duration_ms = int((time.time() - start_time) * 1000)
            confirmation_msg = self._build_confirmation_message(manifest, context)

            logger.info(
                f"技能需要确认: {manifest.skill_id}",
                extra={
                    "risk_level": manifest.risk_level.value,
                    "approval_mode": manifest.approval_mode.value,
                },
            )
            return SkillExecutionResult(
                success=True,
                stage=ExecutionStage.CONFIRM,
                confirmation_pending=True,
                confirmation_message=confirmation_msg,
                duration_ms=duration_ms,
            )

        # 步骤 4: 执行
        result = await self._do_execute(manifest, context)
        result.duration_ms = int((time.time() - start_time) * 1000)

        return result

    async def _do_execute(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        """执行技能的实际逻辑。

        当前为占位实现，后续将扩展支持
        不同的执行方式（callable、endpoint、script）。

        Args:
            manifest: 待执行的技能
            context: 执行上下文

        Returns:
            SkillExecutionResult
        """
        logger.info(
            f"执行技能逻辑: {manifest.skill_id}",
            extra={
                "skill_id": manifest.skill_id,
                "stage": context.stage.value,
            },
        )

        if manifest.callable:
            return await self._execute_callable(manifest, context)

        return SkillExecutionResult(
            success=True,
            stage=context.stage,
            output=f"Skill {manifest.skill_id} executed successfully",
            rollback_available=manifest.supports_rollback,
        )

    async def _execute_callable(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        """执行 manifest.callable 指定的 Python 入口。"""
        try:
            module_name, func_name = manifest.callable.split(":", 1)
        except ValueError:
            return SkillExecutionResult(
                success=False,
                stage=context.stage,
                error=f"Invalid callable format: {manifest.callable}",
                error_code="INVALID_CALLABLE",
                recoverable=False,
            )

        try:
            module = importlib.import_module(module_name)
            target = getattr(module, func_name)
        except Exception as exc:
            return SkillExecutionResult(
                success=False,
                stage=context.stage,
                error=f"Failed to load callable {manifest.callable}: {exc}",
                error_code="CALLABLE_IMPORT_ERROR",
                recoverable=False,
            )

        try:
            result = target(manifest, context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            logger.error(
                "Callable skill execution failed",
                extra={
                    "skill_id": manifest.skill_id,
                    "callable": manifest.callable,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            return SkillExecutionResult(
                success=False,
                stage=context.stage,
                error=f"Callable execution failed: {exc}",
                error_code="CALLABLE_EXECUTION_ERROR",
                recoverable=True,
            )

        if isinstance(result, SkillExecutionResult):
            return result

        return SkillExecutionResult(
            success=True,
            stage=context.stage,
            output=str(result),
            rollback_available=manifest.supports_rollback,
        )

    def _build_confirmation_message(
        self,
        manifest: SkillManifest,
        context: SkillExecutionContext,
    ) -> str:
        """构建人类可读的确认消息。

        Args:
            manifest: 需要确认的技能
            context: 执行上下文

        Returns:
            确认消息字符串
        """
        parts = [
            f"Skill '{manifest.skill_id}' requires confirmation.",
            f"Risk level: {manifest.risk_level.value}.",
        ]

        if manifest.side_effect:
            parts.append("This skill has side effects.")

        if manifest.description:
            parts.append(f"Description: {manifest.description}")

        return " ".join(parts)
