from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field


class BaseTool(StructuredTool, ABC):
    """
    Base class for all tools in the x-agent2 system.
    Inherits from LangChain's StructuredTool to ensure compatibility
    with LangChain's agent framework.
    """

    name: str
    description: str
    args_schema: Optional[type] = None

    def __init__(self, name: str, description: str, args_schema: Optional[type] = None, **kwargs):
        """
        Initialize the base tool with name, description, and optional args schema.

        Args:
            name: Name of the tool
            description: Description of what the tool does
            args_schema: Pydantic model defining the arguments for the tool
        """
        super().__init__(
            name=name,
            description=description,
            func=self._run,
            args_schema=args_schema,
            **kwargs
        )

    @abstractmethod
    def _run(self, *args, **kwargs) -> str:
        """
        Abstract method that all tools must implement.
        This method contains the actual logic for the tool.

        Args:
            *args: Arguments passed to the tool
            **kwargs: Keyword arguments passed to the tool

        Returns:
            Result of the tool execution as a string
        """
        pass