"""Terminal/CLI execution tools for X-Agent.

Provides tools for:
- Executing shell commands
- Running background processes
- Checking terminal output
- Managing running processes

Security features:
- Command blacklist to block dangerous commands (configurable via x-agent.yaml)
- High-risk command list requiring user confirmation
- Audit logging for all executed commands
- Working directory restriction
- Timeout protection
"""

import asyncio
import shlex
import uuid
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

# Global store for pending confirmations (tool_call_id -> command)
# This is used to verify that user has confirmed the command
_pending_confirmations: dict[str, dict[str, Any]] = {}


def generate_confirmation_id() -> str:
    """Generate a unique confirmation ID."""
    return f"confirm_{uuid.uuid4().hex[:12]}"


def store_pending_confirmation(confirmation_id: str, command: str, tool_call_id: str) -> None:
    """Store a pending confirmation for later verification."""
    _pending_confirmations[confirmation_id] = {
        "command": command,
        "tool_call_id": tool_call_id,
        "confirmed": False,
    }
    logger.info(
        "Stored pending confirmation",
        extra={"confirmation_id": confirmation_id, "command": command}
    )


def set_confirmation_confirmed(confirmation_id: str) -> bool:
    """Mark a confirmation as confirmed by user."""
    if confirmation_id in _pending_confirmations:
        _pending_confirmations[confirmation_id]["confirmed"] = True
        logger.info(
            "Confirmation marked as confirmed",
            extra={"confirmation_id": confirmation_id}
        )
        return True
    return False


