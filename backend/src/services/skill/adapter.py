"""SkillAdapter - 技能系统统一对外接口。

为 agent-core 提供单一入口，
与技能系统交互（搜索、执行、管理）。
"""

from typing import Any

from ...models.skill import (
    ExecutionStage,
    SkillCard,
    SkillExecutionContext,
    SkillExecutionResult,
    SkillManifest,
    SkillSearchContext,
)
from ...utils.logger import get_logger
from .discovery import SkillDiscovery
from .embedder import SkillEmbedder, get_embedder
from .executor import SkillExecutor
from .param_completer import ParamCompleter
from .progressive import ProgressiveExecutor
from .registry import SkillRegistry
from .scorer import SkillScorer

logger = get_logger(__name__)


class SkillAdapter:
    """技能系统统一接口。

    为 agent-core 提供简洁的 API:
    - 搜索/发现技能
    - 带风险管理的技能执行
    - 获取技能信息

    示例:
        adapter = SkillAdapter(registry=registry)

        # 搜索技能
        cards = adapter.search("转换为 pdf")

        # 执行技能
        result = await adapter.execute(
            skill_id="pdf-converter",
            session_id="session-123",
            params={"source_file": "report.md"},
        )
    """

    def __init__(
        self,
        registry: SkillRegistry,
        embedder: SkillEmbedder | None = None,
        scorer: SkillScorer | None = None,
    ) -> None:
        """初始化技能适配器。

        Args:
            registry: 技能注册表
            embedder: 嵌入器（为 None 时使用默认实例）
            scorer: 评分器（为 None 时使用默认实例）
        """
        self.registry = registry
        self.embedder = embedder or get_embedder()
        self.scorer = scorer or SkillScorer()
        self.discovery = SkillDiscovery(
            registry=registry,
            embedder=self.embedder,
            scorer=self.scorer,
        )
        self.executor = SkillExecutor()
        self.progressive = ProgressiveExecutor()
        self.param_completer = ParamCompleter()

        logger.info("SkillAdapter 初始化完成")

    def search(
        self,
        query: str,
        top_k: int = 10,
        domains: list[str] | None = None,
        available_params: dict[str, Any] | None = None,
        user_permissions: list[str] | None = None,
    ) -> list[SkillCard]:
        """搜索相关技能。

        Args:
            query: 用户查询文本
            top_k: 最大返回结果数
            domains: 领域过滤（可选）
            available_params: 上下文中可用的参数
            user_permissions: 用户权限列表

        Returns:
            按相关性排序的 SkillCard 列表
        """
        context = SkillSearchContext(
            user_input=query,
            available_params=available_params or {},
            user_permissions=user_permissions or [],
        )

        return self.discovery.discover(
            context=context,
            top_k=top_k,
            domains=domains,
        )

    async def execute(
        self,
        skill_id: str,
        session_id: str,
        params: dict[str, Any] | None = None,
        user_input: str = "",
        user_permissions: list[str] | None = None,
        stage: ExecutionStage = ExecutionStage.COMMIT,
        auto_confirm: bool = False,
    ) -> SkillExecutionResult:
        """按 ID 执行技能。

        处理参数补全、风险检查和执行。

        Args:
            skill_id: 技能标识符
            session_id: 会话 ID（用于追踪）
            params: 技能参数
            user_input: 原始用户输入（用于上下文提取）
            user_permissions: 用户权限列表
            stage: 执行阶段
            auto_confirm: 是否跳过高风险技能的确认

        Returns:
            SkillExecutionResult
        """
        # 查找技能
        manifest = self.registry.get_skill(skill_id)
        if not manifest:
            return SkillExecutionResult(
                success=False,
                error=f"Skill not found: {skill_id}",
                error_code="SKILL_NOT_FOUND",
            )

        # 补全参数
        completion = self.param_completer.complete(
            manifest=manifest,
            provided_params=params or {},
            user_input=user_input,
        )

        # 构建执行上下文
        context = SkillExecutionContext(
            session_id=session_id,
            user_input=user_input,
            user_permissions=user_permissions or [],
            params=completion.params,
            missing_params=completion.missing_params,
            stage=stage,
            auto_confirm=auto_confirm,
        )

        # 执行
        if stage != ExecutionStage.COMMIT:
            # 非提交阶段使用渐进式执行器
            stage_result = await self.progressive.execute_stage(manifest, context)
            return SkillExecutionResult(
                success=stage_result.success,
                stage=stage_result.stage,
                output=stage_result.output or stage_result.preview,
                rollback_available=stage_result.rollback_available,
                error=stage_result.error,
            )

        return await self.executor.execute(manifest, context)

    def get_skill(self, skill_id: str) -> SkillManifest | None:
        """按 ID 获取技能清单。

        Args:
            skill_id: 技能标识符

        Returns:
            SkillManifest 或 None
        """
        return self.registry.get_skill(skill_id)

    def list_skills(self) -> list[SkillManifest]:
        """列出所有可用技能。

        Returns:
            SkillManifest 列表
        """
        return self.registry.list_skills()

    def get_stats(self) -> dict[str, Any]:
        """获取技能系统统计信息。

        Returns:
            包含系统统计的字典
        """
        stats = self.registry.get_stats()
        return {
            "total_skills": stats.get("total_count", 0),
            "user_skills": stats.get("user_count", 0),
            "system_skills": stats.get("system_count", 0),
            "cache_valid": stats.get("cache_valid", False),
        }
