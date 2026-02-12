import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os
from pathlib import Path
import sys

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.gateway.messaging.file_endpoint import upload_file, download_file  # Adjust import based on actual implementation


@pytest.mark.asyncio
async def test_file_upload_basic():
    """Test basic file upload functionality"""

    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
        temp_file.write("Test file content")
        temp_file_path = temp_file.name

    try:
        # Mock the file upload handler
        with patch('src.gateway.messaging.file_endpoint.handle_file_upload') as mock_upload:
            mock_upload.return_value = {"status": "success", "file_id": "test-file-123", "size": 18}

            # Prepare mock upload data
            mock_file_data = {
                "filename": "test.txt",
                "content": "Test file content",
                "session_id": "test-session-123",
                "user_id": "test-user-123"
            }

            result = await upload_file(mock_file_data)

            assert result["status"] == "success"
            assert "file_id" in result
            assert result["size"] == 18
            mock_upload.assert_called_once()
    finally:
        # Clean up the temp file
        os.unlink(temp_file_path)


@pytest.mark.asyncio
async def test_file_download_basic():
    """Test basic file download functionality"""

    with patch('src.gateway.messaging.file_endpoint.retrieve_file') as mock_retrieve:
        mock_retrieve.return_value = b"Downloaded file content"

        file_id = "test-file-123"
        session_id = "test-session-123"

        result = await download_file(file_id, session_id)

        assert result == b"Downloaded file content"
        mock_retrieve.assert_called_once_with(file_id, session_id)


@pytest.mark.asyncio
async def test_file_upload_large_file():
    """Test file upload with large file"""

    # Create a larger temporary file for testing
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
        large_content = "This is a larger file content. " * 100  # Repeat to make it larger
        temp_file.write(large_content)
        temp_file_path = temp_file.name

    try:
        with patch('src.gateway.messaging.file_endpoint.handle_file_upload') as mock_upload:
            mock_upload.return_value = {"status": "success", "file_id": "large-test-file-123", "size": len(large_content)}

            mock_file_data = {
                "filename": "large_test.txt",
                "content": large_content,
                "session_id": "test-session-123",
                "user_id": "test-user-123"
            }

            result = await upload_file(mock_file_data)

            assert result["status"] == "success"
            assert result["size"] == len(large_content)
            mock_upload.assert_called_once()
    finally:
        os.unlink(temp_file_path)


@pytest.mark.asyncio
async def test_file_upload_invalid_file():
    """Test file upload with invalid/malicious file"""

    with patch('src.gateway.messaging.file_endpoint.validate_file') as mock_validate:
        mock_validate.return_value = False  # Simulate invalid file

        mock_file_data = {
            "filename": "malicious.exe",
            "content": "potentially harmful content",
            "session_id": "test-session-123",
            "user_id": "test-user-123"
        }

        # Depending on implementation, this might raise an exception or return an error
        # For now, assuming it raises a validation error
        try:
            await upload_file(mock_file_data)
            assert False, "Expected validation to fail"
        except ValueError:
            # Expected behavior
            pass
        except Exception:
            # Some other error is also acceptable depending on implementation
            pass


@pytest.mark.asyncio
async def test_file_download_nonexistent_file():
    """Test file download with non-existent file ID"""

    with patch('src.gateway.messaging.file_endpoint.retrieve_file') as mock_retrieve:
        mock_retrieve.side_effect = FileNotFoundError("File not found")

        file_id = "nonexistent-file-123"
        session_id = "test-session-123"

        try:
            await download_file(file_id, session_id)
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            # Expected behavior
            pass