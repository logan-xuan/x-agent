"""Unit tests for Channel Adapters.

Tests for DingtalkChannelAdapter, FeishuChannelAdapter, 
ChannelRegistry, and create_channel_adapter factory.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config.models import ChannelConfig
from src.conversation.identity import ChannelProtocol, ChannelType
from src.gateway.envelope import Envelope
from src.gateway.response import GatewayEvent, GatewayEventType
from src.channel.registry import ChannelRegistry, create_channel_adapter


# =============================================================================
# TestDingtalkChannelAdapter
# =============================================================================


class TestDingtalkChannelAdapter:
    """Tests for DingtalkChannelAdapter."""

    def test_creation(self):
        """Test DingtalkChannelAdapter creation with parameters."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-dingtalk-channel",
                app_key="test_app_key",
                app_secret="test_app_secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            assert adapter is not None
            assert adapter._channel_id == "test-dingtalk-channel"
            assert adapter._app_key == "test_app_key"
            assert adapter._app_secret == "test_app_secret"

    def test_channel_type(self):
        """Test channel_type returns ChannelType.DINGTALK."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            assert adapter.channel_type == ChannelType.DINGTALK

    @pytest.mark.asyncio
    async def test_to_envelope_single_chat(self):
        """Test to_envelope for single chat message (peer_kind='user')."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            # Mock ChatbotMessage for single chat
            mock_message = MagicMock()
            mock_message.sender_staff_id = "user123"
            mock_message.sender_id = "sender_456"
            mock_message.conversation_id = "conv_789"
            mock_message.conversation_type = "1"  # 单聊
            mock_message.message_id = "msg_001"
            mock_message.sender_nick = "测试用户"
            mock_message.session_webhook = "https://webhook.example.com"
            mock_message.session_webhook_expired_time = 1234567890
            mock_message.robot_code = "robot_001"
            mock_message.message_type = "text"
            mock_message.text = MagicMock()
            mock_message.text.content = "  你好，机器人  "
            
            envelope = await adapter.to_envelope(mock_message)
            
            assert envelope is not None
            assert envelope.content == "你好，机器人"
            assert envelope.channel_type == ChannelType.DINGTALK
            assert envelope.channel_protocol == ChannelProtocol.STREAM
            assert envelope.user_id == "user123"
            assert envelope.peer_id == "conv_789"
            assert envelope.peer_kind == "user"
            assert envelope.channel_id == "test-channel"

    @pytest.mark.asyncio
    async def test_to_envelope_group_chat(self):
        """Test to_envelope for group chat message (peer_kind='group')."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            # Mock ChatbotMessage for group chat
            mock_message = MagicMock()
            mock_message.sender_staff_id = "user123"
            mock_message.sender_id = "sender_456"
            mock_message.conversation_id = "group_789"
            mock_message.conversation_type = "2"  # 群聊
            mock_message.message_id = "msg_002"
            mock_message.sender_nick = "测试用户"
            mock_message.session_webhook = "https://webhook.example.com"
            mock_message.session_webhook_expired_time = 1234567890
            mock_message.robot_code = "robot_001"
            mock_message.message_type = "text"
            mock_message.text = MagicMock()
            mock_message.text.content = "群消息内容"
            
            envelope = await adapter.to_envelope(mock_message)
            
            assert envelope is not None
            assert envelope.peer_kind == "group"
            assert envelope.peer_id == "group_789"
            assert "dingtalk_group_789" in envelope.session_id

    @pytest.mark.asyncio
    async def test_to_envelope_fields(self):
        """Test all Envelope fields are correctly set."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel-id",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            mock_message = MagicMock()
            mock_message.sender_staff_id = "staff_001"
            mock_message.sender_id = "sender_id_001"
            mock_message.conversation_id = "conversation_001"
            mock_message.conversation_type = "1"
            mock_message.message_id = "message_id_001"
            mock_message.sender_nick = "用户昵称"
            mock_message.session_webhook = "https://webhook.url"
            mock_message.session_webhook_expired_time = 9999999
            mock_message.robot_code = "robot_code_001"
            mock_message.message_type = "text"
            mock_message.text = MagicMock()
            mock_message.text.content = "测试内容"
            
            envelope = await adapter.to_envelope(mock_message)
            
            # 验证所有字段
            assert envelope.content == "测试内容"
            assert envelope.channel_type == ChannelType.DINGTALK
            assert envelope.channel_protocol == ChannelProtocol.STREAM
            assert envelope.user_id == "staff_001"
            assert envelope.peer_id == "conversation_001"
            assert envelope.peer_kind == "user"
            assert envelope.channel_id == "test-channel-id"
            
            # 验证 metadata
            assert envelope.metadata["dingtalk_message_id"] == "message_id_001"
            assert envelope.metadata["dingtalk_conversation_id"] == "conversation_001"
            assert envelope.metadata["dingtalk_conversation_type"] == "1"
            assert envelope.metadata["dingtalk_sender_nick"] == "用户昵称"
            assert envelope.metadata["dingtalk_session_webhook"] == "https://webhook.url"
            assert envelope.metadata["dingtalk_robot_code"] == "robot_code_001"

    @pytest.mark.asyncio
    async def test_render_response_text_chunk(self):
        """Test render_response for TEXT_CHUNK event."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            event = GatewayEvent.text_chunk("这是流式文本")
            result = await adapter.render_response(event)
            
            assert result["action"] == "streaming"
            assert result["content"] == "这是流式文本"

    @pytest.mark.asyncio
    async def test_render_response_message_end(self):
        """Test render_response for MESSAGE_END event."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            event = GatewayEvent.message_end("完整消息内容")
            result = await adapter.render_response(event)
            
            assert result["action"] == "finish"
            assert result["content"] == "完整消息内容"

    @pytest.mark.asyncio
    async def test_render_response_error(self):
        """Test render_response for ERROR event."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            event = GatewayEvent.error("处理失败", error_type="TestError")
            result = await adapter.render_response(event)
            
            assert result["action"] == "error"
            assert result["content"] == "处理失败"

    @pytest.mark.asyncio
    async def test_render_response_unknown_event(self):
        """Test render_response for unknown event type returns ignore action."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            # 使用未知事件类型
            event = GatewayEvent.pong()
            result = await adapter.render_response(event)
            
            assert result["action"] == "ignore"
            assert "type" in result

    @pytest.mark.asyncio
    async def test_get_access_token(self):
        """Test get_access_token with mocked httpx."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="test_key",
                app_secret="test_secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            # Mock httpx.AsyncClient
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "accessToken": "test_access_token_123",
                "expireIn": 7200,
            }
            mock_response.raise_for_status = MagicMock()
            
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client
                
                token = await adapter.get_access_token()
                
                assert token == "test_access_token_123"
                # 验证请求被调用
                mock_client.post.assert_called_once()
                # 验证 URL 包含 accessToken 路径
                call_args = mock_client.post.call_args
                request_url = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
                assert "accessToken" in str(request_url)

    @pytest.mark.asyncio
    async def test_access_token_cache(self):
        """Test access_token caching mechanism."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="test_key",
                app_secret="test_secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            # 手动设置缓存的 token
            adapter._access_token = "cached_token"
            adapter._token_expire_time = time.time() + 3600  # 1小时后过期
            
            # 第二次调用不应该发请求
            token = await adapter.get_access_token()
            
            assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_start_creates_stream_client(self):
        """Test start() creates Stream client and starts background task."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            # Mock dingtalk_stream 模块
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_credential = MagicMock()
            
            # 正确设置 ChatbotMessage 和 TOPIC 属性
            mock_chatbot_message = MagicMock()
            mock_chatbot_message.TOPIC = "chatbot_message"
            
            mock_dingtalk.DingTalkStreamClient.return_value = mock_client
            mock_dingtalk.Credential.return_value = mock_credential
            mock_dingtalk.ChatbotMessage = mock_chatbot_message
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            await adapter.start()
            
            # 验证客户端创建
            mock_dingtalk.Credential.assert_called_once_with("key", "secret")
            mock_dingtalk.DingTalkStreamClient.assert_called_once()
            
            # 验证回调注册
            mock_client.register_callback_handler.assert_called_once()
            
            # 验证 running 状态
            assert adapter._running is True
            assert adapter._start_task is not None
            
            # 清理
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_stop_cleanup(self):
        """Test stop() correctly cleans up resources."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_client = MagicMock()
            mock_client.start = AsyncMock()
            mock_credential = MagicMock()
            
            # 正确设置 ChatbotMessage 和 TOPIC 属性
            mock_chatbot_message = MagicMock()
            mock_chatbot_message.TOPIC = "chatbot_message"
            
            mock_dingtalk.DingTalkStreamClient.return_value = mock_client
            mock_dingtalk.Credential.return_value = mock_credential
            mock_dingtalk.ChatbotMessage = mock_chatbot_message
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            from src.channel.adapters.dingtalk import DingtalkChannelAdapter
            
            adapter = DingtalkChannelAdapter(
                channel_id="test-channel",
                app_key="key",
                app_secret="secret",
                dispatcher_factory=lambda: MagicMock(),
            )
            
            await adapter.start()
            await adapter.stop()
            
            # 验证资源清理
            assert adapter._running is False
            assert adapter._client is None
            assert adapter._start_task is None


