"""ReAct loop implementation for X-Agent.

The ReAct (Reasoning + Acting) loop enables the agent to:
1. Think about what to do next
2. Decide whether to use a tool
3. Execute the tool if needed
4. Observe the result
5. Reflect on the outcome and adjust strategy
6. Repeat until done

This creates an iterative problem-solving capability with self-reflection.
"""

import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ..services.llm.router import LLMRouter
from ..tools.base import BaseTool, ToolResult
from ..tools.manager import ToolManager
from src.utils.logger import get_logger

logger = get_logger(__name__)

__all__ = [
    # Event types
    "REACT_EVENT_THINKING",
    "REACT_EVENT_TOOL_CALL",
    "REACT_EVENT_TOOL_RESULT",
    "REACT_EVENT_CHUNK",
    "REACT_EVENT_FINAL",
    "REACT_EVENT_ERROR",
    "REACT_EVENT_REFLECTION",
    "REACT_EVENT_STRATEGY_ADJUSTMENT",
    # Data classes
    "ReflectionType",
    "ReflectionResult",
    "ReflectionRecord",
    "ToolExecutionRecord",
    "StrategyState",
    "ToolCallRequest",
    # Main class
    "ReActLoop",
]


# ReAct event types
REACT_EVENT_THINKING = "thinking"
REACT_EVENT_TOOL_CALL = "tool_call"
REACT_EVENT_TOOL_RESULT = "tool_result"
REACT_EVENT_CHUNK = "chunk"
REACT_EVENT_FINAL = "final_answer"
REACT_EVENT_ERROR = "error"
REACT_EVENT_REFLECTION = "reflection"  # NEW: Reflection event
REACT_EVENT_STRATEGY_ADJUSTMENT = "strategy_adjustment"  # NEW: Strategy adjustment event


class ReflectionType(str, Enum):
    """Types of reflection in the ReAct loop."""
    TOOL_RESULT = "tool_result"  # Reflect on tool execution result
    PLAN_ADJUSTMENT = "plan_adjustment"  # Reflect and adjust plan
    FAILURE_ANALYSIS = "failure_analysis"  # Analyze failure and suggest recovery
    FINAL_VERIFICATION = "final_verification"  # Verify final answer completeness


@dataclass
class ReflectionResult:
    """Result of a reflection operation.
    
    Attributes:
        should_adjust: Whether strategy adjustment is needed
        reason: Explanation of the reflection
        suggestion: Suggested adjustment or correction
        confidence: Confidence level (0.0-1.0)
        adjusted_plan: Optional adjusted plan
    """
    should_adjust: bool
    reason: str
    suggestion: str
    confidence: float = 0.5
    adjusted_plan: str | None = None


@dataclass
class ToolExecutionRecord:
    """Record of a tool execution for pattern analysis.
    
    Attributes:
        tool_name: Name of the tool
        arguments: Tool arguments
        success: Whether execution succeeded
        output: Execution output
        error: Error message if failed
        iteration: Iteration number when executed
    """
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    output: str
    error: str | None
    iteration: int


@dataclass
class ReflectionRecord:
    """Record of a reflection event.
    
    Attributes:
        iteration: Iteration number when reflection occurred
        reflection_type: Type of reflection
        reason: Explanation of the reflection
        suggestion: Suggested adjustment
        timestamp: When the reflection occurred
    """
    iteration: int
    reflection_type: str
    reason: str
    suggestion: str
    timestamp: float = field(default_factory=lambda: __import__('time').time())


