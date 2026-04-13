"""Channel 渠道层（预留模块）。

定义外部消息通道适配器的抽象接口，
未来用于接入钉钉、微信、Telegram、飞书等平台。

当前仅提供接口定义，不包含具体实现。

核心组件：
- ChannelAdapter: 渠道适配器抽象基类
- ChannelRegistry: 渠道注册表
"""

# 导入 adapters 子模块（具体适配器实现）
# 后续可通过 from channel.adapters import DingTalkAdapter, FeishuAdapter 等
from . import adapters
from .base import ChannelAdapter
from .registry import ChannelRegistry

__all__ = [
    "ChannelAdapter",
    "ChannelRegistry",
    "adapters",
]
