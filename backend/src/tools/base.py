"""Base classes for X-Agent tools.

This module defines the tool interface that all X-Agent tools must implement.
Tools extend the agent's capabilities by providing executable actions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
import re


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
    """Definition of a tool parameter with advanced validation.
    
    Attributes:
        name: Parameter name
        type: Parameter type (JSON Schema type)
        description: Human-readable description
        required: Whether this parameter is required
        default: Default value if not provided
        enum: List of allowed values
        min_length: Minimum string length (for STRING type)
        max_length: Maximum string length (for STRING type)
        min_value: Minimum numeric value (for NUMBER/INTEGER type)
        max_value: Maximum numeric value (for NUMBER/INTEGER type)
        pattern: Regex pattern for validation (for STRING type)
        validator: Custom validation function (value) -> (is_valid, error_msg)
        
    Example:
        # String with length constraint
        ToolParameter(
            name="username",
            type=ToolParameterType.STRING,
            min_length=3,
            max_length=20,
            pattern=r"^[a-zA-Z0-9_]+$",
        )
        
        # Number with range constraint
        ToolParameter(
            name="port",
            type=ToolParameterType.INTEGER,
            min_value=1024,
            max_value=65535,
        )
        
        # Custom validator
        def validate_email(value):
            if "@" not in value:
                return False, "Invalid email format"
            return True, None
        
        ToolParameter(
            name="email",
            type=ToolParameterType.STRING,
            validator=validate_email,
        )
    """
    name: str
    type: ToolParameterType = ToolParameterType.STRING
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None
    
    # String validation
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None  # Regex pattern
    
    # Numeric validation
    min_value: float | int | None = None
    max_value: float | int | None = None
    
    # Custom validation
    validator: Callable[[Any], tuple[bool, str | None]] | None = None
    
    def to_json_schema(self) -> dict:
        """Convert to JSON Schema format with validation constraints."""
        schema: dict[str, Any] = {
            "type": self.type.value,
            "description": self.description,
        }
        
        # Add enum constraint
        if self.enum:
            schema["enum"] = self.enum
        
        # Add default value
        if self.default is not None:
            schema["default"] = self.default
        
        # Add string constraints
        if self.type == ToolParameterType.STRING:
            if self.min_length is not None:
                schema["minLength"] = self.min_length
            if self.max_length is not None:
                schema["maxLength"] = self.max_length
            if self.pattern is not None:
                schema["pattern"] = self.pattern
        
        # Add numeric constraints
        if self.type in (ToolParameterType.NUMBER, ToolParameterType.INTEGER):
            if self.min_value is not None:
                schema["minimum"] = self.min_value
            if self.max_value is not None:
                schema["maximum"] = self.max_value
        
        return schema
    
    def validate(self, value: Any) -> tuple[bool, str | None]:
        """Validate a parameter value against all constraints.
        
        Args:
            value: Value to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Type check (basic)
        if self.type == ToolParameterType.STRING and not isinstance(value, str):
            return False, f"Parameter '{self.name}' must be a string"
        elif self.type == ToolParameterType.NUMBER and not isinstance(value, (int, float)):
            return False, f"Parameter '{self.name}' must be a number"
        elif self.type == ToolParameterType.INTEGER and not isinstance(value, int):
            return False, f"Parameter '{self.name}' must be an integer"
        elif self.type == ToolParameterType.BOOLEAN and not isinstance(value, bool):
            return False, f"Parameter '{self.name}' must be a boolean"
        
        # Enum check
        if self.enum and value not in self.enum:
            return False, f"Parameter '{self.name}' must be one of: {self.enum}"
        
        # String-specific validation
        if self.type == ToolParameterType.STRING and isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                return False, f"Parameter '{self.name}' must be at least {self.min_length} characters"
            if self.max_length is not None and len(value) > self.max_length:
                return False, f"Parameter '{self.name}' must be at most {self.max_length} characters"
            if self.pattern is not None:
                try:
                    if not re.match(self.pattern, value):
                        return False, f"Parameter '{self.name}' does not match required pattern"
                except re.error as e:
                    return False, f"Invalid regex pattern for '{self.name}': {e}"
        
        # Numeric-specific validation
        if self.type in (ToolParameterType.NUMBER, ToolParameterType.INTEGER):
            if isinstance(value, (int, float)):
                if self.min_value is not None and value < self.min_value:
                    return False, f"Parameter '{self.name}' must be at least {self.min_value}"
                if self.max_value is not None and value > self.max_value:
                    return False, f"Parameter '{self.name}' must be at most {self.max_value}"
        
        # Custom validator
        if self.validator is not None:
            try:
                is_valid, error_msg = self.validator(value)
                if not is_valid:
                    return False, error_msg or f"Parameter '{self.name}' failed custom validation"
            except Exception as e:
                return False, f"Validation error for '{self.name}': {str(e)}"
        
        return True, None


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
        """Validate parameters against the schema with enhanced validation.
        
        Args:
            params: Parameters to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        for param in self.parameters:
            # Check required parameters
            if param.required and param.name not in params:
                return False, f"Missing required parameter: {param.name}"
            
            # Validate parameter value if present
            if param.name in params:
                value = params[param.name]
                is_valid, error_msg = param.validate(value)
                if not is_valid:
                    return False, error_msg
        
        return True, None
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"
