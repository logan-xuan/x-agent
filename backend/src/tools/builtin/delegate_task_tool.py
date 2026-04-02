"""Agent 任务委派工具。

DelegateTaskTool 允许一个 Agent 将任务委派给另一个 Agent。
与 NotifyTool 的区别：
- NotifyTool: 直接推送文本消息，不经过 agent_loop
- DelegateTaskTool: 触发目标 Agent 的完整 agent_loop（加载上下文、技能、工具等）

使用场景：
1. Main Agent 需要将复杂任务分派给专业 Agent（如代码审查、天气查询）
2. Agent 之间的协作任务，需要对方执行分析并返回结果
3. 需要目标 Agent 使用其专属工具完成任务

与 notify 的关键区别：
- notify: 只是消息转发，适合提醒/告警等简单通知
- delegate_task: 完整任务执行，目标 Agent 会调用工具、分析、返回结果
"""

import asyncio

from src.utils.logger import get_logger

from ..base import BaseTool, ToolParameter, ToolParameterType, ToolResult

logger = get_logger(__name__)


class DelegateTaskTool(BaseTool):
    """Agent 任务委派工具。

    允许一个 Agent 将任务委派给另一个 Agent 执行。
    目标 Agent 通过完整的 agent loop 处理任务（包括加载上下文、技能、工具等），
    然后将结果返回给调用方。

    Features:
    - 完整 Agent Loop 执行（区别于 notify 的直接消息转发）
    - 支持指定目标 session（可选，不传则自动解析）
    - 支持同步等待结果或异步委派
    """

    @property
    def name(self) -> str:
        return "delegate_task"

    @property
    def description(self) -> str:
        return (
            "Delegate a task to another Agent for processing. The target Agent will execute "
            "the task through its complete agent loop, which includes loading its own context, "
            "skills, tools, and performing any necessary analysis or tool calls.\n\n"
            "This is the CORRECT way to ask another Agent to perform work (e.g., query weather, "
            "analyze code, search documents). The target Agent will process the task using its "
            "full capabilities and return the result.\n\n"
            "When to use:\n"
            "- You need another Agent to execute a task and get the result\n"
            "- The task requires the target Agent's specialized tools or knowledge\n"
            "- User says 'tell [agent] to do X' or 'ask [agent] about Y'\n"
            "- User says '发消息给 [agent] 让他 [做某事]' or '让 [agent] 帮我 [查询/分析/...]'\n\n"
            "When NOT to use (use 'notify' instead):\n"
            "- You only need to send a simple notification/alert/reminder\n"
            "- No response or task execution is needed from the target Agent\n\n"
            "Key parameters:\n"
            "- agent_id: Target Agent ID (e.g., 'product-assistant', 'code-assistant')\n"
            "- task: The task description for the target Agent to execute\n"
            "- session_id: (optional) Target session ID, auto-resolved if not provided\n"
            "- wait_for_result: (optional) Whether to wait for task completion, default true"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="agent_id",
                type=ToolParameterType.STRING,
                description=(
                    "The target Agent ID to delegate the task to. "
                    "Examples: 'product-assistant', 'code-assistant', 'research-agent'. "
                    "Use the exact agent_id from the multi-agent configuration."
                ),
                required=True,
                min_length=1,
                max_length=100,
            ),
            ToolParameter(
                name="task",
                type=ToolParameterType.STRING,
                description=(
                    "The task description to delegate to the target Agent. "
                    "Be clear and specific about what you want the Agent to do. "
                    "The target Agent will execute this through its full agent loop."
                ),
                required=True,
                min_length=1,
                max_length=8192,
            ),
            ToolParameter(
                name="session_id",
                type=ToolParameterType.STRING,
                description=(
                    "Target session ID (optional). If not provided, the system will "
                    "automatically resolve the active session for the target Agent, "
                    "or create a new one if needed."
                ),
                required=False,
                default=None,
            ),
            ToolParameter(
                name="wait_for_result",
                type=ToolParameterType.BOOLEAN,
                description=(
                    "Whether to wait for the target Agent to complete the task and "
                    "return the result. Default is true. Set to false for fire-and-forget tasks."
                ),
                required=False,
                default=True,
            ),
            ToolParameter(
                name="timeout",
                type=ToolParameterType.NUMBER,
                description=(
                    "Maximum time in seconds to wait for the target agent to complete. "
                    "Default is 120 seconds. Set a higher value for complex tasks. "
                    "Only applies when wait_for_result is true."
                ),
                required=False,
                default=120,
            ),
        ]

    async def execute(
        self,
        agent_id: str,
        task: str,
        session_id: str | None = None,
        wait_for_result: bool = True,
        timeout: float = 120,
    ) -> ToolResult:
        """Execute task delegation to another Agent.

        Args:
            agent_id: Target Agent ID to delegate to.
            task: Task description for the target Agent.
            session_id: Target session ID (optional, auto-resolved if not provided).
            wait_for_result: Whether to wait for completion and return result.
            timeout: Maximum time in seconds to wait for the target agent.

        Returns:
            ToolResult with the delegated task's response or status.
        """
        try:
            from src.gateway.agent_invoker import AgentInvoker, InvokeSource

            logger.info(
                "DelegateTaskTool executing",
                extra={
                    "target_agent_id": agent_id,
                    "task_length": len(task),
                    "session_id": session_id,
                    "wait_for_result": wait_for_result,
                },
            )

            # Create invoker
            invoker = AgentInvoker()

            # Fire-and-forget mode: delegate without waiting for result
            if not wait_for_result:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                loop.create_task(
                    invoker.invoke(
                        content=task,
                        agent_id=agent_id,
                        session_id=session_id,
                        source=InvokeSource.AGENT,
                    )
                )

                logger.info(
                    "DelegateTaskTool: fire-and-forget task delegated",
                    extra={
                        "target_agent_id": agent_id,
                        "session_id": session_id,
                        "task_length": len(task),
                    },
                )

                return ToolResult.ok(
                    f"Task has been delegated to agent '{agent_id}' asynchronously. "
                    f"The agent will process the task in the background and the result "
                    f"will be delivered to the user directly.",
                    agent_id=agent_id,
                    async_mode=True,
                )

            # Synchronous mode: wait for result with timeout protection
            try:
                result = await asyncio.wait_for(
                    invoker.invoke(
                        content=task,
                        agent_id=agent_id,
                        session_id=session_id,
                        source=InvokeSource.AGENT,
                    ),
                    timeout=float(timeout),
                )
            except TimeoutError:
                logger.warning(
                    "DelegateTaskTool timed out",
                    extra={
                        "agent_id": agent_id,
                        "timeout": timeout,
                        "task_preview": task[:100] if len(task) > 100 else task,
                    },
                )
                return ToolResult.ok(
                    f"Task delegated to agent '{agent_id}' but it did not complete within {timeout} seconds. "
                    f"The agent may still be processing the task in the background. "
                    f"The result will be delivered to the user directly when ready.",
                    agent_id=agent_id,
                    timed_out=True,
                    timeout=timeout,
                )

            # Handle error case
            if result.error:
                logger.error(
                    "DelegateTaskTool failed",
                    extra={
                        "target_agent_id": agent_id,
                        "error": result.error,
                    },
                )
                return ToolResult.error_result(
                    f"Failed to delegate task to '{agent_id}': {result.error}",
                    agent_id=agent_id,
                    session_id=result.session_id,
                )

            # Build success response
            logger.info(
                "DelegateTaskTool completed",
                extra={
                    "target_agent_id": agent_id,
                    "session_id": result.session_id,
                    "delivered": result.delivered,
                    "response_length": len(result.response) if result.response else 0,
                },
            )

            return ToolResult.ok(
                f"Agent '{agent_id}' completed the task.\n\nResponse:\n{result.response}",
                agent_id=agent_id,
                session_id=result.session_id,
                trace_id=result.trace_id,
                delivered=result.delivered,
            )

        except ValueError as exc:
            # Agent not found in configuration
            logger.warning(
                "DelegateTaskTool: Agent not found",
                extra={"agent_id": agent_id, "error": str(exc)},
            )
            return ToolResult.error_result(
                f"Agent '{agent_id}' not found. Please check the agent_id is correct. "
                f"Error: {str(exc)}",
                agent_id=agent_id,
            )

        except Exception as exc:
            logger.error(
                "DelegateTaskTool execution failed",
                extra={
                    "agent_id": agent_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return ToolResult.error_result(
                f"Failed to delegate task to '{agent_id}': {str(exc)}",
                agent_id=agent_id,
            )
