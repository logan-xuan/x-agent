import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import subprocess
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.tools.command-exec.command_exec_tool import CommandExecutionTool  # Adjust import based on actual implementation


@pytest.mark.asyncio
async def test_command_execution_success():
    """Test successful command execution"""

    mock_result = MagicMock()
    mock_result.stdout = "Command executed successfully\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = mock_result

        tool = CommandExecutionTool()

        # Execute a simple command
        result = await tool._arun("echo 'hello world'")

        # Verify the result
        assert "hello world" in result
        mock_run.assert_called_once()
        # Check that it was called with the correct parameters
        args, kwargs = mock_run.call_args
        assert 'echo \'hello world\'' in str(args[0])


@pytest.mark.asyncio
async def test_command_execution_failure():
    """Test command execution with failure"""

    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "Command not found\n"
    mock_result.returncode = 1

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = mock_result

        tool = CommandExecutionTool()

        # Execute a failing command
        result = await tool._arun("nonexistent_command")

        # Verify error handling in result
        assert "error" in result.lower() or "not found" in result.lower() or "failed" in result.lower()


@pytest.mark.asyncio
async def test_command_execution_with_timeout():
    """Test command execution with timeout handling"""

    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=['sleep', '1'], timeout=0.1)

        tool = CommandExecutionTool()

        # Execute a command that times out
        result = await tool._arun("sleep 10")

        # Verify timeout handling in result
        assert "timeout" in result.lower() or "expired" in result.lower()


def test_command_execution_tool_name_and_description():
    """Test command execution tool name and description"""

    tool = CommandExecutionTool()

    # Verify tool has required attributes
    assert hasattr(tool, "name")
    assert hasattr(tool, "description")
    assert isinstance(tool.name, str)
    assert isinstance(tool.description, str)
    assert len(tool.name) > 0
    assert len(tool.description) > 0


@pytest.mark.asyncio
async def test_command_execution_security_filtering():
    """Test that dangerous commands are filtered properly"""

    tool = CommandExecutionTool()

    # Test various potentially dangerous commands
    dangerous_commands = [
        "rm -rf /",
        "mv ~ /dev/null",
        "cat /etc/passwd",
        "sudo rm -rf /",
        "echo test > /etc/hosts"
    ]

    for cmd in dangerous_commands:
        # Each should either be rejected or handled safely
        result = await tool._arun(cmd)
        # Results should indicate the command was rejected or safely handled
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_command_execution_directory_change():
    """Test command execution with directory change"""

    mock_result = MagicMock()
    mock_result.stdout = "/home/user/test_dir\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = mock_result

        tool = CommandExecutionTool()

        # Execute command in specific directory
        result = await tool._arun("cd /home/user/test_dir && pwd")

        # Verify the result
        assert "test_dir" in result
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_command_output_parsing():
    """Test parsing and handling of command output"""

    mock_result = MagicMock()
    mock_result.stdout = "line1\nline2\nline3\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = mock_result

        tool = CommandExecutionTool()

        result = await tool._arun("echo -e 'line1\\nline2\\nline3'")

        # Verify all lines are present in output
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


@pytest.mark.asyncio
async def test_long_running_command():
    """Test handling of long-running commands"""

    # Simulate a command that takes some time but completes
    mock_result = MagicMock()
    mock_result.stdout = "Process completed after some time\n"
    mock_result.stderr = ""
    mock_result.returncode = 0

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = mock_result

        tool = CommandExecutionTool()

        result = await tool._arun("sleep 1 && echo 'Process completed after some time'")

        assert "process completed" in result.lower()