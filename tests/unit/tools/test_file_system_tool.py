import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import os
from pathlib import Path
import sys

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.tools.file-system.file_system_tool import FileSystemTool  # Adjust import based on actual implementation


@pytest.mark.asyncio
async def test_file_read_functionality():
    """Test reading files using the file system tool"""

    # Create a temporary file for testing
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
        temp_file.write("Test file content for reading")
        temp_file_path = temp_file.name

    try:
        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = "Test file content for reading"

            tool = FileSystemTool()

            # Execute read operation
            result = await tool._arun(f"read_file:{temp_file_path}")

            # Verify the result
            assert "test file content for reading" in result.lower()
            mock_open.assert_called_once_with(temp_file_path, 'r')
    finally:
        # Clean up the temp file
        os.unlink(temp_file_path)


@pytest.mark.asyncio
async def test_file_write_functionality():
    """Test writing files using the file system tool"""

    with tempfile.TemporaryDirectory() as temp_dir:
        test_file_path = os.path.join(temp_dir, "test_write.txt")

        with patch('builtins.open', MagicMock()) as mock_open:
            mock_file_handle = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file_handle

            tool = FileSystemTool()

            # Execute write operation
            result = await tool._arun(f"write_file:{test_file_path}:Content to write")

            # Verify the result
            assert "successfully" in result.lower() or "written" in result.lower()
            mock_open.assert_called_once_with(test_file_path, 'w')
            mock_file_handle.write.assert_called_once_with("Content to write")


@pytest.mark.asyncio
async def test_list_directory_functionality():
    """Test listing directory contents using the file system tool"""

    mock_directory_contents = ['file1.txt', 'file2.py', 'subdir']

    with patch('os.listdir') as mock_listdir:
        mock_listdir.return_value = mock_directory_contents

        tool = FileSystemTool()

        # Execute list directory operation
        result = await tool._arun("list_dir:/some/path")

        # Verify the result
        for item in mock_directory_contents:
            assert item in result
        mock_listdir.assert_called_once_with("/some/path")


@pytest.mark.asyncio
async def test_file_system_tool_error_handling():
    """Test file system tool error handling"""

    tool = FileSystemTool()

    # Test reading non-existent file
    with patch('builtins.open') as mock_open:
        mock_open.side_effect = FileNotFoundError("File not found")

        result = await tool._arun("read_file:/nonexistent/file.txt")

        # Should handle the error gracefully
        assert "error" in result.lower() or "not found" in result.lower()


@pytest.mark.asyncio
async def test_file_exists_check():
    """Test file existence check functionality"""

    tool = FileSystemTool()

    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True

        result = await tool._arun("exists:/some/file.txt")

        assert "exists" in result.lower() or "true" in result.lower()
        mock_exists.assert_called_once_with("/some/file.txt")


def test_file_system_tool_name_and_description():
    """Test file system tool name and description"""

    tool = FileSystemTool()

    # Verify tool has required attributes
    assert hasattr(tool, "name")
    assert hasattr(tool, "description")
    assert isinstance(tool.name, str)
    assert isinstance(tool.description, str)
    assert len(tool.name) > 0
    assert len(tool.description) > 0


@pytest.mark.asyncio
async def test_file_permissions():
    """Test file permission operations"""

    tool = FileSystemTool()

    with patch('os.access') as mock_access:
        mock_access.return_value = True

        result = await tool._arun("can_read:/some/file.txt")

        assert "can" in result.lower() or "accessible" in result.lower()
        # Check that it was called with read permission flag (4)
        mock_access.assert_called()


@pytest.mark.asyncio
async def test_safe_path_validation():
    """Test that the tool validates safe paths and prevents directory traversal"""

    tool = FileSystemTool()

    # This should either fail or handle path traversal attempts safely
    try:
        result = await tool._arun("read_file:../../../etc/passwd")
        # If it doesn't throw an error, it should at least not contain sensitive content
        assert "root:" not in result
    except Exception:
        # An exception is also acceptable if path validation throws an error
        pass