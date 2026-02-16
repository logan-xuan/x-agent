"""ReAct loop implementation for X-Agent.

The ReAct (Reasoning + Acting) loop enables the agent to:
1. Think about what to do next
2. Decide whether to use a tool
3. Execute the tool if needed
4. Observe the result
5. Repeat until done

This creates an iterative problem-solving capability.
"""

import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Callable

from ..services.llm.router import LLMRouter
from ..tools.base import BaseTool, ToolResult
from ..tools.manager import ToolManager
from ..utils.logger import get_logger

logger = get_logger(__name__)


# ReAct event types
REACT_EVENT_THINKING = "thinking"
REACT_EVENT_TOOL_CALL = "tool_call"
REACT_EVENT_TOOL_RESULT = "tool_result"
REACT_EVENT_CHUNK = "chunk"
REACT_EVENT_FINAL = "final_answer"
REACT_EVENT_ERROR = "error"


@dataclass
class ToolCallRequest:
    """A request to call a tool from the LLM.
    
    Attributes:
        id: Unique ID for this tool call
        name: Name of the tool to call
        arguments: Arguments to pass to the tool
    """
    id: str
    name: str
    arguments: dict[str, Any]


class ReActLoop:
    """ReAct loop for iterative reasoning and action.
    
    Implements the ReAct pattern:
    - Reason about what to do
    - Act by calling tools
    - Observe the results
    - Repeat until task is complete
    
    Example:
        loop = ReActLoop(llm_router, tool_manager)
        
        # Streaming mode
        async for event in loop.run_streaming(messages):
            if event["type"] == "thinking":
                print(f"Thinking: {event['content']}")
            elif event["type"] == "tool_call":
                print(f"Calling tool: {event['name']}")
            elif event["type"] == "final_answer":
                print(f"Answer: {event['content']}")
    """
    
    MAX_ITERATIONS = 5  # Maximum ReAct iterations
    
    def __init__(
        self,
        llm_router: LLMRouter,
        tool_manager: ToolManager,
        max_iterations: int = 5,
    ) -> None:
        """Initialize the ReAct loop.
        
        Args:
            llm_router: LLM router for making API calls
            tool_manager: Tool manager for executing tools
            max_iterations: Maximum number of iterations
        """
        self.llm_router = llm_router
        self.tool_manager = tool_manager
        self.max_iterations = max_iterations
        
        logger.info(
            "ReActLoop initialized",
            extra={"max_iterations": max_iterations}
        )
    
    async def run(
        self,
        messages: list[dict[str, str]],
        tools: list[BaseTool] | None = None,
    ) -> str:
        """Run the ReAct loop (non-streaming).
        
        Args:
            messages: Conversation messages
            tools: Available tools (uses tool_manager if not provided)
            
        Returns:
            Final response string
        """
        result = ""
        async for event in self.run_streaming(messages, tools):
            if event.get("type") == REACT_EVENT_FINAL:
                result = event.get("content", "")
            elif event.get("type") == REACT_EVENT_ERROR:
                result = f"Error: {event.get('error', 'Unknown error')}"
        
        return result
    
    async def run_streaming(
        self,
        messages: list[dict[str, str]],
        tools: list[BaseTool] | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the ReAct loop with streaming events.
        
        Yields events as the loop progresses:
        - thinking: LLM is reasoning
        - tool_call: A tool is being called
        - tool_result: Result from tool execution
        - chunk: Response chunk from LLM
        - final_answer: Final response
        - error: An error occurred
        
        Args:
            messages: Conversation messages
            tools: Available tools (uses tool_manager if not provided)
            session_id: Optional session ID for logging
            
        Yields:
            Event dictionaries
        """
        # Use provided tools or get from manager
        if tools is None:
            tools = self.tool_manager.get_all_tools()
        
        # Get OpenAI tool definitions
        openai_tools = [tool.to_openai_tool() for tool in tools] if tools else None
        
        # Working message list
        working_messages = list(messages)
        
        logger.info(
            "ReAct loop started",
            extra={
                "tools_count": len(tools) if tools else 0,
                "max_iterations": self.max_iterations,
            }
        )
        
        for iteration in range(self.max_iterations):
            logger.debug(
                f"ReAct iteration {iteration + 1}/{self.max_iterations}"
            )
            
            try:
                # Call LLM with tools for function calling
                response = await self.llm_router.chat(
                    working_messages,
                    stream=False,
                    session_id=session_id,
                    tools=openai_tools,  # Pass tools for OpenAI function calling
                )
                
                # Check for tool calls in response
                tool_calls = self._extract_tool_calls(response)
                
                if tool_calls:
                    # Emit thinking event
                    yield {
                        "type": REACT_EVENT_THINKING,
                        "content": f"Iteration {iteration + 1}: Deciding to use tools",
                        "tool_calls": [tc.name for tc in tool_calls],
                    }
                    
                    # Process each tool call
                    for tool_call in tool_calls:
                        # Emit tool_call event
                        yield {
                            "type": REACT_EVENT_TOOL_CALL,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "id": tool_call.id,
                        }
                        
                        # Execute tool
                        result = await self.tool_manager.execute(
                            tool_call.name,
                            tool_call.arguments,
                        )
                        
                        # Emit tool_result event
                        yield {
                            "type": REACT_EVENT_TOOL_RESULT,
                            "tool_name": tool_call.name,
                            "success": result.success,
                            "output": result.output[:500] if result.output else "",
                            "error": result.error,
                        }
                        
                        # Add tool result to messages
                        working_messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": json.dumps(tool_call.arguments),
                                }
                            }]
                        })
                        working_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result.output if result.success else f"Error: {result.error}",
                        })
                    
                    # Continue to next iteration
                    continue
                
                # No tool calls - we have the final answer
                final_content = response.content if hasattr(response, 'content') else str(response)
                
                logger.info(
                    "ReAct loop completed",
                    extra={
                        "iterations": iteration + 1,
                        "response_length": len(final_content),
                    }
                )
                
                yield {
                    "type": REACT_EVENT_FINAL,
                    "content": final_content,
                }
                return
                
            except Exception as e:
                logger.error(
                    "ReAct iteration failed",
                    extra={
                        "iteration": iteration + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                
                yield {
                    "type": REACT_EVENT_ERROR,
                    "error": str(e),
                    "iteration": iteration + 1,
                }
                
                # Try to continue with next iteration
                continue
        
        # Max iterations reached
        logger.warning("ReAct loop reached max iterations")
        
        yield {
            "type": REACT_EVENT_ERROR,
            "error": f"Maximum iterations ({self.max_iterations}) reached without completing the task",
        }
    
    def _extract_tool_calls(self, response: Any) -> list[ToolCallRequest]:
        """Extract tool calls from LLM response.
        
        Handles different response formats from different providers:
        1. OpenAI standard function calling format
        2. XML format (used by some models like qwen)
        
        Args:
            response: LLM response object
            
        Returns:
            List of ToolCallRequest objects
        """
        tool_calls = []
        
        # Try LLMResponse with tool_calls field (our format)
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tc in response.tool_calls:
                # Handle dict format (from BailianProvider)
                if isinstance(tc, dict):
                    func = tc.get('function', {})
                    args = func.get('arguments', '{}')
                    if isinstance(args, str):
                        try:
                            arguments = json.loads(args)
                        except json.JSONDecodeError:
                            arguments = {"raw": args}
                    else:
                        arguments = args
                    
                    tool_calls.append(ToolCallRequest(
                        id=tc.get('id', ''),
                        name=func.get('name', ''),
                        arguments=arguments,
                    ))
                # Handle OpenAI object format
                elif hasattr(tc, 'function'):
                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            arguments = json.loads(args)
                        except json.JSONDecodeError:
                            arguments = {"raw": args}
                    else:
                        arguments = args
                    
                    tool_calls.append(ToolCallRequest(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    ))
        
        # Try dict format (legacy)
        elif isinstance(response, dict):
            if 'tool_calls' in response:
                for tc in response['tool_calls']:
                    args = tc.get('function', {}).get('arguments', {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except:
                            args = {"raw": args}
                    
                    tool_calls.append(ToolCallRequest(
                        id=tc.get('id', ''),
                        name=tc.get('function', {}).get('name', ''),
                        arguments=args,
                    ))
        
        # Try XML format tool calls (for models that don't support standard function calling)
        # Format: <function=name>\n<parameter=param_name>\nvalue\n</parameter>\n</function>
        if not tool_calls and hasattr(response, 'content') and response.content:
            xml_tool_calls = self._parse_xml_tool_calls(response.content)
            tool_calls.extend(xml_tool_calls)
        
        logger.debug(
            "Tool calls extracted",
            extra={"count": len(tool_calls), "names": [tc.name for tc in tool_calls]}
        )
        
        return tool_calls
    
    def _parse_xml_tool_calls(self, content: str) -> list[ToolCallRequest]:
        """Parse XML format tool calls from response content.
        
        Handles format like:
        <function=list_dir>
        <parameter=path>
        ~/Documents/x-agent/
        </parameter>
        </function>
        
        Also handles multiple parameters:
        <function=write_file>
        <parameter=path>
        /path/to/file
        </parameter>
        <parameter=content>
        file content here
        </parameter>
        </function>
        
        Args:
            content: Response text content
            
        Returns:
            List of ToolCallRequest objects
        """
        tool_calls = []
        
        # Match <function=name>...</function> blocks
        function_pattern = r'<function=([^>]+)>(.*?)</function>'
        function_matches = re.findall(function_pattern, content, re.DOTALL)
        
        for func_name, func_body in function_matches:
            arguments = {}
            
            # Match <parameter=name>value</parameter> within function body
            param_pattern = r'<parameter=([^>]+)>(.*?)</parameter>'
            param_matches = re.findall(param_pattern, func_body, re.DOTALL)
            
            for param_name, param_value in param_matches:
                # Clean up parameter value (strip whitespace)
                arguments[param_name.strip()] = param_value.strip()
            
            # If no parameters found but function has content, use as single argument
            if not arguments and func_body.strip():
                arguments["value"] = func_body.strip()
            
            tool_calls.append(ToolCallRequest(
                id=f"xml_{func_name}_{len(tool_calls)}",
                name=func_name.strip(),
                arguments=arguments,
            ))
            
            logger.info(
                "Parsed XML tool call",
                extra={"function": func_name, "arguments": arguments}
            )
        
        return tool_calls
