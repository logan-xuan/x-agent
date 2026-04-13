"""临时脚本：重写 websocket.py"""

import pathlib

target = pathlib.Path(__file__).parent / "websocket.py"

content = '''\
"""Agent Core WebSocket 端点（纯协议层）。

提供 /ws/agent/{session_id} 端点，桥接 WebSocket 与 Gateway。

所有业务逻辑（Agent 创建、技能调度、消息持久化、Session 管理）
已迁移到 Gateway 层（GatewayDispatcher + AgentBridge），
本模块仅负责：
1. WebSocket 协议处理（accept/receive/send/disconnect）
2. 将客户端消息转换为 Envelope
3. 将 GatewayEvent 转换为 WebSocket JSON 消息

消息协议:
- 客户端发送: {"content": "用户消息"} 或 {"type": "abort"} 或 {"type": "ping"}
- 服务端发送:
  - {"type": "chunk", "content": delta}
  - {"type": "thinking", "content": delta}
  - {"type": "message", "content": text, "model": model, "is_finished": true}
  - {"type": "tool_call", "tool_call_id": id, "name": name, "arguments": args}
  - {"type": "tool_result", "tool_call_id": id, "result": result, "is_error": bool}
  - {"type": "error", "message": error_message}
  - {"type": "pong"} (心跳响应)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...gateway import (
    Envelope,
    GatewayDispatcher,
    GatewayEvent,
    GatewayEventType,
)
from ...conversation.identity import ChannelType, ChannelProtocol

try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

router = APIRouter()

# 模块级 GatewayDispatcher 单例
_dispatcher: GatewayDispatcher | None = None


def _get_dispatcher() -> GatewayDispatcher:
    """获取 GatewayDispatcher 单例。"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = GatewayDispatcher()
    return _dispatcher


# ============================================================================
# GatewayEvent -> WebSocket JSON 转换
# ============================================================================

def _convert_gateway_event_to_ws(event: GatewayEvent) -> dict[str, Any] | None:
    """将 GatewayEvent 转换为 WebSocket JSON 消息。

    保持与前端现有协议的完全兼容。

    Args:
        event: GatewayEvent 实例。

    Returns:
        WebSocket JSON 消息字典，内部事件返回 None。
    """
    event_type = event.type
    data = event.data

    if event_type == GatewayEventType.TEXT_CHUNK:
        return {
            "type": "chunk",
            "content": data.get("content", ""),
        }

    if event_type == GatewayEventType.THINKING_CHUNK:
        return {
            "type": "thinking",
            "content": data.get("content", ""),
        }

    if event_type == GatewayEventType.MESSAGE_END:
        return {
            "type": "message",
            "content": data.get("content", ""),
            "model": data.get("model", ""),
            "provider": data.get("provider", ""),
            "stop_reason": data.get("stop_reason", ""),
            "usage": data.get("usage", {}),
            "is_finished": True,
        }

    if event_type == GatewayEventType.TOOL_CALL:
        return {
            "type": "tool_call",
            "tool_call_id": data.get("tool_call_id", ""),
            "name": data.get("name", ""),
            "arguments": data.get("arguments", {}),
        }

    if event_type == GatewayEventType.TOOL_RESULT:
        return {
            "type": "tool_result",
            "tool_call_id": data.get("tool_call_id", ""),
            "name": data.get("name", ""),
            "result": data.get("result", ""),
            "is_error": data.get("is_error", False),
        }

    if event_type == GatewayEventType.ERROR:
        return {
            "type": "error",
            "message": data.get("message", "Unknown error"),
        }

    if event_type == GatewayEventType.PONG:
        return {"type": "pong"}

    # AGENT_START, AGENT_END, MESSAGE_START 等内部事件不发送到 WebSocket
    return None


# ============================================================================
# WebSocket 消息处理
# ============================================================================

async def _handle_ws_message(
    websocket: WebSocket,
    dispatcher: GatewayDispatcher,
    content: str,
    session_id: str,
) -> None:
    """通过 GatewayDispatcher 处理用户消息。

    将用户消息封装为 Envelope，通过 Dispatcher 分发，
    将产出的 GatewayEvent 转换为 WebSocket JSON 发送给客户端。

    Args:
        websocket: WebSocket 连接。
        dispatcher: GatewayDispatcher 实例。
        content: 用户消息文本。
        session_id: 会话 ID。
    """
    envelope = Envelope.create_chat(
        session_id=session_id,
        content=content,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )

    async for event in dispatcher.dispatch(envelope):
        ws_msg = _convert_gateway_event_to_ws(event)
        if ws_msg:
            try:
                await websocket.send_json(ws_msg)
            except Exception as send_error:
                logger.warning(
                    "WebSocket send failed, continuing for persistence",
                    extra={
                        "session_id": session_id,
                        "error": str(send_error),
                    },
                )


# ============================================================================
# WebSocket 端点
# ============================================================================

@router.websocket("/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str) -> None:
    """Agent WebSocket 端点。

    纯协议层：只负责 WebSocket 协议处理，
    所有业务逻辑委托给 GatewayDispatcher。

    Args:
        websocket: WebSocket 连接。
        session_id: 会话 ID。
    """
    await websocket.accept()

    logger.info("WebSocket connected", extra={"session_id": session_id})

    dispatcher = _get_dispatcher()

    # 当前处理任务
    message_task: asyncio.Task | None = None

    async def receive_messages():
        """接收 WebSocket 消息的协程。"""
        while True:
            try:
                data = await websocket.receive_json()
                yield data
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })

    try:
        async for data in receive_messages():
            msg_type = data.get("type", "message")

            # 心跳响应
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # 中止请求
            if msg_type == "abort":
                if message_task and not message_task.done():
                    message_task.cancel()
                    try:
                        await message_task
                    except asyncio.CancelledError:
                        pass
                    message_task = None
                logger.info("Agent aborted", extra={"session_id": session_id})
                await websocket.send_json({
                    "type": "message",
                    "content": "",
                    "is_finished": True,
                    "stop_reason": "aborted",
                })
                continue

            # 处理用户消息
            content = data.get("content", "")
            if content:
                # 等待之前的任务完成
                if message_task and not message_task.done():
                    await message_task

                # 启动新任务
                message_task = asyncio.create_task(
                    _handle_ws_message(websocket, dispatcher, content, session_id)
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"session_id": session_id})

        # 等待后台任务完成，确保持久化不被中断
        if message_task and not message_task.done():
            logger.info(
                "Waiting for background task to complete after disconnect",
                extra={"session_id": session_id},
            )
            try:
                await message_task
                logger.info(
                    "Background task completed successfully after disconnect",
                    extra={"session_id": session_id},
                )
            except Exception as task_error:
                logger.error(
                    "Background task failed after disconnect",
                    extra={
                        "session_id": session_id,
                        "error": str(task_error),
                    },
                )

        # 断开连接时关闭 Session
        await dispatcher.close_session(session_id)
        logger.info("Session closed", extra={"session_id": session_id})

    except Exception as exc:
        logger.error(
            "WebSocket error",
            extra={"session_id": session_id, "error": str(exc)},
        )
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(exc),
            })
        except Exception:
            pass
'''

target.write_text(content)
print(f"Written {len(content)} bytes to {target}")
