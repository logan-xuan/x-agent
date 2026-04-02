"""Agent Core API.

对外接口，包括 REST API。
WebSocket 端点已迁移到 gateway.endpoints.websocket。
"""

from .converters import convert_event_to_websocket
from .dev_routes import router as agent_rest_router

__all__ = [
    "agent_rest_router",
    "convert_event_to_websocket",
]