# =============================================================================
# TestFeishuChannelAdapter
# =============================================================================


class TestFeishuChannelAdapter:
    """Tests for FeishuChannelAdapter."""

    def test_creation(self):
        """Test FeishuChannelAdapter creation with parameters."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-feishu-channel",
            app_id="test_app_id",
            app_secret="test_app_secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        assert adapter is not None
        assert adapter._channel_id == "test-feishu-channel"
        assert adapter._app_id == "test_app_id"
        assert adapter._app_secret == "test_app_secret"

    def test_channel_type(self):
        """Test channel_type returns ChannelType.FEISHU."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        assert adapter.channel_type == ChannelType.FEISHU

    @pytest.mark.asyncio
    async def test_to_envelope_text_message(self):
        """Test to_envelope for text message."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        # 构造飞书消息事件字典
        event_dict = {
            "event": {
                "message": {
                    "chat_id": "chat_001",
                    "chat_type": "p2p",
                    "message_id": "msg_001",
                    "msg_type": "text",
                    "content": json.dumps({"text": "你好，飞书机器人"}),
                    "mentions": [],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_123456",
                    },
                },
            },
        }
        
        envelope = await adapter.to_envelope(event_dict)
        
        assert envelope is not None
        assert envelope.content == "你好，飞书机器人"
        assert envelope.channel_type == ChannelType.FEISHU
        assert envelope.channel_protocol == ChannelProtocol.STREAM
        assert envelope.user_id == "ou_123456"
        assert envelope.peer_id == "chat_001"
        assert envelope.peer_kind == "user"

    @pytest.mark.asyncio
    async def test_to_envelope_group_chat(self):
        """Test to_envelope for group chat (chat_type=group)."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event_dict = {
            "event": {
                "message": {
                    "chat_id": "group_chat_001",
                    "chat_type": "group",
                    "message_id": "msg_002",
                    "msg_type": "text",
                    "content": json.dumps({"text": "群消息内容"}),
                    "mentions": [],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_789",
                    },
                },
            },
        }
        
        envelope = await adapter.to_envelope(event_dict)
        
        assert envelope is not None
        assert envelope.peer_kind == "group"
        assert envelope.peer_id == "group_chat_001"

    @pytest.mark.asyncio
    async def test_to_envelope_p2p_chat(self):
        """Test to_envelope for p2p chat (chat_type=p2p)."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event_dict = {
            "event": {
                "message": {
                    "chat_id": "p2p_chat_001",
                    "chat_type": "p2p",
                    "message_id": "msg_003",
                    "msg_type": "text",
                    "content": json.dumps({"text": "私聊消息"}),
                    "mentions": [],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_p2p_user",
                    },
                },
            },
        }
        
        envelope = await adapter.to_envelope(event_dict)
        
        assert envelope is not None
        assert envelope.peer_kind == "user"

    @pytest.mark.asyncio
    async def test_to_envelope_with_mention(self):
        """Test to_envelope with @bot mention removed."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        # 消息包含 @机器人
        event_dict = {
            "event": {
                "message": {
                    "chat_id": "chat_mention",
                    "chat_type": "group",
                    "message_id": "msg_mention",
                    "msg_type": "text",
                    "content": json.dumps({
                        "text": '<at user_id="ou_bot_id">@机器人</at> 请帮我处理这个问题'
                    }),
                    "mentions": [
                        {
                            "key": "ou_bot_id",
                            "name": "机器人",
                        }
                    ],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_sender",
                    },
                },
            },
        }
        
        envelope = await adapter.to_envelope(event_dict)
        
        assert envelope is not None
        # @机器人 应该被移除
        assert "<at" not in envelope.content
        assert "</at>" not in envelope.content
        assert "请帮我处理这个问题" in envelope.content

    @pytest.mark.asyncio
    async def test_to_envelope_with_placeholder_mention(self):
        """Test to_envelope removes Feishu @_user_N placeholder mentions."""
        from src.channel.adapters.feishu import FeishuChannelAdapter

        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )

        event_dict = {
            "event": {
                "message": {
                    "chat_id": "chat_placeholder",
                    "chat_type": "group",
                    "message_id": "msg_placeholder",
                    "msg_type": "text",
                    "content": json.dumps({"text": "@_user_1 请帮我处理这个问题"}),
                    "mentions": [
                        {
                            "key": "@_user_1",
                            "name": "机器人",
                        }
                    ],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_sender",
                    },
                },
            },
        }

        envelope = await adapter.to_envelope(event_dict)

        assert envelope is not None
        assert "@_user_1" not in envelope.content
        assert "请帮我处理这个问题" == envelope.content

    @pytest.mark.asyncio
    async def test_to_envelope_fields(self):
        """Test all Envelope fields are correctly set."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel-id",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event_dict = {
            "event": {
                "message": {
                    "chat_id": "chat_fields",
                    "chat_type": "p2p",
                    "message_id": "msg_fields",
                    "msg_type": "text",
                    "content": json.dumps({"text": "测试字段"}),
                    "mentions": [],
                },
                "sender": {
                    "sender_id": {
                        "open_id": "ou_test_user",
                    },
                },
            },
        }
        
        envelope = await adapter.to_envelope(event_dict)
        
        # 验证所有字段
        assert envelope.content == "测试字段"
        assert envelope.channel_type == ChannelType.FEISHU
        assert envelope.channel_protocol == ChannelProtocol.STREAM
        assert envelope.user_id == "ou_test_user"
        assert envelope.peer_id == "chat_fields"
        assert envelope.peer_kind == "user"
        assert envelope.channel_id == "test-channel-id"
        
        # 验证 metadata
        assert envelope.metadata["feishu_message_id"] == "msg_fields"
        assert envelope.metadata["feishu_chat_type"] == "p2p"
        assert envelope.metadata["feishu_msg_type"] == "text"

    def test_remove_bot_mention(self):
        """Test _remove_bot_mention regex cleaning."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        # 测试带 @机器人 的消息
        content = '<at user_id="ou_bot_123">@机器人</at> 你好，请帮我处理'
        mentions = [{"key": "ou_bot_123", "name": "机器人"}]
        
        result = adapter._remove_bot_mention(content, mentions)
        
        assert "<at" not in result
        assert "</at>" not in result
        assert "@机器人" not in result
        assert "你好，请帮我处理" in result

        placeholder_result = adapter._remove_bot_mention(
            "@_user_1 请帮我处理",
            [{"key": "@_user_1", "name": "机器人"}],
        )
        assert placeholder_result == "请帮我处理"

    @pytest.mark.asyncio
    async def test_handle_message_deduplicates_same_feishu_message_id(self):
        """Test duplicate inbound Feishu events are ignored by raw message_id."""
        from src.channel.adapters.feishu import FeishuChannelAdapter

        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )

        event_dict = {
            "event": {
                "message": {
                    "message_id": "msg_dedup_001",
                    "chat_id": "chat_001",
                    "chat_type": "p2p",
                }
            }
        }

        envelope = Envelope.create_chat(
            content="你好",
            session_id="feishu_chat_001",
            channel_type=ChannelType.FEISHU,
            channel_protocol=ChannelProtocol.STREAM,
            user_id="ou_123",
            channel_id="test-channel",
            peer_id="chat_001",
            peer_kind="user",
            metadata={"feishu_message_id": "msg_dedup_001"},
        )

        adapter._parse_event = MagicMock(return_value=event_dict)
        adapter.to_envelope = AsyncMock(return_value=envelope)
        adapter._process_stream_response = AsyncMock()
        adapter._dispatcher_factory = MagicMock(return_value=MagicMock())

        await adapter._handle_message(object())
        await adapter._handle_message(object())

        assert adapter.to_envelope.await_count == 1
        adapter._process_stream_response.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_render_response_text_chunk(self):
        """Test render_response for TEXT_CHUNK event."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event = GatewayEvent.text_chunk("流式文本", agent_name="Main Agent")
        result = await adapter.render_response(event)

        assert result["msg_type"] == "interactive"
        content = json.loads(result["content"])
        assert content["schema"] == "2.0"
        assert content["config"]["update_multi"] is True
        assert content["header"]["title"]["content"] == "Main Agent"
        assert content["header"]["subtitle"]["content"] == "正在生成"
        assert content["body"]["elements"][0]["tag"] == "markdown"
        assert "流式文本" in content["body"]["elements"][0]["content"]

    @pytest.mark.asyncio
    async def test_render_response_message_end(self):
        """Test render_response for MESSAGE_END event."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event = GatewayEvent.message_end("完整消息", agent_name="Main Agent")
        result = await adapter.render_response(event)

        assert result["msg_type"] == "interactive"
        content = json.loads(result["content"])
        assert content["header"]["title"]["content"] == "Main Agent"
        assert content["header"]["subtitle"]["content"] == "已完成"
        assert "完整消息" in content["body"]["elements"][0]["content"]

    @pytest.mark.asyncio
    async def test_render_response_error(self):
        """Test render_response for ERROR event."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        event = GatewayEvent.error("出错了", error_type="TestError", agent_name="Main Agent")
        result = await adapter.render_response(event)

        assert result["msg_type"] == "interactive"
        content = json.loads(result["content"])
        assert content["header"]["title"]["content"] == "Main Agent"
        assert content["header"]["subtitle"]["content"] == "处理失败"
        assert content["header"]["template"] == "red"
        assert "❌ 出错了" in content["body"]["elements"][0]["content"]

    def test_build_card_content_respects_size_limit(self):
        """Test interactive card content is truncated to Feishu size limit."""
        from src.channel.adapters.feishu import FeishuChannelAdapter

        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )

        long_content = "内容" * 20000
        content = adapter._build_card_content(
            long_content,
            title="Main Agent",
            status="已完成",
        )

        assert len(content.encode("utf-8")) <= 30 * 1024
        payload = json.loads(content)
        assert payload["config"]["update_multi"] is True
        assert "已截断显示" in payload["body"]["elements"][0]["content"]

    @pytest.mark.asyncio
    async def test_send_message_uses_interactive_card_payload(self):
        """Test _send_message sends interactive card payloads."""
        from src.channel.adapters.feishu import FeishuChannelAdapter

        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )

        response = MagicMock()
        response.success.return_value = True
        response.data.message_id = "om_card_001"

        adapter._client = MagicMock()
        adapter._client.im.v1.message.create = MagicMock(return_value=response)

        async def immediate_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("src.channel.feishu.message_client.asyncio.to_thread", new=immediate_to_thread):
            message_id = await adapter._send_message(
                receive_id="ou_123",
                receive_id_type="open_id",
                content="hello streaming card",
                title="Main Agent",
                status="正在生成",
            )

        assert message_id == "om_card_001"
        request = adapter._client.im.v1.message.create.call_args.kwargs["request"]
        assert request.body.msg_type == "interactive"
        payload = json.loads(request.body.content)
        assert payload["schema"] == "2.0"
        assert payload["config"]["update_multi"] is True
        assert payload["header"]["title"]["content"] == "Main Agent"

    @pytest.mark.asyncio
    async def test_start_creates_ws_client(self):
        """Test start() creates WebSocket client (non-blocking)."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        # Mock lark_oapi 模块
        mock_lark = MagicMock()
        mock_client = MagicMock()
        mock_lark.Client.builder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = mock_client
        
        mock_ws_client = MagicMock()
        mock_ws_client.start = MagicMock()  # 同步方法
        mock_ws_client.on = MagicMock()
        
        with patch.dict(
            "sys.modules",
            {"lark_oapi": mock_lark, "lark_oapi.ws": MagicMock(Client=MagicMock(return_value=mock_ws_client))},
        ):
            await adapter.start()
            
            # 验证 running 状态
            assert adapter._running is True
            assert adapter._ws_client is not None
            assert adapter._ws_task is not None
            
            # 清理
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_stop_cleanup(self):
        """Test stop() correctly cleans up resources."""
        from src.channel.adapters.feishu import FeishuChannelAdapter
        
        adapter = FeishuChannelAdapter(
            channel_id="test-channel",
            app_id="app_id",
            app_secret="secret",
            dispatcher_factory=lambda: MagicMock(),
        )
        
        # Mock lark_oapi 模块
        mock_lark = MagicMock()
        mock_client = MagicMock()
        mock_lark.Client.builder.return_value.app_id.return_value.app_secret.return_value.log_level.return_value.build.return_value = mock_client
        
        mock_ws_client = MagicMock()
        mock_ws_client.start = MagicMock()
        mock_ws_client.stop = MagicMock()
        mock_ws_client.on = MagicMock()
        
        with patch.dict(
            "sys.modules",
            {"lark_oapi": mock_lark, "lark_oapi.ws": MagicMock(Client=MagicMock(return_value=mock_ws_client))},
        ):
            await adapter.start()
            await adapter.stop()
            
            # 验证资源清理
            assert adapter._running is False
            mock_ws_client.stop.assert_called_once()


