"""Gateway HTTP/SSE 客户端。

通过 HTTP POST + SSE 流式连接 Backend 的 Gateway REST 端点，
将用户消息发送到 /api/v1/gateway/chat 并接收流式事件。

支持 Remote 模式（连接远程 Backend）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import CLIConfig


@dataclass
class GatewaySSEEvent:
    """从 SSE 流解析出的事件。

    Attributes:
        event_type: 事件类型（如 text_chunk、message_end 等）。
        data: 事件数据字典。
        agent_id: 响应来源 Agent ID。
        agent_name: 响应来源 Agent 名称。
        is_done: 是否为流结束标记。
    """
    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    agent_name: str | None = None
    is_done: bool = False


class GatewayClient:
    """Gateway HTTP/SSE 客户端。

    通过 HTTP POST 发送消息到 Gateway REST 端点，
    以 SSE 格式接收流式响应事件。

    持久化 httpx.AsyncClient 以复用连接，减少交互模式下的连接开销。
    使用完毕后应调用 close() 释放资源。

    用法::

        client = GatewayClient(config)
        async for event in client.chat("你好", session_id="sess-123"):
            print(event.event_type, event.data)
        await client.close()
    """

    def __init__(self, config: CLIConfig) -> None:
        self._config = config
        self._base_url = config.server_url
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建持久化的 httpx.AsyncClient。"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._config.timeout, connect=10.0),
            )
        return self._http_client

    async def close(self) -> None:
        """关闭底层 HTTP 客户端，释放连接资源。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def chat(
        self,
        content: str,
        session_id: str,
        *,
        agent_name: str | None = None,
        agent_id: str | None = None,
        images: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[GatewaySSEEvent, None]:
        """发送对话消息并流式接收响应。

        Args:
            content: 用户消息文本。
            session_id: 会话 ID。
            agent_name: 目标 Agent 名称（可选）。
            agent_id: 目标 Agent ID（可选）。
            images: 图片列表（可选）。

        Yields:
            GatewaySSEEvent 事件。
        """
        # CLI 交互使用统一的 cli_channel 作为默认 channel_id
        request_body: dict[str, Any] = {
            "content": content,
            "session_id": session_id,
            "channel_id": "cli_channel",  # CLI 交互默认 channel
        }
        if agent_name:
            request_body["agent_name"] = agent_name
        if agent_id:
            request_body["agent_id"] = agent_id
        if images:
            request_body["images"] = images

        client = self._get_http_client()
        async with client.stream(
            "POST",
            "/api/v1/gateway/chat",
            json=request_body,
            headers={"Accept": "text/event-stream"},
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                raise GatewayClientError(
                    f"Gateway returned {response.status_code}: {error_body.decode()}"
                )

            async for event in self._parse_sse_stream(response):
                yield event

    async def check_health(self) -> dict[str, Any]:
        """检查 Backend 健康状态。

        Returns:
            健康状态响应数据。

        Raises:
            GatewayClientError: 连接失败或响应异常。
        """
        client = self._get_http_client()
        response = await client.get(
            "/api/v1/health",
            timeout=httpx.Timeout(5.0),
        )
        if response.status_code != 200:
            raise GatewayClientError(
                f"Health check failed: {response.status_code}"
            )
        return response.json()

    async def _parse_sse_stream(
        self,
        response: httpx.Response,
    ) -> AsyncGenerator[GatewaySSEEvent, None]:
        """解析 SSE 流为 GatewaySSEEvent。

        遵循 SSE 规范：同一事件中的多个 data: 行会被拼接（以换行分隔），
        然后作为一个完整的 JSON 进行解析。

        SSE 格式：
        - data: {"type": "text_chunk", "data": {...}, ...}
        - data: [DONE]

        Args:
            response: httpx 流式响应。

        Yields:
            GatewaySSEEvent 事件。
        """
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                message_block, buffer = buffer.split("\n\n", 1)
                message_block = message_block.strip()
                if not message_block:
                    continue

                data_parts: list[str] = []
                for line in message_block.split("\n"):
                    if line.startswith("data: "):
                        data_parts.append(line[6:])

                if not data_parts:
                    continue

                combined_data = "\n".join(data_parts)

                if combined_data == "[DONE]":
                    yield GatewaySSEEvent(
                        event_type="done",
                        is_done=True,
                    )
                    return

                try:
                    payload = json.loads(combined_data)
                except json.JSONDecodeError:
                    continue

                yield GatewaySSEEvent(
                    event_type=payload.get("type", "unknown"),
                    data=payload.get("data", {}),
                    agent_id=payload.get("agent_id"),
                    agent_name=payload.get("agent_name"),
                )


class GatewayClientError(Exception):
    """Gateway 客户端错误。"""
