"""组件注册中心实现.

提供组件的注册、发现、生命周期管理。
支持 Tools、Skills、Plugins 等组件的统一管理。

特性:
    - 组件注册与注销
    - 按类别分组
    - 延迟初始化（工厂模式）
    - 依赖声明与检查
    - 健康检查

Example:
    # 创建注册中心
    registry = ComponentRegistry[AgentTool]()

    # 注册组件
    registry.register(
        name="web_search",
        item=web_search_tool,
        category="search",
        dependencies=["http_client"],
    )

    # 获取组件
    tool = registry.get("web_search")

    # 按类别列出
    search_tools = registry.list_by_category("search")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

if TYPE_CHECKING:
    from .types import AgentTool

logger = logging.getLogger(__name__)

# 泛型类型
T = TypeVar("T")


class ComponentStatus(Enum):
    """组件状态."""

    REGISTERED = "registered"  # 已注册
    INITIALIZED = "initialized"  # 已初始化
    ACTIVE = "active"  # 活跃
    DISABLED = "disabled"  # 已禁用
    ERROR = "error"  # 错误


@dataclass
class ComponentEntry(Generic[T]):
    """组件注册项.

    Attributes:
        name: 组件名称
        item: 组件实例（如果直接注册）
        factory: 工厂函数（如果延迟初始化）
        category: 分类
        dependencies: 依赖的其他组件
        metadata: 元数据
        status: 当前状态
        error: 错误信息
    """

    name: str
    item: T | None = None
    factory: Any = None  # Callable[[], T] | Callable[[], Awaitable[T]] | None
    category: str = "default"
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: ComponentStatus = ComponentStatus.REGISTERED
    error: str = ""


class ComponentRegistry(Generic[T]):
    """组件注册中心.

    泛型组件注册中心，支持任意类型的组件管理。

    Example:
        # 工具注册中心
        tool_registry = ComponentRegistry[AgentTool]()

        # 技能注册中心
        skill_registry = ComponentRegistry[Skill]()
    """

    def __init__(self, name: str = "ComponentRegistry"):
        """初始化注册中心.

        Args:
            name: 注册中心名称（用于日志）
        """
        self._name = name
        self._entries: dict[str, ComponentEntry[T]] = {}
        self._categories: dict[str, set[str]] = {"default": set()}
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        item: T | Callable[[], T] | Callable[[], Awaitable[T]],
        category: str = "default",
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """注册组件.

        Args:
            name: 组件名称
            item: 组件实例或工厂函数
            category: 分类
            dependencies: 依赖的其他组件
            metadata: 元数据

        Returns:
            bool: 是否注册成功

        Example:
            # 直接注册实例
            registry.register("tool1", tool_instance, category="search")

            # 延迟初始化
            registry.register("tool2", lambda: create_tool(), category="search")
        """
        if name in self._entries:
            logger.warning(
                f"[{self._name}] Component '{name}' already registered, overwriting",
                extra={"registry": self._name, "component": name},
            )

        # 判断是实例还是工厂
        is_factory = callable(item) and not hasattr(item, "__dataclass_fields__")

        entry = ComponentEntry[T](
            name=name,
            item=item if not is_factory else None,
            factory=item if is_factory else None,
            category=category,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        self._entries[name] = entry

        # 更新分类索引
        if category not in self._categories:
            self._categories[category] = set()
        self._categories[category].add(name)

        logger.debug(
            f"[{self._name}] Component '{name}' registered",
            extra={
                "registry": self._name,
                "component": name,
                "category": category,
                "is_factory": is_factory,
            },
        )

        return True

    def unregister(self, name: str) -> bool:
        """注销组件.

        Args:
            name: 组件名称

        Returns:
            bool: 是否成功注销
        """
        if name not in self._entries:
            return False

        entry = self._entries.pop(name)

        # 从分类中移除
        if entry.category in self._categories:
            self._categories[entry.category].discard(name)

        logger.debug(
            f"[{self._name}] Component '{name}' unregistered",
            extra={"registry": self._name, "component": name},
        )

        return True

    def get(self, name: str) -> T | None:
        """获取组件.

        如果组件使用工厂注册，会自动初始化。

        Args:
            name: 组件名称

        Returns:
            T | None: 组件实例，不存在返回 None
        """
        entry = self._entries.get(name)
        if entry is None:
            return None

        # 延迟初始化
        if entry.item is None and entry.factory is not None:
            try:
                result = entry.factory()
                # 处理异步工厂
                if asyncio.iscoroutine(result):
                    # 同步上下文中不能 await，返回 None
                    logger.warning(
                        f"[{self._name}] Async factory for '{name}' called in sync context",
                        extra={"registry": self._name, "component": name},
                    )
                    return None

                entry.item = result  # type: ignore
                entry.status = ComponentStatus.INITIALIZED

            except Exception as e:
                entry.status = ComponentStatus.ERROR
                entry.error = str(e)
                logger.error(
                    f"[{self._name}] Failed to initialize component '{name}': {e}",
                    extra={"registry": self._name, "component": name, "error": str(e)},
                )
                return None

        return entry.item

    async def get_async(self, name: str) -> T | None:
        """异步获取组件.

        支持异步工厂函数。

        Args:
            name: 组件名称

        Returns:
            T | None: 组件实例
        """
        entry = self._entries.get(name)
        if entry is None:
            return None

        # 延迟初始化
        if entry.item is None and entry.factory is not None:
            try:
                result = entry.factory()

                # 处理异步工厂
                if asyncio.iscoroutine(result):
                    entry.item = await result  # type: ignore
                else:
                    entry.item = result  # type: ignore

                entry.status = ComponentStatus.INITIALIZED

            except Exception as e:
                entry.status = ComponentStatus.ERROR
                entry.error = str(e)
                logger.error(
                    f"[{self._name}] Failed to initialize component '{name}': {e}",
                    extra={"registry": self._name, "component": name, "error": str(e)},
                )
                return None

        return entry.item

    def has(self, name: str) -> bool:
        """检查组件是否存在.

        Args:
            name: 组件名称

        Returns:
            bool: 是否存在
        """
        return name in self._entries

    def list_all(self) -> list[str]:
        """列出所有组件.

        Returns:
            list[str]: 组件名称列表
        """
        return list(self._entries.keys())

    def list_by_category(self, category: str) -> list[str]:
        """按类别列出组件.

        Args:
            category: 分类名称

        Returns:
            list[str]: 组件名称列表
        """
        return list(self._categories.get(category, set()))

    def list_categories(self) -> list[str]:
        """列出所有分类.

        Returns:
            list[str]: 分类名称列表
        """
        return list(self._categories.keys())

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        """获取组件元数据.

        Args:
            name: 组件名称

        Returns:
            dict | None: 元数据
        """
        entry = self._entries.get(name)
        return entry.metadata if entry else None

    def get_status(self, name: str) -> ComponentStatus | None:
        """获取组件状态.

        Args:
            name: 组件名称

        Returns:
            ComponentStatus | None: 状态
        """
        entry = self._entries.get(name)
        return entry.status if entry else None

    def check_dependencies(self, name: str) -> tuple[bool, list[str]]:
        """检查组件依赖.

        Args:
            name: 组件名称

        Returns:
            tuple[bool, list[str]]: (是否满足依赖, 缺失的依赖列表)
        """
        entry = self._entries.get(name)
        if entry is None:
            return False, [f"Component '{name}' not found"]

        missing = []
        for dep in entry.dependencies:
            if dep not in self._entries:
                missing.append(dep)

        return len(missing) == 0, missing

    def enable(self, name: str) -> bool:
        """启用组件.

        Args:
            name: 组件名称

        Returns:
            bool: 是否成功
        """
        entry = self._entries.get(name)
        if entry is None:
            return False

        if entry.status == ComponentStatus.DISABLED:
            entry.status = ComponentStatus.REGISTERED
            logger.debug(
                f"[{self._name}] Component '{name}' enabled",
                extra={"registry": self._name, "component": name},
            )

        return True

    def disable(self, name: str) -> bool:
        """禁用组件.

        Args:
            name: 组件名称

        Returns:
            bool: 是否成功
        """
        entry = self._entries.get(name)
        if entry is None:
            return False

        entry.status = ComponentStatus.DISABLED
        logger.debug(
            f"[{self._name}] Component '{name}' disabled",
            extra={"registry": self._name, "component": name},
        )

        return True

    def clear(self) -> None:
        """清空所有组件."""
        self._entries.clear()
        self._categories = {"default": set()}

        logger.debug(f"[{self._name}] All components cleared", extra={"registry": self._name})

    def __len__(self) -> int:
        """返回组件数量."""
        return len(self._entries)

    def __contains__(self, name: str) -> bool:
        """支持 `in` 操作符."""
        return name in self._entries


# ============================================================
# 全局注册中心实例
# ============================================================

# 工具注册中心
_tool_registry: ComponentRegistry[AgentTool] | None = None


def get_tool_registry() -> ComponentRegistry[AgentTool]:
    """获取全局工具注册中心.

    Returns:
        ComponentRegistry[AgentTool]: 工具注册中心
    """
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ComponentRegistry[AgentTool](name="ToolRegistry")
    return _tool_registry


def reset_tool_registry() -> None:
    """重置工具注册中心（用于测试）."""
    global _tool_registry
    _tool_registry = None
