"""Feishu channel adapter facade."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import Any

from ...conversation.identity import ChannelType
from ...gateway.envelope import Envelope
from ...gateway.response import GatewayEvent
from ..base import ChannelAdapter
from .cards import build_card_content, render_gateway_event
from .constants import FEISHU_CARD_DEFAULT_STATUS, FEISHU_CARD_DEFAULT_TITLE
from .dedup import ProcessedMessageTracker
from .event_parser import FeishuEventParser, remove_bot_mention
from .message_client import FeishuMessageClient
from .streaming import FeishuStreamProcessor, should_flush_card_update

logger = logging.getLogger(__name__)


class FeishuChannelAdapter(ChannelAdapter):
    """Facade for the Feishu channel adapter."""

    def __init__(
        self,
        channel_id: str,
        app_id: str,
        app_secret: str,
        dispatcher_factory: Callable[[], Any],
    ) -> None:
        self._channel_id = channel_id
        self._app_id = app_id
        self._app_secret = app_secret
        self._dispatcher_factory = dispatcher_factory

        self._client: Any = None
        self._ws_client: Any = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_task: threading.Thread | None = None

        self._event_parser = FeishuEventParser(channel_id)
        self._message_client = FeishuMessageClient(lambda: self._client)
        self._stream_processor = FeishuStreamProcessor(self._message_client)
        self._processed_messages = ProcessedMessageTracker()

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.FEISHU

    def _run_ws_client(self, ws_client: Any) -> None:
        """Run the blocking Feishu WebSocket client in a dedicated thread."""
        import lark_oapi.ws as ws_module

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        ws_module.client.loop = new_loop

        try:
            ws_client.start()
        except Exception as exc:
            logger.error(
                "Feishu WebSocket client error",
                extra={"channel_id": self._channel_id, "error": str(exc)},
            )
        finally:
            new_loop.close()

    async def start(self) -> None:
        """Start the Feishu WebSocket connection."""
        try:
            import lark_oapi as lark
            from lark_oapi.ws import Client as WsClient

            try:
                from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
            except ImportError:
                EventDispatcherHandler = None  # type: ignore[assignment]

            self._loop = asyncio.get_running_loop()
            self._client = (
                lark.Client.builder()
                .app_id(self._app_id)
                .app_secret(self._app_secret)
                .log_level(lark.LogLevel.DEBUG)
                .build()
            )

            def on_message(event: Any) -> None:
                self._handle_message_sync(event)

            event_handler = None
            if EventDispatcherHandler is not None:
                event_handler = (
                    EventDispatcherHandler.builder(
                        encrypt_key="",
                        verification_token="",
                    )
                    .register_p2_im_message_receive_v1(on_message)
                    .build()
                )

            self._ws_client = WsClient(
                app_id=self._app_id,
                app_secret=self._app_secret,
                event_handler=event_handler,
            )

            self._running = True
            logger.info(
                "Feishu WebSocket client starting",
                extra={"channel_id": self._channel_id, "app_id": self._app_id},
            )

            self._ws_thread = threading.Thread(
                target=self._run_ws_client,
                args=(self._ws_client,),
                name=f"feishu-ws-{self._channel_id}",
                daemon=True,
            )
            self._ws_thread.start()
            self._ws_task = self._ws_thread
        except ImportError as exc:
            logger.error(
                "Failed to import lark_oapi, please ensure lark-oapi is installed",
                extra={"error": str(exc)},
            )
            raise RuntimeError(
                "lark-oapi SDK not installed. Please add 'lark-oapi>=1.0.0' to your dependencies."
            ) from exc
        except Exception as exc:
            logger.exception(
                "Failed to start Feishu WebSocket client",
                extra={"channel_id": self._channel_id, "error": str(exc)},
            )
            raise

    async def stop(self) -> None:
        """Stop the Feishu WebSocket connection."""
        self._running = False
        if self._ws_client is not None:
            stop = getattr(self._ws_client, "stop", None)
            if callable(stop):
                stop()
        self._ws_thread = None
        self._ws_task = None
        logger.info(
            "Feishu WebSocket client stopped",
            extra={"channel_id": self._channel_id},
        )

    def _handle_message_sync(self, event: Any) -> None:
        """Schedule event processing back onto the asyncio loop."""
        if not self._running or not self._loop:
            return

        asyncio.run_coroutine_threadsafe(
            self._handle_message(event),
            self._loop,
        )

    async def _handle_message(self, event: Any) -> None:
        """Handle a Feishu event end to end."""
        try:
            event_dict = self._parse_event(event)
            if not event_dict:
                logger.warning("Failed to parse Feishu event", extra={"event": event})
                return

            raw_message_id = self._event_parser.extract_message_id(event_dict)
            if await self._processed_messages.seen_or_add(raw_message_id):
                logger.info(
                    "Skipping duplicate Feishu message",
                    extra={"feishu_message_id": raw_message_id},
                )
                return

            envelope = await self.to_envelope(event_dict)
            if not envelope:
                logger.debug("Message filtered or invalid, skipping")
                return

            logger.info(
                "Feishu message received",
                extra={
                    "feishu_message_id": raw_message_id,
                    "session_id": envelope.session_id,
                    "chat_type": event_dict.get("event", {}).get("message", {}).get("chat_type"),
                },
            )

            dispatcher = self._dispatcher_factory()
            await self._process_stream_response(envelope, dispatcher)
        except Exception as exc:
            logger.exception(
                "Error handling Feishu message",
                extra={"error": str(exc)},
            )

    async def _process_stream_response(self, envelope: Envelope, dispatcher: Any) -> None:
        await self._stream_processor.process(envelope, dispatcher)

    async def _send_message(
        self,
        receive_id: str,
        receive_id_type: str,
        content: str,
        *,
        title: str = FEISHU_CARD_DEFAULT_TITLE,
        status: str = FEISHU_CARD_DEFAULT_STATUS,
        is_error: bool = False,
    ) -> str | None:
        return await self._message_client.send_card_message(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            content=content,
            title=title,
            status=status,
            is_error=is_error,
        )

    async def _send_text_message(self, receive_id: str, receive_id_type: str, content: str) -> str | None:
        return await self._message_client.send_text_message(receive_id, receive_id_type, content)

    async def _update_message(
        self,
        message_id: str,
        content: str,
        *,
        title: str = FEISHU_CARD_DEFAULT_TITLE,
        status: str = FEISHU_CARD_DEFAULT_STATUS,
        is_error: bool = False,
    ) -> bool:
        return await self._message_client.update_card_message(
            message_id=message_id,
            content=content,
            title=title,
            status=status,
            is_error=is_error,
        )

    def _build_card_content(
        self,
        content: str,
        *,
        title: str,
        status: str,
        is_error: bool = False,
    ) -> str:
        return build_card_content(
            content,
            title=title,
            status=status,
            is_error=is_error,
        )

    def _parse_event(self, event: Any) -> dict[str, Any] | None:
        return self._event_parser.parse_event(event)

    async def to_envelope(self, raw_message: Any) -> Envelope | None:
        return await self._event_parser.to_envelope(raw_message)

    def _remove_bot_mention(self, content: str, mentions: list[dict]) -> str:
        return remove_bot_mention(content, mentions)

    def _should_flush_card_update(self, last_card_update_at: float | None) -> bool:
        return should_flush_card_update(last_card_update_at)

    async def render_response(self, event: GatewayEvent) -> dict[str, Any]:
        return render_gateway_event(event)

    def __repr__(self) -> str:
        return f"<FeishuChannelAdapter channel_id={self._channel_id!r} running={self._running}>"
