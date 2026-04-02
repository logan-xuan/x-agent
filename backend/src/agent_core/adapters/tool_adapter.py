"""XAgentToolAdapter - 适配 X-Agent ToolManager 到 ToolPort.

将 X-Agent 的 ToolManager (工具注册、执行、验证) 包装为
agent_core 的 ToolPort Protocol。

类型映射:
- tools.base.BaseTool → agent_core.types.AgentTool
- tools.base.ToolParameter → agent_core.types.ToolParameter
- tools.base.ToolResult (success/output/error) → agent_core.types.ToolResult (content/details)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..types import (
    AgentTool,
)
from ..types import (
    ToolParameter as ACToolParameter,
)
from ..types import (
    ToolResult as ACToolResult,
)

if TYPE_CHECKING:
    pass


class XAgentToolAdapter:
    """ToolPort 适配器，包装 X-Agent 的 ToolManager.
    
    Example:
        from src.tools.manager import get_tool_manager
        
        manager = get_tool_manager()
        adapter = XAgentToolAdapter(manager)
        
        config = AgentCoreConfig(tools=adapter)
    """

    def __init__(self, manager: Any) -> None:
        """初始化适配器.
        
        Args:
            manager: X-Agent ToolManager 实例
        """
        self._manager = manager

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        abort_event: asyncio.Event | None = None,
        on_progress: Callable[[Any], None] | None = None,
    ) -> ACToolResult:
        """执行工具.
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            abort_event: 中止事件
            on_progress: 进度回调
        
        Returns:
            agent_core ToolResult
        """
        try:
            result = await self._manager.execute(tool_name, arguments)
            return _convert_tool_result(result)
        except Exception as e:
            return ACToolResult.from_error(
                str(e),
                details={"error_type": type(e).__name__},
            )

    def get_tools(self) -> list[AgentTool]:
        """获取所有可用工具.
        
        Returns:
            agent_core AgentTool 列表
        """
        tools = self._manager.get_all_tools()
        return [_convert_base_tool(t) for t in tools]


def _convert_tool_result(result: Any) -> ACToolResult:
    """将 X-Agent ToolResult 转换为 agent_core ToolResult.
    
    Args:
        result: X-Agent tools.base.ToolResult
    
    Returns:
        agent_core ToolResult
    """
    metadata = result.metadata if hasattr(result, 'metadata') else {}

    if hasattr(result, 'success') and result.success:
        output = result.output if hasattr(result, 'output') else ""
        return ACToolResult.from_text(output, details=metadata)
    else:
        error = ""
        if hasattr(result, 'error') and result.error:
            error = result.error
        elif hasattr(result, 'output'):
            error = result.output
        return ACToolResult.from_error(error, details=metadata)


def _convert_base_tool(tool: Any) -> AgentTool:
    """将 X-Agent BaseTool 转换为 agent_core AgentTool.
    
    Args:
        tool: X-Agent tools.base.BaseTool
    
    Returns:
        agent_core AgentTool
    """
    parameters = []
    if hasattr(tool, 'parameters'):
        for param in tool.parameters:
            parameters.append(_convert_tool_parameter(param))

    return AgentTool(
        name=tool.name,
        label=tool.name,  # 使用 name 作为 label
        description=tool.description if hasattr(tool, 'description') else "",
        parameters=parameters,
    )


def _convert_tool_parameter(param: Any) -> ACToolParameter:
    """将 X-Agent ToolParameter 转换为 agent_core ToolParameter.
    
    Args:
        param: X-Agent tools.base.ToolParameter
    
    Returns:
        agent_core ToolParameter
    """
    # ToolParameterType 是 str enum，.value 得到 "string" 等
    param_type = param.type.value if hasattr(param.type, 'value') else str(param.type)

    return ACToolParameter(
        name=param.name,
        type=param_type,
        description=param.description if hasattr(param, 'description') else "",
        required=param.required if hasattr(param, 'required') else True,
        default=param.default if hasattr(param, 'default') else None,
        enum=param.enum if hasattr(param, 'enum') else None,
    )
