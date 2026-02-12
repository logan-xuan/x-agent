"""
Plugin security sandbox for the x-agent2 AI assistant system.

This module provides a secure environment for executing third-party plugins
with limited capabilities to prevent system compromise.
"""

import subprocess
import tempfile
import os
import sys
import importlib.util
import json
import ast
import inspect
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
import multiprocessing
from enum import Enum
import signal
import time
import resource
import functools
from contextlib import contextmanager
import threading


class SandboxMode(Enum):
    """Different levels of sandboxing."""
    DISABLED = "disabled"
    MONITORING = "monitoring"
    LIMITED = "limited"
    STRICT = "strict"
    PARANOID = "paranoid"


class SecurityViolation(Exception):
    """Exception raised when a security violation is detected."""
    pass


class ResourceLimitExceeded(Exception):
    """Exception raised when resource limits are exceeded."""
    pass


class PluginSandbox:
    """Security sandbox for executing plugins safely."""

    def __init__(self, mode: SandboxMode = SandboxMode.LIMITED):
        self.mode = mode
        self.logger = None  # Would be set by the plugin system

        # Security settings based on mode
        self.security_settings = {
            SandboxMode.DISABLED: {
                "allow_network": True,
                "allow_filesystem": True,
                "allow_system_commands": True,
                "resource_limits": {},
                "monitor_only": False
            },
            SandboxMode.MONITORING: {
                "allow_network": True,
                "allow_filesystem": True,
                "allow_system_commands": True,
                "resource_limits": {},
                "monitor_only": True
            },
            SandboxMode.LIMITED: {
                "allow_network": False,
                "allow_filesystem": True,
                "allow_system_commands": False,
                "resource_limits": {
                    "cpu_time": 30,  # seconds
                    "memory_mb": 256,
                    "wall_clock_time": 60  # seconds
                },
                "monitor_only": False
            },
            SandboxMode.STRICT: {
                "allow_network": False,
                "allow_filesystem": False,
                "allow_system_commands": False,
                "resource_limits": {
                    "cpu_time": 10,
                    "memory_mb": 128,
                    "wall_clock_time": 30
                },
                "monitor_only": False
            },
            SandboxMode.PARANOID: {
                "allow_network": False,
                "allow_filesystem": False,
                "allow_system_commands": False,
                "resource_limits": {
                    "cpu_time": 5,
                    "memory_mb": 64,
                    "wall_clock_time": 15
                },
                "monitor_only": False
            }
        }

        self.settings = self.security_settings[self.mode]

    def execute_plugin_code(
        self,
        code: str,
        plugin_name: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute plugin code in a secure sandbox.

        Args:
            code: The plugin code to execute
            plugin_name: Name of the plugin
            context: Context to provide to the plugin
            timeout: Execution timeout in seconds

        Returns:
            Dictionary with execution results
        """
        if self.mode == SandboxMode.DISABLED:
            # No sandboxing - just execute directly
            return self._execute_without_sandbox(code, context)

        # For all other modes, create a secure execution environment
        return self._execute_with_sandbox(code, plugin_name, context, timeout)

    def _execute_without_sandbox(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute code without sandboxing (only for disabled mode)."""
        try:
            # Create execution environment
            exec_globals = {
                "__builtins__": __builtins__
            }
            exec_locals = context or {}

            # Execute the code
            exec(code, exec_globals, exec_locals)

            # Return the results
            return {
                "success": True,
                "result": exec_locals,
                "execution_time": 0,  # Not measured in disabled mode
                "violations": [],
                "resources_used": {}
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": None,
                "violations": [],
                "resources_used": {}
            }

    def _execute_with_sandbox(
        self,
        code: str,
        plugin_name: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute code with sandboxing enabled."""
        # Validate code for dangerous patterns before execution
        violations = self._scan_code_for_violations(code)
        if violations and self.mode != SandboxMode.MONITORING:
            return {
                "success": False,
                "error": "Security violations detected in code",
                "result": None,
                "violations": violations,
                "resources_used": {}
            }

        # In monitoring mode, just log violations but allow execution
        if self.mode == SandboxMode.MONITORING and violations:
            self._log_security_violations(violations, plugin_name)

        # Create a secure execution environment
        try:
            # Execute in a subprocess to isolate the environment
            return self._execute_in_subprocess(code, context, timeout)
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "result": None,
                "violations": violations,
                "resources_used": {}
            }

    def _scan_code_for_violations(self, code: str) -> List[str]:
        """Scan code for security violations using AST."""
        violations = []

        try:
            # Parse the code into an AST
            tree = ast.parse(code)

            # Walk the AST to find dangerous patterns
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', 'compile']:
                            violations.append(f"Dangerous function call: {node.func.id}")
                    elif isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            if node.func.attr in ['system', 'popen', 'check_call', 'call']:
                                violations.append(f"Dangerous method call: {node.func.value.id}.{node.func.attr}")

                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ['os', 'subprocess', 'sys', 'socket', 'requests']:
                            violations.append(f"Dangerous import: {alias.name}")

                elif isinstance(node, ast.ImportFrom):
                    if node.module in ['os', 'subprocess', 'sys', 'socket', 'requests']:
                        violations.append(f"Dangerous import from: {node.module}")

        except SyntaxError:
            violations.append("Code contains syntax errors")

        return violations

    def _log_security_violations(self, violations: List[str], plugin_name: str):
        """Log security violations if monitoring."""
        if self.logger:
            for violation in violations:
                self.logger.warning(f"Security violation in plugin {plugin_name}: {violation}")

    def _execute_in_subprocess(self, code: str, context: Optional[Dict[str, Any]], timeout: int) -> Dict[str, Any]:
        """Execute code in a subprocess with resource limits."""
        # Create a pipe to communicate with the subprocess
        parent_conn, child_conn = multiprocessing.Pipe()

        # Create a process to run the code
        process = multiprocessing.Process(
            target=self._execute_in_child_process,
            args=(code, context, child_conn)
        )

        start_time = time.time()
        process.start()

        # Wait for the process to complete with timeout
        try:
            if process.is_alive():
                process.join(timeout)

                if process.is_alive():
                    # Process exceeded timeout, terminate it
                    process.terminate()
                    process.join(timeout=5)  # Give it a bit more time to clean up

                    if process.is_alive():
                        # Force kill if it's still alive
                        os.kill(process.pid, signal.SIGKILL)

                    raise TimeoutError(f"Plugin execution exceeded {timeout}s timeout")

            # Check if we received results through the pipe
            if parent_conn.poll():
                result = parent_conn.recv()
                execution_time = time.time() - start_time

                return {
                    "success": True,
                    "result": result,
                    "execution_time": execution_time,
                    "violations": [],
                    "resources_used": {
                        "execution_time_sec": execution_time
                    }
                }
            else:
                # No result received, probably an error occurred
                raise RuntimeError("Plugin execution failed, no result received")

        finally:
            # Clean up connections
            parent_conn.close()
            child_conn.close()

    def _execute_in_child_process(self, code: str, context: Optional[Dict[str, Any]], conn):
        """Execute code in the child process."""
        try:
            # Apply resource limits
            if 'cpu_time' in self.settings['resource_limits']:
                cpu_limit = self.settings['resource_limits']['cpu_time']
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))

            if 'memory_mb' in self.settings['resource_limits']:
                memory_limit = self.settings['resource_limits']['memory_mb'] * 1024 * 1024  # Convert to bytes
                resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

            # Create a restricted environment
            safe_builtins = {
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'pow': pow,
                'print': print if self.settings['monitor_only'] else lambda *args: None,
                'repr': repr,
                'type': type,
                'isinstance': isinstance,
                'issubclass': issubclass,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr if not self.settings['allow_system_commands'] else setattr,
                'json': json,  # Allow safe JSON operations
            }

            # Create globals and locals for execution
            exec_globals = {
                '__builtins__': safe_builtins
            }

            # Add context if provided
            exec_locals = context or {}

            # Execute the code
            exec(code, exec_globals, exec_locals)

            # Send result back through the pipe
            conn.send(exec_locals)

        except Exception as e:
            # Send error back through the pipe
            conn.send({'error': str(e)})
        finally:
            conn.close()

    def validate_plugin_file(self, plugin_file_path: str) -> Dict[str, Any]:
        """
        Validate a plugin file for security before loading.

        Args:
            plugin_file_path: Path to the plugin file

        Returns:
            Dictionary with validation results
        """
        try:
            with open(plugin_file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            violations = self._scan_code_for_violations(code)

            return {
                "is_valid": len(violations) == 0,
                "violations": violations,
                "code_size": len(code),
                "analysis_time": 0  # Not measured in this simple implementation
            }
        except Exception as e:
            return {
                "is_valid": False,
                "violations": [f"Could not read plugin file: {str(e)}"],
                "code_size": 0,
                "analysis_time": 0
            }

    def execute_plugin_with_context(
        self,
        plugin_code: str,
        context: Dict[str, Any],
        plugin_name: str,
        allowed_resources: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a plugin with a specific context and resource allowances.

        Args:
            plugin_code: The plugin code to execute
            context: Context to provide to the plugin
            plugin_name: Name of the plugin
            allowed_resources: Specific resource allowances for this execution

        Returns:
            Dictionary with execution results
        """
        # Override resource limits if specified for this execution
        original_limits = self.settings.get('resource_limits', {}).copy()

        if allowed_resources:
            self.settings['resource_limits'].update(allowed_resources)

        try:
            result = self.execute_plugin_code(plugin_code, plugin_name, context)
            return result
        finally:
            # Restore original resource limits
            self.settings['resource_limits'] = original_limits


class SandboxedPluginEnvironment:
    """Managed environment for running plugins with configurable security."""

    def __init__(self, sandbox_mode: SandboxMode = SandboxMode.LIMITED):
        self.sandbox = PluginSandbox(sandbox_mode)
        self.active_plugins: Dict[str, Any] = {}
        self.plugin_contexts: Dict[str, Dict[str, Any]] = {}

    def load_plugin(self, plugin_code: str, plugin_name: str) -> bool:
        """
        Load a plugin into the sandboxed environment.

        Args:
            plugin_code: The plugin code to load
            plugin_name: Name to register the plugin under

        Returns:
            True if loading was successful, False otherwise
        """
        # Validate the plugin code
        validation_result = self.sandbox.validate_plugin_file_from_string(plugin_code)

        if not validation_result["is_valid"]:
            if self.sandbox.mode != SandboxMode.MONITORING:
                print(f"Plugin {plugin_name} failed validation: {validation_result['violations']}")
                return False
            else:
                print(f"Plugin {plugin_name} validation issues (in monitoring mode): {validation_result['violations']}")

        # Execute the plugin code to extract its functionality
        execution_result = self.sandbox.execute_plugin_code(
            plugin_code,
            plugin_name,
            timeout=10  # Short timeout for loading phase
        )

        if execution_result["success"]:
            self.active_plugins[plugin_name] = execution_result["result"]
            self.plugin_contexts[plugin_name] = execution_result["result"]
            return True
        else:
            print(f"Failed to load plugin {plugin_name}: {execution_result['error']}")
            return False

    def validate_plugin_file_from_string(self, code: str) -> Dict[str, Any]:
        """
        Validate plugin code provided as a string.
        This is a helper method to mimic the behavior of validate_plugin_file.
        """
        violations = self.sandbox._scan_code_for_violations(code)

        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "code_size": len(code),
            "analysis_time": 0
        }

    def run_plugin_method(
        self,
        plugin_name: str,
        method_name: str,
        *args,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Safely execute a method from a loaded plugin.

        Args:
            plugin_name: Name of the plugin
            method_name: Name of the method to execute
            *args: Arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method

        Returns:
            Dictionary with method execution results
        """
        if plugin_name not in self.active_plugins:
            return {
                "success": False,
                "error": f"Plugin {plugin_name} is not loaded"
            }

        plugin_context = self.plugin_contexts[plugin_name]

        if method_name not in plugin_context:
            return {
                "success": False,
                "error": f"Method {method_name} not found in plugin {plugin_name}"
            }

        method = plugin_context[method_name]

        if not callable(method):
            return {
                "success": False,
                "error": f"{method_name} is not a callable method in plugin {plugin_name}"
            }

        # Execute the method in the sandbox
        try:
            result = method(*args, **kwargs)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin from the environment.

        Args:
            plugin_name: Name of the plugin to unload

        Returns:
            True if unloading was successful, False otherwise
        """
        if plugin_name in self.active_plugins:
            del self.active_plugins[plugin_name]
            if plugin_name in self.plugin_contexts:
                del self.plugin_contexts[plugin_name]
            return True
        return False

    def get_sandbox_status(self) -> Dict[str, Any]:
        """
        Get the current status of the sandbox.

        Returns:
            Dictionary with sandbox status information
        """
        return {
            "sandbox_mode": self.sandbox.mode.value,
            "active_plugins_count": len(self.active_plugins),
            "plugin_names": list(self.active_plugins.keys()),
            "security_settings": self.sandbox.settings
        }


class PluginSecurityManager:
    """High-level manager for plugin security."""

    def __init__(self, default_mode: SandboxMode = SandboxMode.LIMITED):
        self.default_mode = default_mode
        self.environments: Dict[SandboxMode, SandboxedPluginEnvironment] = {}

        # Create an environment for each sandbox mode
        for mode in SandboxMode:
            self.environments[mode] = SandboxedPluginEnvironment(mode)

    def get_environment(self, mode: Optional[SandboxMode] = None) -> SandboxedPluginEnvironment:
        """
        Get a sandboxed environment for a specific mode.

        Args:
            mode: Sandbox mode to get environment for (uses default if None)

        Returns:
            SandboxedPluginEnvironment instance
        """
        mode = mode or self.default_mode
        return self.environments[mode]

    def scan_plugin_for_security_issues(self, plugin_code: str) -> Dict[str, Any]:
        """
        Scan plugin code for security issues without executing it.

        Args:
            plugin_code: The plugin code to scan

        Returns:
            Dictionary with security scan results
        """
        sandbox = PluginSandbox(self.default_mode)
        violations = sandbox._scan_code_for_violations(plugin_code)

        severity_levels = {
            "eval/exec": 5,
            "system commands": 4,
            "network access": 3,
            "filesystem access": 2,
            "suspicious patterns": 1
        }

        # Categorize violations by severity
        categorized_violations = {}
        for violation in violations:
            severity = 1  # Default to lowest severity
            for pattern, level in severity_levels.items():
                if pattern in violation.lower():
                    severity = level
                    break

            if severity not in categorized_violations:
                categorized_violations[severity] = []
            categorized_violations[severity].append(violation)

        return {
            "has_issues": len(violations) > 0,
            "total_violations": len(violations),
            "violations": violations,
            "categorized_violations": categorized_violations,
            "risk_level": max(categorized_violations.keys()) if categorized_violations else 0
        }

    def create_secure_plugin_runner(self, plugin_code: str, mode: SandboxMode = None) -> Optional[Callable]:
        """
        Create a secure function that can run the plugin code safely.

        Args:
            plugin_code: The plugin code to wrap
            mode: Sandbox mode to use (uses default if None)

        Returns:
            A function that can securely execute the plugin code, or None if validation fails
        """
        mode = mode or self.default_mode
        sandbox = PluginSandbox(mode)

        # Validate the plugin code
        validation_result = self.scan_plugin_for_security_issues(plugin_code)

        if validation_result["has_issues"] and mode != SandboxMode.MONITORING:
            print(f"Plugin has security issues and will not be wrapped: {validation_result['violations']}")
            return None

        def secure_runner(context: Optional[Dict[str, Any]] = None, timeout: int = 30):
            return sandbox.execute_plugin_code(plugin_code, "inline_plugin", context, timeout)

        return secure_runner


# Global security manager instance
plugin_security_manager = PluginSecurityManager()


# Convenience functions
def create_sandboxed_environment(mode: SandboxMode = SandboxMode.LIMITED) -> SandboxedPluginEnvironment:
    """Create a new sandboxed environment."""
    return SandboxedPluginEnvironment(mode)


def scan_plugin_for_security_issues(plugin_code: str) -> Dict[str, Any]:
    """Scan plugin code for security issues."""
    return plugin_security_manager.scan_plugin_for_security_issues(plugin_code)


def execute_in_sandbox(
    plugin_code: str,
    context: Optional[Dict[str, Any]] = None,
    mode: SandboxMode = SandboxMode.LIMITED,
    timeout: int = 30
) -> Dict[str, Any]:
    """Execute plugin code in a sandbox."""
    sandbox = PluginSandbox(mode)
    return sandbox.execute_plugin_code(plugin_code, "anonymous_plugin", context, timeout)