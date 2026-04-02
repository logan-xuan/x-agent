"""Agent 委派端口定义.

DelegatePort 定义了 agent_core 与其他 Agent 交互的接口。
允许 Agent 在循环中委派任务给其他 Agent。

设计原则：
- 零外部依赖，仅使用 Python 标准库
- 使用 Protocol 定义接口，实现结构化子类型
- 使用 dataclass 定义数据类型
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class DelegateTask:
    """委派任务描述.
    
    Attributes:
        task_type: 任务类型标识（如 "research", "code-analysis", "summarize"）
        description: 任务描述（自然语言）
        payload: 任务参数
        priority: 优先级（数字越大越优先）
        timeout: 超时秒数
        required_capabilities: 指定目标 Agent 所需能力而非 ID
    """

    task_type: str          # 任务类型标识
    description: str        # 任务描述（自然语言）
    payload: dict[str, Any] = field(default_factory=dict)  # 任务参数
    priority: int = 0       # 优先级
    timeout: float = 120.0  # 超时秒数

    # 可选：指定目标 Agent 能力而非 ID
    required_capabilities: list[str] | None = None

    @classmethod
    def create(
        cls,
        task_type: str,
        description: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> DelegateTask:
        """创建委派任务的便捷方法.
        
        Args:
            task_type: 任务类型
            description: 任务描述
            payload: 任务参数
            **kwargs: 其他参数（priority, timeout, required_capabilities）
            
        Returns:
            DelegateTask: 委派任务
        """
        return cls(
            task_type=task_type,
            description=description,
            payload=payload or {},
            **kwargs,
        )


@dataclass
class DelegateResult:
    """委派结果.
    
    Attributes:
        success: 是否成功
        result: 执行结果
        error: 错误信息（如果失败）
        agent_id: 实际执行的 Agent ID
        execution_time_ms: 执行时间（毫秒）
        metadata: 额外元数据
    """

    success: bool
    result: Any = None
    error: str | None = None
    agent_id: str | None = None  # 实际执行的 Agent
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_success(
        cls,
        result: Any,
        agent_id: str,
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> DelegateResult:
        """创建成功结果.
        
        Args:
            result: 执行结果
            agent_id: 执行的 Agent ID
            execution_time_ms: 执行时间
            metadata: 额外元数据
            
        Returns:
            DelegateResult: 成功结果
        """
        return cls(
            success=True,
            result=result,
            agent_id=agent_id,
            execution_time_ms=execution_time_ms,
            metadata=metadata or {},
        )

    @classmethod
    def from_error(
        cls,
        error: str,
        agent_id: str | None = None,
        execution_time_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> DelegateResult:
        """创建失败结果.
        
        Args:
            error: 错误信息
            agent_id: 尝试执行的 Agent ID（可选）
            execution_time_ms: 执行时间
            metadata: 额外元数据
            
        Returns:
            DelegateResult: 失败结果
        """
        return cls(
            success=False,
            error=error,
            agent_id=agent_id,
            execution_time_ms=execution_time_ms,
            metadata=metadata or {},
        )


class DelegatePort(Protocol):
    """Agent Core 的委派接口.
    
    允许 Agent 在循环中委派任务给其他 Agent。
    
    支持的委派模式：
    1. 定向委派：指定目标 Agent ID
    2. 能力匹配：根据所需能力自动选择 Agent
    3. 广播通知：向所有 Agent 发送通知
    4. 并行委派：同时委派多个任务
    
    Example:
        class MyDelegateAdapter:
            def __init__(self, bus: AgentBus, registry: AgentRegistry):
                self.bus = bus
                self.registry = registry
            
            async def delegate(
                self,
                target_agent_id: str,
                task: DelegateTask,
            ) -> DelegateResult:
                # 创建请求消息
                request = AgentMessage.create_request(
                    source=self.current_agent_id,
                    target=target_agent_id,
                    payload={
                        "task_type": task.task_type,
                        "description": task.description,
                        "payload": task.payload,
                    },
                    ttl=task.timeout,
                )
                
                # 发送并等待响应
                response = await self.bus.request(request, timeout=task.timeout)
                
                if response.message_type == AgentMessageType.ERROR:
                    return DelegateResult.from_error(
                        error=response.payload.get("error", "Unknown error"),
                        agent_id=target_agent_id,
                    )
                
                return DelegateResult.from_success(
                    result=response.payload,
                    agent_id=target_agent_id,
                )
    """

    async def delegate(
        self,
        target_agent_id: str,
        task: DelegateTask,
    ) -> DelegateResult:
        """委派任务给指定 Agent.
        
        Args:
            target_agent_id: 目标 Agent ID
            task: 委派任务描述
            
        Returns:
            DelegateResult: 委派结果
        """
        ...

    async def delegate_by_capability(
        self,
        task: DelegateTask,
    ) -> DelegateResult:
        """根据所需能力自动选择 Agent 并委派.
        
        选择策略：
        1. 查找拥有所有 required_capabilities 的 Agent
        2. 选择负载最低的 Agent
        3. 如果没有合适的 Agent，返回失败
        
        Args:
            task: 委派任务描述（需设置 required_capabilities）
            
        Returns:
            DelegateResult: 委派结果
        """
        ...

    async def broadcast(
        self,
        notification: dict[str, Any],
    ) -> int:
        """广播通知给所有 Agent.
        
        Args:
            notification: 通知内容
            
        Returns:
            int: 接收通知的 Agent 数量
        """
        ...

    async def delegate_parallel(
        self,
        tasks: list[tuple[str, DelegateTask]],
    ) -> list[DelegateResult]:
        """并行委派多个任务，等待所有完成.
        
        Args:
            tasks: 任务列表，每项为 (target_agent_id, task)
            
        Returns:
            list[DelegateResult]: 结果列表，顺序与输入一致
        """
        ...