# =============================================================================
# TestChannelAdapterFactory
# =============================================================================


class TestChannelAdapterFactory:
    """Tests for create_channel_adapter factory function."""

    def test_create_dingtalk_adapter(self):
        """Test factory creates DingtalkChannelAdapter."""
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            config = ChannelConfig(
                id="dingtalk-channel",
                type="dingtalk",
                protocol="stream",
                enabled=True,
                config={
                    "app_key": "test_key",
                    "app_secret": "test_secret",
                },
            )
            
            adapter = create_channel_adapter(config, lambda: MagicMock())
            
            assert adapter is not None
            assert adapter.channel_type == ChannelType.DINGTALK

    def test_create_feishu_adapter(self):
        """Test factory creates FeishuChannelAdapter."""
        config = ChannelConfig(
            id="feishu-channel",
            type="feishu",
            protocol="stream",
            enabled=True,
            config={
                "app_id": "test_app_id",
                "app_secret": "test_app_secret",
            },
        )
        
        adapter = create_channel_adapter(config, lambda: MagicMock())
        
        assert adapter is not None
        assert adapter.channel_type == ChannelType.FEISHU

    def test_disabled_channel_returns_none(self):
        """Test enabled=False returns None."""
        config = ChannelConfig(
            id="disabled-channel",
            type="dingtalk",
            protocol="stream",
            enabled=False,
            config={
                "app_key": "test_key",
                "app_secret": "test_secret",
            },
        )
        
        adapter = create_channel_adapter(config, lambda: MagicMock())
        
        assert adapter is None

    def test_unknown_type_returns_none(self):
        """Test unknown type returns None."""
        config = ChannelConfig(
            id="unknown-channel",
            type="unknown_platform",
            protocol="stream",
            enabled=True,
            config={},
        )
        
        adapter = create_channel_adapter(config, lambda: MagicMock())
        
        assert adapter is None

    def test_missing_config_keys(self):
        """Test handling of missing configuration keys."""
        config = ChannelConfig(
            id="incomplete-channel",
            type="dingtalk",
            protocol="stream",
            enabled=True,
            config={},  # 缺少 app_key 和 app_secret
        )
        
        with patch("src.channel.adapters.dingtalk.dingtalk_stream") as mock_dingtalk:
            mock_dingtalk.DingTalkStreamClient = MagicMock
            mock_dingtalk.Credential = MagicMock
            mock_dingtalk.ChatbotMessage = MagicMock
            mock_dingtalk.AckMessage = MagicMock
            mock_dingtalk.AIMarkdownCardInstance = MagicMock
            
            # 应该创建成功，但配置为空字符串
            adapter = create_channel_adapter(config, lambda: MagicMock())
            
            assert adapter is not None
            assert adapter._app_key == ""
            assert adapter._app_secret == ""


