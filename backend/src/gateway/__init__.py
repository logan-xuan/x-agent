"""X-Agent Gateway 网关层。

提供协议无关的统一消息入口，承接上游 WebChat / CLI / Channel 的消息，
转发到 Agent Core 调用 agent_loop 流程。

核心组件：
- Envelope: 统一消息信封
- GatewayDispatcher: 请求分发器
- AgentBridge: Agent Core 桥接器
- GatewayEvent: 统一响应事件
"""

from .envelope import Envelope, EnvelopeIntent
from .response import GatewayEvent, GatewayEventType
from .agent_info import AgentInfo
from .agent_bridge import AgentBridge
from .dispatcher import GatewayDispatcher
from .errors import (
    GatewayError,
    AgentNotFoundError,
    SessionNotFoundError,
    EnvelopeValidationError,
    DispatchError,
    AbortError,
)

__all__ = [
    "Envelope",
    "EnvelopeIntent",
    "GatewayEvent",
    "GatewayEventType",
    "AgentInfo",
    "AgentBridge",
    "GatewayDispatcher",
    "GatewayError",
    "AgentNotFoundError",
    "SessionNotFoundError",
    "EnvelopeValidationError",
    "DispatchError",
    "AbortError",
]
