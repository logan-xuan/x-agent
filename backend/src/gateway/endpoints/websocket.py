"""Gateway WebSocket 端点（纯协议层）。

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
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..envelope import Envelope
from ..dispatcher import GatewayDispatcher
from ..response import GatewayEvent, GatewayEventType
from ..agent_bridge import AgentBridge
from ..agent_info import AgentInfo
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

_EVENT_TYPE_TO_WS_TYPE: dict[GatewayEventType, str] = {
    GatewayEventType.TEXT_CHUNK: "chunk",
    GatewayEventType.THINKING_CHUNK: "thinking",
    GatewayEventType.MESSAGE_END: "message",
    GatewayEventType.TOOL_CALL: "tool_call",
    GatewayEventType.TOOL_RESULT: "tool_result",
    GatewayEventType.ERROR: "error",
    GatewayEventType.PONG: "pong",
}

def convert_gateway_event_to_ws(event: GatewayEvent) -> dict[str, Any] | None:
    """将 GatewayEvent 转换为 WebSocket JSON 消息。

    跳过 WebSocket 协议不需要的事件类型（如 AGENT_START、AGENT_END、MESSAGE_START）。

    Args:
        event: Gateway 统一响应事件。

    Returns:
        WebSocket JSON 字典，或 None（表示跳过该事件）。
    """
    ws_type = _EVENT_TYPE_TO_WS_TYPE.get(event.type)
    if ws_type is None:
        return None

    if event.type == GatewayEventType.TEXT_CHUNK:
        return {
            "type": "chunk",
            "content": event.data.get("content", ""),
        }

    if event.type == GatewayEventType.THINKING_CHUNK:
        return {
            "type": "thinking",
            "content": event.data.get("content", ""),
        }

    if event.type == GatewayEventType.MESSAGE_END:
        return {
            "type": "message",
            "content": event.data.get("content", ""),
            "model": event.data.get("model", ""),
            "is_finished": True,
        }

    if event.type == GatewayEventType.TOOL_CALL:
        return {
            "type": "tool_call",
            "tool_call_id": event.data.get("tool_call_id", ""),
            "name": event.data.get("name", ""),
            "arguments": event.data.get("arguments", {}),
        }

    if event.type == GatewayEventType.TOOL_RESULT:
        return {
            "type": "tool_result",
            "tool_call_id": event.data.get("tool_call_id", ""),
            "result": event.data.get("result", ""),
            "is_error": event.data.get("is_error", False),
        }

    if event.type == GatewayEventType.ERROR:
        return {
            "type": "error",
            "message": event.data.get("message", "Unknown error"),
        }

    if event.type == GatewayEventType.PONG:
        return {"type": "pong"}

    return None

# ============================================================================
# WebSocket 消息 -> Envelope 转换
# ============================================================================

def _parse_ws_message_to_envelope(
    data: dict[str, Any],
    session_id: str,
) -> Envelope:
    """将 WebSocket 客户端消息解析为 Envelope。

    Args:
        data: 客户端发送的 JSON 数据。
        session_id: 当前 WebSocket 会话 ID。

    Returns:
        对应意图的 Envelope 实例。
    """
    msg_type = data.get("type", "message")

    if msg_type == "ping":
        return Envelope.create_ping(
            channel_type=ChannelType.WEB_CHAT,
            channel_protocol=ChannelProtocol.WEBSOCKET,
        )

    if msg_type == "abort":
        return Envelope.create_abort(
            session_id=session_id,
            channel_type=ChannelType.WEB_CHAT,
            channel_protocol=ChannelProtocol.WEBSOCKET,
        )

    content = data.get("content", "")
    images_raw = data.get("images", [])
    images: list[tuple[str, str]] = []
    for img in images_raw:
        if isinstance(img, dict):
            images.append((img.get("data", ""), img.get("mime_type", "image/png")))

    return Envelope.create_chat(
        content=content,
        session_id=session_id,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        images=images if images else None,
    )

# ============================================================================
# WebSocket 端点
# ============================================================================

@router.websocket("/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str) -> None:
    """Agent WebSocket 端点（纯协议层）。

    职责仅限于 WebSocket 协议处理：
    - accept / receive / send / disconnect
    - 将客户端 JSON 转换为 Envelope
    - 将 GatewayEvent 转换为 WebSocket JSON
    - 中止信号传递

    所有业务逻辑由 GatewayDispatcher 处理。

    Args:
        websocket: WebSocket 连接。
        session_id: 会话 ID。
    """
    await websocket.accept()
    logger.info("WebSocket connected", extra={"session_id": session_id})

    dispatcher = _get_dispatcher()
    bridge = AgentBridge()
    abort_event = asyncio.Event()
    message_task: asyncio.Task | None = None

    # 注册连接到 ConnectionRegistry
    # web chat 交互使用统一的 web_channel 作为默认 channel_id
    from ...conversation.dao import DEFAULT_CHANNEL_ID
    registry = get_connection_registry()
    channel_id = DEFAULT_CHANNEL_ID  # 统一使用 "web_channel"

    async def ws_sender(message: dict) -> bool:
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            return False

    registry.register(session_id, ConnectionHandle(
        channel_id=channel_id,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        send=ws_sender,
    ))

    logger.info(
        "WebSocket connection registered",
        extra={
            "session_id": session_id,
            "channel_id": channel_id,
            "channel_type": "web",
            "protocol": "websocket",
        },
    )

    # 重新激活 session（WebSocket 断开时会标记为 closed，重连时需要恢复为 active）
    try:
        from ...conversation.session import SessionManager as _ReactivateSessionManager
        _reactivate_mgr = _ReactivateSessionManager()
        await _reactivate_mgr.reactivate_session(session_id)
    except Exception as reactivate_error:
        logger.warning(
            "Failed to reactivate session on WebSocket connect",
            extra={"session_id": session_id, "error": str(reactivate_error)},
        )

    # 连接建立后，投递 outbox 中暂存的离线消息（如 cron 定时任务生成的通知）
    try:
        from ..message_bus import get_message_bus
        outbox_bus = get_message_bus()
        delivered_messages = await outbox_bus.drain_outbox(session_id)
        if delivered_messages:
            logger.info(
                "Outbox drained on WebSocket connect",
                extra={
                    "session_id": session_id,
                    "delivered_count": len(delivered_messages),
                },
            )
    except Exception as drain_error:
        logger.warning(
            "Failed to drain outbox on connect",
            extra={"session_id": session_id, "error": str(drain_error)},
        )

    # 通过 session_id 查出对应的 agent_id，用于创建正确 workspace 的 Agent
    from ...conversation.dao import DEFAULT_AGENT_ID
    from ...conversation.dao.models import Agent as AgentORM

    connection_agent_info: AgentInfo | None = None
    try:
        from ...conversation.session import SessionManager
        session_manager = SessionManager()
        existing_session = await session_manager.get_session(session_id)
        logger.info(
            "[workspace-debug] get_session result",
            extra={
                "session_id": session_id,
                "session_found": existing_session is not None,
                "session_agent_id": existing_session.agent_id if existing_session else None,
            },
        )
        if existing_session and existing_session.agent_id:
            agent_orm = AgentORM.from_config(existing_session.agent_id)
            logger.info(
                "[workspace-debug] AgentORM.from_config result",
                extra={
                    "session_id": session_id,
                    "agent_id": existing_session.agent_id,
                    "agent_orm_found": agent_orm is not None,
                    "agent_orm_workspace": getattr(agent_orm, 'workspace', None) if agent_orm else None,
                },
            )
            if agent_orm:
                connection_agent_info = AgentInfo.from_orm(agent_orm)
                logger.info(
                    "[workspace-debug] Resolved agent_info from session",
                    extra={
                        "session_id": session_id,
                        "agent_id": connection_agent_info.agent_id,
                        "agent_name": connection_agent_info.agent_name,
                    },
                )
    except Exception as resolve_error:
        logger.warning(
            "[workspace-debug] Failed to resolve agent from session, will use default",
            extra={"session_id": session_id, "error": str(resolve_error)},
        )

    if connection_agent_info is None:
        logger.info(
            "[workspace-debug] No agent resolved from session, using DEFAULT_AGENT_ID",
            extra={"session_id": session_id, "default_agent_id": DEFAULT_AGENT_ID},
        )
        connection_agent_info = AgentInfo(
            agent_id=DEFAULT_AGENT_ID,
            agent_name="default",
        )

    # 投递 agent 级别的暂存消息（通知发送时目标 agent 没有活跃 session，
    # 消息以空 session_id 暂存，重连后通过 agent_id 查找并投递）
    try:
        from ..message_bus import get_message_bus as _get_agent_bus
        agent_bus = _get_agent_bus()
        agent_delivered = await agent_bus.drain_outbox_by_agent(
            agent_id=connection_agent_info.agent_id,
            session_id=session_id,
        )
        if agent_delivered:
            logger.info(
                "Agent-level outbox drained on WebSocket connect",
                extra={
                    "session_id": session_id,
                    "agent_id": connection_agent_info.agent_id,
                    "delivered_count": len(agent_delivered),
                },
            )
    except Exception as agent_drain_error:
        logger.warning(
            "Failed to drain agent-level outbox on connect",
            extra={
                "session_id": session_id,
                "agent_id": connection_agent_info.agent_id,
                "error": str(agent_drain_error),
            },
        )

    # 连接级别：创建 Agent 实例并加载历史，整个连接生命周期复用
    cached_agent = None
    try:
        cached_agent = bridge.create_agent(agent_info=connection_agent_info)
        await bridge.load_session_history(cached_agent, session_id)
        logger.info(
            "Agent created and history loaded for WebSocket connection",
            extra={"session_id": session_id, "agent_id": connection_agent_info.agent_id},
        )
    except Exception as agent_error:
        logger.warning(
            "Failed to create Agent on connect, will fallback to per-request creation",
            extra={"session_id": session_id, "error": str(agent_error)},
        )
        cached_agent = None

    # 确保 Session 存在（委托给 dispatcher）
    try:
        await dispatcher.ensure_session(session_id, connection_agent_info)
    except Exception as session_error:
        logger.warning(
            "Failed to ensure session on connect, will retry on first message",
            extra={"session_id": session_id, "error": str(session_error)},
        )

    async def _dispatch_and_send(envelope: Envelope) -> None:
        """分发 Envelope 并将 GatewayEvent 流式发送到 WebSocket。

        有状态协议优化：传入连接级别缓存的 Agent 实例，
        避免每条消息重新创建 Agent 和加载历史。

        Args:
            envelope: 要分发的消息信封。
        """
        try:
            async for gateway_event in dispatcher.dispatch(
                envelope, abort_event=abort_event, agent=cached_agent,
            ):
                ws_message = convert_gateway_event_to_ws(gateway_event)
                if ws_message is not None:
                    try:
                        await websocket.send_json(ws_message)
                    except Exception:
                        break
        except Exception as dispatch_error:
            logger.exception(
                "Dispatch error",
                extra={
                    "session_id": session_id,
                    "error": str(dispatch_error),
                },
            )
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": str(dispatch_error),
                })
            except Exception:
                pass

    try:
        while True:
            try:
                raw_data = await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception:
                continue

            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            envelope = _parse_ws_message_to_envelope(data, session_id)

            # 心跳：直接响应，不走 dispatcher
            if envelope.intent.value == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # 中止：设置中止信号，取消当前任务
            if envelope.intent.value == "abort":
                abort_event.set()
                if message_task and not message_task.done():
                    message_task.cancel()
                    try:
                        await message_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    message_task = None
                abort_event.clear()

                await websocket.send_json({
                    "type": "message",
                    "content": "",
                    "is_finished": True,
                    "stop_reason": "aborted",
                })
                logger.info("Agent aborted", extra={"session_id": session_id})
                continue

            # 对话消息：等待前一个任务完成，然后启动新任务
            content = data.get("content", "")
            if content:
                if message_task and not message_task.done():
                    await message_task

                # 更新会话活跃时间
                try:
                    await dispatcher.touch_session(session_id)
                except Exception:
                    pass

                abort_event.clear()
                message_task = asyncio.create_task(
                    _dispatch_and_send(envelope)
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"session_id": session_id})

        # 注销连接
        registry.unregister(session_id, channel_id)

        # 等待后台任务完成，确保持久化不被中断
        if message_task and not message_task.done():
            logger.info(
                "Waiting for background task to complete after disconnect",
                extra={"session_id": session_id},
            )
            try:
                await message_task
            except Exception as task_error:
                logger.error(
                    "Background task failed after disconnect",
                    extra={
                        "session_id": session_id,
                        "error": str(task_error),
                    },
                )

        # 不再自动关闭 Session — 让 session 保持 active 状态
        # 这样用户切换 agent 后可以恢复之前的会话
        # Session 只在以下情况下关闭：
        # 1. 用户点击"新建会话"按钮（前端调用 createSession with closeExisting=true）
        # 2. 用户在 admin panel 手动关闭或删除 session
        # 3. Session 超时清理（如果有配置）
        #
        # 之前的逻辑：WebSocket 断开就关闭 session，导致切换 agent 时 session 被意外关闭
        # try:
        #     await dispatcher.close_session(session_id)
        # except Exception as close_error:
        #     logger.error(
        #         "Failed to close session",
        #         extra={
        #             "session_id": session_id,
        #             "error": str(close_error),
        #         },
        #     )
        logger.info(
            "WebSocket disconnected, session remains active",
            extra={"session_id": session_id},
        )