# =============================================================================
# TestChannelRegistry
# =============================================================================


class TestChannelRegistry:
    """Tests for ChannelRegistry."""

    def test_register_and_get(self):
        """Test registering and getting an adapter."""
        registry = ChannelRegistry()
        mock_adapter = MagicMock()
        mock_adapter.channel_type = ChannelType.DINGTALK
        
        registry.register("channel-1", mock_adapter)
        
        assert registry.get("channel-1") is mock_adapter
        assert registry.get("non-existent") is None

    def test_register_duplicate_raises(self):
        """Test registering duplicate channel_id raises ValueError."""
        registry = ChannelRegistry()
        mock_adapter = MagicMock()
        mock_adapter.channel_type = ChannelType.DINGTALK
        
        registry.register("channel-1", mock_adapter)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register("channel-1", MagicMock())

    def test_list_channels(self):
        """Test listing registered channel IDs."""
        registry = ChannelRegistry()
        mock_adapter1 = MagicMock()
        mock_adapter2 = MagicMock()
        
        registry.register("channel-1", mock_adapter1)
        registry.register("channel-2", mock_adapter2)
        
        channels = registry.list_channels()
        
        assert len(channels) == 2
        assert "channel-1" in channels
        assert "channel-2" in channels

    @pytest.mark.asyncio
    async def test_start_all(self):
        """Test starting all channels in parallel."""
        registry = ChannelRegistry()
        
        mock_adapter1 = MagicMock()
        mock_adapter1.start = AsyncMock()
        mock_adapter2 = MagicMock()
        mock_adapter2.start = AsyncMock()
        
        registry.register("channel-1", mock_adapter1)
        registry.register("channel-2", mock_adapter2)
        
        await registry.start_all()
        
        mock_adapter1.start.assert_called_once()
        mock_adapter2.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all(self):
        """Test stopping all channels in parallel."""
        registry = ChannelRegistry()
        
        mock_adapter1 = MagicMock()
        mock_adapter1.stop = AsyncMock()
        mock_adapter2 = MagicMock()
        mock_adapter2.stop = AsyncMock()
        
        registry.register("channel-1", mock_adapter1)
        registry.register("channel-2", mock_adapter2)
        
        await registry.stop_all()
        
        mock_adapter1.stop.assert_called_once()
        mock_adapter2.stop.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
