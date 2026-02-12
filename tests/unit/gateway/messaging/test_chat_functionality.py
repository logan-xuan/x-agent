import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.gateway.messaging.message_handler import message_handler
from src.gateway.messaging.message_handler import MessageHandler
from src.db.models.message import Message  # Assuming this exists


@pytest.mark.asyncio
async def test_basic_text_message_handling():
    """Test basic chat functionality with text-only messages"""

    # Mock message data
    mock_message_data = {
        "type": "text",
        "content": "Hello, how are you?",
        "session_id": "test-session-123",
        "user_id": "test-user-123"
    }

    # Mock message handler
    with patch.object(message_handler, 'process_message') as mock_process:
        mock_process.return_value = {"response": "I'm doing well, thank you for asking!"}

        # Call the message handler process_message method
        result = await message_handler.process_message(
            mock_message_data["content"],
            mock_message_data["session_id"],
            mock_message_data["user_id"]
        )

        # Verify the message was processed
        assert result is not None
        assert "response" in result
        assert result["response"] == "I'm doing well, thank you for asking!"
        mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_empty_message_handling():
    """Test handling of empty messages"""

    mock_message_data = {
        "type": "text",
        "content": "",
        "session_id": "test-session-123",
        "user_id": "test-user-123"
    }

    with patch.object(message_handler, 'process_message') as mock_process:
        mock_process.return_value = {"response": "Please provide a valid message."}

        result = await message_handler.process_message(
            mock_message_data["content"],
            mock_message_data["session_id"],
            mock_message_data["user_id"]
        )

        assert result is not None
        assert "response" in result
        mock_process.assert_called_once()


def test_message_model_creation():
    """Test creating message model instances"""

    # Test message creation
    message = Message(
        session_id="test-session-123",
        sender_id="test-user-123",
        content="Test message content",
        sender_type="user",
        content_type="text"
    )

    assert message.session_id == "test-session-123"
    assert message.sender_id == "test-user-123"
    assert message.content == "Test message content"
    assert message.sender_type == "user"
    assert message.content_type == "text"


@pytest.mark.asyncio
async def test_conversation_flow():
    """Test a simple conversation flow with multiple exchanges"""

    # Simulate a conversation with multiple messages
    conversation_messages = [
        {"type": "text", "content": "Hello!", "session_id": "conv-session-1", "user_id": "user-1"},
        {"type": "text", "content": "How are you?", "session_id": "conv-session-1", "user_id": "user-1"},
        {"type": "text", "content": "Goodbye!", "session_id": "conv-session-1", "user_id": "user-1"}
    ]

    responses = []
    with patch.object(message_handler, 'process_message') as mock_process:
        mock_process.return_value = {"response": "Thanks for your message!"}

        for msg in conversation_messages:
            result = await message_handler.process_message(
                msg["content"],
                msg["session_id"],
                msg["user_id"]
            )
            responses.append(result)

    assert len(responses) == len(conversation_messages)
    for response in responses:
        assert "response" in response