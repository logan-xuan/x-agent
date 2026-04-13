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
import base64
import binascii
import contextlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...conversation.identity import ChannelProtocol, ChannelType
from ...extensions.voice import (
    AudioTranscriptionRequest,
    SpeechSynthesisRequest,
    get_voice_service,
)
from ...extensions.voice.assets import AudioAssetStore, get_audio_asset_store
from ..agent_bridge import AgentBridge
from ..agent_info import AgentInfo
from ..connection_registry import (
    ConnectionHandle,
    get_connection_registry,
)
from ..dispatcher import GatewayDispatcher
from ..envelope import Envelope
from ..response import GatewayEvent, GatewayEventType

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


class VoiceProcessingError(RuntimeError):
    """Structured voice-processing error for WebSocket protocol responses."""

    def __init__(
        self,
        *,
        message: str,
        stage: str,
        code: str,
        recoverable: bool = True,
        message_id: str | None = None,
        audio: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.recoverable = recoverable
        self.message_id = message_id
        self.audio = audio


def _build_error_event(
    message: str,
    *,
    code: str = "unknown_error",
    stage: str | None = None,
    recoverable: bool = False,
    message_id: str | None = None,
    audio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "error",
        "message": message,
        "code": code,
        "recoverable": recoverable,
    }
    if stage:
        payload["stage"] = stage
    if message_id:
        payload["message_id"] = message_id
    if audio is not None:
        payload["audio"] = audio
    return payload


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
            "message_id": event.data.get("message_id"),
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
            "name": event.data.get("name", ""),
            "result": event.data.get("result", ""),
            "is_error": event.data.get("is_error", False),
            "details": event.data.get("details", {}),
            "duration_ms": event.data.get("duration_ms"),
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
    metadata = dict(data.get("metadata", {}) or {})

    return Envelope.create_chat(
        content=content,
        session_id=session_id,
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        images=images if images else None,
        metadata=metadata if metadata else None,
    )


def _resolve_agent_voice_defaults(agent_id: str) -> dict[str, Any]:
    """读取当前 Agent 的默认语音配置。"""
    from ...config.manager import get_config

    agent_cfg = get_config().multi_agent.get_agent(agent_id)
    if agent_cfg is None:
        return {}
    return agent_cfg.voice.model_dump()


def _normalize_duration_ms(value: Any) -> int | None:
    """Normalize optional duration milliseconds from untyped payloads."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        duration_ms = int(value)
        return duration_ms if duration_ms > 0 else None
    return None


def _classify_voice_transcription_failure(exc: Exception, *, provider: str) -> tuple[str, str]:
    """Map provider exceptions to user-facing ASR error messages."""
    error_text = str(exc)
    normalized = error_text.upper()

    if "TIMED OUT" in normalized or "TIMEOUT" in normalized:
        return (
            "语音转写超时，请稍后重试",
            "voice_transcription_timeout",
        )
    if "FFMPEG" in normalized or "FFPROBE" in normalized:
        return (
            "语音格式暂不兼容，服务端转码失败，请尝试上传 mp3 或 wav",
            "voice_transcode_failed",
        )
    if provider == "funasr-bailian":
        return (
            "FunASR 实时转写失败，请检查模型、采样率和音频格式配置",
            "voice_transcription_failed",
        )
    return ("语音转写失败，请重试", "voice_transcription_failed")


async def _prepare_voice_chat_payload(
    data: dict[str, Any],
    *,
    session_id: str,
    agent_id: str,
    asset_store: AudioAssetStore | None = None,
    voice_service=None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """将携带音频的 WebSocket 消息转成可进入聊天主流程的文本负载。"""
    audio = data.get("audio")
    if not isinstance(audio, dict):
        return data, None

    audio_b64 = str(audio.get("data", "") or "")
    if not audio_b64:
        raise ValueError("audio.data is required for audio messages")

    try:
        audio_bytes = base64.b64decode(audio_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("audio.data must be valid base64") from exc

    mime_type = str(audio.get("mime_type", "audio/webm"))
    audio_format = str(audio.get("format", "webm"))
    original_filename = audio.get("filename")
    duration_ms = _normalize_duration_ms(audio.get("duration_ms"))
    agent_voice_defaults = _resolve_agent_voice_defaults(agent_id)
    asr_provider = str(audio.get("asr_provider") or agent_voice_defaults.get("asr_provider") or "openai")
    logger.info(
        "Received voice message payload",
        extra={
            "session_id": session_id,
            "agent_id": agent_id,
            "provider": asr_provider,
            "mime_type": mime_type,
            "audio_format": audio_format,
            "original_filename": original_filename,
            "duration_ms": duration_ms,
            "audio_bytes": len(audio_bytes),
        },
    )
    store = asset_store or get_audio_asset_store()
    service = voice_service or get_voice_service()

    stored = await store.save_uploaded_audio(
        agent_id=agent_id,
        session_id=session_id,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        audio_format=audio_format,
        original_filename=str(original_filename) if original_filename else None,
        duration_ms=duration_ms,
    )
    logger.info(
        "Stored uploaded voice asset",
        extra={
            "session_id": session_id,
            "agent_id": agent_id,
            "provider": asr_provider,
            "asset_id": stored.asset_id,
            "audio_public_url": stored.public_url,
            "duration_ms": stored.duration_ms,
            "audio_format": stored.audio_format,
            "size_bytes": stored.size_bytes,
        },
    )
    asset_ref = stored.to_ref(
        source="upload",
        metadata={"original_filename": original_filename} if original_filename else {},
    )

    audio_metadata = {
        "asset_id": asset_ref.asset_id,
        "public_url": asset_ref.public_url,
        "playback_url": asset_ref.playback_url,
        "mime_type": asset_ref.mime_type,
        "format": asset_ref.format,
        "original_filename": original_filename,
        "duration_ms": stored.duration_ms,
    }

    try:
        transcription = await service.transcribe(
            AudioTranscriptionRequest(
                provider=asr_provider,
                asset=asset_ref,
                language_hint=str(audio.get("language_hint")) if audio.get("language_hint") else None,
                prompt=str(audio.get("prompt")) if audio.get("prompt") else None,
            )
        )
    except Exception as exc:
        user_message, error_code = _classify_voice_transcription_failure(
            exc,
            provider=asr_provider,
        )
        logger.warning(
            "Voice transcription failed",
            extra={
                "session_id": session_id,
                "agent_id": agent_id,
                "provider": asr_provider,
                "audio_public_url": asset_ref.public_url,
                "audio_format": asset_ref.format,
                "error": str(exc),
            },
        )
        raise VoiceProcessingError(
            message=user_message,
            stage="asr",
            code=error_code,
            recoverable=True,
            audio=audio_metadata,
        ) from exc

    prepared = dict(data)
    metadata = dict(prepared.get("metadata", {}) or {})
    metadata["audio"] = audio_metadata
    metadata["transcript"] = {
        "text": transcription.text,
        "provider": transcription.provider,
        "language": transcription.language,
    }
    logger.info(
        "Voice transcription succeeded",
        extra={
            "session_id": session_id,
            "agent_id": agent_id,
            "provider": transcription.provider,
            "asset_id": asset_ref.asset_id,
            "audio_public_url": asset_ref.public_url,
            "duration_ms": stored.duration_ms,
            "language": transcription.language,
            "transcript_length": len(transcription.text),
        },
    )
    if "voice_reply" in prepared:
        metadata["voice_reply"] = bool(prepared.get("voice_reply"))
    if prepared.get("tts_provider"):
        metadata["voice_reply_provider"] = str(prepared.get("tts_provider"))
    if prepared.get("tts_voice"):
        metadata["voice_reply_voice"] = str(prepared.get("tts_voice"))
    prepared["metadata"] = metadata
    prepared["content"] = transcription.text
    prepared.pop("audio", None)

    transcript_event = {
        "type": "transcript",
        "content": transcription.text,
        "provider": transcription.provider,
        "language": transcription.language,
        "audio": metadata["audio"],
    }
    return prepared, transcript_event


async def _maybe_build_voice_reply_payload(
    envelope: Envelope,
    message_content: str,
    *,
    voice_service=None,
) -> dict[str, Any] | None:
    """在用户请求语音回复时，为 assistant 文本生成音频回复元数据。"""
    if not envelope.metadata.get("voice_reply"):
        agent_defaults = _resolve_agent_voice_defaults(envelope.agent_id or "")
        if not bool(agent_defaults.get("reply_enabled")):
            return None
    else:
        agent_defaults = _resolve_agent_voice_defaults(envelope.agent_id or "")
    if not message_content.strip():
        return None

    service = voice_service or get_voice_service()
    result = await service.synthesize(
        SpeechSynthesisRequest(
            text=message_content,
            provider=str(
                envelope.metadata.get("voice_reply_provider")
                or agent_defaults.get("tts_provider")
                or "edge"
            ),
            voice=(
                str(envelope.metadata.get("voice_reply_voice"))
                if envelope.metadata.get("voice_reply_voice")
                else (
                    str(agent_defaults.get("tts_voice"))
                    if agent_defaults.get("tts_voice")
                    else None
                )
            ),
            metadata={
                "agent_id": envelope.agent_id or "main-agent",
                "session_id": envelope.session_id,
            },
        )
    )
    return {
        "asset_id": result.asset.asset_id,
        "public_url": result.asset.public_url,
        "playback_url": result.asset.playback_url,
        "mime_type": result.asset.mime_type,
        "format": result.asset.format,
        "provider": result.provider,
        "voice": result.voice,
    }


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

    registry.register(
        session_id,
        ConnectionHandle(
            channel_id=channel_id,
            channel_type=ChannelType.WEB_CHAT,
            channel_protocol=ChannelProtocol.WEBSOCKET,
            send=ws_sender,
        ),
    )

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
        await _reactivate_mgr.touch_session(session_id)
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
                    "agent_orm_workspace": getattr(agent_orm, "workspace", None)
                    if agent_orm
                    else None,
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
                envelope,
                abort_event=abort_event,
                agent=cached_agent,
            ):
                ws_message = convert_gateway_event_to_ws(gateway_event)
                if ws_message is not None:
                    deferred_error_message: dict[str, Any] | None = None
                    if gateway_event.type == GatewayEventType.MESSAGE_END:
                        try:
                            audio_reply = await _maybe_build_voice_reply_payload(
                                envelope,
                                str(gateway_event.data.get("content", "")),
                            )
                            if audio_reply is not None:
                                ws_message["audio_reply"] = audio_reply
                                message_id = gateway_event.data.get("message_id")
                                if isinstance(message_id, str) and message_id:
                                    from ...conversation.session import SessionManager

                                    session_manager = SessionManager()
                                    await session_manager.update_message_metadata(
                                        message_id,
                                        {"audio_reply": audio_reply},
                                    )
                        except Exception as voice_reply_error:
                            logger.warning(
                                "Failed to synthesize assistant voice reply",
                                extra={
                                    "session_id": session_id,
                                    "agent_id": envelope.agent_id,
                                    "error": str(voice_reply_error),
                                },
                            )
                            deferred_error_message = _build_error_event(
                                "语音回复生成失败，已保留文本回复",
                                code="voice_reply_failed",
                                stage="tts",
                                recoverable=True,
                                message_id=(
                                    str(gateway_event.data.get("message_id"))
                                    if gateway_event.data.get("message_id")
                                    else None
                                ),
                            )
                    try:
                        await websocket.send_json(ws_message)
                        if deferred_error_message is not None:
                            await websocket.send_json(deferred_error_message)
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
            with contextlib.suppress(Exception):
                await websocket.send_json(
                    _build_error_event(str(dispatch_error), code="dispatch_failed")
                )

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
                await websocket.send_json(
                    _build_error_event("Invalid JSON", code="invalid_json")
                )
                continue

            try:
                data, transcript_event = await _prepare_voice_chat_payload(
                    data,
                    session_id=session_id,
                    agent_id=connection_agent_info.agent_id,
                )
            except ValueError as voice_payload_error:
                await websocket.send_json(
                    _build_error_event(
                        str(voice_payload_error),
                        code="invalid_audio_payload",
                        stage="asr",
                        recoverable=True,
                    )
                )
                continue
            except VoiceProcessingError as voice_processing_error:
                logger.warning(
                    "Sending structured voice-processing error to client",
                    extra={
                        "session_id": session_id,
                        "agent_id": connection_agent_info.agent_id,
                        "stage": voice_processing_error.stage,
                        "code": voice_processing_error.code,
                        "recoverable": voice_processing_error.recoverable,
                        "message_id": voice_processing_error.message_id,
                        "audio": voice_processing_error.audio,
                        "error": str(voice_processing_error),
                    },
                )
                await websocket.send_json(
                    _build_error_event(
                        str(voice_processing_error),
                        code=voice_processing_error.code,
                        stage=voice_processing_error.stage,
                        recoverable=voice_processing_error.recoverable,
                        message_id=voice_processing_error.message_id,
                        audio=voice_processing_error.audio,
                    )
                )
                continue
            except Exception as voice_processing_error:
                logger.warning(
                    "Failed to process voice message payload",
                    extra={
                        "session_id": session_id,
                        "error": str(voice_processing_error),
                    },
                )
                await websocket.send_json(
                    _build_error_event(
                        "语音消息处理失败，请稍后重试",
                        code="voice_processing_failed",
                        stage="asr",
                        recoverable=True,
                    )
                )
                continue

            if transcript_event is not None:
                await websocket.send_json(transcript_event)

            envelope = _parse_ws_message_to_envelope(data, session_id)
            envelope.agent_id = connection_agent_info.agent_id

            # 心跳：直接响应，不走 dispatcher
            if envelope.intent.value == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # 中止：设置中止信号，取消当前任务
            if envelope.intent.value == "abort":
                abort_event.set()
                if message_task and not message_task.done():
                    message_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await message_task
                    message_task = None
                abort_event.clear()

                await websocket.send_json(
                    {
                        "type": "message",
                        "content": "",
                        "is_finished": True,
                        "stop_reason": "aborted",
                    }
                )
                logger.info("Agent aborted", extra={"session_id": session_id})
                continue

            # 对话消息：等待前一个任务完成，然后启动新任务
            content = data.get("content", "")
            if content:
                if message_task and not message_task.done():
                    await message_task

                # 更新会话活跃时间
                with contextlib.suppress(Exception):
                    await dispatcher.touch_session(session_id)

                abort_event.clear()
                message_task = asyncio.create_task(_dispatch_and_send(envelope))

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
