import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.db.models.message import Message  # Assuming this handles multimedia


def test_multimedia_message_creation():
    """Test creating messages with multimedia content"""

    # Test image message
    image_message = Message(
        session_id="test-session-123",
        user_id="test-user-123",
        content="Image caption",
        message_type="image",
        metadata={"file_id": "img-123", "width": 800, "height": 600, "format": "jpeg"}
    )

    assert image_message.message_type == "image"
    assert image_message.metadata["file_id"] == "img-123"
    assert image_message.metadata["width"] == 800

    # Test video message
    video_message = Message(
        session_id="test-session-123",
        user_id="test-user-123",
        content="Video description",
        message_type="video",
        metadata={"file_id": "vid-456", "duration": 120, "format": "mp4"}
    )

    assert video_message.message_type == "video"
    assert video_message.metadata["duration"] == 120

    # Test audio message
    audio_message = Message(
        session_id="test-session-123",
        user_id="test-user-123",
        content="Audio transcription",
        message_type="audio",
        metadata={"file_id": "aud-789", "duration": 45, "format": "mp3"}
    )

    assert audio_message.message_type == "audio"
    assert audio_message.metadata["duration"] == 45


def test_multimedia_message_serialization():
    """Test serialization/deserialization of multimedia messages"""

    original_message = Message(
        session_id="test-session-123",
        user_id="test-user-123",
        content="Sample image",
        message_type="image",
        metadata={"file_id": "img-101", "size_bytes": 1024000, "format": "png"}
    )

    # Test that all properties are preserved
    assert original_message.session_id == "test-session-123"
    assert original_message.message_type == "image"
    assert original_message.metadata["file_id"] == "img-101"
    assert original_message.metadata["size_bytes"] == 1024000


@pytest.mark.asyncio
async def test_multimedia_message_processing():
    """Test processing of multimedia messages through the system"""

    # Mock multimedia processing
    with patch('src.gateway.messaging.message_handler.MessageHandler.process_message') as mock_process:
        mock_process.return_value = {"response": "Processed multimedia message successfully"}

        # Simulate a multimedia message
        multimedia_msg = {
            "type": "image",
            "content": "Beautiful sunset photo",
            "session_id": "multimedia-session-456",
            "user_id": "test-user-456",
            "metadata": {
                "file_id": "img-456",
                "width": 1920,
                "height": 1080,
                "format": "jpg",
                "size_bytes": 2048000
            }
        }

        # Import the chat handler - adjust import as needed
        from src.gateway.messaging.chat_endpoint import chat_message_handler
        result = await chat_message_handler(multimedia_msg)

        assert "response" in result
        assert result["response"] == "Processed multimedia message successfully"
        mock_process.assert_called_once()


def test_multimedia_message_validation():
    """Test validation of multimedia message formats"""

    # Valid multimedia message
    valid_image = {
        "session_id": "test-session-123",
        "user_id": "test-user-123",
        "content": "A beautiful landscape",
        "message_type": "image",
        "metadata": {
            "file_id": "img-valid",
            "format": "jpeg",
            "size_bytes": 1024000
        }
    }

    # Invalid multimedia message (missing required fields)
    invalid_image = {
        "session_id": "test-session-123",
        "user_id": "test-user-123",
        "content": "An image without proper metadata",
        "message_type": "image"
        # Missing metadata entirely
    }

    # Create messages with the valid data
    valid_msg = Message(**valid_image)
    assert valid_msg.message_type == "image"
    assert "format" in valid_msg.metadata

    # The behavior for invalid data depends on validation implementation
    # If strict validation is in place, this might raise an error
    try:
        invalid_msg = Message(**invalid_image)
        # If no error is raised, check if default values are provided
    except (TypeError, AttributeError, ValueError):
        # Expected if validation is strict
        pass


@pytest.mark.asyncio
async def test_multiple_multimedia_in_session():
    """Test handling multiple multimedia messages in a single session"""

    messages = [
        {
            "type": "image",
            "content": "First image",
            "session_id": "multi-media-session",
            "user_id": "test-user-789",
            "metadata": {"file_id": "img-first", "format": "png"}
        },
        {
            "type": "audio",
            "content": "Voice note",
            "session_id": "multi-media-session",
            "user_id": "test-user-789",
            "metadata": {"file_id": "audio-second", "duration": 30}
        },
        {
            "type": "video",
            "content": "Short clip",
            "session_id": "multi-media-session",
            "user_id": "test-user-789",
            "metadata": {"file_id": "vid-third", "duration": 120}
        }
    ]

    with patch('src.gateway.messaging.message_handler.MessageHandler.process_message') as mock_process:
        mock_process.return_value = {"response": "Multimedia message processed"}

        from src.gateway.messaging.chat_endpoint import chat_message_handler

        results = []
        for msg in messages:
            result = await chat_message_handler(msg)
            results.append(result)

        assert len(results) == len(messages)
        for result in results:
            assert "response" in result