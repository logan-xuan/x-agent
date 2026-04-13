"""SkillRegistry - 技能注册表，提供技能发现与管理。

支持两级来源优先级 (USER > SYSTEM) 和缓存机制。

特性:
- 两级来源优先级: USER 技能覆盖同名 SYSTEM 技能
- 基于 TTL 的缓存，支持手动失效
- 结构化日志，便于可观测
"""

import contextlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...models.skill import SkillManifest, SkillSource
from ...utils.logger import get_logger
from .manifest_parser import ManifestParseError, ManifestParser

logger = get_logger(__name__)


class SkillRegistry:
    """技能发现与管理注册表。

    支持两级来源优先级:
    - USER (优先级 100): 用户/工作区技能 - 最高优先级
    - SYSTEM (优先级 200): 系统内置技能 - 较低优先级

    当 skill_id 相同时，USER 技能覆盖 SYSTEM 技能。

    示例:
        registry = SkillRegistry(
            user_skills_dir=Path("workspace/skills"),
            system_skills_dir=Path("backend/src/skills"),
        )

        # 列出所有技能
        skills = registry.list_skills()

        # 获取指定技能
        skill = registry.get_skill("pdf-converter")

        # 清空缓存以强制重新加载
        registry.clear_cache()
    """

    def __init__(
        self,
        user_skills_dir: Path | None = None,
        system_skills_dir: Path | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """初始化技能注册表。

        Args:
            user_skills_dir: 用户技能目录路径（最高优先级）
            system_skills_dir: 系统技能目录路径
            cache_ttl_seconds: 缓存 TTL 秒数（默认 5 分钟）
        """
        self.user_skills_dir = user_skills_dir.resolve() if user_skills_dir else None
        self.system_skills_dir = system_skills_dir.resolve() if system_skills_dir else None

        self._parser = ManifestParser()
        self._cache: dict[str, tuple[SkillManifest, SkillSource]] = {}
        self._last_scan_time: datetime | None = None

        # 从环境变量或参数配置 TTL
        env_ttl = os.getenv("X_AGENT_SKILL_CACHE_TTL")
        if env_ttl:
            with contextlib.suppress(ValueError):
                cache_ttl_seconds = int(env_ttl)

        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)

        logger.info(
            "SkillRegistry initialized",
            extra={
                "user_skills_dir": str(self.user_skills_dir) if self.user_skills_dir else None,
                "system_skills_dir": str(self.system_skills_dir)
                if self.system_skills_dir
                else None,
                "cache_ttl_seconds": cache_ttl_seconds,
            },
        )

    def list_skills(
        self,
        source: SkillSource | None = None,
    ) -> list[SkillManifest]:
        """列出所有可用技能。

        Args:
            source: 按来源过滤 (USER 或 SYSTEM)，None 表示全部

        Returns:
            SkillManifest 对象列表
        """
        self._ensure_cache_valid()

        if source is None:
            return [manifest for manifest, _ in self._cache.values()]

        return [
            manifest for manifest, skill_source in self._cache.values() if skill_source == source
        ]

    def get_skill(self, skill_id: str) -> SkillManifest | None:
        """按 ID 获取技能。

        Args:
            skill_id: 技能标识符

        Returns:
            找到时返回 SkillManifest，否则返回 None
        """
        self._ensure_cache_valid()

        entry = self._cache.get(skill_id)
        if entry:
            return entry[0]
        return None

    def get_skill_source(self, skill_id: str) -> SkillSource | None:
        """获取技能的来源。

        Args:
            skill_id: 技能标识符

        Returns:
            找到时返回 SkillSource，否则返回 None
        """
        self._ensure_cache_valid()

        entry = self._cache.get(skill_id)
        if entry:
            return entry[1]
        return None

    def get_skill_with_source(self, skill_id: str) -> tuple[SkillManifest, SkillSource] | None:
        """获取技能及其来源。

        Args:
            skill_id: 技能标识符

        Returns:
            找到时返回 (SkillManifest, SkillSource) 元组，否则返回 None
        """
        self._ensure_cache_valid()
        return self._cache.get(skill_id)

    def clear_cache(self) -> None:
        """清空技能缓存。

        下次访问时强制重新加载。
        """
        self._cache.clear()
        self._last_scan_time = None
        logger.info("技能缓存已清空")

    def get_stats(self) -> dict[str, Any]:
        """获取注册表统计信息。

        Returns:
            包含注册表统计的字典
        """
        self._ensure_cache_valid()

        user_count = sum(1 for _, source in self._cache.values() if source == SkillSource.USER)
        system_count = sum(1 for _, source in self._cache.values() if source == SkillSource.SYSTEM)

        return {
            "total_count": len(self._cache),
            "user_count": user_count,
            "system_count": system_count,
            "skill_ids": sorted(self._cache.keys()),
            "cache_valid": self._is_cache_valid(),
            "last_scan_time": (self._last_scan_time.isoformat() if self._last_scan_time else None),
            "cache_ttl_seconds": self._cache_ttl.total_seconds(),
        }

    def _ensure_cache_valid(self) -> None:
        """确保缓存有效，必要时重新加载。"""
        if not self._is_cache_valid():
            self._reload_cache()

    def _is_cache_valid(self) -> bool:
        """检查缓存是否仍然有效。

        Returns:
            缓存有效时返回 True
        """
        if self._last_scan_time is None:
            return False

        return datetime.now() - self._last_scan_time < self._cache_ttl

    def _reload_cache(self) -> None:
        """重新加载所有技能到缓存。"""
        new_cache: dict[str, tuple[SkillManifest, SkillSource]] = {}

        # 先加载 SYSTEM 技能（最低优先级）
        if self.system_skills_dir and self.system_skills_dir.exists():
            system_skills = self._scan_directory(self.system_skills_dir, SkillSource.SYSTEM)
            for manifest in system_skills:
                new_cache[manifest.skill_id] = (manifest, SkillSource.SYSTEM)

            logger.debug(
                f"已加载 {len(system_skills)} 个系统技能",
                extra={"path": str(self.system_skills_dir)},
            )

        # 再加载 USER 技能（最高优先级，覆盖 SYSTEM）
        if self.user_skills_dir and self.user_skills_dir.exists():
            user_skills = self._scan_directory(self.user_skills_dir, SkillSource.USER)
            for manifest in user_skills:
                if manifest.skill_id in new_cache:
                    logger.info(
                        f"用户技能覆盖系统技能: {manifest.skill_id}",
                        extra={"path": str(manifest.path)},
                    )
                new_cache[manifest.skill_id] = (manifest, SkillSource.USER)

            logger.debug(
                f"已加载 {len(user_skills)} 个用户技能", extra={"path": str(self.user_skills_dir)}
            )

        self._cache = new_cache
        self._last_scan_time = datetime.now()

        logger.info(
            f"Skill cache reloaded: {len(self._cache)} skills",
            extra={
                "user_count": sum(1 for _, s in self._cache.values() if s == SkillSource.USER),
                "system_count": sum(1 for _, s in self._cache.values() if s == SkillSource.SYSTEM),
            },
        )

    def _scan_directory(
        self,
        directory: Path,
        source: SkillSource,
    ) -> list[SkillManifest]:
        """扫描目录中的技能。

        Args:
            directory: 待扫描的目录
            source: 赋予发现技能的来源标识

        Returns:
            发现的 SkillManifest 对象列表
        """
        skills: list[SkillManifest] = []

        if not directory.exists() or not directory.is_dir():
            return skills

        for item in directory.iterdir():
            if not item.is_dir():
                continue

            # 跳过隐藏目录
            if item.name.startswith("."):
                continue

            # 检查是否有清单文件
            has_manifest = (item / "manifest.json").exists() or (item / "SKILL.md").exists()

            if not has_manifest:
                logger.debug(f"目录中未发现清单: {item}")
                continue

            try:
                manifest = self._parser.parse(item)
                skills.append(manifest)
            except ManifestParseError as e:
                logger.warning(f"解析技能 {item.name} 失败: {e}", extra={"path": str(item)})
            except Exception as e:
                logger.error(f"解析技能 {item.name} 时发生意外错误: {e}", extra={"path": str(item)})

        return skills


# =============================================================================
# 全局注册表实例
# =============================================================================

_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表实例。

    Returns:
        SkillRegistry 实例

    Raises:
        RuntimeError: 注册表未初始化时抛出
    """
    global _registry
    if _registry is None:
        raise RuntimeError("Skill registry not initialized. Call init_skill_registry() first.")
    return _registry


def init_skill_registry(
    user_skills_dir: Path | None = None,
    system_skills_dir: Path | None = None,
    cache_ttl_seconds: int = 300,
) -> SkillRegistry:
    """初始化全局技能注册表。

    Args:
        user_skills_dir: 用户技能目录路径
        system_skills_dir: 系统技能目录路径
        cache_ttl_seconds: 缓存 TTL 秒数

    Returns:
        初始化后的 SkillRegistry
    """
    global _registry
    _registry = SkillRegistry(
        user_skills_dir=user_skills_dir,
        system_skills_dir=system_skills_dir,
        cache_ttl_seconds=cache_ttl_seconds,
    )
    return _registry


def reset_skill_registry() -> None:
    """重置全局技能注册表。"""
    global _registry
    _registry = None
