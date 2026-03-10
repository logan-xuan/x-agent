"""Gateway REST/SSE 端点。

提供 HTTP POST /gateway/chat 端点，通过 SSE（Server-Sent Events）
流式返回 GatewayEvent。

适用于无状态客户端（CLI Remote 模式、第三方集成等），
每个请求独立创建 Agent 实例，不复用连接。

SSE 协议格式:
  data: {"type": "text_chunk", "data": {"content": "..."}, ...}
  data: {"type": "message_end", "data": {"content": "...", "model": "..."}, ...}
  data: {"type": "tool_call", "data": {"tool_call_id": "...", "name": "...", ...}, ...}
  data: {"type": "tool_result", "data": {"tool_call_id": "...", "result": "...", ...}, ...}
  data: {"type": "error", "data": {"message": "..."}, ...}
  data: [DONE]
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..dispatcher import GatewayDispatcher
from ..envelope import Envelope
from ..response import GatewayEvent, GatewayEventType
from ..errors import GatewayError, EnvelopeValidationError
from ..connection_registry import (
    ConnectionHandle,
    get_connection_registry,
)
from ...conversation.identity import ChannelType, ChannelProtocol

try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["Gateway"])

# 模块级 GatewayDispatcher 单例
_dispatcher: GatewayDispatcher | None = None


def _get_dispatcher() -> GatewayDispatcher:
    """获取 GatewayDispatcher 单例。"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = GatewayDispatcher()
    return _dispatcher


# ============================================================================
# Request / Response Models
# ============================================================================

class ImagePayload(BaseModel):
    """图片附件。

    Attributes:
        data: Base64 编码的图片数据。
        mime_type: 图片 MIME 类型。
    """
    data: str
    mime_type: str = "image/png"


class ChatRequest(BaseModel):
    """Gateway chat 请求体。

    Attributes:
        content: 用户消息文本。
        session_id: 会话 ID，不传则自动生成。
        images: 附带图片列表，每项包含 base64 数据和 MIME 类型。
        agent_id: 目标 Agent ID（可选，按 ID 路由）。
        agent_name: 目标 Agent 名称（可选，按名称路由）。
        metadata: 附加元数据。
    """
    content: str
    session_id: str | None = None
    images: list[ImagePayload] | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

# ============================================================================
# GatewayEvent -> SSE 转换
# ============================================================================

def _gateway_event_to_sse(event: GatewayEvent) -> str:
    """将 GatewayEvent 转换为 SSE data 行。

    Args:
        event: Gateway 统一响应事件。

    Returns:
        SSE 格式的字符串（含 data: 前缀和双换行）。
    """
    payload: dict[str, Any] = {
        "type": event.type.value,
        "data": event.data,
    }
    if event.agent_id:
        payload["agent_id"] = event.agent_id
    if event.agent_name:
        payload["agent_name"] = event.agent_name

    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

# ============================================================================
# REST/SSE 端点
# ============================================================================

@router.post("/chat")
async def gateway_chat(request: ChatRequest) -> StreamingResponse:
    """Gateway 对话端点（SSE 流式响应）。

    接收 JSON 请求体，将其转换为 Envelope 后交给 GatewayDispatcher 处理，
    以 SSE 格式流式返回 GatewayEvent。

    无状态协议：每个请求独立创建 Agent 实例，不复用连接。
    适用于 CLI Remote 模式和第三方 HTTP 集成。

    Args:
        request: 对话请求体。

    Returns:
        SSE StreamingResponse。
    """
    session_id = request.session_id or str(uuid.uuid4())

    images: list[tuple[str, str]] | None = None
    if request.images:
        images = [(img.data, img.mime_type) for img in request.images]

    envelope = Envelope.create_chat(
        content=request.content,
        session_id=session_id,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.REST_API,
        images=images,
        agent_id=request.agent_id,
        agent_name=request.agent_name,
        metadata=request.metadata,
    )

    logger.info(
        "Gateway REST chat request",
        extra={
            "session_id": session_id,
            "content_length": len(request.content),
            "has_images": bool(request.images),
            "agent_id": request.agent_id,
            "agent_name": request.agent_name,
        },
    )

    dispatcher = _get_dispatcher()

    # 注册 SSE 连接到 ConnectionRegistry
    # web chat 交互使用统一的 web_channel 作为默认 channel_id
    from ...conversation.dao import DEFAULT_CHANNEL_ID
    registry = get_connection_registry()
    sse_channel_id = DEFAULT_CHANNEL_ID  # 统一使用 "web_channel"
    sse_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def sse_sender(message: dict[str, Any]) -> bool:
        await sse_queue.put(message)
        return True

    registry.register(session_id, ConnectionHandle(
        channel_id=sse_channel_id,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.SSE,
        send=sse_sender,
    ))

    logger.info(
        "SSE connection registered",
        extra={
            "session_id": session_id,
            "channel_id": sse_channel_id,
            "channel_type": "web",
            "protocol": "sse",
        },
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        """生成 SSE 事件流。"""
        try:
            async for gateway_event in dispatcher.dispatch(envelope):
                yield _gateway_event_to_sse(gateway_event)
        except EnvelopeValidationError as validation_error:
            error_event = GatewayEvent.error(
                message=str(validation_error),
                error_type="EnvelopeValidationError",
            )
            yield _gateway_event_to_sse(error_event)
        except GatewayError as gateway_error:
            error_event = GatewayEvent.error(
                message=str(gateway_error),
                error_type=type(gateway_error).__name__,
            )
            yield _gateway_event_to_sse(error_event)
        except Exception as unexpected_error:
            logger.exception(
                "Unexpected error in gateway chat",
                extra={"session_id": session_id},
            )
            error_event = GatewayEvent.error(
                message=f"Internal server error: {unexpected_error}",
                error_type="InternalError",
            )
            yield _gateway_event_to_sse(error_event)
        finally:
            # 注销 SSE 连接
            registry.unregister(session_id, sse_channel_id)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-Id": session_id,
        },
    )


@router.post("/abort/{session_id}", status_code=501)
async def gateway_abort(session_id: str) -> dict[str, Any]:
    """中止指定会话的处理。

    当前尚未实现实际的中止逻辑，返回 501 Not Implemented。

    Args:
        session_id: 要中止的会话 ID。

    Returns:
        操作结果（含未实现提示）。
    """
    logger.info("Gateway REST abort request", extra={"session_id": session_id})

    return {
        "success": False,
        "data": {
            "session_id": session_id,
            "message": "Abort is not yet implemented",
        },
    }
