"""Terminal/CLI execution tools for X-Agent.

Provides tools for:
- Executing shell commands
- Running background processes
- Checking terminal output
- Managing running processes

Security features:
- Command blacklist to block dangerous commands (configurable via x-agent.yaml)
- Audit logging for all executed commands
- Working directory restriction
- Timeout protection
"""

import asyncio
import shlex
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult, ToolParameter, ToolParameterType
from ...utils.logger import get_logger

logger = get_logger(__name__)


def _get_tools_config():
    """Get tools configuration from config manager.
    
    Returns:
        ToolsConfig instance or None if config not available
    """
    try:
        from ...config.manager import ConfigManager
        return ConfigManager().config.tools
    except Exception:
        return None


# Commands that require special handling (always blocked)
SENSITIVE_COMMANDS = {
    "sudo",
    "su",
    "passwd",
    "chpasswd",
}


class RunInTerminalTool(BaseTool):
    """Tool to execute shell commands in the terminal.
    
    Executes shell commands and returns their output. Supports both
    foreground (blocking) and background execution modes.
    
    Security features:
    - Blacklist blocks dangerous commands (rm, dd, etc.)
    - All commands are logged for audit
    - Timeout protection prevents hanging
    - Working directory can be restricted
    """
    
    def __init__(
        self,
        blacklist: set[str] | None = None,
        default_timeout: int = 60,
        allowed_working_dirs: list[str] | None = None,
    ) -> None:
        """Initialize the terminal tool.
        
        Args:
            blacklist: Set of forbidden commands (uses DEFAULT_BLACKLIST if None)
            default_timeout: Default command timeout in seconds
            allowed_working_dirs: List of allowed working directories (None = any)
        """
        # Get blacklist from config, fallback to provided value or default
        config = _get_tools_config()
        if config and hasattr(config, 'terminal_blacklist'):
            config_blacklist = set(config.terminal_blacklist)
        else:
            # Default dangerous commands
            config_blacklist = {
                "rm", "dd", "mkfs", "fdisk", "format", "shutdown",
                "reboot", "poweroff", "halt", "init", "systemctl",
                "service", "sudo", "su", "passwd", "chpasswd"
            }

        self.blacklist = blacklist or config_blacklist
        self.default_timeout = default_timeout
        self.allowed_working_dirs = allowed_working_dirs
        self._background_processes: dict[str, asyncio.subprocess.Process] = {}
    
    @property
    def name(self) -> str:
        return "run_in_terminal"
    
    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the terminal. "
            "Returns the command output. "
            "Common use cases: listing files (ls), searching (grep), "
            "file operations (cp, mv, mkdir), git commands, npm/yarn/pip operations, "
            "running scripts. "
            "Dangerous commands like 'rm' are blocked for safety."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="command",
                type=ToolParameterType.STRING,
                description="The shell command to execute (e.g., 'ls -la', 'git status', 'npm install')",
                required=True,
            ),
            ToolParameter(
                name="working_dir",
                type=ToolParameterType.STRING,
                description="Working directory for the command. Defaults to current directory.",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="timeout",
                type=ToolParameterType.INTEGER,
                description="Timeout in seconds. Defaults to 60 seconds.",
                required=False,
                default=60,
            ),
            ToolParameter(
                name="is_background",
                type=ToolParameterType.BOOLEAN,
                description="Run in background (non-blocking). Returns a process ID to check later.",
                required=False,
                default=False,
            ),
        ]
    
    def _extract_command(self, command: str) -> str:
        """Extract the base command from a command string.
        
        Args:
            command: Full command string
            
        Returns:
            Base command name
        """
        # Handle command chains (&&, ||, ;)
        for separator in ["&&", "||", ";"]:
            if separator in command:
                command = command.split(separator)[0]
        
        # Parse the command
        try:
            parts = shlex.split(command.strip())
            if not parts:
                return ""
            
            # Handle sudo/su prefix
            base_cmd = parts[0]
            if base_cmd in ("sudo", "su") and len(parts) > 1:
                base_cmd = parts[1]
            
            # Remove path prefix if present
            return Path(base_cmd).name
        except ValueError:
            # If shlex fails, simple split
            return command.strip().split()[0] if command.strip() else ""
    
    def _is_command_allowed(self, command: str) -> tuple[bool, str | None]:
        """Check if a command is allowed to execute.
        
        Args:
            command: Command string to check
            
        Returns:
            Tuple of (is_allowed, error_message)
        """
        base_cmd = self._extract_command(command)
        
        if not base_cmd:
            return False, "Empty command"
        
        # Check blacklist
        if base_cmd in self.blacklist:
            return False, f"Command '{base_cmd}' is blocked for safety reasons"
        
        # Check sensitive commands
        if base_cmd in SENSITIVE_COMMANDS:
            return False, f"Command '{base_cmd}' requires elevated privileges and is blocked"
        
        return True, None
    
    def _validate_working_dir(self, working_dir: str) -> tuple[bool, str | None]:
        """Validate working directory is allowed.
        
        Args:
            working_dir: Working directory path
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.allowed_working_dirs is None:
            return True, None
        
        try:
            path = Path(working_dir).resolve()
            for allowed in self.allowed_working_dirs:
                allowed_path = Path(allowed).resolve()
                try:
                    path.relative_to(allowed_path)
                    return True, None
                except ValueError:
                    continue
            return False, f"Working directory '{working_dir}' is not in allowed paths"
        except Exception as e:
            return False, f"Invalid working directory: {str(e)}"
    
    async def execute(
        self,
        command: str,
        working_dir: str = ".",
        timeout: int = 60,
        is_background: bool = False,
    ) -> ToolResult:
        """Execute a shell command.
        
        Args:
            command: Shell command to execute
            working_dir: Working directory for the command
            timeout: Timeout in seconds
            is_background: Whether to run in background
            
        Returns:
            ToolResult with command output or error
        """
        # Validate command
        is_allowed, error = self._is_command_allowed(command)
        if not is_allowed:
            logger.warning(
                "Blocked command execution",
                extra={"command": command, "reason": error}
            )
            return ToolResult.error_result(error or "Command not allowed")
        
        # Validate working directory
        is_valid, error = self._validate_working_dir(working_dir)
        if not is_valid:
            return ToolResult.error_result(error or "Invalid working directory")
        
        # Resolve working directory
        try:
            cwd = Path(working_dir).expanduser().resolve()
            if not cwd.exists():
                return ToolResult.error_result(f"Working directory not found: {working_dir}")
            if not cwd.is_dir():
                return ToolResult.error_result(f"Not a directory: {working_dir}")
        except Exception as e:
            return ToolResult.error_result(f"Invalid working directory: {str(e)}")
        
        # Log command execution (audit trail)
        logger.info(
            "Executing terminal command",
            extra={
                "command": command,
                "working_dir": str(cwd),
                "is_background": is_background,
                "timeout": timeout,
            }
        )
        
        try:
            if is_background:
                return await self._execute_background(command, cwd)
            else:
                return await self._execute_foreground(command, cwd, timeout)
        
        except Exception as e:
            logger.error(
                "Command execution failed",
                extra={"command": command, "error": str(e)}
            )
            return ToolResult.error_result(f"Command execution failed: {str(e)}")
    
    async def _execute_foreground(
        self,
        command: str,
        cwd: Path,
        timeout: int,
    ) -> ToolResult:
        """Execute command in foreground (blocking).
        
        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds
            
        Returns:
            ToolResult with output
        """
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        
        try:
            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            
            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
            
            # Build result
            output_parts = []
            if stdout_str:
                output_parts.append(f"STDOUT:\n{stdout_str}")
            if stderr_str:
                output_parts.append(f"STDERR:\n{stderr_str}")
            
            output = "\n\n".join(output_parts) if output_parts else "Command completed with no output"
            
            # Truncate if too long
            max_length = 10000
            was_truncated = False
            if len(output) > max_length:
                output = output[:max_length] + f"\n\n... [truncated, {len(output)} total characters]"
                was_truncated = True
            
            success = process.returncode == 0
            
            logger.info(
                "Command completed",
                extra={
                    "returncode": process.returncode,
                    "stdout_length": len(stdout_str),
                    "stderr_length": len(stderr_str),
                }
            )
            
            if success:
                return ToolResult.ok(
                    output,
                    returncode=process.returncode,
                    truncated=was_truncated,
                )
            else:
                return ToolResult.error_result(
                    f"Command failed with exit code {process.returncode}\n\n{output}",
                    returncode=process.returncode,
                )
        
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning(
                "Command timed out",
                extra={"command": command, "timeout": timeout}
            )
            return ToolResult.error_result(
                f"Command timed out after {timeout} seconds",
                timeout=timeout,
            )
    
    async def _execute_background(
        self,
        command: str,
        cwd: Path,
    ) -> ToolResult:
        """Execute command in background (non-blocking).
        
        Args:
            command: Command to execute
            cwd: Working directory
            
        Returns:
            ToolResult with process ID
        """
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        
        # Generate process ID
        import uuid
        process_id = f"proc_{uuid.uuid4().hex[:8]}"
        self._background_processes[process_id] = process
        
        logger.info(
            "Background process started",
            extra={
                "process_id": process_id,
                "pid": process.pid,
                "command": command,
            }
        )
        
        return ToolResult.ok(
            f"Background process started with ID: {process_id}\nPID: {process.pid}",
            process_id=process_id,
            pid=process.pid,
        )


class GetTerminalOutputTool(BaseTool):
    """Tool to check output from a background terminal process.
    
    Retrieves the current output from a previously started background
    process without blocking.
    """
    
    def __init__(self, terminal_tool: RunInTerminalTool | None = None) -> None:
        """Initialize with reference to terminal tool.
        
        Args:
            terminal_tool: The RunInTerminalTool instance managing background processes
        """
        self._terminal_tool = terminal_tool
    
    @property
    def name(self) -> str:
        return "get_terminal_output"
    
    @property
    def description(self) -> str:
        return (
            "Get output from a background terminal process. "
            "Use this to check the progress or result of a command started with is_background=true."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="process_id",
                type=ToolParameterType.STRING,
                description="The process ID returned by run_in_terminal when running in background",
                required=True,
            ),
        ]
    
    async def execute(self, process_id: str) -> ToolResult:
        """Get output from a background process.
        
        Args:
            process_id: Process ID to check
            
        Returns:
            ToolResult with process output/status
        """
        if self._terminal_tool is None:
            return ToolResult.error_result("Terminal tool not available")
        
        process = self._terminal_tool._background_processes.get(process_id)
        if process is None:
            return ToolResult.error_result(f"Process not found: {process_id}")
        
        # Check if process has completed
        if process.returncode is not None:
            # Process completed, get final output
            stdout, stderr = await process.communicate()
            
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
            
            # Build result
            output_parts = []
            if stdout_str:
                output_parts.append(f"STDOUT:\n{stdout_str}")
            if stderr_str:
                output_parts.append(f"STDERR:\n{stderr_str}")
            
            output = "\n\n".join(output_parts) if output_parts else "Process completed with no output"
            
            # Clean up
            del self._terminal_tool._background_processes[process_id]
            
            if process.returncode == 0:
                return ToolResult.ok(
                    f"Process completed (exit code: {process.returncode})\n\n{output}",
                    returncode=process.returncode,
                    completed=True,
                )
            else:
                return ToolResult.error_result(
                    f"Process failed (exit code: {process.returncode})\n\n{output}",
                    returncode=process.returncode,
                    completed=True,
                )
        
        else:
            # Process still running
            return ToolResult.ok(
                f"Process {process_id} is still running (PID: {process.pid})",
                pid=process.pid,
                completed=False,
            )


class KillProcessTool(BaseTool):
    """Tool to kill a running background process.
    
    Terminates a process that was started in the background.
    """
    
    def __init__(self, terminal_tool: RunInTerminalTool | None = None) -> None:
        """Initialize with reference to terminal tool.
        
        Args:
            terminal_tool: The RunInTerminalTool instance managing background processes
        """
        self._terminal_tool = terminal_tool
    
    @property
    def name(self) -> str:
        return "kill_process"
    
    @property
    def description(self) -> str:
        return (
            "Kill a background process started with run_in_terminal. "
            "Use this to stop long-running commands like development servers."
        )
    
    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="process_id",
                type=ToolParameterType.STRING,
                description="The process ID returned by run_in_terminal",
                required=True,
            ),
        ]
    
    async def execute(self, process_id: str) -> ToolResult:
        """Kill a background process.
        
        Args:
            process_id: Process ID to kill
            
        Returns:
            ToolResult with kill result
        """
        if self._terminal_tool is None:
            return ToolResult.error_result("Terminal tool not available")
        
        process = self._terminal_tool._background_processes.get(process_id)
        if process is None:
            return ToolResult.error_result(f"Process not found: {process_id}")
        
        try:
            process.kill()
            await process.wait()
            
            # Clean up
            del self._terminal_tool._background_processes[process_id]
            
            logger.info(
                "Process killed",
                extra={"process_id": process_id, "pid": process.pid}
            )
            
            return ToolResult.ok(
                f"Process {process_id} (PID: {process.pid}) killed successfully",
                process_id=process_id,
                pid=process.pid,
            )
        
        except Exception as e:
            return ToolResult.error_result(f"Failed to kill process: {str(e)}")
