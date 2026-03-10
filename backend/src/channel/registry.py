"""Channel 注册表。

管理所有已注册的 ChannelAdapter 实例，
提供按 ChannelType 查找、启动和停止渠道的能力。

使用示例（未来实现）::

    registry = ChannelRegistry()
    registry.register(DingtalkChannel(config))
    registry.register(WechatChannel(config))

    await registry.start_all()   # 启动所有渠道
    adapter = registry.get(ChannelType.DINGTALK)  # 按类型查找
    await registry.stop_all()    # 停止所有渠道
"""

from __future__ import annotations

import asyncio

from ..conversation.identity import ChannelType
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
    支持按 ChannelType 注册、查找和生命周期管理。
    """

    def __init__(self) -> None:
        self._adapters: dict[ChannelType, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter) -> None:
        """注册一个渠道适配器。

        Args:
            adapter: ChannelAdapter 实例。

        Raises:
            ValueError: 如果该 ChannelType 已被注册。
        """
        channel_type = adapter.channel_type
        if channel_type in self._adapters:
            raise ValueError(
                f"Channel type {channel_type.value} is already registered"
            )
        self._adapters[channel_type] = adapter
        logger.info(
            "Channel registered",
            extra={"channel_type": channel_type.value, "adapter": repr(adapter)},
        )

    def unregister(self, channel_type: ChannelType) -> ChannelAdapter | None:
        """注销一个渠道适配器。

        Args:
            channel_type: 要注销的渠道类型。

        Returns:
            被注销的适配器实例，如果不存在则返回 None。
        """
        adapter = self._adapters.pop(channel_type, None)
        if adapter is not None:
            logger.info(
                "Channel unregistered",
                extra={"channel_type": channel_type.value},
            )
        return adapter

    def get(self, channel_type: ChannelType) -> ChannelAdapter | None:
        """按渠道类型查找适配器。

        Args:
            channel_type: 渠道类型。

        Returns:
            对应的 ChannelAdapter 实例，不存在则返回 None。
        """
        return self._adapters.get(channel_type)

    def list_channels(self) -> list[ChannelType]:
        """列出所有已注册的渠道类型。

        Returns:
            已注册的 ChannelType 列表。
        """
        return list(self._adapters.keys())

    async def start_all(self) -> None:
        """并行启动所有已注册的渠道。

        使用 asyncio.gather 并行调用每个适配器的 start() 方法。
        单个渠道启动失败不影响其他渠道。
        """
        if not self._adapters:
            return

        async def _start_one(channel_type: ChannelType, adapter: ChannelAdapter) -> None:
            try:
                await adapter.start()
                logger.info(
                    "Channel started",
                    extra={"channel_type": channel_type.value},
                )
            except Exception as start_error:
                logger.error(
                    "Failed to start channel",
                    extra={
                        "channel_type": channel_type.value,
                        "error": str(start_error),
                    },
                )

        await asyncio.gather(
            *(_start_one(ct, ad) for ct, ad in self._adapters.items())
        )

    async def stop_all(self) -> None:
        """并行停止所有已注册的渠道。

        使用 asyncio.gather 并行调用每个适配器的 stop() 方法。
        单个渠道停止失败不影响其他渠道。
        """
        if not self._adapters:
            return

        async def _stop_one(channel_type: ChannelType, adapter: ChannelAdapter) -> None:
            try:
                await adapter.stop()
                logger.info(
                    "Channel stopped",
                    extra={"channel_type": channel_type.value},
                )
            except Exception as stop_error:
                logger.error(
                    "Failed to stop channel",
                    extra={
                        "channel_type": channel_type.value,
                        "error": str(stop_error),
                    },
                )

        await asyncio.gather(
            *(_stop_one(ct, ad) for ct, ad in self._adapters.items())
        )

    def __len__(self) -> int:
        return len(self._adapters)

    def __repr__(self) -> str:
        channel_names = [ct.value for ct in self._adapters]
        return f"<ChannelRegistry channels={channel_names}>"
