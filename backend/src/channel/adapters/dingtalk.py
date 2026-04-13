"""钉钉 Channel Adapter 实现。

基于 dingtalk-stream SDK 建立 Stream 长连接接收消息，
通过钉钉 OpenAPI 实现流式回复（使用 AI 卡片）。

架构：
1. Stream 长连接：接收机器人消息回调
2. AI 卡片：实现流式输出效果（ai_start -> ai_streaming -> ai_finish）
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from ...conversation.identity import ChannelProtocol, ChannelType
from ...gateway.envelope import Envelope
from ...gateway.response import GatewayEvent, GatewayEventType
from ..base import ChannelAdapter

try:
    import dingtalk_stream
    from dingtalk_stream import (
        AckMessage,
        AIMarkdownCardInstance,
        ChatbotHandler,
        ChatbotMessage,
    )
except ImportError:
    dingtalk_stream = None  # type: ignore[assignment]
    ChatbotMessage = None  # type: ignore[assignment]
    AckMessage = None  # type: ignore[assignment]
    AIMarkdownCardInstance = None  # type: ignore[assignment]

    # 提供 dummy 基类，以便模块可以正常导入
    class ChatbotHandler:  # type: ignore[misc]
        """Dummy ChatbotHandler for import fallback."""

        def __init__(self) -> None:
            pass


try:
    from ...utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# 钉钉 OpenAPI 端点
DINGTALK_OPENAPI_ENDPOINT = "https://api.dingtalk.com"


class DingtalkChannelAdapter(ChannelAdapter):
    """钉钉 Stream 模式 Channel Adapter。

    使用 dingtalk-stream SDK 建立 WebSocket 长连接，
    接收机器人消息并通过 AI 卡片实现流式回复。

    Attributes:
        channel_id: 配置中的 channel id。
        app_key: 钉钉应用 AppKey。
        app_secret: 钉钉应用 AppSecret。
        dispatcher_factory: 用于获取 GatewayDispatcher 实例的工厂函数。
    """

    def __init__(
        self,
        channel_id: str,
        app_key: str,
        app_secret: str,
        dispatcher_factory: Callable[[], Any],
    ) -> None:
        """初始化钉钉 Channel Adapter。

        Args:
            channel_id: 配置中的 channel id。
            app_key: 钉钉应用 AppKey（Client ID）。
            app_secret: 钉钉应用 AppSecret（Client Secret）。
            dispatcher_factory: 用于获取 GatewayDispatcher 实例的工厂函数。
        """
        if dingtalk_stream is None:
            raise ImportError(
                "dingtalk-stream is required for DingtalkChannelAdapter. "
                "Install it with: pip install dingtalk-stream"
            )

        self._channel_id = channel_id
        self._app_key = app_key
        self._app_secret = app_secret
        self._dispatcher_factory = dispatcher_factory

        # Stream 客户端
        self._client: dingtalk_stream.DingTalkStreamClient | None = None
        self._running = False
        self._start_task: asyncio.Task | None = None

        # Access token 缓存
        self._access_token: str | None = None
        self._token_expire_time: float = 0

        # 消息处理状态（用于流式回复）
        # key: session_id, value: AIMarkdownCardInstance
        self._card_instances: dict[str, AIMarkdownCardInstance] = {}
        # key: session_id, value: accumulated text
        self._accumulated_text: dict[str, str] = {}

    @property
    def channel_type(self) -> ChannelType:
        """返回渠道类型。"""
        return ChannelType.DINGTALK

    async def start(self) -> None:
        """启动钉钉 Stream 连接。

        创建 DingTalkStreamClient 并注册消息回调处理器，
        在后台启动 Stream 连接。
        """
        if self._running:
            logger.warning("DingtalkChannelAdapter is already running")
            return

        # 创建凭证和客户端
        credential = dingtalk_stream.Credential(self._app_key, self._app_secret)
        self._client = dingtalk_stream.DingTalkStreamClient(credential)

        # 注册消息回调处理器
        handler = _DingtalkMessageHandler(self)
        self._client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            handler,
        )

        self._running = True

        # 在后台启动客户端（client.start() 是异步的）
        self._start_task = asyncio.create_task(self._run_client())

        logger.info(
            "DingtalkChannelAdapter started",
            extra={"channel_id": self._channel_id},
        )

    async def _run_client(self) -> None:
        """运行 Stream 客户端（处理自动重连）。"""
        while self._running:
            if self._client is None:
                logger.error("DingtalkChannelAdapter client is None")
                break
            try:
                await self._client.start()
            except asyncio.CancelledError:
                logger.info("DingtalkChannelAdapter client cancelled")
                break
            except Exception as e:
                logger.error(
                    "DingtalkChannelAdapter client error, will retry",
                    extra={"error": str(e)},
                )
                if self._running:
                    await asyncio.sleep(10)  # 等待后重连

    async def stop(self) -> None:
        """停止钉钉 Stream 连接。"""
        self._running = False

        if self._start_task:
            self._start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._start_task
            self._start_task = None

        self._client = None

        logger.info(
            "DingtalkChannelAdapter stopped",
            extra={"channel_id": self._channel_id},
        )

    async def to_envelope(self, raw_message: ChatbotMessage) -> Envelope:
        """将钉钉消息转换为统一信封。

        Args:
            raw_message: 钉钉 ChatbotMessage 实例。

        Returns:
            转换后的 Envelope 实例。
        """
        # 提取用户标识
        user_id = raw_message.sender_staff_id or raw_message.sender_id

        # 提取会话标识
        # conversationId 作为 peer_id，用于 bindings 匹配
        peer_id = raw_message.conversation_id

        # 确定 peer_kind（1=单聊, 2=群聊）
        peer_kind = "user" if raw_message.conversation_type == "1" else "group"

        # 提取消息内容
        content = ""
        if raw_message.text and raw_message.text.content:
            content = raw_message.text.content.strip()
        elif raw_message.message_type == "richText":
            # 富文本消息
            text_list = raw_message.get_text_list()
            content = "\n".join(text_list) if text_list else ""

        # 生成 session_id
        # 对于单聊：使用 user_id 作为 session 标识
        # 对于群聊：使用 conversation_id 作为 session 标识
        if raw_message.conversation_type == "1":
            # 单聊：user_id + robot_code 组合确保唯一性
            session_id = f"dingtalk_{raw_message.sender_staff_id or raw_message.sender_id}"
        else:
            # 群聊：conversation_id 作为 session
            session_id = f"dingtalk_{raw_message.conversation_id}"

        # 创建 Envelope
        envelope = Envelope.create_chat(
            content=content,
            session_id=session_id,
            channel_type=ChannelType.DINGTALK,
            channel_protocol=ChannelProtocol.STREAM,
            user_id=user_id,
            channel_id=self._channel_id,
            peer_id=peer_id,
            peer_kind=peer_kind,
            metadata={
                "dingtalk_message_id": raw_message.message_id,
                "dingtalk_conversation_id": raw_message.conversation_id,
                "dingtalk_conversation_type": raw_message.conversation_type,
                "dingtalk_sender_nick": raw_message.sender_nick,
                "dingtalk_session_webhook": raw_message.session_webhook,
                "dingtalk_session_webhook_expired_time": raw_message.session_webhook_expired_time,
                "dingtalk_robot_code": raw_message.robot_code,
            },
        )

        return envelope

    async def render_response(self, event: GatewayEvent) -> dict[str, Any]:
        """将 GatewayEvent 转换为钉钉消息格式。

        Args:
            event: Gateway 统一响应事件。

        Returns:
            钉钉消息格式的字典。
        """
        if event.type == GatewayEventType.TEXT_CHUNK:
            return {
                "action": "streaming",
                "content": event.data.get("content", ""),
            }
        elif event.type == GatewayEventType.MESSAGE_END:
            return {
                "action": "finish",
                "content": event.data.get("content", ""),
            }
        elif event.type == GatewayEventType.ERROR:
            return {
                "action": "error",
                "content": event.data.get("message", "Unknown error"),
            }
        else:
            return {
                "action": "ignore",
                "type": event.type.value,
            }

    async def get_access_token(self) -> str | None:
        """获取钉钉 access_token（带缓存）。

        access_token 有效期通常为 2 小时，提前 5 分钟刷新。

        Returns:
            access_token 或 None（获取失败时）。
        """
        # 检查缓存是否有效
        if self._access_token and time.time() < self._token_expire_time:
            return self._access_token

        # 获取新的 access_token
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{DINGTALK_OPENAPI_ENDPOINT}/v1.0/oauth2/accessToken",
                    json={
                        "appKey": self._app_key,
                        "appSecret": self._app_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()

                self._access_token = data.get("accessToken")
                # 提前 5 分钟过期
                expire_in = data.get("expireIn", 7200) - 300
                self._token_expire_time = time.time() + expire_in

                logger.debug(
                    "DingTalk access_token refreshed",
                    extra={"expire_in": expire_in},
                )

                return self._access_token

        except Exception as e:
            logger.error(
                "Failed to get DingTalk access_token",
                extra={"error": str(e)},
            )
            return None

    async def handle_message(self, incoming_message: ChatbotMessage) -> tuple[int, str]:
        """处理钉钉消息回调。

        将消息转换为 Envelope，调用 dispatcher 处理，
        并通过 AI 卡片实现流式回复。

        Args:
            incoming_message: 钉钉 ChatbotMessage 实例。

        Returns:
            (status_code, message) 元组，用于 ACK 响应。
        """
        try:
            # 1. 转换为 Envelope
            envelope = await self.to_envelope(incoming_message)

            logger.info(
                "DingTalk message received",
                extra={
                    "session_id": envelope.session_id,
                    "content_length": len(envelope.content),
                    "conversation_type": incoming_message.conversation_type,
                },
            )

            # 2. 获取 dispatcher
            dispatcher = self._dispatcher_factory()

            # 3. 初始化 AI 卡片实例
            card_instance = self._create_ai_card_instance(incoming_message)
            if card_instance:
                self._card_instances[envelope.session_id] = card_instance
                self._accumulated_text[envelope.session_id] = ""

            # 4. 流式处理事件
            async for event in dispatcher.dispatch(envelope):
                await self._handle_event(envelope.session_id, event, incoming_message)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.exception(
                "Error handling DingTalk message",
                extra={"error": str(e)},
            )
            return AckMessage.STATUS_OK, f"Error: {e}"

    def _create_ai_card_instance(
        self,
        incoming_message: ChatbotMessage,
    ) -> AIMarkdownCardInstance | None:
        """创建 AI 卡片实例。

        Args:
            incoming_message: 钉钉消息。

        Returns:
            AIMarkdownCardInstance 实例或 None。
        """
        try:
            if self._client is None:
                return None

            card_instance = AIMarkdownCardInstance(self._client, incoming_message)
            card_instance.ai_start()
            return card_instance

        except Exception as e:
            logger.error(
                "Failed to create AI card instance",
                extra={"error": str(e)},
            )
            return None

    async def _handle_event(
        self,
        session_id: str,
        event: GatewayEvent,
        incoming_message: ChatbotMessage,
    ) -> None:
        """处理 GatewayEvent 事件。

        根据事件类型更新 AI 卡片内容。

        Args:
            session_id: 会话 ID。
            event: GatewayEvent 事件。
            incoming_message: 原始钉钉消息。
        """
        card_instance = self._card_instances.get(session_id)
        accumulated = self._accumulated_text.get(session_id, "")

        if event.type == GatewayEventType.TEXT_CHUNK:
            # 累积文本
            chunk = event.data.get("content", "")
            accumulated += chunk
            self._accumulated_text[session_id] = accumulated

            # 更新卡片（流式输出）
            if card_instance:
                try:
                    # 在线程池中执行同步的 SDK 方法
                    await asyncio.to_thread(
                        card_instance.ai_streaming,
                        accumulated,
                        False,  # append=False，全量替换
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update AI card streaming",
                        extra={"error": str(e), "session_id": session_id},
                    )

        elif event.type == GatewayEventType.MESSAGE_END:
            # 最终消息
            final_content = event.data.get("content", accumulated)

            if card_instance:
                try:
                    await asyncio.to_thread(
                        card_instance.ai_finish,
                        final_content,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to finish AI card",
                        extra={"error": str(e), "session_id": session_id},
                    )

            # 清理状态
            self._card_instances.pop(session_id, None)
            self._accumulated_text.pop(session_id, None)

        elif event.type == GatewayEventType.ERROR:
            error_msg = event.data.get("message", "Unknown error")

            if card_instance:
                try:
                    await asyncio.to_thread(
                        card_instance.ai_finish,
                        f"❌ 错误: {error_msg}",
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to finish AI card with error",
                        extra={"error": str(e), "session_id": session_id},
                    )

            # 清理状态
            self._card_instances.pop(session_id, None)
            self._accumulated_text.pop(session_id, None)

        else:
            # 忽略其他事件类型
            pass


class _DingtalkMessageHandler(ChatbotHandler):
    """钉钉消息回调处理器。

    继承 ChatbotHandler，将消息转发给 DingtalkChannelAdapter 处理。
    """

    def __init__(self, adapter: DingtalkChannelAdapter):
        """初始化处理器。

        Args:
            adapter: DingtalkChannelAdapter 实例。
        """
        super().__init__()
        self._adapter = adapter

    def process(self, callback: dingtalk_stream.CallbackMessage) -> tuple[int, str]:
        """处理钉钉消息回调。"""
        try:
            incoming_message = ChatbotMessage.from_dict(callback.data)

            try:
                loop = asyncio.get_running_loop()
                # 在当前 loop 上调度协程，不阻塞等待
                loop.create_task(self._adapter.handle_message(incoming_message))
                # 立即返回 OK，避免阻塞事件循环
                return AckMessage.STATUS_OK, "OK"
            except RuntimeError:
                # 没有运行中的事件循环，创建新的
                return asyncio.run(self._adapter.handle_message(incoming_message))

        except Exception as e:
            logger.exception(
                "Error in _DingtalkMessageHandler.process",
                extra={"error": str(e)},
            )
            return AckMessage.STATUS_OK, f"Handler error: {e}"
