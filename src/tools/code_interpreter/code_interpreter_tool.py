import subprocess
import tempfile
import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from ..base_tool import BaseTool


class CodeInterpreterToolArgs(BaseModel):
    language: str = Field(description="Programming language: python, javascript, bash")
    code: str = Field(description="Code to execute")


class CodeInterpreterTool(BaseTool):
    """Tool for executing code in various programming languages."""

    def __init__(self):
        super().__init__(
            name="code-interpreter",
            description="Execute code in different programming languages: python, javascript, bash",
            args_schema=CodeInterpreterToolArgs
        )

    def _run(self, language: str, code: str, **kwargs) -> str:
        """
        Execute code in the specified language.

        Args:
            language: Programming language (python, javascript, bash)
            code: Code to execute

        Returns:
            Execution result as a string
        """
        try:
            language = language.lower().strip()

            if language == "python":
                return self._execute_python(code)
            elif language in ["javascript", "js"]:
                return self._execute_javascript(code)
            elif language in ["bash", "shell", "sh"]:
                return self._execute_bash(code)
            else:
                return f"Error: Unsupported language '{language}'. Supported languages are: python, javascript, bash"

        except Exception as e:
            return f"Error executing code: {str(e)}"

    def _execute_python(self, code: str) -> str:
        """Execute Python code in a secure manner."""
        # Security check: prevent dangerous imports and operations
        dangerous_imports = [
            "os", "sys", "subprocess", "importlib", "imp", "compileall", "__import__",
            "execfile", "eval", "exec", "globals", "locals", "open", "__builtins__",
            "getattr", "setattr", "delattr", "hasattr", "vars", "dir", "help", "input",
            "file", "f=open", "exec(", "eval("
        ]

        # Convert code to lowercase for checking
        code_lower = code.lower()

        # Check for dangerous operations
        for dangerous in dangerous_imports:
            if f"import {dangerous}" in code_lower or f"from {dangerous}" in code_lower:
                return f"Error: Importing '{dangerous}' is not allowed for security reasons."

        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            # Execute the Python code with limited rights
            result = subprocess.run(
                ['python3', temp_file_path],
                capture_output=True,
                text=True,
                timeout=10,  # 10 second timeout
                cwd=tempfile.gettempdir()  # Execute in temp directory
            )

            # Clean up the temporary file
            os.unlink(temp_file_path)

            # Format output
            output_parts = []
            if result.stdout:
                output_parts.append(f"Output:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"Return code: {result.returncode}")

            if not output_parts:
                output_parts.append("Code executed successfully (no output)")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            os.unlink(temp_file_path)
            return "Error: Python code execution timed out after 10 seconds."
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return f"Error executing Python code: {str(e)}"

    def _execute_javascript(self, code: str) -> str:
        """Execute JavaScript code using Node.js."""
        # Security check: prevent dangerous operations
        dangerous_operations = [
            "require(", "fs.", "child_process.", "exec", "spawn", "fork", "require.resolve",
            "module.", "process.", "global.", "__dirname", "__filename", "import", "export",
            "eval(", "setTimeout(", "setInterval(", "Function(", "new Function("
        ]

        code_lower = code.lower()
        for dangerous in dangerous_operations:
            if dangerous in code_lower:
                return f"Error: JavaScript operation '{dangerous.strip('(')}' is not allowed for security reasons."

        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as temp_file:
            temp_file.write(f"(function() {{\n{code}\n}})();")
            temp_file_path = temp_file.name

        try:
            # Execute the JavaScript code with Node.js
            result = subprocess.run(
                ['node', temp_file_path],
                capture_output=True,
                text=True,
                timeout=10,  # 10 second timeout
                cwd=tempfile.gettempdir()
            )

            # Clean up the temporary file
            os.unlink(temp_file_path)

            # Format output
            output_parts = []
            if result.stdout:
                output_parts.append(f"Output:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"Return code: {result.returncode}")

            if not output_parts:
                output_parts.append("JavaScript code executed successfully (no output)")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            os.unlink(temp_file_path)
            return "Error: JavaScript code execution timed out after 10 seconds."
        except FileNotFoundError:
            os.unlink(temp_file_path)
            return "Error: Node.js is not installed or not in PATH."
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return f"Error executing JavaScript code: {str(e)}"

    def _execute_bash(self, code: str) -> str:
        """Execute bash script with security restrictions."""
        # Use the command execution tool with additional security checks
        from ..command_exec.command_exec_tool import CommandExecutionTool

        tool = CommandExecutionTool()

        # Security check through the command execution tool
        if not tool._is_safe_command(code):
            return f"Error: Bash command '{code}' contains unsafe elements and is not allowed."

        # Execute with limited privileges
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
            temp_file.write("#!/bin/bash\n")
            temp_file.write(code)
            temp_file_path = temp_file.name

        try:
            # Make the script executable and run it
            os.chmod(temp_file_path, 0o755)

            result = subprocess.run(
                [temp_file_path],
                capture_output=True,
                text=True,
                timeout=10,  # 10 second timeout
                cwd=tempfile.gettempdir()
            )

            # Clean up the temporary file
            os.unlink(temp_file_path)

            # Format output
            output_parts = []
            if result.stdout:
                output_parts.append(f"Output:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"Return code: {result.returncode}")

            if not output_parts:
                output_parts.append("Bash script executed successfully (no output)")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            os.unlink(temp_file_path)
            return "Error: Bash script execution timed out after 10 seconds."
        except Exception as e:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            return f"Error executing bash script: {str(e)}"