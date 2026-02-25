"""Tool manager for registering and executing tools.

This module provides the ToolManager that:
- Registers and manages available tools
- Executes tool calls from the LLM
- Provides tools in OpenAI function calling format
"""

from typing import Any

from .base import BaseTool, ToolResult
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ToolNotAllowedError(Exception):
    """Exception raised when a tool is not allowed by skill constraints."""
    
    def __init__(self, message: str, allowed_tools: list[str] | None = None):
        super().__init__(message)
        self.allowed_tools = allowed_tools


class ToolManager:
    """Manager for tool registration and execution.
    
    The ToolManager maintains a registry of available tools and handles
    their execution when requested by the LLM.
    
    Example:
        manager = ToolManager()
        
        # Register tools
        manager.register(ReadFileTool())
        manager.register(WebSearchTool())
        
        # Get OpenAI format for LLM
        tools = manager.get_openai_tools()
        
        # Execute a tool call
        result = await manager.execute("read_file", {"file_path": "/tmp/test.txt"})
    """
    
    def __init__(self) -> None:
        """Initialize the tool manager."""
        self._tools: dict[str, BaseTool] = {}
        
        logger.info("ToolManager initialized")
    
    def _correct_tool_parameters(self, tool_name: str, arguments: dict) -> dict:
        """Correct known tool parameter mismatches to prevent execution failures.
        
        Args:
            tool_name: Name of the tool
            arguments: Original arguments from LLM
            
        Returns:
            Corrected arguments dictionary
        """
        corrected = arguments.copy()
        
        # Fix search_files tool parameter mismatch
        # LLM often uses 'search_dir' but the tool expects 'path'
        if tool_name == "search_files" and "search_dir" in corrected:
            corrected["path"] = corrected.pop("search_dir")
            logger.debug(
                "Fixed search_files parameter: search_dir -> path",
                extra={"tool_name": tool_name}
            )
        
        # Add more parameter corrections here as needed
        # Example pattern:
        # if tool_name == "some_tool" and "wrong_param" in corrected:
        #     corrected["correct_param"] = corrected.pop("wrong_param")
        
        return corrected
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool.
        
        Args:
            tool: The tool to register
            
        Raises:
            ValueError: If a tool with the same name already exists
        """
        if tool.name in self._tools:
            logger.warning(
                "Tool already registered, replacing",
                extra={"tool_name": tool.name}
            )
        
        self._tools[tool.name] = tool
        logger.info(
            "Tool registered",
            extra={
                "tool_name": tool.name,
                "description": tool.description[:50] if tool.description else "",
            }
        )
    
    def unregister(self, name: str) -> bool:
        """Unregister a tool.
        
        Args:
            name: Name of the tool to unregister
            
        Returns:
            True if the tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.info("Tool unregistered", extra={"tool_name": name})
            return True
        return False
    
    def get_tool(self, name: str) -> BaseTool | None:
        """Get a tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            The tool if found, None otherwise
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools.
        
        Returns:
            List of all registered tools
        """
        return list(self._tools.values())
    
    def get_tool_names(self) -> list[str]:
        """Get names of all registered tools.
        
        Returns:
            List of tool names
        """
        return list(self._tools.keys())
    
    def get_openai_tools(self) -> list[dict]:
        """Get all tools in OpenAI function calling format.
        
        Returns:
            List of tool definitions in OpenAI format
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]
    
    async def execute(
        self, 
        name: str, 
        params: dict[str, Any],
        skill_context: Any = None  # Phase 2 - Skill metadata for tool restrictions
    ) -> ToolResult:
        """Execute a tool by name.
        
        Args:
            name: Name of the tool to execute
            params: Parameters to pass to the tool
            skill_context: SkillMetadata object (optional, for tool restrictions)
            
        Returns:
            ToolResult with execution result
            
        Raises:
            ToolNotAllowedError: If the tool is not allowed by skill constraints
        """
        # Phase 2: Check if tool is allowed by skill constraints
        if skill_context and hasattr(skill_context, 'allowed_tools') and skill_context.allowed_tools:
            if name not in skill_context.allowed_tools:
                error_msg = (
                    f"Tool '{name}' is not allowed by skill '{skill_context.name}'. "
                    f"Allowed tools: {', '.join(skill_context.allowed_tools)}"
                )
                logger.warning(
                    "Tool blocked by skill constraints",
                    extra={
                        "tool_name": name,
                        "skill_name": skill_context.name,
                        "allowed_tools": skill_context.allowed_tools,
                    }
                )
                raise ToolNotAllowedError(error_msg, skill_context.allowed_tools)
        
        # Find tool
        tool = self._tools.get(name)
        if tool is None:
            logger.warning(
                "Tool not found",
                extra={"tool_name": name, "available_tools": list(self._tools.keys())}
            )
            return ToolResult.error_result(f"Tool not found: {name}")
        
        # Validate parameters
        is_valid, error = tool.validate_params(params)
        if not is_valid:
            logger.warning(
                "Tool parameter validation failed",
                extra={"tool_name": name, "error": error}
            )
            return ToolResult.error_result(error or "Invalid parameters")
        
        # Execute tool
        logger.info(
            "Executing tool",
            extra={
                "tool_name": name,
                "params": str(params)[:200],
            }
        )
        
        # ✅ FIX: Correct known tool parameter mismatches before execution
        params = self._correct_tool_parameters(name, params)
        
        try:
            result = await tool.execute(**params)
            
            logger.info(
                "Tool execution completed",
                extra={
                    "tool_name": name,
                    "success": result.success,
                    "output_length": len(result.output) if result.output else 0,
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Tool execution failed",
                extra={
                    "tool_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            return ToolResult.error_result(f"Tool execution failed: {str(e)}")
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered.
        
        Args:
            name: Tool name
            
        Returns:
            True if the tool is registered
        """
        return name in self._tools
    
    def get_stats(self) -> dict:
        """Get manager statistics.
        
        Returns:
            Dict with stats
        """
        return {
            "tools_count": len(self._tools),
            "tool_names": list(self._tools.keys()),
        }


# Global tool manager instance
_tool_manager: ToolManager | None = None


def get_tool_manager() -> ToolManager:
    """Get or create the global tool manager instance.
    
    Returns:
        ToolManager instance
    """
    global _tool_manager
    
    if _tool_manager is None:
        _tool_manager = ToolManager()
    
    return _tool_manager


def reset_tool_manager() -> None:
    """Reset the global tool manager."""
    global _tool_manager
    _tool_manager = None
