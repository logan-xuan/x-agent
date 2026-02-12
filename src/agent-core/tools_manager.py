"""LangChain-based tools manager for the x-agent2 system."""

from typing import Dict, Any, List, Optional
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
import subprocess
import os
from pathlib import Path
import requests


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query")


def web_search_tool_func(query: str) -> str:
    """Perform a web search using DuckDuckGo API."""
    try:
        # Using DuckDuckGo Instant Answer API (free and doesn't require API key)
        url = "https://api.duckduckgo.com/"
        params = {
            'q': query,
            'format': 'json',
            'no_html': '1',
            'skip_disambig': '1'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Format the results
        results = []
        if data.get('Abstract'):
            results.append(f"Summary: {data['Abstract']}")
        if data.get('AbstractURL'):
            results.append(f"Source: {data['AbstractURL']}")

        if data.get('RelatedTopics'):
            topics = data['RelatedTopics'][:3]  # Limit to first 3 topics
            for topic in topics:
                if 'Text' in topic and 'FirstURL' in topic:
                    results.append(f"- {topic['Text']}: {topic['FirstURL']}")

        if not results:
            return f"No clear results found for '{query}'. Try rephrasing your search."

        return "\n".join(results)

    except requests.exceptions.RequestException as e:
        return f"Error performing web search: {str(e)}"
    except Exception as e:
        return f"Unexpected error during web search: {str(e)}"


web_search_tool = StructuredTool.from_function(
    func=web_search_tool_func,
    name="web-search",
    description="Search the web for information",
    args_schema=WebSearchInput
)


class FileReadInput(BaseModel):
    file_path: str = Field(description="Path to the file to read")


def file_read_tool_func(file_path: str) -> str:
    """Read a file from the local filesystem."""
    try:
        file_path = Path(file_path)
        # Security check: ensure file is in allowed location
        if not str(file_path.resolve()).startswith(str(Path.cwd())):
            return "Error: Cannot access file outside working directory"

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Limit content size to prevent memory issues
            return content[:2000] + "..." if len(content) > 2000 else content
    except Exception as e:
        return f"Error reading file: {str(e)}"


file_read_tool = StructuredTool.from_function(
    func=file_read_tool_func,
    name="file-read",
    description="Read a file from the local filesystem",
    args_schema=FileReadInput
)


class FileWriteInput(BaseModel):
    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")


def file_write_tool_func(file_path: str, content: str) -> str:
    """Write content to a file in the local filesystem."""
    try:
        file_path = Path(file_path)
        # Security check: ensure file is in allowed location
        if not str(file_path.resolve()).startswith(str(Path.cwd())):
            return "Error: Cannot write file outside working directory"

        # Create directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


file_write_tool = StructuredTool.from_function(
    func=file_write_tool_func,
    name="file-write",
    description="Write content to a file in the local filesystem",
    args_schema=FileWriteInput
)


class CommandExecutionInput(BaseModel):
    command: str = Field(description="The command to execute")


def command_execution_tool_func(command: str) -> str:
    """Execute a command safely within controlled parameters."""
    # Security check: only allow safe commands
    forbidden_commands = ["rm", "mv", "dd", "kill", "chmod", "chown", "sudo", "su", "mount", "umount"]
    if any(forbidden in command.split() for forbidden in forbidden_commands):
        return "Error: Command not allowed for security reasons"

    try:
        # Execute command with timeout and limited output
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=os.getcwd()
        )

        output = result.stdout[:1000]  # Limit output size
        if result.stderr:
            output += f"\nError: {result.stderr[:500]}"

        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error executing command: {str(e)}"


command_execution_tool = StructuredTool.from_function(
    func=command_execution_tool_func,
    name="command-exec",
    description="Execute a command safely within controlled parameters",
    args_schema=CommandExecutionInput
)


class ToolsManager:
    """Manages LangChain tools for the agent system."""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.register_default_tools()

    def register_tool(self, tool: BaseTool):
        """Register a new tool."""
        self.tools[tool.name] = tool

    def register_default_tools(self):
        """Register the default tools for the system."""
        self.register_tool(web_search_tool)
        self.register_tool(file_read_tool)
        self.register_tool(file_write_tool)
        self.register_tool(command_execution_tool)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(name)

    def get_available_tools(self) -> List[BaseTool]:
        """Get all registered tools."""
        return list(self.tools.values())

    def execute_tool(self, name: str, **kwargs) -> str:
        """Execute a tool by name with given arguments."""
        tool = self.get_tool(name)
        if not tool:
            return f"Error: Tool '{name}' not found"

        try:
            return tool.invoke(kwargs)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"
