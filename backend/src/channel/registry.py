"""Channel 注册表。

管理所有已注册的 ChannelAdapter 实例，
提供按 channel_id 查找、启动和停止渠道的能力。

使用示例::

    registry = ChannelRegistry()
    registry.register("dingtalk_channel", dingtalk_adapter)
    registry.register("feishu_channel", feishu_adapter)

    await registry.start_all()   # 启动所有渠道
    adapter = registry.get("dingtalk_channel")  # 按 ID 查找
    await registry.stop_all()    # 停止所有渠道
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ..config.models import ChannelConfig
from .base import ChannelAdapter

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class ChannelRegistry:
    """Channel 注册表。

    线程安全的渠道适配器注册中心，
    支持按 channel_id 注册、查找和生命周期管理。
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, channel_id: str, adapter: ChannelAdapter) -> None:
        """注册一个渠道适配器。

        Args:
            channel_id: 渠道配置 ID。
            adapter: ChannelAdapter 实例。

        Raises:
            ValueError: 如果该 channel_id 已被注册。
        """
        if channel_id in self._adapters:
            raise ValueError(f"Channel ID {channel_id} is already registered")
        self._adapters[channel_id] = adapter
        logger.info(
            "Channel registered",
            extra={"channel_id": channel_id, "adapter": repr(adapter)},
        )

    def unregister(self, channel_id: str) -> ChannelAdapter | None:
        """注销一个渠道适配器。

        Args:
            channel_id: 要注销的渠道 ID。

        Returns:
            被注销的适配器实例，如果不存在则返回 None。
        """
        adapter = self._adapters.pop(channel_id, None)
        if adapter is not None:
            logger.info(
                "Channel unregistered",
                extra={"channel_id": channel_id},
            )
        return adapter

    def get(self, channel_id: str) -> ChannelAdapter | None:
        """按渠道 ID 查找适配器。

        Args:
            channel_id: 渠道配置 ID。

        Returns:
            对应的 ChannelAdapter 实例，不存在则返回 None。
        """
        return self._adapters.get(channel_id)

    def list_channels(self) -> list[str]:
        """列出所有已注册的渠道 ID。

        Returns:
            已注册的 channel_id 列表。
        """
        return list(self._adapters.keys())

    async def start_all(self) -> None:
        """并行启动所有已注册的渠道。

        使用 asyncio.gather 并行调用每个适配器的 start() 方法。
        单个渠道启动失败不影响其他渠道。
        """
        if not self._adapters:
            return

        async def _start_one(channel_id: str, adapter: ChannelAdapter) -> None:
            try:
                await adapter.start()
                logger.info(
                    "Channel started",
                    extra={"channel_id": channel_id},
                )
            except Exception as start_error:
                logger.error(
                    "Failed to start channel",
                    extra={
                        "channel_id": channel_id,
                        "error": str(start_error),
                    },
                )

        await asyncio.gather(*(_start_one(cid, ad) for cid, ad in self._adapters.items()))

    async def stop_all(self) -> None:
        """并行停止所有已注册的渠道。

        使用 asyncio.gather 并行调用每个适配器的 stop() 方法。
        单个渠道停止失败不影响其他渠道。
        """
        if not self._adapters:
            return

        async def _stop_one(channel_id: str, adapter: ChannelAdapter) -> None:
            try:
                await adapter.stop()
                logger.info(
                    "Channel stopped",
                    extra={"channel_id": channel_id},
                )
            except Exception as stop_error:
                logger.error(
                    "Failed to stop channel",
                    extra={
                        "channel_id": channel_id,
                        "error": str(stop_error),
                    },
                )

        await asyncio.gather(*(_stop_one(cid, ad) for cid, ad in self._adapters.items()))

    def __len__(self) -> int:
        return len(self._adapters)

    def __repr__(self) -> str:
        channel_ids = list(self._adapters.keys())
        return f"<ChannelRegistry channels={channel_ids}>"


def create_channel_adapter(
    channel_config: ChannelConfig,
    dispatcher_factory: Callable[[], Any],
) -> ChannelAdapter | None:
    """根据配置创建对应的 Channel Adapter 实例。

    Args:
        channel_config: 渠道配置。
        dispatcher_factory: 用于获取 GatewayDispatcher 实例的工厂函数。

    Returns:
        ChannelAdapter 实例，如果 channel 未启用或类型不支持则返回 None。
    """
    if not channel_config.enabled:
        return None

    channel_type = channel_config.type.lower()
    config_dict = channel_config.config

    if channel_type == "dingtalk":
        from .adapters.dingtalk import DingtalkChannelAdapter

        return DingtalkChannelAdapter(
            channel_id=channel_config.id,
            app_key=config_dict.get("app_key", ""),
            app_secret=config_dict.get("app_secret", ""),
            dispatcher_factory=dispatcher_factory,
        )
    elif channel_type == "feishu":
        from .feishu import FeishuChannelAdapter

        return FeishuChannelAdapter(
            channel_id=channel_config.id,
            app_id=config_dict.get("app_id", ""),
            app_secret=config_dict.get("app_secret", ""),
            dispatcher_factory=dispatcher_factory,
        )

    # 其他渠道类型暂不支持自动创建
    logger.debug(
        "Channel type not supported for auto-creation",
        extra={"channel_type": channel_type, "channel_id": channel_config.id},
    )
    return None


# 全局 ChannelRegistry 单例
_channel_registry: ChannelRegistry | None = None


def get_channel_registry() -> ChannelRegistry:
    """获取全局 ChannelRegistry 单例。

    Returns:
        ChannelRegistry 实例。
    """
    global _channel_registry
    if _channel_registry is None:
        _channel_registry = ChannelRegistry()
    return _channel_registry


def set_channel_registry(registry: ChannelRegistry) -> None:
    """设置全局 ChannelRegistry 单例。

    Args:
        registry: ChannelRegistry 实例。
    """
    global _channel_registry
    _channel_registry = registry
