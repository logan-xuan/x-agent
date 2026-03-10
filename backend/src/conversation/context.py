"""X-Agent 上下文管理。

提供贯穿 Agent 生命周期的执行上下文，
包括会话状态、追踪和元数据管理。

身份字段（session_id、trace_id、agent_id、channel_id、user_id、agent_type）
委托给 :class:`Identity` 值对象，同时保持与现有调用方的完全向后兼容。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid
from contextvars import ContextVar

from .identity import (
    AgentType,
    ChannelProtocol,
    ChannelType,
    Identity,
    get_identity_manager,
    set_current_identity,
)

# 向后兼容别名 — ContextSource 已废弃。
# 请使用 ChannelProtocol（通信协议）和 ChannelType（交互渠道）替代。
ContextSource = ChannelProtocol

# 请求级上下文变量
_current_context: ContextVar["AgentContext"] = ContextVar("agent_context")

def get_current_context() -> Optional["AgentContext"]:
    """获取当前请求上下文，如果未设置则返回 None。"""
    try:
        return _current_context.get()
    except LookupError:
        return None

def set_current_context(ctx: "AgentContext") -> None:
    """设置当前请求上下文。

    同时同步 Identity 上下文变量，使通过 ``get_current_identity()``
    获取的身份与当前上下文一致。
    """
    _current_context.set(ctx)
    if ctx is not None and ctx.identity is not None:
        identity_mgr = get_identity_manager()
        identity_mgr.activate(ctx.identity)

def clear_current_context() -> None:
    """清除当前请求上下文。"""
    try:
        _current_context.set(None)  # type: ignore
        set_current_identity(None)
    except LookupError:
        pass

@dataclass
class AgentContext:
    """单次 Agent 请求的执行上下文。

    此上下文贯穿整个请求生命周期：
    1. 请求到达时创建（WebSocket 消息或 REST API 调用）
    2. 传递给所有中间件和处理器
    3. 用于日志、追踪和状态管理
    4. 请求完成时清理

    身份字段（trace_id、session_id、agent_id、channel_id、user_id、
    agent_type、channel_type、channel_protocol）存储在内嵌的
    :pyattr:`identity` 对象中。为了向后兼容，常用字段也作为
    顶层 property 暴露。

    Attributes:
        identity: 不可变的身份值对象。
        request_id: 会话内唯一的请求标识符。
        metadata: 附加的上下文数据。
        created_at: 上下文创建时间。
    """

    # --- 核心身份 -------------------------------------------------------
    identity: Identity = field(default_factory=Identity)

    # --- 请求级字段 ------------------------------------------------
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # 计时追踪
    _start_time: Optional[float] = field(default=None, repr=False)
    _end_time: Optional[float] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._start_time = datetime.utcnow().timestamp()

    # --- 向后兼容的 property 代理 -------------------------------

    @property
    def trace_id(self) -> str:
        return self.identity.trace_id

    @trace_id.setter
    def trace_id(self, value: str) -> None:
        # Identity 是 frozen 的，需要用新值重建
        self.identity = Identity(
            session_id=self.identity.session_id,
            trace_id=value,
            agent_id=self.identity.agent_id,
            channel_id=self.identity.channel_id,
            channel_type=self.identity.channel_type,
            channel_protocol=self.identity.channel_protocol,
            user_id=self.identity.user_id,
            agent_type=self.identity.agent_type,
            parent_trace_id=self.identity.parent_trace_id,
            metadata=self.identity.metadata,
        )

    @property
    def session_id(self) -> Optional[str]:
        return self.identity.session_id

    @session_id.setter
    def session_id(self, value: Optional[str]) -> None:
        self.identity = Identity(
            session_id=value or str(uuid.uuid4()),
            trace_id=self.identity.trace_id,
            agent_id=self.identity.agent_id,
            channel_id=self.identity.channel_id,
            channel_type=self.identity.channel_type,
            channel_protocol=self.identity.channel_protocol,
            user_id=self.identity.user_id,
            agent_type=self.identity.agent_type,
            parent_trace_id=self.identity.parent_trace_id,
            metadata=self.identity.metadata,
        )

    @property
    def user_id(self) -> Optional[str]:
        return self.identity.user_id

    @user_id.setter
    def user_id(self, value: Optional[str]) -> None:
        self.identity = Identity(
            session_id=self.identity.session_id,
            trace_id=self.identity.trace_id,
            agent_id=self.identity.agent_id,
            channel_id=self.identity.channel_id,
            channel_type=self.identity.channel_type,
            channel_protocol=self.identity.channel_protocol,
            user_id=value,
            agent_type=self.identity.agent_type,
            parent_trace_id=self.identity.parent_trace_id,
            metadata=self.identity.metadata,
        )

    @property
    def parent_trace_id(self) -> Optional[str]:
        return self.identity.parent_trace_id

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def channel_id(self) -> Optional[str]:
        return self.identity.channel_id

    @property
    def agent_type(self) -> AgentType:
        return self.identity.agent_type

    @property
    def channel_type(self) -> ChannelType:
        return self.identity.channel_type

    @property
    def channel_protocol(self) -> ChannelProtocol:
        return self.identity.channel_protocol

    @property
    def source(self) -> ChannelProtocol:
        """channel_protocol 的向后兼容别名。"""
        return self.identity.channel_protocol

    # --- 计时 -------------------------------------------------------------

    @property
    def elapsed_ms(self) -> Optional[float]:
        """自上下文创建以来的耗时（毫秒）。"""
        if self._start_time is None:
            return None
        end = self._end_time or datetime.utcnow().timestamp()
        return (end - self._start_time) * 1000

    def complete(self) -> None:
        """标记此上下文为已完成。"""
        self._end_time = datetime.utcnow().timestamp()

    # --- 序列化 ------------------------------------------------------

    def to_log_dict(self) -> dict[str, Any]:
        """转换为日志字典（包含完整身份信息）。"""
        metadata_dict = self.metadata if isinstance(self.metadata, dict) else {}
        result = self.identity.to_dict()
        result.update({
            "request_id": self.request_id,
            "elapsed_ms": self.elapsed_ms,
            "created_at": self.created_at.isoformat(),
            "metadata": {k: v for k, v in metadata_dict.items() if not k.startswith("_")},
        })
        return result

    # --- 子上下文 / 派生 -----------------------------------------------------

    def child(self, **overrides: Any) -> "AgentContext":
        """为嵌套操作创建子上下文。"""
        child_identity = self.identity.derive(
            agent_type=overrides.pop("agent_type", self.identity.agent_type),
            agent_id=overrides.pop("agent_id", None) or self.identity.agent_id,
            user_id=overrides.pop("user_id", self.identity.user_id),
        )
        return AgentContext(
            identity=child_identity,
            request_id=str(uuid.uuid4())[:8],
            metadata={**self.metadata, **overrides.get("metadata", {})},
        )

    # --- 工厂类方法 ----------------------------------------------

    @classmethod
    def for_internal(
        cls,
        session_id: str,
        *,
        source: str = "cron",
        agent_id: Optional[str] = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        **metadata: Any,
    ) -> "AgentContext":
        """为内部触发（cron/webhook/agent-to-agent）创建上下文。

        与 for_websocket 的区别：
        - channel_protocol = INTERNAL
        - user_id = "system"
        - metadata 中携带 source 信息

        Args:
            session_id: 会话 ID。
            source: 触发来源（cron/webhook/agent/system）。
            agent_id: 目标 Agent ID。
            channel_type: 目标渠道类型。
            **metadata: 附加元数据。

        Returns:
            配置好的 AgentContext。
        """
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            session_id=session_id,
            agent_id=agent_id,
            channel_type=channel_type,
            channel_protocol=ChannelProtocol.INTERNAL,
            user_id="system",
            metadata={"source": source, **metadata},
        )
        return cls(identity=identity, metadata={"source": source, **metadata})

    @classmethod
    def for_websocket(
        cls,
        session_id: str,
        *,
        agent_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_type: AgentType = AgentType.MAIN,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        **metadata: Any,
    ) -> "AgentContext":
        """为 WebSocket 消息创建上下文。"""
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            session_id=session_id,
            agent_id=agent_id,
            channel_id=channel_id,
            user_id=user_id,
            agent_type=agent_type,
            channel_type=channel_type,
            channel_protocol=ChannelProtocol.WEBSOCKET,
        )
        return cls(identity=identity, metadata=metadata)

    @classmethod
    def for_rest_api(
        cls,
        session_id: Optional[str] = None,
        *,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        **metadata: Any,
    ) -> "AgentContext":
        """为 REST API 请求创建上下文。"""
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            channel_type=channel_type,
            channel_protocol=ChannelProtocol.REST_API,
        )
        return cls(identity=identity, metadata=metadata)

    @classmethod
    def for_cli(cls, **metadata: Any) -> "AgentContext":
        """为 CLI 命令创建上下文。"""
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            channel_type=ChannelType.CLI,
            channel_protocol=ChannelProtocol.REST_API,
        )
        return cls(identity=identity, metadata=metadata)


class ContextManager:
    """Manages context lifecycle for requests.

    Usage::

        async with context_manager.request(session_id="abc") as ctx:
            # ctx is automatically set as current context
            # and available via get_current_context()
            ...
    """

    def __init__(self) -> None:
        self._active_contexts: dict[str, AgentContext] = {}

    def request(
        self,
        session_id: Optional[str] = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        channel_protocol: ChannelProtocol = ChannelProtocol.WEBSOCKET,
        **metadata: Any,
    ) -> "ContextGuard":
        """Create a request-scoped context.

        Args:
            session_id: Optional session identifier
            channel_type: User-facing interaction channel
            channel_protocol: Underlying communication protocol
            **metadata: Additional context metadata

        Returns:
            Context guard for use with 'async with'
        """
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create(
            session_id=session_id,
            channel_type=channel_type,
            channel_protocol=channel_protocol,
        )
        ctx = AgentContext(identity=identity, metadata=metadata)
        return ContextGuard(self, ctx)

    def register(self, ctx: AgentContext) -> None:
        """Register an active context."""
        self._active_contexts[ctx.trace_id] = ctx
        set_current_context(ctx)

    def unregister(self, ctx: AgentContext) -> None:
        """Unregister a context."""
        if ctx.trace_id in self._active_contexts:
            del self._active_contexts[ctx.trace_id]
        clear_current_context()

    def get_active_contexts(self) -> list[AgentContext]:
        """Get all active contexts."""
        return list(self._active_contexts.values())


class ContextGuard:
    """Context manager guard for request-scoped context."""

    def __init__(self, manager: ContextManager, ctx: AgentContext) -> None:
        self._manager = manager
        self._ctx = ctx

    def __enter__(self) -> AgentContext:
        self._manager.register(self._ctx)
        return self._ctx

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._ctx.complete()
        self._manager.unregister(self._ctx)

    async def __aenter__(self) -> AgentContext:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


# Global context manager instance
context_manager = ContextManager()
