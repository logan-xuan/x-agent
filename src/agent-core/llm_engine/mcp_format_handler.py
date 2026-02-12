from typing import Dict, Any, Union
import json
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_core.tools import BaseTool


class MCPTaskFormatHandler:
    """
    Handles the formatting of tasks using Model Control Protocol (MCP) standards.
    Converts between various formats for tool calling and function definitions.
    """

    def __init__(self):
        pass

    def format_tool_for_mcp(self, tool: BaseTool) -> Dict[str, Any]:
        """
        Convert a LangChain tool to MCP-compatible format.

        Args:
            tool: LangChain BaseTool instance

        Returns:
            Dictionary in MCP-compatible format
        """
        # Convert the tool to OpenAI function format which is compatible with MCP
        function_def = convert_to_openai_function(tool)

        # Add MCP-specific fields
        mcp_format = {
            "name": function_def["name"],
            "description": function_def["description"],
            "inputSchema": {
                "type": "object",
                "properties": function_def["parameters"]["properties"],
                "required": function_def["parameters"].get("required", [])
            }
        }

        return mcp_format

    def format_multiple_tools_for_mcp(self, tools: list) -> Dict[str, Any]:
        """
        Convert multiple tools to MCP-compatible format.

        Args:
            tools: List of LangChain BaseTool instances

        Returns:
            Dictionary containing all tools in MCP format
        """
        mcp_tools = []
        for tool in tools:
            mcp_tools.append(self.format_tool_for_mcp(tool))

        return {
            "tools": mcp_tools
        }

    def parse_mcp_result(self, result: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Parse an MCP-formatted result to extract structured data.

        Args:
            result: Raw result from MCP call

        Returns:
            Parsed result as dictionary
        """
        if isinstance(result, str):
            try:
                # Try to parse as JSON if it's a string
                parsed_result = json.loads(result)
            except json.JSONDecodeError:
                # If not valid JSON, treat as plain text result
                parsed_result = {"output": result}
        elif isinstance(result, dict):
            parsed_result = result
        else:
            parsed_result = {"output": str(result)}

        return parsed_result

    def validate_mcp_format(self, data: Dict[str, Any]) -> bool:
        """
        Validate if the provided data follows MCP format conventions.

        Args:
            data: Data to validate

        Returns:
            True if valid MCP format, False otherwise
        """
        # Check if it has the basic structure of an MCP response
        if not isinstance(data, dict):
            return False

        # Check for MCP-specific fields
        has_tools = "tools" in data and isinstance(data["tools"], list)
        has_tool_calls = "tool_calls" in data

        return has_tools or has_tool_calls

    def convert_structured_output(self, raw_output: str) -> Dict[str, Any]:
        """
        Convert raw output to structured format according to MCP conventions.

        Args:
            raw_output: Raw output from LLM

        Returns:
            Structured output in MCP-compatible format
        """
        try:
            # Try to parse as JSON first
            structured_output = json.loads(raw_output)
        except json.JSONDecodeError:
            # If not valid JSON, wrap in a standard format
            structured_output = {
                "type": "text",
                "content": raw_output
            }

        # Ensure the output follows MCP conventions
        if isinstance(structured_output, dict) and "type" not in structured_output:
            structured_output["type"] = "object"

        return structured_output

    def create_mcp_call(self, tool_name: str, tool_arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an MCP-formatted tool call.

        Args:
            tool_name: Name of the tool to call
            tool_arguments: Arguments to pass to the tool

        Returns:
            Dictionary representing an MCP tool call
        """
        return {
            "type": "tool-call",
            "name": tool_name,
            "arguments": tool_arguments
        }

    def create_mcp_response(self, tool_call_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an MCP-formatted response to a tool call.

        Args:
            tool_call_id: ID of the original tool call
            result: Result from executing the tool

        Returns:
            Dictionary representing an MCP response
        """
        return {
            "type": "tool-response",
            "call_id": tool_call_id,
            "content": result
        }