@dataclass
class StrategyState:
    """Track strategy state for adaptive behavior.
    
    Attributes:
        consecutive_failures: Number of consecutive tool failures
        same_tool_repeated: Count of same tool being called repeatedly
        last_tool_name: Name of last executed tool
        adjustment_count: Number of strategy adjustments made
        failed_tool_patterns: Set of tools that have failed
        reflection_history: List of past reflections
    """
    consecutive_failures: int = 0
    same_tool_repeated: int = 0
    last_tool_name: str | None = None
    adjustment_count: int = 0
    failed_tool_patterns: set[str] = field(default_factory=set)
    reflection_history: list[ReflectionRecord] = field(default_factory=list)
    tool_execution_history: list[ToolExecutionRecord] = field(default_factory=list)


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
    """ReAct loop for iterative reasoning and action with self-reflection.
    
    Implements the ReAct pattern with enhanced self-reflection:
    - Reason about what to do
    - Act by calling tools
    - Observe the results
    - Reflect on outcomes and adjust strategy
    - Repeat until task is complete
    
    Example:
        loop = ReActLoop(llm_router, tool_manager)
        
        # Streaming mode
        async for event in loop.run_streaming(messages):
            if event["type"] == "thinking":
                print(f"Thinking: {event['content']}")
            elif event["type"] == "tool_call":
                print(f"Calling tool: {event['name']}")
            elif event["type"] == "reflection":
                print(f"Reflection: {event['content']}")
            elif event["type"] == "final_answer":
                print(f"Answer: {event['content']}")
    """
    
    MAX_ITERATIONS = 8  # Maximum ReAct iterations
    MAX_CONSECUTIVE_FAILURES = 2  # Max failures before strategy adjustment
    MAX_SAME_TOOL_REPEATS = 2  # Max repeats of same tool before suggesting alternative
    MAX_ADJUSTMENTS = 3  # Max strategy adjustments to prevent infinite loops
    
    def __init__(
        self,
        llm_router: LLMRouter,
        tool_manager: ToolManager,
        max_iterations: int = 8,
        enable_reflection: bool = True,  # NEW: Enable/disable reflection
    ) -> None:
        """Initialize the ReAct loop.
        
        Args:
            llm_router: LLM router for making API calls
            tool_manager: Tool manager for executing tools
            max_iterations: Maximum number of iterations
            enable_reflection: Whether to enable self-reflection capabilities
        """
        self.llm_router = llm_router
        self.tool_manager = tool_manager
        self.max_iterations = max_iterations
        self.enable_reflection = enable_reflection
        
        logger.info(
            "ReActLoop initialized",
            extra={
                "max_iterations": max_iterations,
                "enable_reflection": enable_reflection,
            }
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
        
        # Initialize strategy state for reflection and adjustment
        strategy_state = StrategyState()
        
        logger.info(
            "ReAct loop started",
            extra={
                "tools_count": len(tools) if tools else 0,
                "max_iterations": self.max_iterations,
                "session_id": session_id,
                "enable_reflection": self.enable_reflection,
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
                        
                        # ===== PHASE 2: Tool Constraint Validation BEFORE execution =====
                        # Check if this tool is allowed based on skill_context
                        if skill_context and hasattr(skill_context, 'allowed_tools') and skill_context.allowed_tools:
                            if tool_call.name not in skill_context.allowed_tools:
                                logger.warning(
                                    "Tool call blocked by skill constraints (ReAct Loop)",
                                    extra={
                                        "tool_name": tool_call.name,
                                        "allowed_tools": skill_context.allowed_tools,
                                        "skill_name": getattr(skill_context, 'name', 'unknown'),
                                    }
                                )
                                
                                # Add system message to inform LLM about the constraint
                                working_messages.append({
                                    "role": "system",
                                    "content": f"⚠️ 工具 '{tool_call.name}' 不可用。当前技能 '{skill_context.name}' 只允许使用以下工具：{skill_context.allowed_tools}。请选择允许的工具重新尝试。"
                                })
                                
                                # Skip this tool call - don't execute it
                                continue
                        
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
                        
                        # Record tool execution for pattern analysis
                        execution_record = ToolExecutionRecord(
                            tool_name=tool_call.name,
                            arguments=tool_call.arguments,
                            success=result.success,
                            output=result.output if result.output else "",
                            error=result.error,
                            iteration=actual_iterations,
                        )
                        strategy_state.tool_execution_history.append(execution_record)
                        
                        # Update strategy state
                        self._update_strategy_state(strategy_state, tool_call.name, result.success)
                        
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
                        
                        # ===== REFLECTION: Analyze tool execution result =====
                        if self.enable_reflection:
                            reflection = await self._reflect_on_tool_result(
                                tool_call.name,
                                result,
                                strategy_state,
                            )
                            
                            if reflection.should_adjust and strategy_state.adjustment_count < self.MAX_ADJUSTMENTS:
                                strategy_state.adjustment_count += 1
                                strategy_state.reflection_history.append(ReflectionRecord(
                                    iteration=actual_iterations,
                                    reflection_type=ReflectionType.TOOL_RESULT.value,
                                    reason=reflection.reason,
                                    suggestion=reflection.suggestion,
                                ))
                                
                                # Emit reflection event
                                yield {
                                    "type": REACT_EVENT_REFLECTION,
                                    "reflection_type": ReflectionType.TOOL_RESULT.value,
                                    "content": reflection.reason,
                                    "suggestion": reflection.suggestion,
                                    "confidence": reflection.confidence,
                                }
                                
                                # Emit strategy adjustment event
                                yield {
                                    "type": REACT_EVENT_STRATEGY_ADJUSTMENT,
                                    "reason": reflection.reason,
                                    "suggestion": reflection.suggestion,
                                    "adjustment_count": strategy_state.adjustment_count,
                                }
                                
                                # Add reflection guidance to messages
                                working_messages.append({
                                    "role": "system",
                                    "content": f"🤔 **执行反思**\n\n{reflection.reason}\n\n**建议调整**：{reflection.suggestion}",
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
                
                # ===== NEW: Check if LLM repeatedly violated tool constraints =====
                # If LLM keeps trying forbidden tools, provide explicit guidance
                if tool_calls_count == 0 and iteration >= 1:
                    # No valid tool calls made in this iteration
                    # Check if there were constraint violations
                    working_messages.append({
                        "role": "system",
                        "content": "💡 提示：你刚才尝试使用的工具不在当前技能的允许列表中。\n\n"
                                  "请仔细查看 System Prompt 中的技能说明，只使用明确列出的工具。\n"
                                  "如果不确定应该用什么工具，请先分析任务需求，然后选择最匹配的工具。"
                    })
                
                completed_early = True
                
                # ===== REFLECTION: Verify final answer before returning =====
                if self.enable_reflection:
                    # Get original user query
                    original_query = ""
                    for msg in messages:
                        if msg.get("role") == "user":
                            original_query = msg.get("content", "")
                            break
                    
                    final_reflection = await self._reflect_on_final_answer(
                        final_content,
                        original_query,
                        working_messages,
                    )
                    
                    if final_reflection.should_adjust:
                        # Add verification feedback and give LLM one more chance
                        working_messages.append({
                            "role": "system",
                            "content": f"🔍 **最终答案验证**\n\n{final_reflection.reason}\n\n**改进建议**：{final_reflection.suggestion}",
                        })
                        
                        yield {
                            "type": REACT_EVENT_REFLECTION,
                            "reflection_type": ReflectionType.FINAL_VERIFICATION.value,
                            "content": final_reflection.reason,
                            "suggestion": final_reflection.suggestion,
                        }
                        
                        # Continue to next iteration for improvement
                        continue
                
                logger.info(
                    "ReAct loop completed",
                    extra={
                        "iterations": iteration + 1,
                        "response_length": len(final_content),
                        "strategy_summary": self.get_strategy_summary(strategy_state),
                    }
                )
                
                yield {
                    "type": REACT_EVENT_FINAL,
                    "content": final_content,
                    "reflection_count": len(strategy_state.reflection_history),
                    "adjustment_count": strategy_state.adjustment_count,
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
        
        # Generate failure analysis
        failure_analysis = self._generate_failure_analysis(strategy_state, actual_iterations)
        
        logger.warning(
            "ReAct loop reached max iterations",
            extra={
                "actual_iterations": actual_iterations,
                "max_iterations": self.max_iterations,
                "utilization_rate": f"{utilization_rate:.1f}%",
                "total_tool_calls": tool_calls_count,
                "completed_early": completed_early,
                "session_id": session_id,
                "strategy_summary": self.get_strategy_summary(strategy_state),
                "failure_analysis": failure_analysis,
            }
        )
        
        # ALWAYS emit failure reflection event when max iterations reached
        # This helps with debugging and understanding why the loop didn't complete
        yield {
            "type": REACT_EVENT_REFLECTION,
            "reflection_type": ReflectionType.FAILURE_ANALYSIS.value,
            "content": failure_analysis["primary_reason"],
            "suggestion": failure_analysis["recommendation"],
            "failure_details": failure_analysis,
        }
        
        yield {
            "type": REACT_EVENT_ERROR,
            "error": f"Maximum iterations ({self.max_iterations}) reached without completing the task",
            "failure_analysis": failure_analysis,
            "strategy_summary": self.get_strategy_summary(strategy_state),
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
    
    def _update_strategy_state(
        self,
        state: StrategyState,
        tool_name: str,
        success: bool,
    ) -> None:
        """Update strategy state based on tool execution result.
        
        Args:
            state: Current strategy state
            tool_name: Name of the executed tool
            success: Whether execution succeeded
        """
        if success:
            # Reset consecutive failures on success
            state.consecutive_failures = 0
        else:
            # Increment consecutive failures
            state.consecutive_failures += 1
            state.failed_tool_patterns.add(tool_name)
        
        # Track repeated tool usage
        if tool_name == state.last_tool_name:
            state.same_tool_repeated += 1
        else:
            state.same_tool_repeated = 0
            state.last_tool_name = tool_name
    
    async def _reflect_on_tool_result(
        self,
        tool_name: str,
        result: ToolResult,
        state: StrategyState,
    ) -> ReflectionResult:
        """Reflect on tool execution result and determine if strategy adjustment is needed.
        
        Args:
            tool_name: Name of the tool that was executed
            result: Tool execution result
            state: Current strategy state
            
        Returns:
            ReflectionResult with analysis and adjustment suggestion
        """
        # Case 1: Tool execution failed
        if not result.success:
            # Check for repeated failures
            if state.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                return ReflectionResult(
                    should_adjust=True,
                    reason=f"工具 '{tool_name}' 已连续失败 {state.consecutive_failures} 次",
                    suggestion="请尝试：1) 检查参数是否正确；2) 换用其他工具；3) 调整任务策略",
                    confidence=0.8,
                )
            
            # Single failure - provide specific guidance based on error
            error_lower = (result.error or "").lower()
            if "not found" in error_lower or "不存在" in error_lower:
                return ReflectionResult(
                    should_adjust=True,
                    reason=f"目标文件/路径不存在",
                    suggestion="请检查路径是否正确，或先使用 list_dir 查看可用文件",
                    confidence=0.7,
                )
            elif "permission" in error_lower or "权限" in error_lower:
                return ReflectionResult(
                    should_adjust=True,
                    reason="权限不足，无法执行该操作",
                    suggestion="请尝试其他方法，或向用户说明需要更高权限",
                    confidence=0.7,
                )
            elif "timeout" in error_lower or "超时" in error_lower:
                return ReflectionResult(
                    should_adjust=True,
                    reason="操作超时",
                    suggestion="请尝试简化操作，或分步骤执行",
                    confidence=0.6,
                )
            else:
                return ReflectionResult(
                    should_adjust=True,
                    reason=f"工具执行失败: {result.error}",
                    suggestion="请分析错误原因，调整参数后重试，或尝试其他工具",
                    confidence=0.5,
                )
        
        # Case 2: Tool succeeded but might need verification
        if result.success:
            # Check for empty or suspicious results
            # Note: Some tools returning empty results is normal (e.g., list_dir on empty directory)
            output = result.output or ""
            if len(output.strip()) == 0 and not self._is_empty_result_normal(tool_name):
                return ReflectionResult(
                    should_adjust=True,
                    reason=f"工具 '{tool_name}' 返回了空结果",
                    suggestion="请检查参数是否正确，或尝试其他工具获取信息",
                    confidence=0.6,
                )
            
            # Check for repeated same tool usage (possible loop)
            if state.same_tool_repeated >= self.MAX_SAME_TOOL_REPEATS:
                return ReflectionResult(
                    should_adjust=True,
                    reason=f"连续多次使用同一工具 '{tool_name}'，可能存在循环",
                    suggestion="请重新评估任务策略，尝试不同的方法或工具组合",
                    confidence=0.75,
                )
        
        # No adjustment needed
        return ReflectionResult(
            should_adjust=False,
            reason="工具执行成功",
            suggestion="继续执行",
            confidence=0.9,
        )
    
    async def _reflect_on_plan_progress(
        self,
        original_plan: str,
        completed_steps: list[str],
        current_step: int,
        state: StrategyState,
    ) -> ReflectionResult:
        """Reflect on plan execution progress and suggest adjustments.
        
        Args:
            original_plan: Original plan text
            completed_steps: List of completed step descriptions
            current_step: Current step number
            state: Current strategy state
            
        Returns:
            ReflectionResult with plan adjustment suggestion
        """
        total_steps = len(original_plan.split("\n")) if original_plan else 0
        progress = len(completed_steps) / total_steps if total_steps > 0 else 0
        
        # Check if progress is too slow
        if state.adjustment_count < self.MAX_ADJUSTMENTS:
            if progress < 0.3 and state.consecutive_failures > 0:
                return ReflectionResult(
                    should_adjust=True,
                    reason="任务进展缓慢，遇到多次失败",
                    suggestion="建议简化计划，优先完成核心任务，或寻求用户澄清",
                    confidence=0.7,
                    adjusted_plan=None,  # Could generate simplified plan here
                )
            
            # Check if too many steps have been attempted
            if len(state.tool_execution_history) > total_steps * 2:
                return ReflectionResult(
                    should_adjust=True,
                    reason="执行步骤数远超计划步骤，可能存在效率问题",
                    suggestion="请重新评估当前方法，考虑更直接的解决方案",
                    confidence=0.6,
                )
        
        return ReflectionResult(
            should_adjust=False,
            reason="计划执行正常",
            suggestion="继续按计划执行",
            confidence=0.8,
        )
    
    async def _reflect_on_final_answer(
        self,
        draft_answer: str,
        original_query: str,
        messages: list[dict[str, str]],
    ) -> ReflectionResult:
        """Reflect on final answer before returning to user.
        
        Args:
            draft_answer: Draft final answer
            original_query: Original user query
            messages: Full conversation history
            
        Returns:
            ReflectionResult with verification result
        """
        # Check for incomplete indicators - uncertainty expressions
        incomplete_indicators = [
            "我不确定", "可能", "大概", "也许", "不确定", "不清楚",
            "i'm not sure", "maybe", "possibly", "perhaps", "uncertain",
        ]
        if any(indicator in draft_answer.lower() for indicator in incomplete_indicators):
            return ReflectionResult(
                should_adjust=True,
                reason="回答中包含不确定性表述",
                suggestion="如果信息不确定，请明确说明，或尝试获取更多可靠信息",
                confidence=0.6,
            )
        
        # Check for placeholder or incomplete response patterns
        incomplete_patterns = [
            r"我需要.*才能", r"请提供.*信息", r"缺少.*数据",
            r"i need.*to", r"please provide.*information", r"missing.*data",
        ]
        import re
        for pattern in incomplete_patterns:
            if re.search(pattern, draft_answer.lower()):
                return ReflectionResult(
                    should_adjust=True,
                    reason="回答暗示需要更多信息才能完成",
                    suggestion="请明确告知用户需要哪些具体信息，或尝试用现有信息尽可能回答",
                    confidence=0.65,
                )
        
        # Check answer length appropriateness
        # Too short might be incomplete, too long might be unfocused
        answer_length = len(draft_answer)
        if answer_length < 20 and len(original_query) > 20:
            return ReflectionResult(
                should_adjust=True,
                reason="回答过于简短，可能不够完整",
                suggestion="请提供更详细的解释或步骤说明",
                confidence=0.5,
            )
        
        return ReflectionResult(
            should_adjust=False,
            reason="回答完整且相关",
            suggestion="可以返回给用户",
            confidence=0.85,
        )
    
    def get_strategy_summary(self, state: StrategyState) -> dict[str, Any]:
        """Get summary of strategy state for debugging.
        
        Args:
            state: Strategy state to summarize
            
        Returns:
            Dictionary with strategy summary
        """
        return {
            "consecutive_failures": state.consecutive_failures,
            "same_tool_repeated": state.same_tool_repeated,
            "last_tool_name": state.last_tool_name,
            "adjustment_count": state.adjustment_count,
            "failed_tool_patterns": list(state.failed_tool_patterns),
            "reflection_count": len(state.reflection_history),
            "tool_execution_count": len(state.tool_execution_history),
            "success_rate": (
                sum(1 for r in state.tool_execution_history if r.success) / len(state.tool_execution_history)
                if state.tool_execution_history else 0
            ),
        }
    
    def _is_empty_result_normal(self, tool_name: str) -> bool:
        """Check if empty result is normal for this tool.
        
        Some tools legitimately return empty results in certain cases.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            True if empty result is expected/acceptable for this tool
        """
        # Tools that can legitimately return empty results
        tools_allowing_empty = {
            "list_dir",           # Empty directory is valid
            "search_files",       # No matches found is valid
            "aliyun_web_search",  # No search results is valid
            "web_search",         # No search results is valid
            "fetch_web_content",  # Empty page or 404 is possible
        }
        return tool_name in tools_allowing_empty
    
    def _generate_failure_analysis(
        self,
        state: StrategyState,
        iterations: int,
    ) -> dict[str, Any]:
        """Generate failure analysis when max iterations is reached.
        
        Args:
            state: Strategy state
            iterations: Number of iterations executed
            
        Returns:
            Dictionary with failure analysis
        """
        analysis = {
            "primary_reason": "",
            "contributing_factors": [],
            "recommendation": "",
            "suggested_user_action": "",
        }
        
        # Determine primary reason
        if state.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            analysis["primary_reason"] = "连续多次工具执行失败"
            analysis["contributing_factors"].append(f"工具失败模式: {list(state.failed_tool_patterns)}")
        elif state.same_tool_repeated >= self.MAX_SAME_TOOL_REPEATS:
            analysis["primary_reason"] = "可能陷入工具调用循环"
            analysis["contributing_factors"].append(f"重复工具: {state.last_tool_name}")
        elif state.adjustment_count >= self.MAX_ADJUSTMENTS:
            analysis["primary_reason"] = "策略调整次数过多，任务复杂度可能超出当前能力"
        elif iterations >= self.max_iterations:
            analysis["primary_reason"] = "任务过于复杂，需要更多迭代次数"
        else:
            analysis["primary_reason"] = "未能找到有效的任务解决方案"
        
        # Add execution stats
        if state.tool_execution_history:
            success_count = sum(1 for r in state.tool_execution_history if r.success)
            total_count = len(state.tool_execution_history)
            analysis["contributing_factors"].append(
                f"工具执行成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)"
            )
        
        # Generate recommendations
        if state.failed_tool_patterns:
            analysis["recommendation"] = (
                "建议检查失败工具的配置和参数，或尝试使用替代工具完成任务。"
            )
        elif state.same_tool_repeated >= self.MAX_SAME_TOOL_REPEATS:
            analysis["recommendation"] = (
                "建议重新评估任务策略，尝试不同的方法组合，避免重复相同的操作。"
            )
        else:
            analysis["recommendation"] = (
                "建议将任务分解为更小的子任务，或向用户寻求更明确的指导。"
            )
        
        analysis["suggested_user_action"] = (
            "您可以尝试：1) 简化任务描述；2) 提供更多上下文信息；"
            "3) 将任务拆分为多个步骤；4) 检查相关工具和资源的可用性。"
        )
        
        return analysis
