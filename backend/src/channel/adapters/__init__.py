"""Channel Adapters - 渠道适配器实现。

此包包含各 IM 平台的具体适配器实现：
- DingTalkAdapter: 钉钉 Stream 模式适配器
- FeishuAdapter: 飞书开放平台适配器
- WechatAdapter: 微信公众号/企微适配器
- TelegramAdapter: Telegram Bot 适配器

所有适配器遵循统一的 Envelope 协议，通过 ChannelRegistry 注册。
"""

from ..feishu import FeishuChannelAdapter
from .dingtalk import DingtalkChannelAdapter

__all__ = [
    "DingtalkChannelAdapter",
    "FeishuChannelAdapter",
]
