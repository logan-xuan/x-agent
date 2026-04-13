"""Channel 适配器抽象基类。

每个外部消息通道（钉钉 / 微信 / Telegram / 飞书等）
实现此接口，负责：
1. 接收外部平台的 Webhook / 长轮询消息
2. 将平台原始消息转换为 Gateway Envelope
3. 将 GatewayEvent 转换为平台回复格式
4. 管理通道生命周期（启动 / 停止）

使用示例（未来实现）::

    class DingtalkChannel(ChannelAdapter):
        def channel_type(self) -> ChannelType:
            return ChannelType.DINGTALK

        async def start(self) -> None:
            # 启动 Webhook 监听
            ...

        async def stop(self) -> None:
            # 停止监听
            ...

        async def to_envelope(self, raw_message: Any) -> Envelope:
            # 将钉钉消息转换为 Envelope
            ...

        async def render_response(self, event: GatewayEvent) -> Any:
            # 将 GatewayEvent 转换为钉钉回复格式
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..conversation.identity import ChannelType
from ..gateway.envelope import Envelope
from ..gateway.response import GatewayEvent


class ChannelAdapter(ABC):
    """外部消息通道适配器抽象基类。

    每个 Channel（钉钉 / 微信 / Telegram / 飞书）实现此接口，
    负责协议适配和消息转换。

    生命周期：
    1. 实例化 → 2. start() → 3. 接收消息循环 → 4. stop()
    """

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType:
        """此适配器对应的渠道类型。

        Returns:
            ChannelType 枚举值。
        """

    @abstractmethod
    async def start(self) -> None:
        """启动渠道监听。

        实现方应在此方法中启动 Webhook 服务器、
        WebSocket 连接或长轮询循环。
        """

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道监听。

        实现方应在此方法中优雅关闭所有连接和资源。
        """

    @abstractmethod
    async def to_envelope(self, raw_message: Any) -> Envelope:
        """将平台原始消息转换为统一信封。

        Args:
            raw_message: 平台特定格式的原始消息
                （如钉钉 Webhook JSON、微信 XML 等）。

        Returns:
            转换后的 Envelope 实例。
        """

    @abstractmethod
    async def render_response(self, event: GatewayEvent) -> Any:
        """将 Gateway 事件转换为平台回复格式。

        Args:
            event: Gateway 统一响应事件。

        Returns:
            平台特定格式的回复数据
            （如钉钉 Markdown 消息、微信文本回复等）。
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__} channel_type={self.channel_type.value}>"
