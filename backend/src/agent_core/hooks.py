"""Hook 机制实现.

提供 Agent 执行流程的生命周期扩展点。
支持在关键节点注入自定义逻辑。

Hook 触发点:
    - BEFORE_LLM_CALL: LLM 调用前
    - AFTER_LLM_CALL: LLM 调用后
    - BEFORE_TOOL_EXEC: 工具执行前
    - AFTER_TOOL_EXEC: 工具执行后
    - ON_CONTEXT_OVERFLOW: 上下文溢出时
    - ON_PLAN_GENERATED: 计划生成后
    - ON_ERROR: 错误发生时
    - ON_TURN_START: Turn 开始时
    - ON_TURN_END: Turn 结束时

Example:
    # 注册 Hook
    @hooks.register(HookPoint.BEFORE_TOOL_EXEC)
    async def log_tool_call(ctx: HookContext) -> HookContext:
        print(f"即将执行工具: {ctx.data['tool_name']}")
        return ctx
    
    # 触发 Hook
    await hooks.trigger(HookContext(
        point=HookPoint.BEFORE_TOOL_EXEC,
        data={"tool_name": "web_search"},
        agent_state=state,
    ))
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import AgentMessage, AgentState

logger = logging.getLogger(__name__)


class HookPoint(Enum):
    """Hook 触发点."""

    # LLM 相关
    BEFORE_LLM_CALL = "before_llm_call"       # LLM 调用前
    AFTER_LLM_CALL = "after_llm_call"         # LLM 调用后

    # 工具相关
    BEFORE_TOOL_EXEC = "before_tool_exec"     # 工具执行前
    AFTER_TOOL_EXEC = "after_tool_exec"       # 工具执行后

    # 上下文相关
    ON_CONTEXT_OVERFLOW = "on_context_overflow"  # 上下文溢出时
    ON_CONTEXT_COMPRESS = "on_context_compress"  # 上下文压缩时

    # 计划相关
    ON_PLAN_GENERATED = "on_plan_generated"   # 计划生成后
    ON_PLAN_UPDATED = "on_plan_updated"       # 计划更新后
    ON_REPLAN = "on_replan"                   # 触发重规划时

    # 流程相关
    ON_TURN_START = "on_turn_start"           # Turn 开始时
    ON_TURN_END = "on_turn_end"               # Turn 结束时
    ON_ITERATION = "on_iteration"             # 每次迭代时

    # 错误处理
    ON_ERROR = "on_error"                     # 错误发生时
    ON_RETRY = "on_retry"                     # 重试时

    # 消息相关
    ON_USER_MESSAGE = "on_user_message"       # 收到用户消息
    ON_ASSISTANT_MESSAGE = "on_assistant_message"  # 生成助手消息

    # Prompt 构建相关
    BEFORE_PROMPT_BUILD = "before_prompt_build"     # prompt 构建前，可注入/移除 section
    AFTER_PROMPT_BUILD = "after_prompt_build"        # prompt 构建后，可修改最终 prompt 字符串
    ON_SECTION_RENDER = "on_section_render"          # 每个 section 渲染时，可动态修改内容

    # Tool 调用生命周期相关
    BEFORE_TOOL_SELECTION = "before_tool_selection"  # LLM 返回工具调用后、执行前，可修改/过滤工具列表
    ON_TOOL_APPROVAL = "on_tool_approval"            # 高危工具审批（可阻断执行）
    ON_TOOL_REGISTER = "on_tool_register"            # 工具注册时
    ON_TOOL_UNREGISTER = "on_tool_unregister"        # 工具注销时
    ON_TOOL_BATCH_START = "on_tool_batch_start"      # 批量工具调用开始
    ON_TOOL_BATCH_END = "on_tool_batch_end"          # 批量工具调用结束

    # Agent 通信相关
    ON_AGENT_DELEGATE = "on_agent_delegate"            # Agent 委派任务时
    ON_AGENT_DELEGATE_RESULT = "on_agent_delegate_result"  # 收到委派结果时
    ON_AGENT_MESSAGE_RECEIVED = "on_agent_message_received"  # 收到 Agent 消息时

    # 多 Agent 协同相关
    ON_COLLABORATION_START = "on_collaboration_start"    # 协同任务开始
    ON_COLLABORATION_END = "on_collaboration_end"        # 协同任务结束
    ON_SHARED_CONTEXT_UPDATE = "on_shared_context_update"  # 共享上下文更新


@dataclass
class HookContext:
    """Hook 上下文.
    
    Attributes:
        point: 触发点
        data: 上下文数据
        agent_state: Agent 状态引用
        metadata: 额外元数据
    """

    point: HookPoint
    data: dict[str, Any] = field(default_factory=dict)
    agent_state: AgentState | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # 以下字段用于特定 HookPoint

    # BEFORE/AFTER_LLM_CALL
    messages: list[AgentMessage] | None = None
    llm_response: Any | None = None

    # BEFORE/AFTER_TOOL_EXEC
    tool_name: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_result: Any | None = None

    # ON_ERROR
    error: Exception | None = None

    # ON_PLAN_*
    plan: Any | None = None


# Hook 处理函数类型
HookHandler = Callable[[HookContext], Awaitable[HookContext | None]]


@dataclass
class HookEntry:
    """Hook 注册项.
    
    Attributes:
        handler: 处理函数
        priority: 优先级（数字越小越先执行）
        name: Hook 名称（用于调试）
        enabled: 是否启用
    """

    handler: HookHandler
    priority: int = 100
    name: str = ""
    enabled: bool = True


class HookRegistry:
    """Hook 注册中心.
    
    管理所有 Hook 的注册、触发和管理。
    
    Example:
        registry = HookRegistry()
        
        # 方式1: 直接注册
        registry.register(
            point=HookPoint.BEFORE_TOOL_EXEC,
            handler=my_handler,
            priority=10,
            name="log_tool",
        )
        
        # 方式2: 装饰器
        @registry.on(HookPoint.AFTER_TOOL_EXEC)
        async def after_tool(ctx: HookContext) -> HookContext:
            return ctx
        
        # 触发
        result = await registry.trigger(ctx)
    """

    def __init__(self):
        """初始化注册中心."""
        self._hooks: dict[HookPoint, list[HookEntry]] = {
            point: [] for point in HookPoint
        }
        self._lock = asyncio.Lock()

    def register(
        self,
        point: HookPoint,
        handler: HookHandler,
        priority: int = 100,
        name: str = "",
    ) -> None:
        """注册 Hook.
        
        Args:
            point: 触发点
            handler: 处理函数
            priority: 优先级（数字越小越先执行）
            name: Hook 名称（用于调试）
        """
        entry = HookEntry(
            handler=handler,
            priority=priority,
            name=name or handler.__name__,
        )
        self._hooks[point].append(entry)
        # 按优先级排序
        self._hooks[point].sort(key=lambda e: e.priority)

        logger.debug(
            "Hook registered",
            extra={
                "point": point.value,
                "name": entry.name,
                "priority": priority,
            }
        )

    def on(
        self,
        point: HookPoint,
        priority: int = 100,
        name: str = "",
    ) -> Callable[[HookHandler], HookHandler]:
        """装饰器方式注册 Hook.
        
        Args:
            point: 触发点
            priority: 优先级
            name: Hook 名称
        
        Returns:
            装饰器函数
        
        Example:
            @hooks.on(HookPoint.BEFORE_TOOL_EXEC, priority=10)
            async def my_hook(ctx: HookContext) -> HookContext:
                return ctx
        """
        def decorator(handler: HookHandler) -> HookHandler:
            self.register(point, handler, priority, name)
            return handler
        return decorator

    async def trigger(self, ctx: HookContext) -> HookContext:
        """触发 Hook 链.
        
        按优先级顺序执行所有注册的 Hook。
        如果某个 Hook 返回 None，停止链式执行。
        
        Args:
            ctx: Hook 上下文
        
        Returns:
            HookContext: 处理后的上下文
        """
        entries = self._hooks.get(ctx.point, [])

        for entry in entries:
            if not entry.enabled:
                continue

            try:
                result = await entry.handler(ctx)

                # None 表示停止链式执行
                if result is None:
                    logger.debug(
                        "Hook chain stopped",
                        extra={
                            "point": ctx.point.value,
                            "stopped_at": entry.name,
                        }
                    )
                    break

                ctx = result

            except Exception as e:
                logger.error(
                    "Hook execution failed",
                    extra={
                        "point": ctx.point.value,
                        "hook_name": entry.name,
                        "error": str(e),
                    }
                )
                # Hook 失败不中断主流程

        return ctx

    def unregister(self, point: HookPoint, name: str) -> bool:
        """注销 Hook.
        
        Args:
            point: 触发点
            name: Hook 名称
        
        Returns:
            bool: 是否成功注销
        """
        entries = self._hooks.get(point, [])
        for i, entry in enumerate(entries):
            if entry.name == name:
                entries.pop(i)
                logger.debug(
                    "Hook unregistered",
                    extra={"point": point.value, "name": name}
                )
                return True
        return False

    def enable(self, point: HookPoint, name: str) -> bool:
        """启用 Hook."""
        for entry in self._hooks.get(point, []):
            if entry.name == name:
                entry.enabled = True
                return True
        return False

    def disable(self, point: HookPoint, name: str) -> bool:
        """禁用 Hook."""
        for entry in self._hooks.get(point, []):
            if entry.name == name:
                entry.enabled = False
                return True
        return False

    def list_hooks(self, point: HookPoint | None = None) -> list[dict[str, Any]]:
        """列出注册的 Hook.
        
        Args:
            point: 指定触发点（可选，None 表示所有）
        
        Returns:
            list[dict]: Hook 信息列表
        """
        result = []

        if point:
            entries = self._hooks.get(point, [])
            for entry in entries:
                result.append({
                    "point": point.value,
                    "name": entry.name,
                    "priority": entry.priority,
                    "enabled": entry.enabled,
                })
        else:
            for p, entries in self._hooks.items():
                for entry in entries:
                    result.append({
                        "point": p.value,
                        "name": entry.name,
                        "priority": entry.priority,
                        "enabled": entry.enabled,
                    })

        return result


# 全局 Hook 注册中心实例
_global_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    """获取全局 Hook 注册中心.
    
    Returns:
        HookRegistry: 全局注册中心实例
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = HookRegistry()
    return _global_registry


def reset_hook_registry() -> None:
    """重置全局 Hook 注册中心（用于测试）."""
    global _global_registry
    _global_registry = None
