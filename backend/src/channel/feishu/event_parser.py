"""Feishu event parsing and Envelope conversion."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...conversation.identity import ChannelProtocol, ChannelType
from ...gateway.envelope import Envelope

logger = logging.getLogger(__name__)


_FEISHU_PLACEHOLDER_PATTERN = re.compile(r"@_user_\d+")
_FEISHU_TAG_PATTERN = re.compile(r"<at [^>]+>.*?</at>")
_FEISHU_WHITESPACE_PATTERN = re.compile(r"[ \t]{2,}")


def remove_bot_mention(content: str, mentions: list[dict]) -> str:
    """Remove Feishu mention placeholders and legacy mention tags."""
    result = content

    # Legacy text payloads may still contain raw <at ...> tags.
    result = _FEISHU_TAG_PATTERN.sub("", result)

    for mention in mentions:
        mention_key = mention.get("key")
        if mention_key:
            result = result.replace(str(mention_key), "")
        name = mention.get("name", "")
        if name:
            result = result.replace(f"@{name}", "")

    # Feishu receive payloads commonly replace mentions with @_user_N placeholders.
    result = _FEISHU_PLACEHOLDER_PATTERN.sub("", result)
    result = _FEISHU_WHITESPACE_PATTERN.sub(" ", result)
    return result.strip()


class FeishuEventParser:
    """Parse Feishu events into internal structures."""

    def __init__(self, channel_id: str) -> None:
        self._channel_id = channel_id

    def parse_event(self, event: Any) -> dict[str, Any] | None:
        """Parse a WebSocket callback event into a dict."""
        try:
            if isinstance(event, dict):
                return event

            if hasattr(event, "event") and event.event is not None:
                event_data = event.event
                message = getattr(event_data, "message", None)
                sender = getattr(event_data, "sender", None)
                if message is None or sender is None:
                    return None

                header = getattr(event, "header", None)
                return {
                    "schema": "p2",
                    "header": {
                        "event_id": getattr(header, "event_id", "") if header else "",
                        "event_type": "im.message.receive_v1",
                        "create_time": getattr(header, "create_time", "") if header else "",
                        "token": getattr(header, "token", "") if header else "",
                        "app_id": getattr(header, "app_id", "") if header else "",
                        "tenant_key": getattr(header, "tenant_key", "") if header else "",
                    },
                    "event": {
                        "sender": {
                            "sender_id": {
                                "open_id": getattr(sender.sender_id, "open_id", "") if sender.sender_id else "",
                                "user_id": getattr(sender.sender_id, "user_id", "") if sender.sender_id else "",
                                "union_id": getattr(sender.sender_id, "union_id", "") if sender.sender_id else "",
                            },
                            "sender_type": getattr(sender, "sender_type", ""),
                            "tenant_key": getattr(sender, "tenant_key", ""),
                        },
                        "message": {
                            "message_id": getattr(message, "message_id", ""),
                            "root_id": getattr(message, "root_id", ""),
                            "parent_id": getattr(message, "parent_id", ""),
                            "create_time": getattr(message, "create_time", 0),
                            "chat_id": getattr(message, "chat_id", ""),
                            "chat_type": getattr(message, "chat_type", "p2p"),
                            "message_type": getattr(message, "message_type", "text"),
                            "content": getattr(message, "content", "{}"),
                            "mentions": [
                                {
                                    "key": getattr(mention, "key", ""),
                                    "id": {
                                        "open_id": getattr(mention.id, "open_id", "") if hasattr(mention, "id") and mention.id else "",
                                        "user_id": getattr(mention.id, "user_id", "") if hasattr(mention, "id") and mention.id else "",
                                    },
                                    "name": getattr(mention, "name", ""),
                                }
                                for mention in (message.mentions or [])
                            ] if message.mentions else [],
                        },
                    },
                }

            if hasattr(event, "__dict__"):
                return dict(event.__dict__)

            return None
        except Exception as exc:
            logger.warning(
                "Failed to parse Feishu event",
                extra={"error": str(exc)},
            )
            return None

    async def to_envelope(self, raw_message: Any) -> Envelope | None:
        """Convert a parsed Feishu event to an Envelope."""
        try:
            event_body = raw_message.get("event", {})
            message = event_body.get("message", {})
            sender = event_body.get("sender", {})

            chat_id = message.get("chat_id")
            chat_type = message.get("chat_type", "p2p")
            message_id = message.get("message_id")
            msg_type = message.get("message_type", "text")
            content_raw = message.get("content", "{}")

            sender_id = sender.get("sender_id", {})
            open_id = sender_id.get("open_id", "unknown")

            if msg_type != "text":
                logger.debug(
                    "Skipping non-text message",
                    extra={"msg_type": msg_type, "message_id": message_id},
                )
                return None

            try:
                content_json = json.loads(content_raw)
                content = content_json.get("text", "")
            except json.JSONDecodeError:
                content = content_raw

            mentions = message.get("mentions", [])
            if mentions:
                content = remove_bot_mention(content, mentions)

            if not content or not content.strip():
                logger.debug("Skipping empty message")
                return None

            peer_kind = "group" if chat_type == "group" else "user"
            session_id = f"feishu_{chat_id}"
            return Envelope.create_chat(
                content=content.strip(),
                session_id=session_id,
                channel_type=ChannelType.FEISHU,
                channel_protocol=ChannelProtocol.STREAM,
                user_id=open_id,
                channel_id=self._channel_id,
                peer_id=chat_id,
                peer_kind=peer_kind,
                metadata={
                    "feishu_message_id": message_id,
                    "feishu_chat_type": chat_type,
                    "feishu_msg_type": msg_type,
                },
            )
        except Exception as exc:
            logger.exception(
                "Failed to convert Feishu message to Envelope",
                extra={"raw_message": raw_message, "error": str(exc)},
            )
            return None

    @staticmethod
    def extract_message_id(raw_message: dict[str, Any]) -> str | None:
        """Extract the raw Feishu message_id from a parsed event dict."""
        return raw_message.get("event", {}).get("message", {}).get("message_id")
