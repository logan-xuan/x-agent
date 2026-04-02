"""Feishu message sending and updating client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from .cards import build_card_content
from .constants import FEISHU_CARD_DEFAULT_STATUS, FEISHU_CARD_DEFAULT_TITLE

logger = logging.getLogger(__name__)


class FeishuMessageClient:
    """Thin wrapper around lark-oapi message APIs."""

    def __init__(self, client_getter: Callable[[], Any]) -> None:
        self._client_getter = client_getter

    def _get_client(self) -> Any | None:
        client = self._client_getter()
        if client is None:
            logger.error("Feishu client is not initialized")
        return client

    async def send_card_message(
        self,
        receive_id: str,
        receive_id_type: str,
        content: str,
        *,
        title: str = FEISHU_CARD_DEFAULT_TITLE,
        status: str = FEISHU_CARD_DEFAULT_STATUS,
        is_error: bool = False,
    ) -> str | None:
        """Send an interactive card message."""
        client = self._get_client()
        if client is None:
            return None

        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            msg_content = build_card_content(
                content,
                title=title,
                status=status,
                is_error=is_error,
            )
            response = await asyncio.to_thread(
                client.im.v1.message.create,
                request=CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("interactive")
                    .content(msg_content)
                    .build()
                )
                .build(),
            )

            if response.success():
                message_id = str(response.data.message_id) if response.data.message_id else None
                logger.debug(
                    "Feishu card message sent",
                    extra={
                        "receive_id": receive_id,
                        "receive_id_type": receive_id_type,
                        "message_id": message_id,
                    },
                )
                return message_id

            logger.error(
                "Failed to send Feishu card message",
                extra={
                    "receive_id": receive_id,
                    "receive_id_type": receive_id_type,
                    "code": response.code,
                    "error_msg": response.msg,
                },
            )
            return None
        except Exception as exc:
            logger.exception(
                "Exception sending Feishu card message",
                extra={"receive_id": receive_id, "error": str(exc)},
            )
            return None

    async def send_text_message(self, receive_id: str, receive_id_type: str, content: str) -> str | None:
        """Send a plain text fallback message."""
        client = self._get_client()
        if client is None:
            return None

        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            msg_content = json.dumps({"text": content}, ensure_ascii=False)
            response = await asyncio.to_thread(
                client.im.v1.message.create,
                request=CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("text")
                    .content(msg_content)
                    .build()
                )
                .build(),
            )

            if response.success():
                return str(response.data.message_id) if response.data.message_id else None

            logger.error(
                "Failed to send Feishu text fallback",
                extra={
                    "receive_id": receive_id,
                    "receive_id_type": receive_id_type,
                    "code": response.code,
                    "error_msg": response.msg,
                },
            )
            return None
        except Exception as exc:
            logger.exception(
                "Exception sending Feishu text fallback",
                extra={"receive_id": receive_id, "error": str(exc)},
            )
            return None

    async def update_card_message(
        self,
        message_id: str,
        content: str,
        *,
        title: str = FEISHU_CARD_DEFAULT_TITLE,
        status: str = FEISHU_CARD_DEFAULT_STATUS,
        is_error: bool = False,
    ) -> bool:
        """Update an interactive card message."""
        client = self._get_client()
        if client is None:
            return False

        try:
            from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

            msg_content = build_card_content(
                content,
                title=title,
                status=status,
                is_error=is_error,
            )
            response = await asyncio.to_thread(
                client.im.v1.message.patch,
                request=PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(msg_content)
                    .build()
                )
                .build(),
            )

            if response.success():
                logger.debug(
                    "Feishu card message updated",
                    extra={"message_id": message_id, "content_length": len(content)},
                )
                return True

            logger.warning(
                "Failed to update Feishu card message",
                extra={
                    "message_id": message_id,
                    "code": response.code,
                    "error_msg": response.msg,
                },
            )
            return False
        except Exception as exc:
            logger.warning(
                "Exception updating Feishu card message",
                extra={"message_id": message_id, "error": str(exc)},
            )
            return False
