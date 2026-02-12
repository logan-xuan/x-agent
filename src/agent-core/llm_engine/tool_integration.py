from typing import Dict, Any, Optional, List
from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage
from .service import LLMEngineService
from ..tools_manager import ToolsManager


class ToolIntegrationService:
    """
    Integrates tool calling capabilities with the LLM engine.
    Uses LangChain's agent framework to enable LLMs to use tools.
    """

    def __init__(self, llm_service: LLMEngineService):
        self.llm_service = llm_service
        self.tools_manager = ToolsManager()
        self.agent_executor = None
        self._setup_agent()

    def _setup_agent(self):
        """Set up the LangChain agent with available tools."""
        # Get all available tools from the tools manager
        tools = self.tools_manager.get_available_tools()

        # Create a prompt template for the agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a helpful assistant that can use tools to get information. "
                       "Use the provided tools when needed to answer user questions. "
                       "Be concise and direct in your responses."),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])

        try:
            # Create a tool-calling agent
            agent = create_tool_calling_agent(
                llm=self.llm_service.primary_client,
                tools=tools,
                prompt=prompt
            )

            # Create the agent executor
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True  # This will show the thought process
            )
        except Exception as e:
            print(f"Error setting up agent: {str(e)}")
            # Fallback to manual tool calling implementation
            self.agent_executor = None

    def process_with_tools(self, user_input: str, context: Optional[str] = None) -> str:
        """
        Process user input using tools when appropriate.

        Args:
            user_input: The input from the user
            context: Additional context for the conversation

        Returns:
            Processed response that may include tool results
        """
        if self.agent_executor:
            # Use the agent to decide whether to use tools
            try:
                response = self.agent_executor.invoke({
                    "input": user_input
                })
                return response.get("output", "No response generated")
            except Exception as e:
                print(f"Agent execution failed: {str(e)}")
                # Fall back to regular LLM response
                return self.llm_service.generate_response(user_input, context)

        else:
            # Manual implementation: detect if tools should be used
            return self._manual_tool_processing(user_input, context)

    def _manual_tool_processing(self, user_input: str, context: Optional[str] = None) -> str:
        """
        Manual implementation for determining if and which tools to use.

        Args:
            user_input: The input from the user
            context: Additional context for the conversation

        Returns:
            Response that may include tool results
        """
        # Determine if any tools should be used based on the user input
        tool_decision = self._determine_tool_usage(user_input)

        if tool_decision["use_tool"]:
            # Execute the determined tool
            tool_result = self.tools_manager.execute_tool(
                tool_decision["tool_name"],
                **tool_decision["tool_args"]
            )

            # Generate final response incorporating the tool result
            augmented_input = f"Original request: {user_input}\n\nTool result: {tool_result}\n\nProvide a comprehensive answer based on this information."
            return self.llm_service.generate_response(augmented_input, context)
        else:
            # Just use regular LLM response
            return self.llm_service.generate_response(user_input, context)

    def _determine_tool_usage(self, user_input: str) -> Dict[str, Any]:
        """
        Determine if and which tool should be used based on user input.

        Args:
            user_input: The input from the user

        Returns:
            Dictionary with tool usage decision
        """
        user_lower = user_input.lower()

        # Define patterns to detect tool usage intent
        if any(keyword in user_lower for keyword in ["search", "find", "look up", "google", "web"]):
            # Extract search query
            query = self._extract_query(user_input, ["search", "find", "look up"])
            return {
                "use_tool": True,
                "tool_name": "web-search",
                "tool_args": {"query": query}
            }
        elif any(keyword in user_lower for keyword in ["read", "get", "show", "file"]):
            # This would require extracting file path from user input
            # Simplified implementation - in practice would need more sophisticated extraction
            return {
                "use_tool": True,
                "tool_name": "file-read",
                "tool_args": {"file_path": "placeholder.txt"}  # Would need actual extraction
            }
        elif any(keyword in user_lower for keyword in ["write", "save", "create file"]):
            # Would need to extract content and file path
            return {
                "use_tool": True,
                "tool_name": "file-write",
                "tool_args": {"file_path": "placeholder.txt", "content": "placeholder content"}
            }
        elif any(keyword in user_lower for keyword in ["run", "execute", "command", "shell"]):
            # Would need to extract command
            return {
                "use_tool": True,
                "tool_name": "command-exec",
                "tool_args": {"command": "echo 'placeholder command'"}
            }
        else:
            # No tool needed
            return {
                "use_tool": False,
                "tool_name": None,
                "tool_args": {}
            }

    def _extract_query(self, user_input: str, keywords: List[str]) -> str:
        """
        Extract search/query text from user input based on keywords.

        Args:
            user_input: Original user input
            keywords: Keywords that indicate a search is needed

        Returns:
            Extracted query string
        """
        # Find the keyword position and extract everything after it
        user_lower = user_input.lower()
        for keyword in keywords:
            pos = user_lower.find(keyword)
            if pos != -1:
                # Extract text after the keyword
                query_start = pos + len(keyword)
                query = user_input[query_start:].strip()

                # Remove common prefixes like "for", "about"
                if query.lower().startswith("for "):
                    query = query[4:].strip()
                elif query.lower().startswith("about "):
                    query = query[6:].strip()

                return query

        # If we can't find the keyword properly, return the original input
        return user_input

    def add_tool_to_agent(self, tool: BaseTool) -> bool:
        """
        Add a new tool to the agent dynamically.

        Args:
            tool: The tool to add

        Returns:
            True if successful, False otherwise
        """
        try:
            self.tools_manager.register_tool(tool)

            # Recreate the agent with the new tool
            self._setup_agent()

            return True
        except Exception as e:
            print(f"Error adding tool to agent: {str(e)}")
            return False