def verify_and_consume_confirmation(confirmation_id: str, command: str) -> bool:
    """Verify and consume a confirmation.
    
    Returns True if the confirmation is valid and matches the command.
    The confirmation is consumed (removed) after verification.
    """
    if confirmation_id not in _pending_confirmations:
        logger.warning(
            "Confirmation not found",
            extra={"confirmation_id": confirmation_id}
        )
        return False
    
    pending = _pending_confirmations[confirmation_id]
    
    # Verify command matches
    if pending["command"] != command:
        logger.warning(
            "Confirmation command mismatch",
            extra={
                "confirmation_id": confirmation_id,
                "expected": pending["command"],
                "actual": command
            }
        )
        return False
    
    # Check if confirmed
    if not pending["confirmed"]:
        logger.warning(
            "Confirmation not yet approved by user",
            extra={"confirmation_id": confirmation_id}
        )
        return False
    
    # Consume the confirmation
    del _pending_confirmations[confirmation_id]
    logger.info(
        "Confirmation verified and consumed",
        extra={"confirmation_id": confirmation_id, "command": command}
    )
    return True


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
        default_timeout: int | None = None,
        allowed_working_dirs: list[str] | None = None,
        max_output_length: int | None = None,
    ) -> None:
        """Initialize the terminal tool.
        
        Args:
            blacklist: Set of forbidden commands (uses config or default if None)
            default_timeout: Default command timeout in seconds (uses config if None)
            allowed_working_dirs: List of allowed working directories (None = any)
            max_output_length: Maximum output length before truncation (uses config if None)
        """
        # Store override values (these take precedence over config)
        self._override_blacklist = blacklist
        self._override_timeout = default_timeout
        self._override_dirs = allowed_working_dirs
        self._override_max_output = max_output_length
        
        # Load initial config
        self._load_config()
        
        # Register for config changes
        self._register_config_callback()
        
        self._background_processes: dict[str, asyncio.subprocess.Process] = {}
    
    def _load_config(self) -> None:
        """Load configuration from ConfigManager."""
        config = _get_tools_config()
        
        # Use override values first, then config, then defaults
        if self._override_blacklist is not None:
            self.blacklist = self._override_blacklist
        elif config is not None:
            self.blacklist = set(config.terminal_blacklist)
        else:
            self.blacklist = {
                "rm", "dd", "mkfs", "fdisk", "format",
                "shutdown", "reboot", "poweroff", "halt", "init",
                "systemctl", "service",
            }
        
        if self._override_timeout is not None:
            self.default_timeout = self._override_timeout
        elif config is not None:
            self.default_timeout = config.terminal_timeout
        else:
            self.default_timeout = 60
        
        if self._override_dirs is not None:
            self.allowed_working_dirs = self._override_dirs
        elif config is not None and config.terminal_allowed_dirs:
            self.allowed_working_dirs = config.terminal_allowed_dirs
        else:
            self.allowed_working_dirs = None
        
        if self._override_max_output is not None:
            self.max_output_length = self._override_max_output
        elif config is not None:
            self.max_output_length = config.terminal_max_output
        else:
            self.max_output_length = 10000
        
        # Load high-risk commands list
        if config is not None:
            self.high_risk_commands = set(config.terminal_high_risk)
        else:
            # Default high-risk commands
            self.high_risk_commands = {
                "kill", "pkill", "killall",
                "docker", "kubectl", "helm", "terraform", "ansible-playbook",
                "pip", "npm", "yarn", "pnpm",
                "apt", "apt-get", "yum", "dnf", "pacman", "brew",
            }
        
        logger.info(
            "Terminal tool configuration loaded",
            extra={
                "blacklist_count": len(self.blacklist),
                "high_risk_count": len(self.high_risk_commands),
                "timeout": self.default_timeout,
                "max_output": self.max_output_length,
            }
        )
    
    def _register_config_callback(self) -> None:
        """Register callback for config hot-reload."""
        try:
            from ...config.manager import ConfigManager
            
            def on_config_change(new_config):
                logger.info("Config changed, reloading terminal tool settings")
                self._load_config()
            
            ConfigManager().on_change(on_config_change)
        except Exception as e:
            logger.debug(f"Could not register config callback: {e}")
    
    @property
    def name(self) -> str:
        return "run_in_terminal"
    
    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the terminal. "
            "Use this tool to perform file operations (delete, copy, move), run scripts, git commands, etc. "
            "IMPORTANT: Always call this tool directly when you need to execute a command. "
            "If a command requires user confirmation (e.g., rm, npm install), the system will automatically "
            "show a confirmation dialog to the user. Do NOT ask the user for confirmation yourself - "
            "just call the tool and the system will handle the confirmation flow."
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
            ToolParameter(
                name="confirmed",
                type=ToolParameterType.BOOLEAN,
                description="Set to true to confirm execution of high-risk commands (kill, docker, npm install, etc.)",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="confirmation_id",
                type=ToolParameterType.STRING,
                description="The confirmation ID received from previous high-risk command response. Required when confirmed=true.",
                required=False,
                default="",
            ),
        ]
    
    def _extract_command(self, command: str) -> str:
        """Extract the base command from a command string.
        
        This extracts the first command in the string (preserving sudo/su).
        
        Args:
            command: Full command string
            
        Returns:
            Base command name (including sudo/su if present)
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
            
            # Return the first part (preserves sudo/su for blocking)
            return Path(parts[0]).name
        except ValueError:
            # If shlex fails, simple split
            return command.strip().split()[0] if command.strip() else ""
    
    def _extract_target_command(self, command: str) -> str:
        """Extract the target command being executed (after sudo/su).
        
        This is used to check the actual command being run after sudo/su.
        
        Args:
            command: Full command string
            
        Returns:
            Target command name (the command after sudo/su)
        """
        # Handle command chains
        for separator in ["&&", "||", ";"]:
            if separator in command:
                command = command.split(separator)[0]
        
        try:
            parts = shlex.split(command.strip())
            if not parts:
                return ""
            
            base_cmd = parts[0]
            # Handle sudo/su prefix - return the actual command being executed
            if base_cmd in ("sudo", "su") and len(parts) > 1:
                return Path(parts[1]).name
            
            return Path(base_cmd).name
        except ValueError:
            return command.strip().split()[0] if command.strip() else ""
    
    def _check_command_status(self, command: str) -> tuple[str, str | None]:
        """Check command status and return appropriate action.
        
        Args:
            command: Command string to check
            
        Returns:
            Tuple of (status, message) where status is:
            - 'allowed': Command can execute directly
            - 'blocked': Command is in blacklist (permanently blocked)
            - 'high_risk': Command requires user confirmation
        """
        base_cmd = self._extract_command(command)
        
        if not base_cmd:
            return 'blocked', "Empty command"
        
        # Check sensitive commands (always blocked)
        if base_cmd in SENSITIVE_COMMANDS:
            return 'blocked', f"Command '{base_cmd}' requires elevated privileges and is blocked"
        
        # Check blacklist (blocked but can be shown to user)
        if base_cmd in self.blacklist:
            return 'blocked', f"Command '{base_cmd}' is blocked for safety reasons. This command cannot be executed."
        
        # Check high-risk commands (requires confirmation)
        # Use target command (after sudo/su) for high-risk check
        target_cmd = self._extract_target_command(command)
        if target_cmd in self.high_risk_commands:
            return 'high_risk', f"Command '{target_cmd}' is high-risk and requires your confirmation"
        
        return 'allowed', None
    
    def _is_high_risk_command(self, command: str) -> tuple[bool, str | None]:
        """Check if a command is high-risk and requires user confirmation.
        
        Args:
            command: Command string to check
            
        Returns:
            Tuple of (is_high_risk, warning_message)
        """
        base_cmd = self._extract_command(command)
        
        if not base_cmd:
            return False, None
        
        if base_cmd in self.high_risk_commands:
            return True, f"Command '{base_cmd}' is high-risk and requires user confirmation"
        
        return False, None
    
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
        confirmed: bool = False,
        confirmation_id: str = "",
    ) -> ToolResult:
        """Execute a shell command.
        
        Args:
            command: Shell command to execute
            working_dir: Working directory for the command
            timeout: Timeout in seconds
            is_background: Whether to run in background
            confirmed: Whether user has confirmed high-risk command execution
            confirmation_id: The confirmation ID for verification
            
        Returns:
            ToolResult with command output or error
        """
        # Check command status
        status, message = self._check_command_status(command)
        
        # Handle blocked commands (blacklist) - show to user but cannot execute
        if status == 'blocked':
            logger.warning(
                "Blocked command execution",
                extra={"command": command, "reason": message}
            )
            return ToolResult.error_result(
                message or "Command not allowed",
                is_blocked=True,
                command=command,
            )
        
        # Handle high-risk commands - require user confirmation with verification
        if status == 'high_risk':
            if not confirmed:
                # Generate a new confirmation ID and store it
                new_confirmation_id = generate_confirmation_id()
                store_pending_confirmation(new_confirmation_id, command, "")
                
                logger.warning(
                    "High-risk command requires confirmation",
                    extra={
                        "command": command,
                        "warning": message,
                        "confirmation_id": new_confirmation_id,
                    }
                )
                return ToolResult.error_result(
                    f"{message}. Click 'Confirm' to execute this command.",
                    requires_confirmation=True,
                    command=command,
                    confirmation_id=new_confirmation_id,
                )
            
            # Verify the confirmation ID
            if not confirmation_id:
                logger.warning(
                    "High-risk command missing confirmation_id",
                    extra={"command": command}
                )
                return ToolResult.error_result(
                    "High-risk command requires valid confirmation_id. "
                    "Please click 'Confirm' in the UI to authorize this command.",
                    requires_confirmation=True,
                    command=command,
                )
            
            if not verify_and_consume_confirmation(confirmation_id, command):
                logger.warning(
                    "High-risk command confirmation verification failed",
                    extra={"command": command, "confirmation_id": confirmation_id}
                )
                return ToolResult.error_result(
                    "Invalid or expired confirmation. Please click 'Confirm' in the UI to authorize this command.",
                    requires_confirmation=True,
                    command=command,
                )
            
            logger.info(
                "High-risk command confirmed by user",
                extra={"command": command, "confirmation_id": confirmation_id}
            )
        
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
                "status": status,
            }
        )
        
        # ===== ADD DETAILED LOGGING FOR DEPENDENCY INSTALLATION DEBUGGING =====
        is_install_command = 'pip install' in command or 'npm install' in command
        if is_install_command:
            from datetime import datetime
            logger.info(
                "🔍 [DEPENDENCY INSTALL] Starting dependency installation",
                extra={
                    "install_type": "pip" if 'pip' in command else "npm",
                    "command": command,
                    "timestamp": datetime.now().isoformat(),
                    "requires_confirmation": status == 'high_risk',
                    "already_confirmed": confirmed,
                    "confirmation_id": confirmation_id if confirmed else None,
                    "working_dir": str(cwd),
                }
            )
        # =======================================================================
        
        try:
            if is_background:
                return await self._execute_background(command, cwd)
            else:
                # Pass is_install_command to foreground execution for logging
                return await self._execute_foreground(command, cwd, timeout, is_install_command)
        
        except Exception as e:
            # ===== ADD DETAILED ERROR LOGGING FOR INSTALL FAILURES =====
            if is_install_command:
                from datetime import datetime
                logger.error(
                    "❌ [DEPENDENCY INSTALL] Installation failed with exception",
                    extra={
                        "install_type": "pip" if 'pip' in command else "npm",
                        "command": command,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                        "exception_type": type(e).__name__,
                    }
                )
            # ================================================================
            
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
        is_install_command: bool = False,  # Added for dependency installation logging
    ) -> ToolResult:
        """Execute command in foreground (blocking).
        
        Args:
            command: Command to execute
            cwd: Working directory
            timeout: Timeout in seconds
            is_install_command: Whether this is a dependency installation command
            
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
            was_truncated = False
            if len(output) > self.max_output_length:
                output = output[:self.max_output_length] + f"\n\n... [truncated, {len(output)} total characters]"
                was_truncated = True
            
            success = process.returncode == 0
            
            # ===== ADD DETAILED LOGGING FOR INSTALL RESULTS =====
            if is_install_command:
                from datetime import datetime
                if success:
                    logger.info(
                        "✅ [DEPENDENCY INSTALL] Installation completed successfully",
                        extra={
                            "install_type": "pip" if 'pip' in command else "npm",
                            "command": command,
                            "returncode": process.returncode,
                            "timestamp": datetime.now().isoformat(),
                            "stdout_length": len(stdout_str),
                            "stderr_length": len(stderr_str),
                        }
                    )
                else:
                    logger.error(
                        "❌ [DEPENDENCY INSTALL] Installation failed with non-zero exit code",
                        extra={
                            "install_type": "pip" if 'pip' in command else "npm",
                            "command": command,
                            "returncode": process.returncode,
                            "timestamp": datetime.now().isoformat(),
                            "error_preview": stderr_str[:200] if stderr_str else stdout_str[:200],
                        }
                    )
            # ===================================================
            
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
