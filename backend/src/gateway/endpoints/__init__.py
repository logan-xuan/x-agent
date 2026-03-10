"""Gateway 协议端点。

各协议的适配层，负责将协议消息转换为 Envelope，
将 GatewayEvent 转换为协议格式的响应。

当前支持：
- WebSocket: websocket.py（长连接，有状态）
- REST/SSE: rest.py（HTTP POST + SSE 流式响应，无状态）
"""

from .websocket import router as websocket_router
from .rest import router as rest_router

__all__ = ["websocket_router", "rest_router"]
