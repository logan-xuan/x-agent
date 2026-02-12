from typing import Dict, Any, Optional
from ..tools_manager import ToolsManager
from ..llm_engine.service import LLMEngineService
from ...db.models.tool_execution import ToolExecution
from sqlalchemy.orm import Session
from datetime import datetime


class ToolExecutionService:
    """
    Service for executing tools and managing their execution lifecycle.
    Integrates with the LLM engine to enable tool calling capabilities.
    """

    def __init__(self, db_session: Session, llm_service: LLMEngineService):
        self.db_session = db_session
        self.llm_service = llm_service
        self.tools_manager = ToolsManager()

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any], session_id: str, message_id: str) -> str:
        """
        Execute a tool with the given parameters and record the execution.

        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters to pass to the tool
            session_id: ID of the session in which the tool is being executed
            message_id: ID of the message that triggered the tool execution

        Returns:
            Result of the tool execution
        """
        # Create a tool execution record
        tool_execution = ToolExecution(
            session_id=session_id,
            message_id=message_id,
            tool_name=tool_name,
            parameters=parameters,
            execution_status="running",
            started_at=datetime.utcnow()
        )

        self.db_session.add(tool_execution)
        self.db_session.commit()

        try:
            # Execute the tool
            result = self.tools_manager.execute_tool(tool_name, **parameters)

            # Update the tool execution record with results
            tool_execution.result_data = {"output": result}
            tool_execution.execution_status = "succeeded"
            tool_execution.completed_at = datetime.utcnow()

            self.db_session.commit()

            return result

        except Exception as e:
            # Handle execution error
            error_msg = str(e)
            tool_execution.error_message = error_msg
            tool_execution.execution_status = "failed"
            tool_execution.completed_at = datetime.utcnow()

            self.db_session.commit()

            return f"Error executing tool '{tool_name}': {error_msg}"

    def get_available_tools(self) -> str:
        """
        Get a list of all available tools with their descriptions.

        Returns:
            Formatted string listing all available tools
        """
        return self.tools_manager.list_available_tools()

    def register_custom_tool(self, tool) -> bool:
        """
        Register a custom tool with the tools manager.

        Args:
            tool: The tool to register

        Returns:
            True if registration was successful, False otherwise
        """
        try:
            self.tools_manager.register_tool(tool)
            return True
        except Exception:
            return False