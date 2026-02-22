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
from src.utils.logger import get_logger

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
    
    MAX_ITERATIONS = 8  # Maximum ReAct iterations (increased from 5 to 8 for better plan execution)
    
    def __init__(
        self,
        llm_router: LLMRouter,
        tool_manager: ToolManager,
        max_iterations: int = 8,  # Increased default from 5 to 8
    ) -> None:
        """Initialize the ReAct loop.
        
        Args:
            llm_router: LLM router for making API calls
            tool_manager: Tool manager for executing tools
            max_iterations: Maximum number of iterations (default: 8 for complex tasks with plans)
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
        skill_context: Any = None,  # Phase 2 - Skill metadata for tool restrictions
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
            skill_context: SkillMetadata object (Phase 2, for tool restrictions)
            
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
        
        # Track iteration statistics
        actual_iterations = 0
        tool_calls_count = 0
        completed_early = False
        
        logger.info(
            "ReAct loop started",
            extra={
                "tools_count": len(tools) if tools else 0,
                "max_iterations": self.max_iterations,
                "session_id": session_id,
            }
        )
        
        for iteration in range(self.max_iterations):
            actual_iterations = iteration + 1
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
                        tool_calls_count += 1
                        
                        # Emit tool_call event
                        tool_call_event = {
                            "type": REACT_EVENT_TOOL_CALL,
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        }
                        logger.info(
                            "Emitting tool_call from react_loop",
                            extra={
                                "tool_call_id": tool_call.id,
                                "tool_call_name": tool_call.name,
                                "event_keys": list(tool_call_event.keys()),
                                "event_tool_call_id": tool_call_event.get("tool_call_id"),
                            }
                        )
                        yield tool_call_event
                        
                        # Execute tool
                        result = await self.tool_manager.execute(
                            tool_call.name,
                            tool_call.arguments,
                            skill_context=skill_context,  # Phase 2 - Pass skill context for tool restrictions
                        )
                        
                        # Check if this requires user confirmation - stop the loop
                        # Fix: Ensure metadata is a dict before accessing
                        metadata_dict = result.metadata if isinstance(result.metadata, dict) else {}
                        requires_confirmation = metadata_dict.get("requires_confirmation", False)
                        is_blocked = metadata_dict.get("is_blocked", False)
                        
                        # Emit tool_result event
                        logger.info(
                            "Emitting tool_result from react_loop",
                            extra={
                                "tool_call_id": tool_call.id,
                                "tool_call_name": tool_call.name,
                                "result_success": result.success,
                                "requires_confirmation": requires_confirmation,
                            }
                        )
                        yield {
                            "type": REACT_EVENT_TOOL_RESULT,
                            "tool_call_id": tool_call.id,
                            "tool_name": tool_call.name,
                            "success": result.success,
                            "output": result.output[:500] if result.output else "",
                            "error": result.error,
                            "result": {
                                "success": result.success,
                                "output": result.output,
                                "error": result.error,
                                "requires_confirmation": requires_confirmation,
                                "is_blocked": is_blocked,
                                # Fix: Ensure metadata is a dict before accessing
                                "confirmation_id": result.metadata.get("confirmation_id", "") if isinstance(result.metadata, dict) else "",
                                "command": result.metadata.get("command", "") if isinstance(result.metadata, dict) else "",
                            },
                        }
                        
                        # If command requires confirmation or is blocked, stop the loop
                        # User must confirm before the command can be executed
                        if requires_confirmation:
                            logger.info(
                                "ReAct loop paused - awaiting user confirmation",
                                extra={
                                    "tool_call_id": tool_call.id,
                                    "confirmation_id": metadata_dict.get("confirmation_id"),
                                }
                            )
                            # Emit a waiting event to tell frontend to wait for user
                            yield {
                                "type": "awaiting_confirmation",
                                "tool_call_id": tool_call.id,
                                "confirmation_id": metadata_dict.get("confirmation_id"),
                                "command": metadata_dict.get("command"),
                            }
                            # Don't continue the loop - wait for user action
                            return
                        
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
                
                # ===== SCHEME 1: Check if tool calls were required but not made =====
                # Detect if user message requires tool calls but LLM didn't call any
                if self._requires_tool_call_but_none_made(messages):
                    logger.warning(
                        "LLM responded without tool calls when tools were required",
                        extra={
                            "iteration": iteration + 1,
                            "response_preview": final_content[:200],
                        }
                    )
                    
                    # If this is within the first 2 iterations and no tools were called at all,
                    # give LLM another chance with explicit reminder
                    # Changed from (iteration == 0) to (iteration < 2) to allow more attempts
                    if iteration < 2 and tool_calls_count == 0:
                        # Add a system reminder to use tools
                        working_messages.append({
                            "role": "system",
                            "content": "⚠️ 注意：你需要调用实际的工具来完成这个任务，而不是只用文字回复。\n\n"
                                      "当用户要求创建/生成/制作任何具体产物（如 PPT、文件、代码等）时：\n"
                                      "1. 必须立即调用相应的工具（read_file, write_file, run_in_terminal）\n"
                                      "2. 绝不能用文字声称'已经完成'而不实际调用工具\n"
                                      "3. 只有在工具真正执行成功后才能告知用户完成\n\n"
                                      "请重新思考并调用适当的工具来完成任务。"
                        })
                        # Continue to next iteration to let LLM try again
                        continue
                
                completed_early = True
                
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
        utilization_rate = (actual_iterations / self.max_iterations * 100) if self.max_iterations > 0 else 0
        
        logger.warning(
            "ReAct loop reached max iterations",
            extra={
                "actual_iterations": actual_iterations,
                "max_iterations": self.max_iterations,
                "utilization_rate": f"{utilization_rate:.1f}%",
                "total_tool_calls": tool_calls_count,
                "completed_early": completed_early,
                "session_id": session_id,
            }
        )
        
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
    
    def _requires_tool_call_but_none_made(self, messages: list[dict]) -> bool:
        """Check if user message requires tool calls but LLM didn't make any.
        
        Detects common patterns that typically require tool execution:
        - File creation/modification requests
        - Code execution requests
        - Terminal command needs
        - Web search requests
        
        Args:
            messages: Conversation messages
            
        Returns:
            True if tool calls were likely required but not made
        """
        # Get last user message
        last_user_message = None
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                last_user_message = msg.get('content', '')
                break
        
        if not last_user_message:
            return False
        
        # Keywords that typically require tool calls
        tool_required_patterns = [
            # File operations
            r'创建.*文件|create.*file|write.*file|save.*file',
            r'删除.*文件|delete.*file|remove.*file',
            r'移动.*文件|move.*file|rename.*file',
            r'读取.*文件|read.*file|open.*file',
            
            # PPT/Document creation - expanded patterns
            r'创建.*PPT|create.*PPT|make.*presentation|generate.*PPT',
            r'创建.*文档|create.*document|make.*doc',
            r'生成.*PPT|generate.*presentation',
            r'制作.*幻灯片|make.*slides',
            r'制作.*PPT|制作一个.*PPT',  # "制作PPT" or "制作一个PPT"
            r'做.*PPT|做一个.*PPT',  # "做PPT" or "做一个PPT"
            r'需要.*PPT|需要制作.*PPT',  # "需要PPT" or "需要制作PPT"
            r'写.*脚本|write.*script|create.*script',
            
            # Code execution
            r'运行.*代码|run.*code|execute.*script',
            r'执行.*命令|execute.*command|run.*command',
            
            # Terminal operations
            r'安装.*库|install.*package|pip install',
            r'创建目录|create.*directory|mkdir',
            
            # Web search
            r'搜索.*信息|search.*information|look up',
            
            # Skill commands (CRITICAL: These MUST trigger tool calls)
            r'/pptx\s+',  # /pptx command followed by whitespace
            r'/xlsx\s+',  # /xlsx command
            r'/pdf\s+',   # /pdf command
            r'/skill\s+', # /skill command
            r'/browser-automation\s+',  # /browser-automation command
            r'/browser\s+',  # /browser shorthand command
        ]
        
        import re
        message_lower = last_user_message.lower()
        
        for pattern in tool_required_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
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
