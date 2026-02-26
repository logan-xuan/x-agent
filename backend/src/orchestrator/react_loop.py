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
from .plan_context import PlanState  # Add PlanState type
from ..utils.logger import get_logger

# ✅ OPTIMIZE: Import error learning service for memory integration
try:
    from ..services.error_learning import get_error_learning_service
    ERROR_LEARNING_AVAILABLE = True
except ImportError:
    ERROR_LEARNING_AVAILABLE = False
    logger.warning("Error learning service not available, memory integration disabled")

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
    """Types of reflection in the ReAct loop.
    
    Implements 5 reflection scenarios:
    1. TOOL_RESULT: Result anomaly (error, empty, format mismatch, low confidence)
    2. CHECKPOINT: Stage goal reached (milestone validation)
    3. PRE_ACTION: Before high-risk actions (delete, write, send, paid API)
    4. ADAPTIVE: Multiple failures (retry strategy adjustment)
    5. LONG_TASK: Periodic check during long execution (prevent drift)
    """
    # Scenario 1: Result anomaly (MUST reflect)
    TOOL_RESULT = "tool_result"  # Reflect on tool execution result
    ERROR_DRIVEN = "error_driven"  # API error, empty result, schema mismatch
    
    # Scenario 2: Checkpoint reflection
    CHECKPOINT = "checkpoint"  # After reaching stage goal
    MILESTONE_REACHED = "milestone_reached"  # Milestone validation passed
    
    # Scenario 3: Pre-action reflection (high-risk)
    PRE_ACTION = "pre_action"  # Before risky operations
    HIGH_RISK_DECISION = "high_risk_decision"  # Delete, write, send, execute
    
    # Scenario 4: Adaptive reflection (multiple failures)
    ADAPTIVE = "adaptive"  # After repeated failures
    STRATEGY_ADJUSTMENT = "strategy_adjustment"  # Adjust approach
    
    # Scenario 5: Long task rhythm control
    LONG_TASK = "long_task"  # Periodic check during execution
    PROGRESS_CHECK = "progress_check"  # Prevent task drift
    
    # Legacy types (backward compatibility)
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
    MAX_RETRY_WITHOUT_TOOL = 2  # Max retries when LLM doesn't call tools (iteration < 2规范)
    
    def __init__(
        self,
        llm_router: LLMRouter,
        tool_manager: ToolManager,
        max_iterations: int = 5,  # ✅ OPTIMIZE: Reduced from 8 to 5 for faster failure detection
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
        
        # 🔥 NEW: SKILL.md content cache (avoid repeated file reads)
        self._skill_md_cache: dict[str, str] = {}
        
        logger.debug(  # Changed from info: initialization is routine
            "ReActLoop initialized with progressive skill disclosure",
            extra={
                "max_iterations": max_iterations,
                "enable_reflection": enable_reflection,
            }
        )
    
    def _extract_skill_guidance_for_execution(self, tool_name: str, arguments: dict) -> str:
        """从 SKILL.md 中提取执行时的关键指引（渐进式披露）
        
        Args:
            tool_name: 工具名称（如 run_in_terminal）
            arguments: 工具参数
            
        Returns:
            提取的关键指引文本
        """
        import re
        from pathlib import Path
        
        # 🔥 检测是否涉及技能脚本执行
        script_name = None
        skill_name = None
        
        if tool_name == "run_in_terminal":
            command = arguments.get("command", "")
            
            # 从命令中提取脚本名
            # 示例：python create_pdf_from_md.py ... → create_pdf_from_md.py
            # node create_presentation.js ... → create_presentation.js
            parts = command.split()
            for i, part in enumerate(parts):
                if part in ["python", "python3", "node", "npm", "yarn"] and i + 1 < len(parts):
                    script_candidate = parts[i + 1]
                    # 提取脚本文件名
                    script_name = script_candidate.split("/")[-1].split("\\")[-1]
                    break
        
        if not script_name:
            return ""
        
        # 🔥 根据脚本名推断技能类型
        if "pdf" in script_name.lower():
            skill_name = "pdf"
        elif "ppt" in script_name.lower() or "presentation" in script_name.lower():
            skill_name = "pptx"
        elif "xlsx" in script_name.lower() or "excel" in script_name.lower():
            skill_name = "xlsx"
        
        if not skill_name:
            return ""
        
        # 检查缓存
        if skill_name in self._skill_md_cache:
            skill_md_content = self._skill_md_cache[skill_name]
        else:
            # 读取 SKILL.md 文件
            try:
                skill_dir = Path(__file__).parent.parent / 'skills' / skill_name
                skill_md_path = skill_dir / 'SKILL.md'
                
                if not skill_md_path.exists():
                    logger.warning(f"SKILL.md not found for skill: {skill_name}")
                    return ""
                
                skill_md_content = skill_md_path.read_text(encoding='utf-8')
                self._skill_md_cache[skill_name] = skill_md_content
                logger.info(
                    f"Loaded SKILL.md for {skill_name} ({len(skill_md_content)} chars)",
                    extra={"skill": skill_name, "tool": tool_name}
                )
            except Exception as e:
                logger.error(f"Failed to read SKILL.md: {e}")
                return ""
        
        # 🔥 渐进式披露策略：
        # 1. 识别当前执行的脚本类型
        # 2. 提取相关的命令格式和示例
        # 3. 只返回最关键的信息（正确用法 + 常见错误）
        
        guidance_parts = []
        
        # === PPTX 技能执行指引 ===
        if skill_name == "pptx" and ("presentation" in script_name.lower() or "ppt" in script_name.lower()):
            guidance_parts.append("\n\n## ⚠️ PPTX 脚本执行关键指引")
            guidance_parts.append("- ✅ **唯一指定脚本**: `create_presentation.js`")
            guidance_parts.append("- ✅ **正确命令格式**: `node create_presentation.js <input.md> <output.pptx>`")
            guidance_parts.append("- ✅ **示例**: `node create_presentation.js /workspace/report.md /workspace/presentation.pptx`")
            guidance_parts.append("- ❌ **禁止**: 使用 Python 脚本或不存在的脚本")
            guidance_parts.append("- 💡 **路径规则**: 直接使用脚本名（系统会自动查找）")
            
            # 从 SKILL.md 中提取 Usage 部分
            usage_match = re.search(r'### Usage[\s\S]*?(?=###|## $)', skill_md_content)
            if usage_match:
                guidance_parts.append("\n\n## 📖 SKILL.md 官方用法")
                guidance_parts.append(usage_match.group(0)[:500])  # 限制长度
            
            logger.info(
                "Extracted PPTX execution guidance",
                extra={
                    "skill": skill_name,
                    "script_name": script_name,
                    "guidance_length": len("\n".join(guidance_parts)),
                }
            )
            return "\n".join(guidance_parts)
        
        # === PDF 技能执行指引 ===
        elif skill_name == "pdf" and "pdf" in script_name.lower():
            guidance_parts.append("\n\n## 🌐 PDF 脚本执行关键指引")
            guidance_parts.append("- ✅ **唯一指定脚本**: `create_pdf_from_md.py`（增强版）")
            guidance_parts.append("- ✅ **正确命令格式**: `python create_pdf_from_md.py output.pdf input.md \"标题\"`")
            guidance_parts.append("- ✅ **已注册中文字体**: PingFang/STHeiti")
            guidance_parts.append("- ✅ **支持多页、自动分页、章节格式化**")
            guidance_parts.append("- ❌ **禁止**: 使用不存在的脚本或旧版脚本")
            guidance_parts.append("- 💡 **路径规则**: 直接使用脚本名（系统会自动查找）")
            
            logger.info(
                "Extracted PDF execution guidance",
                extra={
                    "skill": skill_name,
                    "script_name": script_name,
                    "guidance_length": len("\n".join(guidance_parts)),
                }
            )
            return "\n".join(guidance_parts)
        
        # === XLSX 技能执行指引 ===
        elif skill_name == "xlsx" and ("xlsx" in script_name.lower() or "excel" in script_name.lower()):
            guidance_parts.append("\n\n## 📊 XLSX 脚本执行关键指引")
            guidance_parts.append("- ✅ **使用 Node.js + ExcelJS**")
            guidance_parts.append("- ✅ **正确命令格式**: `node create_spreadsheet.js <input.json> <output.xlsx>`")
            guidance_parts.append("- ✅ **支持中文、公式、格式化**")
            guidance_parts.append("- ❌ **禁止**: 使用不存在的 Python 脚本")
            guidance_parts.append("- 💡 **路径规则**: 直接使用脚本名（系统会自动查找）")
            
            logger.info(
                "Extracted XLSX execution guidance",
                extra={
                    "skill": skill_name,
                    "script_name": script_name,
                    "guidance_length": len("\n".join(guidance_parts)),
                }
            )
            return "\n".join(guidance_parts)
        
        return ""
    
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
        plan_state: PlanState | None = None,  # NEW: PlanState for structured plan tool constraints
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
            plan_state: PlanState object (for structured plan tool constraints)
            
        Yields:
            Event dictionaries
        """
        # Working message list
        working_messages = list(messages)
        
        # Use provided tools or get from manager
        if tools is None:
            tools = self.tool_manager.get_all_tools()
        
        # Apply plan tool constraints if structured plan exists
        if plan_state and hasattr(plan_state, 'structured_plan') and plan_state.structured_plan:
            plan = plan_state.structured_plan
            if hasattr(plan, 'tool_constraints') and plan.tool_constraints:
                # ✅ FIX: Use Plan's original tool constraints directly, don't re-compute
                original_count = len(tools)
                tools = [
                    t for t in tools
                    if plan.tool_constraints.is_allowed(t.name)
                ]
                filtered_count = original_count - len(tools)
                                
                logger.info(
                    "Applied Plan's original tool constraints (highest priority)",
                    extra={
                        "original_tools": original_count,
                        "allowed_tools": len(tools),
                        "filtered_out": filtered_count,
                        "constraint_source": plan.tool_constraints.source,
                        "constraint_priority": plan.tool_constraints.priority,
                        "allowed_list": plan.tool_constraints.allowed if plan.tool_constraints.allowed else "all",
                        "forbidden_list": plan.tool_constraints.forbidden if plan.tool_constraints.forbidden else "none",
                    }
                )
        
                # Emit Info event for user visibility
                if filtered_count > 0:
                    constraint_msg = []
                    if plan.tool_constraints.allowed:
                        constraint_msg.append(f"✅ 仅允许：{', '.join(plan.tool_constraints.allowed)}")
                    if plan.tool_constraints.forbidden:
                        constraint_msg.append(f"❌ 禁止：{', '.join(plan.tool_constraints.forbidden)}")
        
                    yield {
                        "type": "message",
                        "role": "system",
                        "content": f"🔧 **工具约束已应用**\n\n{chr(10).join(constraint_msg)}\n\n已过滤 {filtered_count} 个工具",
                    }
        
        # 🔥 NEW: Add plan execution monitoring if plan_state is provided
        if plan_state and hasattr(plan_state, 'current_step') and hasattr(plan_state, 'total_steps'):
            current_step = plan_state.current_step
            total_steps = plan_state.total_steps
            progress = f"{current_step}/{total_steps}"
                    
            logger.debug(
                "Plan execution monitoring enabled",
                extra={
                    "current_step": current_step,
                    "total_steps": total_steps,
                    "progress": progress,
                }
            )
                    
            # 🔥 ENHANCED: Add detailed plan steps to guide LLM
            plan_details = []
            if hasattr(plan_state, 'structured_plan') and plan_state.structured_plan:
                structured_plan = plan_state.structured_plan
                        
                # Build detailed step-by-step guidance
                plan_details.append(f"\n\n【📋 计划执行步骤】")
                plan_details.append(f"当前进度：{progress}\n")
                        
                for i, step in enumerate(structured_plan.steps, 1):
                    status_icon = "✅" if i < current_step else ("🔴" if i == current_step else "⚪")
                    step_status = "已完成" if i < current_step else ("进行中" if i == current_step else "待执行")
                            
                    plan_details.append(
                        f"{status_icon} **Step {i}: {step.name}**\n"
                        f"   - 工具：`{step.tool}`\n"
                        f"   - 描述：{step.description}\n"
                        f"   - 状态：{step_status}"
                    )
                            
                    # Add skill_command if available
                    if hasattr(step, 'skill_command') and step.skill_command:
                        plan_details.append(f"   - 技能命令：`{step.skill_command}`")
                            
                    plan_details.append("")
                        
                # Add specific guidance for current step
                if current_step <= len(structured_plan.steps):
                    current_step_obj = structured_plan.steps[current_step - 1]
                    plan_details.append(f"\n【🎯 当前任务】\n")
                    plan_details.append(f"请立即执行 **Step {current_step}**: {current_step_obj.name}\n")
                    plan_details.append(f"使用工具：`{current_step_obj.tool}`\n")
                    if hasattr(current_step_obj, 'skill_command') and current_step_obj.skill_command:
                        plan_details.append(f"执行命令：`{current_step_obj.skill_command}`\n")
                    
            # Combine general guidance with detailed steps
            plan_guidance = (
                f"\n\n【计划执行监控】\n"
                f"请严格按照以下计划步骤执行，确保每一步使用正确的工具和参数。\n"
                f"如果当前步骤指定了具体命令（如 skill_command），请直接使用该命令，不要自己创造新的实现方式。\n"
                f"特别是 PDF/PPTX生成任务，必须使用提供的技能脚本，不要使用 inline Python 代码！\n"
            )
                    
            if plan_details:
                plan_guidance += "\n".join(plan_details)
                    
            # Inject into working messages
            working_messages.append({
                "role": "system",
                "content": plan_guidance,
            })
                
        # Get OpenAI tool definitions
        openai_tools = [tool.to_openai_tool() for tool in tools] if tools else None
        
        # Track iteration statistics
        actual_iterations = 0
        tool_calls_count = 0
        completed_early = False
        retry_without_tool_count = 0  # NEW: Track retry attempts when no tools called
        
        # Initialize strategy state for reflection and adjustment
        strategy_state = StrategyState()
        
        logger.debug(  # Changed from info: routine event
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
                        logger.debug(  # Changed from info: routine tool_call event
                            "Emitting tool_call from react_loop",
                            extra={
                                "tool_call_id": tool_call.id,
                                "tool_call_name": tool_call.name,
                                "event_keys": list(tool_call_event.keys()),
                                "event_tool_call_id": tool_call_event.get("tool_call_id"),
                            }
                        )
                        
                        yield tool_call_event
                        
                        # Scenario 3: Pre-Action Reflection for high-risk operations
                        is_risky, risk_desc = self._is_high_risk_action(tool_call.name, tool_call.arguments)
                        if is_risky and self.enable_reflection:
                            risk_warning = (
                                f"🚨 **高风险操作检测**\n\n"
                                f"即将执行：{risk_desc}\n"
                                f"工具：{tool_call.name}\n"
                                f"参数：{str(tool_call.arguments)[:200]}\n\n"
                                f"请再次确认此操作的必要性和安全性。"
                            )
                            
                            # Add pre-action reflection message
                            working_messages.append({
                                "role": "system",
                                "content": risk_warning,
                            })
                            
                            # Emit reflection event
                            yield {
                                "type": REACT_EVENT_REFLECTION,
                                "reflection_type": ReflectionType.PRE_ACTION.value,
                                "content": f"高风险操作：{risk_desc}",
                                "tool_name": tool_call.name,
                                "suggestion": "请确认操作必要性，考虑是否有更安全的替代方案",
                                "risk_level": "high",
                            }
                            
                            logger.warning(
                                "High-risk action detected, reflection triggered",
                                extra={
                                    "tool_name": tool_call.name,
                                    "risk_description": risk_desc,
                                    "arguments": tool_call.arguments,
                                }
                            )
                        
                        # 🔥🔥🔥 CRITICAL: Inject SKILL.md guidance before execution (progressive disclosure)
                        skill_guidance = self._extract_skill_guidance_for_execution(tool_call.name, tool_call.arguments)
                        if skill_guidance:
                            logger.info(
                                "Injecting SKILL.md guidance before tool execution",
                                extra={
                                    "tool": tool_call.name,
                                    "skill_guidance_chars": len(skill_guidance),
                                    "arguments_preview": str(tool_call.arguments)[:100],
                                }
                            )
                            
                            # Add skill guidance message
                            working_messages.append({
                                "role": "system",
                                "content": skill_guidance,
                            })
                            
                            # 🔥 NEW: Emit event for user visibility (optional, for debugging)
                            yield {
                                "type": "skill_guidance_injected",
                                "tool_name": tool_call.name,
                                "guidance_length": len(skill_guidance),
                                "preview": skill_guidance[:200] + "..." if len(skill_guidance) > 200 else skill_guidance,
                            }
                        
                        # Execute tool - constraint checking is done in ToolManager
                        # to avoid duplication and centralize validation logic
                        try:
                            result = await self.tool_manager.execute(
                                tool_call.name,
                                tool_call.arguments,
                                skill_context=skill_context,  # Phase 2 - Pass skill context for tool restrictions
                            )
                        except Exception as e:
                            # Handle ToolNotAllowedError from ToolManager
                            from ..tools.manager import ToolNotAllowedError
                            if isinstance(e, ToolNotAllowedError):
                                logger.warning(
                                    "Tool call blocked by skill constraints",
                                    extra={
                                        "tool_name": tool_call.name,
                                        "allowed_tools": e.allowed_tools,
                                        "skill_context": getattr(skill_context, 'name', 'unknown') if skill_context else None,
                                    }
                                )
                                
                                # Add system message to inform LLM about the constraint
                                working_messages.append({
                                    "role": "system",
                                    "content": f"⚠️ 工具 '{tool_call.name}' 不可用。{str(e)}"
                                })
                                
                                # Skip this tool call - continue to next iteration
                                continue
                            else:
                                # Re-raise other exceptions
                                raise
                        
                        # Check if this requires user confirmation - stop the loop
                        # Fix: Ensure metadata is a dict before accessing
                        metadata_dict = result.metadata if isinstance(result.metadata, dict) else {}
                        requires_confirmation = metadata_dict.get("requires_confirmation", False)
                        is_blocked = metadata_dict.get("is_blocked", False)
                        
                        # Emit tool_result event
                        logger.debug(  # Changed from info: routine tool_result event
                            "Emitting tool_result from react_loop",
                            extra={
                                "tool_call_id": tool_call.id,
                                "tool_call_name": tool_call.name,
                                "result_success": result.success,
                                "requires_confirmation": requires_confirmation,
                            }
                        )
                        
                        # Scenario 1: Check if result anomaly requires reflection (MUST reflect)
                        should_reflect, reflection_type, reason = self._should_reflect_on_result(result)
                        if should_reflect and self.enable_reflection:
                            # ✅ OPTIMIZE: Retrieve relevant memories from past experiences
                            memory_guidance = ""
                            if ERROR_LEARNING_AVAILABLE:
                                try:
                                    error_learning_service = get_error_learning_service(self.llm_router)
                                    
                                    # ✅ OPTIMIZE: Add timeout control to prevent blocking
                                    import asyncio
                                    retrieved_memories = await asyncio.wait_for(
                                        error_learning_service.retrieve_relevant_memories_for_error(
                                            error_type=reflection_type.value,
                                            error_message=(result.error or str(result.output))[:500],
                                            tool_name=tool_call.name,
                                        ),
                                        timeout=3.0,  # 3 seconds timeout
                                    )
                                    
                                    # Create memory injection prompt
                                    if retrieved_memories:
                                        memory_guidance = error_learning_service.create_memory_injection_prompt(
                                            retrieved_memories=retrieved_memories,
                                            current_error_type=reflection_type.value,
                                            current_error_message=(result.error or str(result.output))[:300],
                                        )
                                        
                                        logger.info(
                                            "Retrieved relevant memories for error correction",
                                            extra={
                                                "error_type": reflection_type.value,
                                                "memories_count": len(retrieved_memories),
                                                "top_score": retrieved_memories[0]["score"] if retrieved_memories else 0,
                                            }
                                        )
                                except asyncio.TimeoutError:
                                    logger.warning(
                                        "Memory retrieval timed out, proceeding without memory guidance",
                                        extra={"timeout_seconds": 3.0}
                                    )
                                    memory_guidance = ""
                                except Exception as e:
                                    logger.warning(
                                        "Failed to retrieve memories for error",
                                        extra={"error": str(e)}
                                    )
                            
                            # 🔥 NEW: Add skill path guidance for run_in_terminal errors
                            skill_path_guidance = ""
                            if (tool_call.name == "run_in_terminal" and 
                                skill_context and 
                                hasattr(skill_context, 'scripts_dir') and 
                                skill_context.scripts_dir):
                                skill_path_guidance = (
                                    f"\n\n💡 **技能脚本路径提示**\n"
                                    f"- 技能 `{skill_context.name}` 的脚本目录：`{skill_context.scripts_dir}`\n"
                                    f"- ✅ 正确用法：`python create_pdf_from_md.py ...`（直接使用脚本名）\n"
                                    f"- ❌ 错误用法：`python /workspace/.../create_pdf_from_md.py`（不要使用绝对路径）\n"
                                )
                            
                            # ✅ OPTIMIZE: Add targeted error detection guidance
                            error_specific_guidance = ""
                            error_lower = (result.error or result.output or "").lower()
                            
                            if "module not found" in error_lower or "no such file" in error_lower:
                                error_specific_guidance = (
                                    f"\n\n🚨 **关键错误：文件不存在!**\n"
                                    f"检测到 `MODULE_NOT_FOUND` 或 `No such file` 错误。\n\n"
                                    f"**请立即检查**:\n"
                                    f"1. ✅ 脚本文件是否在正确的位置\n"
                                    f"2. ✅ 是否需要先创建该脚本文件\n"
                                    f"3. ✅ 路径是否正确（建议使用相对路径或直接写脚本名）\n"
                                    f"4. ✅ 工作目录是否正确设置\n\n"
                                    f"**示例修复**:\n"
                                    f"- ❌ 错误：`node /wrong/path/create_presentation.js`\n"
                                    f"- ✅ 正确：`node skills/pptx/scripts/create_presentation.js ...`\n"
                                )
                            elif "permission denied" in error_lower:
                                error_specific_guidance = (
                                    f"\n\n🚨 **权限错误**!\n"
                                    f"检测到 `Permission denied` 错误。\n\n"
                                    f"**解决方案**:\n"
                                    f"1. ✅ 检查文件是否有执行权限：`chmod +x script.py`\n"
                                    f"2. ✅ 检查目录是否有写入权限\n"
                                    f"3. ✅ 尝试使用 `python script.py` 而不是直接执行\n"
                                )
                            elif "command not found" in error_lower or "not recognized" in error_lower:
                                error_specific_guidance = (
                                    f"\n\n🚨 **命令不存在**!\n"
                                    f"检测到 `Command not found` 错误。\n\n"
                                    f"**解决方案**:\n"
                                    f"1. ✅ 检查命令是否已安装\n"
                                    f"2. ✅ 检查 PATH 环境变量\n"
                                    f"3. ✅ 使用完整路径或确认命令名称正确\n"
                                )
                            
                            reflection_content = (
                                f"⚠️ **结果异常检测**\n\n"
                                f"{reason}\n\n"
                                f"工具：{tool_call.name}\n"
                                f"结果：{result.output[:100] if result.output else 'N/A'}...\n"
                                f"{skill_path_guidance}"
                                f"{error_specific_guidance}"
                                f"{memory_guidance}"  # ✅ OPTIMIZE: Add memory guidance
                            )
                            
                            # Add reflection message
                            working_messages.append({
                                "role": "system",
                                "content": reflection_content,
                            })
                            
                            # Emit reflection event
                            yield {
                                "type": REACT_EVENT_REFLECTION,
                                "reflection_type": reflection_type.value,
                                "content": reason,
                                "tool_name": tool_call.name,
                                "suggestion": "请检查工具参数和执行环境，或尝试使用其他方法",
                            }
                            
                            logger.info(
                                "Result anomaly reflection triggered",
                                extra={
                                    "tool_name": tool_call.name,
                                    "reflection_type": reflection_type.value,
                                    "reason": reason,
                                }
                            )
                        
                        # P4-4 NEW: Multi-dimension reflection checks (only if no anomaly reflection)
                        elif self.enable_reflection and plan_state:
                            # Check 2: Step stuck reflection
                            is_stuck, stuck_reason = self._should_step_stuck_reflect(iteration, plan_state, strategy_state)
                            if is_stuck:
                                # 🔥 NEW: Add skill path guidance if skill_context is available
                                skill_path_guidance = ""
                                if skill_context and hasattr(skill_context, 'scripts_dir') and skill_context.scripts_dir:
                                    skill_path_guidance = (
                                        f"\n\n💡 **技能脚本路径提示**\n"
                                        f"- 技能 `{skill_context.name}` 的脚本目录：`{skill_context.scripts_dir}`\n"
                                        f"- ✅ 正确示例：`python create_pdf_from_md.py ...`（直接使用脚本名）\n"
                                        f"- ❌ 错误示例：`python /workspace/.../create_pdf_from_md.py`（不要使用绝对路径）\n"
                                    )
                                
                                # ✅ OPTIMIZE: Add repeated failure warning
                                repeated_failure_warning = ""
                                if len(strategy_state.reflection_history) >= 2:
                                    repeated_failure_warning = (
                                        f"\n\n🚨 **警告：已反思 {len(strategy_state.reflection_history)} 次但仍未进展**!\n"
                                        f"当前方法可能根本不可行，请立即:\n"
                                        f"1. ⛔ **停止当前尝试**\n"
                                        f"2. 💡 **彻底换一种思路**\n"
                                        f"3. 🆘 **或请求用户帮助**\n"
                                    )
                                                        
                                reflection_content = (
                                    f"⚠️ **Step 停滞检测**\n\n"
                                    f"{stuck_reason}\n\n"
                                    f"建议操作:\n"
                                    f"1. 如果正在重复同一工具 → 立即停止，尝试其他方法\n"
                                    f"2. 如果 Step 停滞 → 评估是否可以进入下一步\n"
                                    f"3. 如果工具偏离 → 回顾计划中的工具约束\n"
                                    f"4. 如果任务困难 → 考虑分解为更小的子任务\n"
                                    f"{skill_path_guidance}"
                                    f"{repeated_failure_warning}"
                                )
                                
                                working_messages.append({
                                    "role": "system",
                                    "content": reflection_content,
                                })
                                
                                yield {
                                    "type": REACT_EVENT_REFLECTION,
                                    "reflection_type": ReflectionType.STRATEGY_ADJUSTMENT.value,
                                    "content": stuck_reason,
                                    "suggestion": "请重新评估当前策略，避免陷入循环",
                                }
                                
                                logger.warning(
                                    "Step stuck reflection triggered",
                                    extra={
                                        "iteration": iteration,
                                        "reason": stuck_reason,
                                        "current_step": getattr(plan_state, 'current_step', 'N/A'),
                                    }
                                )
                            
                            # Check 3: Slow progress reflection
                            elif self._should_long_task_reflect(iteration, self.max_iterations, plan_state):
                                reflection_content = (
                                    f"⚠️ **进度缓慢检测**\n\n"
                                    f"当前迭代：{iteration + 1}/{self.max_iterations}\n"
                                    f"当前步骤：{getattr(plan_state, 'current_step', 'N/A')}/{getattr(plan_state, 'total_steps', 'N/A')}\n"
                                    f"工具执行次数：{getattr(plan_state, 'tool_execution_count', 'N/A')}\n\n"
                                    f"建议操作:\n"
                                    f"1. 简化当前方法，避免过度复杂化\n"
                                    f"2. 如果已完成足够信息收集，考虑进入下一步\n"
                                    f"3. 如需帮助，请向用户请求更明确的指导\n"
                                )
                                
                                working_messages.append({
                                    "role": "system",
                                    "content": reflection_content,
                                })
                                
                                yield {
                                    "type": REACT_EVENT_REFLECTION,
                                    "reflection_type": ReflectionType.LONG_TASK.value,
                                    "content": "进度缓慢检测：连续 2 次迭代无进展",
                                    "suggestion": "请加快执行节奏或调整策略",
                                }
                                
                                logger.warning(
                                    "Slow progress reflection triggered",
                                    extra={
                                        "iteration": iteration,
                                        "current_step": getattr(plan_state, 'current_step', 'N/A'),
                                        "tool_execution_count": getattr(plan_state, 'tool_execution_count', 'N/A'),
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
                    retry_without_tool_count += 1
                    
                    # Enforce iteration < 2 retry规范: Only retry in first 2 iterations
                    if retry_without_tool_count >= self.MAX_RETRY_WITHOUT_TOOL or iteration >= 2:
                        # Exceeded retry limit or past early iterations - fail with error
                        logger.error(
                            "LLM persistently not calling tools, task cannot continue",
                            extra={
                                "iteration": iteration + 1,
                                "retry_count": retry_without_tool_count,
                                "max_retry": self.MAX_RETRY_WITHOUT_TOOL,
                            }
                        )
                        yield {
                            "type": REACT_EVENT_ERROR,
                            "error": f"LLM持续不调用工具（重试{retry_without_tool_count}次），任务无法继续",
                            "retry_count": retry_without_tool_count,
                        }
                        return  # Terminate loop
                    
                    logger.warning(
                        "LLM responded without tool calls when tools were required (retrying)",
                        extra={
                            "iteration": iteration + 1,
                            "retry_count": retry_without_tool_count,
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
                
                logger.debug(  # Changed from info: routine completion event
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
                
                # ALWAYS trigger failure reflection on exception (regardless of enable_reflection)
                failure_analysis = self._generate_failure_analysis(strategy_state, iteration + 1)
                
                # Emit reflection event
                yield {
                    "type": REACT_EVENT_REFLECTION,
                    "reflection_type": ReflectionType.FAILURE_ANALYSIS.value,
                    "content": f"异常退出: {str(e)}",
                    "suggestion": failure_analysis["recommendation"],
                    "failure_details": failure_analysis,
                    "exception_type": type(e).__name__,
                }
                
                # Emit error event
                yield {
                    "type": REACT_EVENT_ERROR,
                    "error": str(e),
                    "iteration": iteration + 1,
                    "failure_analysis": failure_analysis,
                }
                
                # Terminate loop on exception
                logger.warning(
                    "ReAct loop terminated by exception",
                    extra={
                        "iteration": iteration + 1,
                        "exception": str(e),
                        "failure_analysis": failure_analysis,
                    }
                )
                
                # ✅ OPTIMIZE: Record error for learning if this was a tool execution error
                if ERROR_LEARNING_AVAILABLE:
                    try:
                        error_learning_service = get_error_learning_service(self.llm_router)
                        
                        # Record the error pattern
                        error_learning_service.record_error(
                            error_type=type(e).__name__,
                            error_message=str(e),
                            tool_name=tool_call.name if 'tool_call' in locals() else "unknown",
                            session_id=session_id or "unknown",
                            context={"iteration": iteration},
                        )
                    except Exception as learn_error:
                        logger.debug(
                            "Failed to record error for learning",
                            extra={"error": str(learn_error)}
                        )
                
                return
        
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
            analysis["contributing_factors"].append(f"工具失败模式：{list(state.failed_tool_patterns)}")
        elif state.same_tool_repeated >= 2:  # P4-2: 降低阈值到 2 次，更早发现循环
            analysis["primary_reason"] = "检测到工具调用循环"
            analysis["contributing_factors"].append(f"重复工具：{state.last_tool_name} (已调用 {state.same_tool_repeated} 次)")
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
    
    def _should_reflect_on_result(self, result: ToolResult) -> tuple[bool, ReflectionType, str]:
        """检查工具结果是否需要反思（场景1：结果异常）
        
        Args:
            result: 工具执行结果
            
        Returns:
            (是否需要反思, 反思类型, 原因)
        """
        # API错误
        if not result.success and result.error:
            return True, ReflectionType.ERROR_DRIVEN, f"工具执行失败: {result.error}"
        
        # 结果为空
        if result.success and (not result.output or len(result.output.strip()) == 0):
            return True, ReflectionType.ERROR_DRIVEN, "工具返回空结果"
        
        # 格式不符合schema（检查特定模式）
        if result.success and result.metadata.get("format_error"):
            return True, ReflectionType.ERROR_DRIVEN, "返回格式不符合预期"
        
        # 置信度低（如果有confidence字段）
        confidence = result.metadata.get("confidence", 1.0)
        if confidence < 0.5:
            return True, ReflectionType.ERROR_DRIVEN, f"结果置信度过低 ({confidence:.2f})"
        
        return False, ReflectionType.TOOL_RESULT, ""
    
    def _is_high_risk_action(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """判断是否为高风险操作（场景3：Pre-Action反思）
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            (是否高风险, 风险描述)
        """
        # 高风险工具列表
        HIGH_RISK_TOOLS = {
            "delete_file": "删除文件",
            "delete_directory": "删除目录",
            "write_file": "写入文件",
            "overwrite_file": "覆盖文件",
            "send_email": "发送邮件",
            "execute_code": "执行代码",
            "run_shell": "执行Shell命令",
            "paid_api_call": "调用付费API",
            "database_delete": "删除数据库记录",
            "api_request": "API请求"  # 某些API可能有副作用
        }
        
        if tool_name in HIGH_RISK_TOOLS:
            risk_desc = HIGH_RISK_TOOLS[tool_name]
            # 检查特定高风险参数
            if tool_name == "write_file" and arguments.get("overwrite"):
                return True, f"{risk_desc}（覆盖模式）"
            if tool_name == "run_shell" and any(cmd in str(arguments) for cmd in ["rm", "del", "format"]):
                return True, f"{risk_desc}（危险命令）"
            return True, risk_desc
        
        return False, ""
    
    def _should_checkpoint_reflect(self, iteration: int, strategy_state: StrategyState) -> bool:
        """判断是否需要阶段性反思（场景2：Checkpoint）
        
        Args:
            iteration: 当前迭代次数
            strategy_state: 策略状态
            
        Returns:
            是否需要反思
        """
        # 每完成一定数量的成功工具调用后反思
        if strategy_state.tool_execution_history:
            success_count = sum(1 for r in strategy_state.tool_execution_history if r.success)
            # 每3个成功工具后反思一次
            if success_count > 0 and success_count % 3 == 0:
                return True
        
        return False
    
    def _should_long_task_reflect(self, iteration: int, max_iterations: int, plan_state: Any = None) -> bool:
        """判断是否需要长任务节奏反思（场景 5：Long Task）
            
        Args:
            iteration: 当前迭代次数
            max_iterations: 最大迭代次数
            plan_state: Plan 状态对象（可选，用于更精确的进度检测）
                
        Returns:
            是否需要反思
        """
        # P4-3 NEW: 如果有 plan_state，添加额外的进度检查
        if plan_state and hasattr(plan_state, 'current_step'):
            # 每 2 次迭代检查一次进展
            if iteration % 2 == 0 and iteration > 0:
                # 使用实例变量跟踪上次的 step
                if not hasattr(self, '_last_step_snapshot'):
                    self._last_step_snapshot = plan_state.current_step
                elif self._last_step_snapshot == plan_state.current_step:
                    # 2 次迭代后仍在同一 step，需要反思
                    logger.warning(
                        "Slow progress detected",
                        extra={
                            "iteration": iteration,
                            "current_step": plan_state.current_step,
                            "last_step": self._last_step_snapshot,
                            "tool_execution_count": getattr(plan_state, 'tool_execution_count', 0),
                        }
                    )
                    return True
                else:
                    # 更新快照
                    self._last_step_snapshot = plan_state.current_step
            
        # 原有逻辑：在任务中期（1/3 和 2/3 处）进行反思，防止跑偏
        checkpoints = [max_iterations // 3, (max_iterations * 2) // 3]
        return iteration in checkpoints
        
    def _should_step_stuck_reflect(
        self,
        iteration: int,
        plan_state: Any,
        strategy_state: StrategyState,
    ) -> tuple[bool, str]:
        """判断是否因 Step 停滞需要反思（新增场景：Step Stuck）
            
        触发条件:
        1. current_step 连续 3 次迭代未变化
        2. tool_execution_count > 3 且仍在同一 Step
        3. 同一工具重复调用 >= 2 次
            
        Args:
            iteration: 当前迭代次数
            plan_state: Plan 状态对象
            strategy_state: 策略状态
                
        Returns:
            tuple[bool, str]: (是否需要反思，原因描述)
        """
        if not plan_state:
            return False, ""
            
        # 检查 1: tool_execution_count 过高但仍在同一 Step
        if hasattr(plan_state, 'tool_execution_count') and hasattr(plan_state, 'current_step'):
            if plan_state.tool_execution_count > 3:
                # 检测是否在同一个 step 上执行了过多工具
                reason = f"Step 停滞检测：current_step={plan_state.current_step}, tool_execution_count={plan_state.tool_execution_count}"
                return True, reason
            
        # 检查 2: 同一工具重复调用 >= 2 次
        if hasattr(strategy_state, 'same_tool_repeated') and strategy_state.same_tool_repeated >= 2:
            reason = f"工具重复检测：{strategy_state.last_tool_name} 已调用 {strategy_state.same_tool_repeated} 次"
            return True, reason
            
        return False, ""
