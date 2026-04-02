"""Streaming response coordinator for Feishu."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from ...gateway.envelope import Envelope
from ...gateway.response import GatewayEventType
from .constants import (
    FEISHU_CARD_DEFAULT_STATUS,
    FEISHU_CARD_DEFAULT_TITLE,
    FEISHU_CARD_DONE_STATUS,
    FEISHU_CARD_ERROR_STATUS,
    FEISHU_CARD_UPDATE_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeishuReplyTarget:
    receive_id: str
    receive_id_type: str


@dataclass(slots=True)
class FeishuStreamState:
    accumulated_text: str = ""
    message_id: str | None = None
    last_card_update_at: float | None = None
    card_stream_enabled: bool = True
    card_title: str = FEISHU_CARD_DEFAULT_TITLE


def should_flush_card_update(last_card_update_at: float | None) -> bool:
    """Return whether a card update should be flushed now."""
    if last_card_update_at is None:
        return True
    return (time.monotonic() - last_card_update_at) >= FEISHU_CARD_UPDATE_INTERVAL_SECONDS


def resolve_reply_target(envelope: Envelope) -> FeishuReplyTarget:
    """Resolve reply target from an Envelope."""
    is_p2p = envelope.peer_kind == "user"
    return FeishuReplyTarget(
        receive_id=envelope.user_id if is_p2p else envelope.peer_id,
        receive_id_type="open_id" if is_p2p else "chat_id",
    )


class FeishuStreamProcessor:
    """Handle dispatcher stream events and send Feishu responses."""

    def __init__(self, message_client: Any) -> None:
        self._message_client = message_client

    async def process(self, envelope: Envelope, dispatcher: Any) -> None:
        """Process streamed Gateway events and push them to Feishu."""
        state = FeishuStreamState()
        reply_target = resolve_reply_target(envelope)
        chat_id = envelope.peer_id

        try:
            async for event in dispatcher.dispatch(envelope):
                if event.agent_name:
                    state.card_title = event.agent_name

                if event.type == GatewayEventType.TEXT_CHUNK:
                    await self._handle_text_chunk(event, state, reply_target)
                elif event.type == GatewayEventType.MESSAGE_END:
                    await self._handle_message_end(event, state, reply_target)
                elif event.type == GatewayEventType.ERROR:
                    await self._handle_error(event, state, reply_target)

        except Exception as exc:
            logger.exception(
                "Error in stream response processing",
                extra={"chat_id": chat_id, "error": str(exc)},
            )
            await self._handle_runtime_exception(exc, state, reply_target)

    async def _handle_text_chunk(
        self,
        event: Any,
        state: FeishuStreamState,
        reply_target: FeishuReplyTarget,
    ) -> None:
        chunk = event.data.get("content", "")
        state.accumulated_text += chunk

        if state.card_stream_enabled and state.message_id is None:
            state.message_id = await self._message_client.send_card_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=state.accumulated_text,
                title=state.card_title,
                status=FEISHU_CARD_DEFAULT_STATUS,
            )
            if state.message_id:
                state.last_card_update_at = time.monotonic()
                logger.debug(
                    "Initial Feishu card sent",
                    extra={
                        "message_id": state.message_id,
                        "content_length": len(state.accumulated_text),
                    },
                )
            else:
                state.card_stream_enabled = False
            return

        if state.card_stream_enabled and state.message_id and should_flush_card_update(state.last_card_update_at):
            updated = await self._message_client.update_card_message(
                message_id=state.message_id,
                content=state.accumulated_text,
                title=state.card_title,
                status=FEISHU_CARD_DEFAULT_STATUS,
            )
            if updated:
                state.last_card_update_at = time.monotonic()
            else:
                state.card_stream_enabled = False

    async def _handle_message_end(
        self,
        event: Any,
        state: FeishuStreamState,
        reply_target: FeishuReplyTarget,
    ) -> None:
        final_content = event.data.get("content", state.accumulated_text)

        if state.card_stream_enabled and state.message_id:
            updated = await self._message_client.update_card_message(
                message_id=state.message_id,
                content=final_content,
                title=state.card_title,
                status=FEISHU_CARD_DONE_STATUS,
            )
            if not updated:
                state.card_stream_enabled = False

        if not state.card_stream_enabled:
            await self._message_client.send_text_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=final_content or "处理完成",
            )
        elif state.message_id is None:
            state.message_id = await self._message_client.send_card_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=final_content or "处理完成",
                title=state.card_title,
                status=FEISHU_CARD_DONE_STATUS,
            )
            if state.message_id is None:
                await self._message_client.send_text_message(
                    receive_id=reply_target.receive_id,
                    receive_id_type=reply_target.receive_id_type,
                    content=final_content or "处理完成",
                )

        logger.info(
            "Feishu card message completed",
            extra={"message_id": state.message_id, "content_length": len(final_content)},
        )

    async def _handle_error(
        self,
        event: Any,
        state: FeishuStreamState,
        reply_target: FeishuReplyTarget,
    ) -> None:
        error_msg = event.data.get("message", "处理出错")
        error_content = f"❌ {error_msg}"

        if state.card_stream_enabled and state.message_id:
            updated = await self._message_client.update_card_message(
                message_id=state.message_id,
                content=error_content,
                title=state.card_title,
                status=FEISHU_CARD_ERROR_STATUS,
                is_error=True,
            )
            if not updated:
                state.card_stream_enabled = False
        elif state.card_stream_enabled:
            state.message_id = await self._message_client.send_card_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=error_content,
                title=state.card_title,
                status=FEISHU_CARD_ERROR_STATUS,
                is_error=True,
            )
            if state.message_id is None:
                state.card_stream_enabled = False

        if not state.card_stream_enabled:
            await self._message_client.send_text_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=error_content,
            )

        logger.error(
            "Feishu card message error",
            extra={"error": error_msg},
        )

    async def _handle_runtime_exception(
        self,
        exc: Exception,
        state: FeishuStreamState,
        reply_target: FeishuReplyTarget,
    ) -> None:
        error_content = f"❌ 处理过程中发生错误: {exc}"
        try:
            if state.card_stream_enabled and state.message_id:
                updated = await self._message_client.update_card_message(
                    message_id=state.message_id,
                    content=error_content,
                    title=state.card_title,
                    status=FEISHU_CARD_ERROR_STATUS,
                    is_error=True,
                )
                if updated:
                    return

            await self._message_client.send_text_message(
                receive_id=reply_target.receive_id,
                receive_id_type=reply_target.receive_id_type,
                content=error_content,
            )
        except Exception:
            pass
