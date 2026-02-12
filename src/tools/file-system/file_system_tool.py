import os
from typing import Dict, Any
from pydantic import BaseModel, Field
from .base_tool import BaseTool


class FileSystemToolArgs(BaseModel):
    operation: str = Field(description="Operation to perform: read, write, list, or delete")
    file_path: str = Field(description="Path to the file or directory")
    content: str = Field(default="", description="Content to write (for write operations)")


class FileSystemTool(BaseTool):
    """Tool for performing file system operations like reading, writing, listing, and deleting files."""

    def __init__(self):
        super().__init__(
            name="file-system",
            description="Perform file system operations: read, write, list, or delete files and directories",
            args_schema=FileSystemToolArgs
        )

    def _run(self, operation: str, file_path: str, content: str = "", **kwargs) -> str:
        """
        Execute a file system operation based on the provided parameters.

        Args:
            operation: The operation to perform (read, write, list, delete)
            file_path: The path to the file or directory
            content: The content to write (for write operations)

        Returns:
            Result of the file operation as a string
        """
        try:
            # Security check: ensure the file_path is within allowed directories
            if not self._is_safe_path(file_path):
                return f"Error: Access to path '{file_path}' is restricted for security reasons."

            if operation.lower() == "read":
                return self._read_file(file_path)
            elif operation.lower() == "write":
                return self._write_file(file_path, content)
            elif operation.lower() == "list":
                return self._list_directory(file_path)
            elif operation.lower() == "delete":
                return self._delete_file(file_path)
            else:
                return f"Error: Unsupported operation '{operation}'. Supported operations are: read, write, list, delete"

        except Exception as e:
            return f"Error performing file operation: {str(e)}"

    def _is_safe_path(self, path: str) -> bool:
        """
        Check if the provided path is safe to access.
        Prevents access to system directories and other sensitive areas.

        Args:
            path: The file path to check

        Returns:
            True if the path is safe, False otherwise
        """
        # Convert to absolute path for comparison
        abs_path = os.path.abspath(path)

        # Define restricted paths
        restricted_paths = [
            "/etc",
            "/root",
            "/proc",
            "/sys",
            "/usr/bin",
            "/usr/sbin",
            "/bin",
            "/sbin",
            os.path.expanduser("~/.ssh"),
            os.path.expanduser("~/.aws"),
            os.path.expanduser("~/.config/gcloud"),
        ]

        # Check if the path starts with any restricted path
        for restricted in restricted_paths:
            if abs_path.startswith(os.path.abspath(restricted)):
                return False

        return True

    def _read_file(self, file_path: str) -> str:
        """Read the content of a file."""
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."

        if os.path.isdir(file_path):
            return f"Error: '{file_path}' is a directory, not a file."

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            # Limit content size to prevent huge outputs
            max_size = 10000  # 10KB
            if len(content) > max_size:
                return f"File content is too large ({len(content)} chars). Preview (first {max_size} chars):\n{content[:max_size]}..."

            return content
        except PermissionError:
            return f"Error: Permission denied when reading file '{file_path}'."
        except UnicodeDecodeError:
            return f"Error: Unable to decode file '{file_path}'. It may be a binary file."
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def _write_file(self, file_path: str, content: str) -> str:
        """Write content to a file."""
        # Create directory if it doesn't exist
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)

            return f"Successfully wrote {len(content)} characters to '{file_path}'."
        except PermissionError:
            return f"Error: Permission denied when writing to file '{file_path}'."
        except Exception as e:
            return f"Error writing to file: {str(e)}"

    def _list_directory(self, dir_path: str) -> str:
        """List the contents of a directory."""
        if not os.path.exists(dir_path):
            return f"Error: Directory '{dir_path}' does not exist."

        if not os.path.isdir(dir_path):
            return f"Error: '{dir_path}' is not a directory."

        try:
            items = os.listdir(dir_path)

            if not items:
                return f"Directory '{dir_path}' is empty."

            # Sort items: directories first, then files
            dirs = [item for item in items if os.path.isdir(os.path.join(dir_path, item))]
            files = [item for item in items if os.path.isfile(os.path.join(dir_path, item))]

            result = [f"Directories in '{dir_path}':"]
            if dirs:
                for d in dirs:
                    result.append(f"  [DIR] {d}")
            else:
                result.append("  (no subdirectories)")

            result.append(f"\nFiles in '{dir_path}':")
            if files:
                for f in files:
                    # Get file size
                    file_path = os.path.join(dir_path, f)
                    size = os.path.getsize(file_path)
                    result.append(f"  [FILE] {f} ({size} bytes)")
            else:
                result.append("  (no files)")

            return "\n".join(result)
        except PermissionError:
            return f"Error: Permission denied when accessing directory '{dir_path}'."
        except Exception as e:
            return f"Error listing directory: {str(e)}"

    def _delete_file(self, file_path: str) -> str:
        """Delete a file."""
        if not os.path.exists(file_path):
            return f"Error: File '{file_path}' does not exist."

        if os.path.isdir(file_path):
            return f"Error: '{file_path}' is a directory. Use appropriate method for directories."

        try:
            os.remove(file_path)
            return f"Successfully deleted file '{file_path}'."
        except PermissionError:
            return f"Error: Permission denied when deleting file '{file_path}'."
        except Exception as e:
            return f"Error deleting file: {str(e)}"