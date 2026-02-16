"""Base classes for X-Agent tools.

This module defines the tool interface that all X-Agent tools must implement.
Tools extend the agent's capabilities by providing executable actions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolParameterType(str, Enum):
    """JSON Schema parameter types."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """Definition of a tool parameter.
    
    Attributes:
        name: Parameter name
        type: Parameter type (JSON Schema type)
        description: Human-readable description
        required: Whether this parameter is required
        default: Default value if not provided
        enum: List of allowed values
    """
    name: str
    type: ToolParameterType = ToolParameterType.STRING
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None
    
    def to_json_schema(self) -> dict:
        """Convert to JSON Schema format."""
        schema: dict[str, Any] = {
            "type": self.type.value,
            "description": self.description,
        }
        
        if self.enum:
            schema["enum"] = self.enum
        
        if self.default is not None:
            schema["default"] = self.default
        
        return schema


@dataclass
class ToolResult:
    """Result of a tool execution.
    
    Attributes:
        success: Whether the execution was successful
        output: The output/result of the tool (for LLM consumption)
        error: Error message if execution failed
        metadata: Additional metadata about the execution
    """
    success: bool
    output: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, output: str, **metadata: Any) -> "ToolResult":
        """Create a successful result.
        
        Args:
            output: The output string
            **metadata: Additional metadata
            
        Returns:
            A successful ToolResult
        """
        return cls(success=True, output=output, metadata=metadata)
    
    @classmethod
    def error_result(cls, error: str, **metadata: Any) -> "ToolResult":
        """Create an error result.
        
        Args:
            error: Error message
            **metadata: Additional metadata
            
        Returns:
            A failed ToolResult
        """
        return cls(success=False, error=error, metadata=metadata)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """Abstract base class for all X-Agent tools.
    
    Tools provide executable actions that the agent can use to interact
    with the world. Each tool must define:
    - name: A unique identifier
    - description: What the tool does (for LLM understanding)
    - parameters: What parameters the tool accepts
    
    Example:
        class ReadFileTool(BaseTool):
            @property
            def name(self) -> str:
                return "read_file"
            
            @property
            def description(self) -> str:
                return "Read the contents of a file"
            
            @property
            def parameters(self) -> list[ToolParameter]:
                return [
                    ToolParameter(
                        name="file_path",
                        type=ToolParameterType.STRING,
                        description="Path to the file to read",
                        required=True,
                    )
                ]
            
            async def execute(self, file_path: str) -> ToolResult:
                try:
                    content = Path(file_path).read_text()
                    return ToolResult.ok(content)
                except Exception as e:
                    return ToolResult.error_result(str(e))
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool's unique name.
        
        This name is used in function calling and must be unique.
        Use snake_case convention (e.g., "read_file", "web_search").
        """
        pass
    
    @property
    def description(self) -> str:
        """Return a description of what the tool does.
        
        This is shown to the LLM when deciding which tool to use.
        Be specific about what the tool does and when to use it.
        """
        return ""
    
    @property
    def parameters(self) -> list[ToolParameter]:
        """Return the list of parameters this tool accepts.
        
        Override this to define the tool's parameters.
        """
        return []
    
    @abstractmethod
    async def execute(self, **params: Any) -> ToolResult:
        """Execute the tool with the given parameters.
        
        This is the main entry point for tool execution.
        Implementations should handle errors gracefully and return
        appropriate ToolResult.
        
        Args:
            **params: Tool parameters as keyword arguments
            
        Returns:
            ToolResult with success/failure and output
        """
        pass
    
    def get_parameter_schema(self) -> dict:
        """Get JSON Schema for all parameters.
        
        Returns:
            JSON Schema dict for the parameters object
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function calling format.
        
        Returns:
            Dict in OpenAI tool format
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameter_schema(),
            }
        }
    
    def validate_params(self, params: dict) -> tuple[bool, str | None]:
        """Validate parameters against the schema.
        
        Args:
            params: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            if param.required and param.name not in params:
                return False, f"Missing required parameter: {param.name}"
            
            if param.name in params:
                value = params[param.name]
                
                # Type check (basic)
                if param.type == ToolParameterType.STRING and not isinstance(value, str):
                    return False, f"Parameter '{param.name}' must be a string"
                elif param.type == ToolParameterType.NUMBER and not isinstance(value, (int, float)):
                    return False, f"Parameter '{param.name}' must be a number"
                elif param.type == ToolParameterType.INTEGER and not isinstance(value, int):
                    return False, f"Parameter '{param.name}' must be an integer"
                elif param.type == ToolParameterType.BOOLEAN and not isinstance(value, bool):
                    return False, f"Parameter '{param.name}' must be a boolean"
                
                # Enum check
                if param.enum and value not in param.enum:
                    return False, f"Parameter '{param.name}' must be one of: {param.enum}"
        
        return True, None
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
