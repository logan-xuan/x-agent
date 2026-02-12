"""
Message handling service for the x-agent2 AI assistant system.

This module implements the core message processing logic, including:
- Message validation and sanitization
- Routing to appropriate handlers (chat, tools, subagents, etc.)
- Integration with LLM engine
- Response formatting and error handling
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from enum import Enum

from src.db.models.message import Message
from src.db.models.session import Session
from src.agent_core.llm_engine.integration import LLMIntegrationService
from src.agent_core.tools_manager import ToolsManager
from src.agent_core.subagents.management import SubAgentManager
from src.agent_core.context.memory_hooks import MemoryHooks
from src.gateway.session.db_session import DatabaseSessionManager


class MessageType(Enum):
    """Types of messages supported by the system."""
    TEXT = "text"
    FILE = "file"
    TOOL_CALL = "tool_call"
    TOOL_RESPONSE = "tool_response"
    SUBAGENT_COMMAND = "subagent_command"
    SYSTEM = "system"


class MessageHandler:
    """Handles the processing of messages in the AI assistant system."""

    def __init__(self):
        self.llm_integration = LLMIntegrationService()
        self.tools_manager = ToolsManager()
        self.subagent_manager = SubAgentManager()
        self.session_manager = DatabaseSessionManager()
        self.memory_hooks = MemoryHooks()

    async def process_message(
        self,
        user_input: str,
        session_id: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process an incoming message and return a response.

        Args:
            user_input: The user's message text
            session_id: The current session ID
            user_id: The user ID (optional)
            context: Additional context for the message

        Returns:
            Dictionary containing the response and metadata
        """
        # Validate and sanitize input
        if not user_input or not user_input.strip():
            return {
                "error": "Empty message received",
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id
            }

        # Retrieve session
        session = await self.session_manager.get_session(session_id)
        if not session:
            session = await self.session_manager.create_session(user_id)

        # Create message object
        message = Message(
            id=str(uuid.uuid4()),
            session_id=session.id,
            user_id=user_id,
            content={"type": MessageType.TEXT.value, "text": user_input},
            message_type=MessageType.TEXT.value,
            timestamp=datetime.utcnow(),
            metadata=context or {}
        )

        # Store incoming message
        await message.save()

        # Enhance with memory if available
        memory_context = await self.memory_hooks.retrieve_memory_context(
            session_id, user_input
        )

        # Process through LLM engine
        try:
            response_content = await self.llm_integration.process_with_context(
                user_input,
                memory_context,
                session_id,
                tools=self._get_available_tools()
            )

            # Create response message
            response_message = Message(
                id=str(uuid.uuid4()),
                session_id=session.id,
                user_id=user_id,
                content=response_content,
                message_type=MessageType.TEXT.value,
                timestamp=datetime.utcnow(),
                metadata={"is_response": True}
            )

            # Store response message
            await response_message.save()

            # Update memory with this interaction
            await self.memory_hooks.store_interaction(
                session_id,
                user_input,
                response_content
            )

            return {
                "response": response_content,
                "session_id": session.id,
                "timestamp": datetime.utcnow().isoformat(),
                "message_id": response_message.id
            }
        except Exception as e:
            # Log error
            print(f"Error processing message: {str(e)}")

            # Create error response message
            error_message = Message(
                id=str(uuid.uuid4()),
                session_id=session.id,
                user_id=user_id,
                content={
                    "type": "error",
                    "message": "Sorry, I encountered an error processing your request."
                },
                message_type="error",
                timestamp=datetime.utcnow(),
                metadata={"error": str(e)}
            )

            await error_message.save()

            return {
                "error": "Processing error occurred",
                "session_id": session.id,
                "timestamp": datetime.utcnow().isoformat(),
                "details": str(e)
            }

    async def process_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process a tool call request.

        Args:
            tool_name: Name of the tool to call
            parameters: Parameters for the tool
            session_id: Current session ID

        Returns:
            Tool execution result
        """
        try:
            # Validate tool and parameters
            if not self.tools_manager.is_tool_available(tool_name):
                return {
                    "error": f"Tool '{tool_name}' is not available",
                    "timestamp": datetime.utcnow().isoformat()
                }

            # Execute tool
            result = await self.tools_manager.execute_tool_async(
                tool_name,
                **parameters
            )

            # Store tool execution
            tool_execution_message = Message(
                id=str(uuid.uuid4()),
                session_id=session_id,
                content={
                    "type": MessageType.TOOL_CALL.value,
                    "tool_name": tool_name,
                    "parameters": parameters,
                    "result": result
                },
                message_type=MessageType.TOOL_CALL.value,
                timestamp=datetime.utcnow()
            )

            await tool_execution_message.save()

            return {
                "result": result,
                "tool_name": tool_name,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "success"
            }
        except Exception as e:
            return {
                "error": f"Tool execution failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed"
            }

    async def process_subagent_command(
        self,
        command: str,
        parameters: Dict[str, Any],
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process a subagent command.

        Args:
            command: The subagent command to execute
            parameters: Parameters for the command
            session_id: Current session ID

        Returns:
            Subagent execution result
        """
        try:
            # Activate subagent based on command
            result = await self.subagent_manager.process_command(
                command,
                parameters,
                session_id
            )

            # Store subagent execution
            subagent_message = Message(
                id=str(uuid.uuid4()),
                session_id=session_id,
                content={
                    "type": MessageType.SUBAGENT_COMMAND.value,
                    "command": command,
                    "parameters": parameters,
                    "result": result
                },
                message_type=MessageType.SUBAGENT_COMMAND.value,
                timestamp=datetime.utcnow()
            )

            await subagent_message.save()

            return {
                "result": result,
                "command": command,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "success"
            }
        except Exception as e:
            return {
                "error": f"Subagent command failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed"
            }

    def _get_available_tools(self) -> List[str]:
        """Get list of available tools for the current session."""
        return self.tools_manager.list_available_tools()

    async def process_file_upload(
        self,
        file_data: bytes,
        filename: str,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process a file upload.

        Args:
            file_data: Raw file data
            filename: Original filename
            session_id: Current session ID

        Returns:
            Processing result
        """
        try:
            # Sanitize filename
            import re
            sanitized_filename = re.sub(r'[^\w\-_\.]', '_', filename)

            # Determine file type
            file_extension = sanitized_filename.split('.')[-1].lower()

            # Store file in session workspace
            file_path = f"workspace/user-files/{session_id}/{sanitized_filename}"

            # Create directory if it doesn't exist
            import os
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Write file
            with open(file_path, 'wb') as f:
                f.write(file_data)

            # Create file message
            file_message = Message(
                id=str(uuid.uuid4()),
                session_id=session_id,
                content={
                    "type": MessageType.FILE.value,
                    "filename": sanitized_filename,
                    "file_path": file_path,
                    "size": len(file_data),
                    "extension": file_extension
                },
                message_type=MessageType.FILE.value,
                timestamp=datetime.utcnow()
            )

            await file_message.save()

            return {
                "status": "success",
                "file_path": file_path,
                "filename": sanitized_filename,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "error": f"File upload failed: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed"
            }


# Global message handler instance
message_handler = MessageHandler()