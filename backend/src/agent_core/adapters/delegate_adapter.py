"""DelegateAdapter - 实现 DelegatePort Protocol.

基于 AgentBus 和 AgentRegistry 实现 Agent 间委派能力。
支持:
- 定向委派（指定目标 Agent ID）
- 能力匹配委派（根据所需能力自动选择）
- 广播通知
- 并行委派

Example:
    from agent_core.adapters.delegate_adapter import (
        DelegateAdapter,
        create_delegate_adapter,
    )
    
    # 使用工厂函数创建
    adapter = create_delegate_adapter(
        source_agent_id="leader-001",
    )
    
    # 定向委派
    result = await adapter.delegate(
        target_agent_id="worker-001",
        task=DelegateTask.create(
            task_type="research",
            description="分析市场数据",
        ),
    )
    
    # 能力匹配委派
    result = await adapter.delegate_by_capability(
        task=DelegateTask.create(
            task_type="code-review",
            description="审查 PR #123",
            required_capabilities=["code-review", "python"],
        ),
    )
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ..agent_bus import AgentBus, AgentBusMessage, get_agent_bus
from ..ports.delegate_port import DelegatePort, DelegateTask, DelegateResult

if TYPE_CHECKING:
    from ..hooks import HookRegistry
    from ...services.agent_registry import AgentRegistry

try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DelegateAdapter:
    """DelegatePort 适配器.
    
    基于 AgentBus 和 AgentRegistry 实现委派逻辑。
    
    职责:
    1. 实现 DelegatePort Protocol
    2. 通过 AgentBus 发送委派请求和接收响应
    3. 通过 AgentRegistry 进行能力匹配
    4. 在委派前后触发对应的 Hook
    
    Attributes:
        _source_agent_id: 发起委派的 Agent ID
        _bus: AgentBus 实例
        _registry: AgentRegistry 实例（可选，用于能力匹配）
        _hooks: HookRegistry 实例（可选）
        _trace_id: 分布式追踪 ID（可选）
    """
    
    def __init__(
        self,
        source_agent_id: str,
        bus: AgentBus | None = None,
        registry: AgentRegistry | None = None,
        hooks: HookRegistry | None = None,
        trace_id: str | None = None,
    ) -> None:
        """初始化适配器.
        
        Args:
            source_agent_id: 发起委派的 Agent ID
            bus: AgentBus 实例，为 None 时使用全局实例
            registry: AgentRegistry 实例，为 None 时使用全局实例
            hooks: Hook 注册中心（可选）
            trace_id: 分布式追踪 ID（可选）
        """
        self._source_agent_id = source_agent_id
        self._bus = bus or get_agent_bus()
        self._registry = registry
        self._hooks = hooks
        self._trace_id = trace_id
        
        # 确保 source agent 订阅消息
        self._bus.subscribe(source_agent_id)
    
    @property
    def source_agent_id(self) -> str:
        """获取发起委派的 Agent ID."""
        return self._source_agent_id
    
    def with_trace_id(self, trace_id: str) -> DelegateAdapter:
        """设置追踪 ID（链式调用）.
        
        Args:
            trace_id: 分布式追踪 ID
            
        Returns:
            self，支持链式调用
        """
        self._trace_id = trace_id
        return self
    
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
        start_time = time.time()
        
        # 触发 ON_AGENT_DELEGATE Hook
        if self._hooks:
            await self._trigger_delegate_hook(target_agent_id, task)
        
        # 创建请求消息
        request = AgentBusMessage.create_request(
            source=self._source_agent_id,
            target=target_agent_id,
            payload={
                "task_type": task.task_type,
                "description": task.description,
                "payload": task.payload,
                "priority": task.priority,
            },
            trace_id=self._trace_id,
            ttl=task.timeout,
        )
        
        logger.info(
            "Delegating task",
            extra={
                "source": self._source_agent_id,
                "target": target_agent_id,
                "task_type": task.task_type,
                "message_id": request.message_id,
            },
        )
        
        # 更新 registry 中的任务计数
        if self._registry:
            self._registry.increment_tasks(target_agent_id)
        
        try:
            # 发送请求并等待响应
            response = await self._bus.request(request, timeout=task.timeout)
            
            execution_time = (time.time() - start_time) * 1000
            
            # 检查响应类型
            if response.message_type.value == "error":
                result = DelegateResult.from_error(
                    error=response.payload.get("error", "Unknown error"),
                    agent_id=target_agent_id,
                    execution_time_ms=execution_time,
                    metadata={
                        "message_id": request.message_id,
                        "response_id": response.message_id,
                        "delegation_chain": list(response.delegation_chain),
                    },
                )
            else:
                result = DelegateResult.from_success(
                    result=response.payload,
                    agent_id=target_agent_id,
                    execution_time_ms=execution_time,
                    metadata={
                        "message_id": request.message_id,
                        "response_id": response.message_id,
                        "delegation_chain": list(response.delegation_chain),
                    },
                )
            
            logger.info(
                "Delegation completed",
                extra={
                    "target": target_agent_id,
                    "success": result.success,
                    "execution_time_ms": execution_time,
                },
            )
            
        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            result = DelegateResult.from_error(
                error=f"Delegation to '{target_agent_id}' timed out after {task.timeout}s",
                agent_id=target_agent_id,
                execution_time_ms=execution_time,
                metadata={"message_id": request.message_id, "timeout": True},
            )
            
            logger.warning(
                "Delegation timed out",
                extra={
                    "target": target_agent_id,
                    "timeout_seconds": task.timeout,
                },
            )
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            result = DelegateResult.from_error(
                error=str(e),
                agent_id=target_agent_id,
                execution_time_ms=execution_time,
                metadata={"message_id": request.message_id, "error_type": type(e).__name__},
            )
            
            logger.error(
                "Delegation failed",
                extra={
                    "target": target_agent_id,
                    "error": str(e),
                },
            )
            
        finally:
            # 更新 registry 中的任务计数
            if self._registry:
                self._registry.decrement_tasks(target_agent_id)
        
        # 触发 ON_AGENT_DELEGATE_RESULT Hook
        if self._hooks:
            await self._trigger_delegate_result_hook(target_agent_id, task, result)
        
        return result
    
    async def delegate_by_capability(
        self,
        task: DelegateTask,
    ) -> DelegateResult:
        """根据所需能力自动选择 Agent 并委派.
        
        Args:
            task: 委派任务描述（需设置 required_capabilities）
            
        Returns:
            DelegateResult: 委派结果
        """
        if self._registry is None:
            return DelegateResult.from_error(
                error="AgentRegistry not available for capability matching",
                execution_time_ms=0,
            )
        
        if not task.required_capabilities:
            return DelegateResult.from_error(
                error="No required_capabilities specified in task",
                execution_time_ms=0,
            )
        
        # 查找最佳匹配的 Agent
        best_agent = self._registry.find_best_match(task.required_capabilities)
        
        if best_agent is None:
            return DelegateResult.from_error(
                error=f"No agent found with capabilities: {task.required_capabilities}",
                execution_time_ms=0,
                metadata={"required_capabilities": task.required_capabilities},
            )
        
        logger.info(
            "Agent matched by capability",
            extra={
                "required_capabilities": task.required_capabilities,
                "matched_agent": best_agent.agent_id,
                "agent_load": best_agent.load,
            },
        )
        
        # 委派给匹配的 Agent
        return await self.delegate(best_agent.agent_id, task)
    
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
        # 创建广播消息
        message = AgentBusMessage.create_notification(
            source=self._source_agent_id,
            target="*",  # 广播标识
            payload=notification,
            trace_id=self._trace_id,
        )
        
        # 发送广播
        await self._bus.send(message)
        
        # 统计接收者数量（排除自己）
        stats = self._bus.get_statistics()
        recipient_count = max(0, stats.get("subscriber_count", 1) - 1)
        
        logger.info(
            "Broadcast notification sent",
            extra={
                "source": self._source_agent_id,
                "recipient_count": recipient_count,
                "notification_type": notification.get("type", "unknown"),
            },
        )
        
        return recipient_count
    
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
        if not tasks:
            return []
        
        logger.info(
            "Starting parallel delegation",
            extra={
                "task_count": len(tasks),
                "targets": [t[0] for t in tasks],
            },
        )
        
        # 创建所有委派任务
        coroutines = [
            self.delegate(target_agent_id, task)
            for target_agent_id, task in tasks
        ]
        
        # 并行执行
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # 处理异常
        final_results: list[DelegateResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(DelegateResult.from_error(
                    error=str(result),
                    agent_id=tasks[i][0],
                    metadata={"error_type": type(result).__name__},
                ))
            else:
                final_results.append(result)
        
        # 统计结果
        success_count = sum(1 for r in final_results if r.success)
        
        logger.info(
            "Parallel delegation completed",
            extra={
                "task_count": len(tasks),
                "success_count": success_count,
                "failure_count": len(tasks) - success_count,
            },
        )
        
        return final_results
    
    # === 内部方法: Hook 触发 ===
    
    async def _trigger_delegate_hook(
        self,
        target_agent_id: str,
        task: DelegateTask,
    ) -> None:
        """触发 ON_AGENT_DELEGATE Hook."""
        from ..hooks import HookContext, HookPoint
        
        if self._hooks is None:
            return
        
        hook_ctx = HookContext(
            point=HookPoint.ON_AGENT_DELEGATE,
            data={
                "source_agent_id": self._source_agent_id,
                "target_agent_id": target_agent_id,
                "task_type": task.task_type,
                "task_description": task.description,
                "task_payload": task.payload,
                "trace_id": self._trace_id,
            },
        )
        await self._hooks.trigger(hook_ctx)
    
    async def _trigger_delegate_result_hook(
        self,
        target_agent_id: str,
        task: DelegateTask,
        result: DelegateResult,
    ) -> None:
        """触发 ON_AGENT_DELEGATE_RESULT Hook."""
        from ..hooks import HookContext, HookPoint
        
        if self._hooks is None:
            return
        
        hook_ctx = HookContext(
            point=HookPoint.ON_AGENT_DELEGATE_RESULT,
            data={
                "source_agent_id": self._source_agent_id,
                "target_agent_id": target_agent_id,
                "task_type": task.task_type,
                "success": result.success,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "trace_id": self._trace_id,
            },
        )
        await self._hooks.trigger(hook_ctx)


# === 工厂函数 ===

def create_delegate_adapter(
    source_agent_id: str,
    bus: AgentBus | None = None,
    registry: AgentRegistry | None = None,
    hooks: HookRegistry | None = None,
    trace_id: str | None = None,
) -> DelegateAdapter:
    """创建 DelegateAdapter 的工厂函数.
    
    Args:
        source_agent_id: 发起委派的 Agent ID
        bus: AgentBus 实例，为 None 时使用全局实例
        registry: AgentRegistry 实例，为 None 时尝试获取全局实例
        hooks: Hook 注册中心（可选）
        trace_id: 分布式追踪 ID（可选）
        
    Returns:
        DelegateAdapter 实例
    """
    # 尝试获取全局 registry
    if registry is None:
        try:
            from ...services.agent_registry import get_agent_registry
            registry = get_agent_registry()
        except ImportError:
            logger.warning(
                "AgentRegistry not available, capability matching will be disabled"
            )
    
    adapter = DelegateAdapter(
        source_agent_id=source_agent_id,
        bus=bus,
        registry=registry,
        hooks=hooks,
        trace_id=trace_id,
    )
    
    logger.info(
        "DelegateAdapter created",
        extra={
            "source_agent_id": source_agent_id,
            "has_registry": registry is not None,
            "has_hooks": hooks is not None,
        },
    )
    
    return adapter
