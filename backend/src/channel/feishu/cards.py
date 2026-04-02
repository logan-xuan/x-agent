"""Card payload builders for Feishu replies."""

from __future__ import annotations

import json
from typing import Any

from ...gateway.response import GatewayEvent, GatewayEventType
from .constants import (
    FEISHU_CARD_DEFAULT_STATUS,
    FEISHU_CARD_DEFAULT_TITLE,
    FEISHU_CARD_DONE_STATUS,
    FEISHU_CARD_ERROR_STATUS,
    FEISHU_CARD_MAX_BYTES,
    FEISHU_CARD_TRUNCATED_SUFFIX,
)


def build_card_payload(
    content: str,
    *,
    title: str,
    status: str,
    is_error: bool = False,
) -> dict[str, Any]:
    """Build a Feishu card JSON 2.0 payload."""
    normalized_content = content.strip() or "_正在生成中..._"
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title or FEISHU_CARD_DEFAULT_TITLE,
            },
            "subtitle": {
                "tag": "plain_text",
                "content": status,
            },
            "template": "red" if is_error else "blue",
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 16px 16px 16px",
            "elements": [
                {
                    "tag": "markdown",
                    "content": normalized_content,
                    "text_align": "left",
                    "text_size": "normal_v2",
                    "margin": "0px 0px 0px 0px",
                },
            ],
        },
    }


def build_card_content(
    content: str,
    *,
    title: str,
    status: str,
    is_error: bool = False,
) -> str:
    """Serialize card content and truncate it to Feishu's payload limit."""
    normalized_content = content.strip() or "_正在生成中..._"

    def serialize(markdown_content: str) -> str:
        payload = build_card_payload(
            markdown_content,
            title=title,
            status=status,
            is_error=is_error,
        )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    serialized = serialize(normalized_content)
    if len(serialized.encode("utf-8")) <= FEISHU_CARD_MAX_BYTES:
        return serialized

    low = 0
    high = len(normalized_content)
    best = serialize("_内容过长，无法显示_")
    while low <= high:
        mid = (low + high) // 2
        candidate = normalized_content[:mid].rstrip() + FEISHU_CARD_TRUNCATED_SUFFIX
        serialized_candidate = serialize(candidate)
        if len(serialized_candidate.encode("utf-8")) <= FEISHU_CARD_MAX_BYTES:
            best = serialized_candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


def render_gateway_event(event: GatewayEvent) -> dict[str, Any]:
    """Convert a GatewayEvent into Feishu interactive message content."""
    if event.type == GatewayEventType.TEXT_CHUNK or event.type == GatewayEventType.MESSAGE_END:
        content = event.data.get("content", "")
        return {
            "msg_type": "interactive",
            "content": build_card_content(
                content,
                title=event.agent_name or FEISHU_CARD_DEFAULT_TITLE,
                status=(
                    FEISHU_CARD_DEFAULT_STATUS
                    if event.type == GatewayEventType.TEXT_CHUNK
                    else FEISHU_CARD_DONE_STATUS
                ),
            ),
        }

    if event.type == GatewayEventType.ERROR:
        message = event.data.get("message", "处理出错")
        return {
            "msg_type": "interactive",
            "content": build_card_content(
                f"❌ {message}",
                title=event.agent_name or FEISHU_CARD_DEFAULT_TITLE,
                status=FEISHU_CARD_ERROR_STATUS,
                is_error=True,
            ),
        }

    return {}
