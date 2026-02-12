from typing import Dict, Any, List
import re


class ToolSecurityValidator:
    """
    Validates tool execution requests to ensure they meet security requirements.
    """

    def __init__(self):
        # Define dangerous patterns that should not be allowed in tool execution
        self.dangerous_patterns = [
            r'\brm\s+-',  # rm command
            r'\bsudo\b',  # sudo command
            r'\bmv\s+/',  # mv to system directories
            r'\bdd\s+',  # dd command (disk operations)
            r'\bkill\s+',  # kill command
            r'\bchmod\s+',  # chmod command
            r'\bchown\s+',  # chown command
            r'\bmount\s+',  # mount command
            r'\bumount\s+',  # umount command
            r'/etc/',  # access to system config
            r'/root/',  # access to root directory
            r'/proc/',  # access to process information
            r'/sys/',  # access to system information
            r';\s*\w+',  # command chaining with semicolon
            r'\|\s*\w+',  # command piping
            r'&&\s*\w+',  # logical AND command chaining
            r'\|\|',  # logical OR command chaining
            r'\$\(',  # command substitution
            r'`\w+`',  # command substitution with backticks
        ]

    def validate_tool_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parameters for a tool execution request.

        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool

        Returns:
            Dictionary with 'valid' (bool) and 'message' (str) keys
        """
        # Validate different tools differently
        if tool_name == "command-exec":
            return self._validate_command_exec(parameters)
        elif tool_name in ["file-read", "file-write", "file-system"]:
            return self._validate_file_operation(parameters)
        elif tool_name == "web-search":
            return self._validate_web_search(parameters)
        else:
            # For other tools, just check for dangerous patterns in parameters
            for param_value in parameters.values():
                if isinstance(param_value, str) and self._contains_dangerous_pattern(param_value):
                    return {
                        "valid": False,
                        "message": f"Parameter contains potentially dangerous patterns: {param_value}"
                    }
            return {"valid": True, "message": "Valid"}

    def _validate_command_exec(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate command execution parameters."""
        if "command" not in parameters:
            return {"valid": False, "message": "Command parameter is required"}

        command = str(parameters["command"])

        # Check for dangerous patterns
        if self._contains_dangerous_pattern(command):
            return {
                "valid": False,
                "message": f"Command contains dangerous patterns: {command}"
            }

        # Additional checks for command-exec tool
        # Check command length (prevent extremely long commands)
        if len(command) > 1000:
            return {
                "valid": False,
                "message": "Command too long (max 1000 characters)"
            }

        # Check if command is empty
        if not command.strip():
            return {
                "valid": False,
                "message": "Command cannot be empty"
            }

        return {"valid": True, "message": "Valid"}

    def _validate_file_operation(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate file operation parameters."""
        if "file_path" not in parameters:
            return {"valid": False, "message": "file_path parameter is required"}

        file_path = str(parameters["file_path"])

        # Check for path traversal attempts
        if "../" in file_path or "..\\" in file_path:
            return {
                "valid": False,
                "message": f"Invalid file path: {file_path} - path traversal detected"
            }

        # Check for dangerous patterns in the file path
        if self._contains_dangerous_pattern(file_path):
            return {
                "valid": False,
                "message": f"File path contains dangerous patterns: {file_path}"
            }

        # Additional validation based on the operation
        if "operation" in parameters and parameters["operation"] == "delete":
            # Additional checks for delete operations
            # Ensure the path is not a system directory or critical location
            dangerous_paths = ["/etc", "/root", "/proc", "/sys", "/var", "/usr", "/opt"]
            for dangerous_path in dangerous_paths:
                if file_path.startswith(dangerous_path):
                    return {
                        "valid": False,
                        "message": f"Cannot delete files in system directories: {file_path}"
                    }

        # Check path length
        if len(file_path) > 1000:
            return {
                "valid": False,
                "message": "File path too long (max 1000 characters)"
            }

        return {"valid": True, "message": "Valid"}

    def _validate_web_search(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate web search parameters."""
        if "query" not in parameters:
            return {"valid": False, "message": "query parameter is required"}

        query = str(parameters["query"])

        # Check query length
        if len(query) > 500:
            return {
                "valid": False,
                "message": "Search query too long (max 500 characters)"
            }

        # Check for dangerous patterns in query
        if self._contains_dangerous_pattern(query):
            return {
                "valid": False,
                "message": f"Search query contains dangerous patterns: {query}"
            }

        # Ensure query is not empty
        if not query.strip():
            return {
                "valid": False,
                "message": "Search query cannot be empty"
            }

        return {"valid": True, "message": "Valid"}

    def _contains_dangerous_pattern(self, text: str) -> bool:
        """
        Check if the text contains any dangerous patterns.

        Args:
            text: Text to check for dangerous patterns

        Returns:
            True if dangerous pattern is found, False otherwise
        """
        for pattern in self.dangerous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def sanitize_input(self, text: str) -> str:
        """
        Sanitize input by removing or escaping dangerous characters.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text
        """
        # Remove potentially dangerous patterns
        sanitized = text

        # Remove command separators
        sanitized = re.sub(r'[;&|]', '', sanitized)

        # Remove command substitution
        sanitized = re.sub(r'\$\([^)]*\)', '', sanitized)
        sanitized = re.sub(r'`[^`]*`', '', sanitized)

        return sanitized


# Global instance of the validator
tool_security_validator = ToolSecurityValidator()