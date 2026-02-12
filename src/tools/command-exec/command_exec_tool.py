import subprocess
import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from .base_tool import BaseTool


class CommandExecutionToolArgs(BaseModel):
    command: str = Field(description="The command to execute")
    timeout: int = Field(default=30, description="Timeout in seconds")


class CommandExecutionTool(BaseTool):
    """Tool for executing shell commands safely with security restrictions."""

    def __init__(self):
        super().__init__(
            name="command-exec",
            description="Execute a shell command in a secure environment",
            args_schema=CommandExecutionToolArgs
        )

    def _run(self, command: str, timeout: int = 30, **kwargs) -> str:
        """
        Execute a shell command with security checks.

        Args:
            command: The command to execute
            timeout: Timeout in seconds (default 30)

        Returns:
            Command execution result as a string
        """
        try:
            # Security validation
            if not self._is_safe_command(command):
                return f"Error: Command '{command}' contains unsafe elements and is not allowed."

            # Execute the command in a subprocess
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()  # Execute in current working directory
            )

            # Format the result
            output_parts = []

            if result.stdout:
                output_parts.append(f"Output:\n{result.stdout}")

            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr}")

            if result.returncode != 0:
                output_parts.append(f"Return code: {result.returncode}")

            if not output_parts:
                output_parts.append("Command executed successfully (no output)")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds."
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def _is_safe_command(self, command: str) -> bool:
        """
        Check if the command is safe to execute based on security policies.

        Args:
            command: The command to validate

        Returns:
            True if the command is safe, False otherwise
        """
        # Convert command to lowercase for easier comparison
        cmd_lower = command.lower()

        # Define dangerous command patterns
        dangerous_patterns = [
            # File system manipulation
            "rm -rf", "rm -fr", "mv /", "dd if=", ">/dev/", "> /dev/",

            # System modification
            "sudo ", "su ", "chmod ", "chown ", "mount ", "umount ",

            # Network scanning/exploitation
            "nmap ", "nc ", "netcat ", "ssh ", "scp ",

            # Process manipulation
            "kill -9", "pkill ", "killall ",

            # Dangerous scripting
            "<(/)", "eval ", "exec ",

            # File system access to sensitive areas
            "/etc/", "/root/", "/proc/", "/sys/", "/boot/",

            # Shell manipulation
            "export ", "alias ", "function ",

            # Command substitution
            "$(", "`", "$(cat",
        ]

        # Check if the command contains any dangerous patterns
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return False

        # Additional check for file system access to sensitive areas
        dangerous_paths = ["/etc", "/root", "/proc", "/sys", "/home", "/var/log"]
        for path in dangerous_paths:
            if f"{path}/" in command or f"{path} " in command:
                return False

        # Check for attempts to escape to a shell
        if any(char in command for char in [';', '&', '|', '`', '$(']):
            # Allow some safe uses but block obvious shell escapes
            if any(dangerous in command for dangerous in ['&&rm', '||rm', ';rm', '|rm']):
                return False

        # If all checks pass, the command is considered safe
        return True