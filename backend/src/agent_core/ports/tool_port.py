"""工具执行接口定义.

ToolPort 定义了 agent_core 与工具系统交互的接口。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, Callable, Any

if TYPE_CHECKING:
    from ..types import AgentTool, ToolResult


class ToolPort(Protocol):
    """工具执行接口.
    
    agent_core 通过此接口执行工具，不关心具体实现。
    实现者需要将具体的工具系统适配到此接口。
    
    Example:
        class MyToolAdapter:
            def __init__(self, tools: dict[str, Callable]):
                self.tools = tools
            
            async def execute(
                self,
                tool_name: str,
                arguments: dict,
                abort_event: asyncio.Event | None = None,
            ) -> ToolResult:
                if tool_name not in self.tools:
                    return ToolResult.from_error(f"Tool not found: {tool_name}")
                result = await self.tools[tool_name](**arguments)
                return ToolResult.from_text(str(result))
            
            def get_tools(self) -> list[AgentTool]:
                return [...]
    """
    
    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        abort_event: "asyncio.Event | None" = None,
        on_progress: "Callable[[Any], None] | None" = None,
    ) -> "ToolResult":
        """执行工具.
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            abort_event: 中止事件（可选），设置时应尽快停止执行
            on_progress: 进度回调（可选），用于长时间运行的工具报告进度
        
        Returns:
            ToolResult: 工具执行结果
        
        Raises:
            Exception: 工具执行失败时可以抛出异常，也可以返回错误结果
        """
        ...
    
    def get_tools(self) -> "list[AgentTool]":
        """获取可用工具列表.
        
        Returns:
            list[AgentTool]: 工具定义列表
        """
        ...
