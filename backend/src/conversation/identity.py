"""X-Agent 全局身份模型。

提供统一的、不可变的身份值对象，贯穿整个 Agent 生命周期。
每条消息、日志条目和工具调用都可以追溯到一个具体的身份。

设计原则：
  - Identity 是不可变值对象（frozen dataclass）
  - IdentityManager 是线程安全的单例，管理身份生命周期
  - 所有身份字段通过 contextvars 提供零成本访问
  - 向后兼容：AgentContext 委托给 Identity
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class AgentType(str, Enum):
    """多 Agent 层级中的 Agent 类型。

    - MAIN: 直接服务用户的主 Agent。
    - PARTNER: 与主 Agent 协作的对等 Agent。
    - SUB: 由主/对等 Agent 派生的子 Agent，用于子任务委派。
    """
    MAIN = "main"
    PARTNER = "partner"
    SUB = "sub"

class ChannelType(str, Enum):
    """用户交互渠道（用户从哪个渠道发起对话）。"""
    WEB_CHAT = "web_chat"
    CLI = "cli"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECHAT = "wechat"
    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"

class ChannelProtocol(str, Enum):
    """渠道底层通信协议。"""
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    SSE = "sse"
    STREAM = "stream"  # Stream 长连接协议（钉钉/飞书 Stream 模式）
    INTERNAL = "internal"  # 内部触发（cron/webhook/agent-to-agent）


@dataclass(frozen=True)
class Identity:
    """单次请求/操作的不可变身份值对象。

    这是"谁在哪个上下文中做什么"的唯一事实来源。
    所有下游组件（日志、压缩、记忆、工具）都从此对象读取，
    而不是各自维护分散的 ID 字段。

    Attributes:
        session_id:  会话级标识符，同一聊天会话内的消息共享。
        trace_id:    请求级标识符，每条用户消息/LLM 调用唯一，用于分布式追踪。
        agent_id:    处理此请求的 Agent 实例标识符，默认自动生成，可覆盖。
        channel_id:  通信通道标识符（如 WebSocket 连接 ID）。
        channel_type: 用户交互渠道（WEB_CHAT / CLI / DINGTALK / WECHAT）。
        channel_protocol: 底层通信协议（WEBSOCKET / REST_API / SSE）。
        user_id:     终端用户标识符（支持多用户场景）。
        agent_type:  Agent 在多 Agent 层级中的角色。
        parent_trace_id: 父操作的 trace_id（用于嵌套/子 Agent 调用）。
        metadata:    附加到此身份的任意额外数据。
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    channel_id: Optional[str] = None
    channel_type: ChannelType = ChannelType.WEB_CHAT
    channel_protocol: ChannelProtocol = ChannelProtocol.WEBSOCKET
    user_id: Optional[str] = None
    agent_type: AgentType = AgentType.MAIN
    parent_trace_id: Optional[str] = None
    metadata: tuple[tuple[str, Any], ...] = ()
    
    # 多 Agent 协同相关
    delegation_chain: tuple[str, ...] = ()      # 委派链路记录
    shared_context_id: Optional[str] = None     # 关联的共享上下文 ID

    # ---- 便捷方法 ------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为扁平字典，适用于日志输出和 JSON 序列化。"""
        return {
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type.value,
            "channel_protocol": self.channel_protocol.value,
            "user_id": self.user_id,
            "agent_type": self.agent_type.value,
            "parent_trace_id": self.parent_trace_id,
        }

    def derive(self, **overrides: Any) -> Identity:
        """派生子身份，继承大部分字段。

        适用于子 Agent 派生或嵌套操作：
        子身份获得新的 trace_id，但保留 session_id、user_id 等。

        Args:
            **overrides: 需要在子身份中覆盖的字段。

        Returns:
            带有新 trace_id 和调用方覆盖值的新 Identity。
        """
        base = {
            "session_id": self.session_id,
            "trace_id": str(uuid.uuid4()),
            "agent_id": self.agent_id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "channel_protocol": self.channel_protocol,
            "user_id": self.user_id,
            "agent_type": self.agent_type,
            "parent_trace_id": self.trace_id,
            "metadata": self.metadata,
            "delegation_chain": self.delegation_chain,
            "shared_context_id": self.shared_context_id,
        }
        base.update(overrides)
        return Identity(**base)


# ---------------------------------------------------------------------------
# 上下文变量 — 当前协程的全局"活跃身份"
# ---------------------------------------------------------------------------

_current_identity: ContextVar[Optional[Identity]] = ContextVar(
    "current_identity", default=None,
)

def get_current_identity() -> Optional[Identity]:
    """返回绑定到当前异步上下文的身份，如果未设置则返回 None。"""
    return _current_identity.get()

def set_current_identity(identity: Optional[Identity]) -> None:
    """将 identity 绑定到当前异步上下文。"""
    _current_identity.set(identity)


# ---------------------------------------------------------------------------
# IdentityManager — 管理身份生命周期的单例
# ---------------------------------------------------------------------------

class IdentityManager:
    """全局单例，负责创建、注册和查询身份。

    典型用法::

        manager = get_identity_manager()

        # WebSocket 连接时
        identity = manager.create(
            session_id=session_id,
            channel_id="ws-conn-abc",
            agent_type=AgentType.MAIN,
        )
        manager.activate(identity)

        # 下游任意位置
        current = manager.current  # 同一个 Identity 对象

        # 派生子 Agent 时
        child = manager.derive(agent_type=AgentType.SUB, agent_id="sub-001")
        manager.activate(child)

        # 清理
        manager.deactivate()
    """

    _instance: Optional[IdentityManager] = None

    def __new__(cls) -> IdentityManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_active_identities"):
            self._active_identities: dict[str, Identity] = {}

    # ---- 工厂方法 ---------------------------------------------------

    def create(
        self,
        *,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        channel_protocol: ChannelProtocol = ChannelProtocol.WEBSOCKET,
        user_id: Optional[str] = None,
        agent_type: AgentType = AgentType.MAIN,
        parent_trace_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Identity:
        """创建新的 Identity，支持显式指定或自动生成字段。

        Args:
            session_id:  会话级 ID（省略时自动生成）。
            trace_id:    请求级 ID（省略时自动生成）。
            agent_id:    Agent 实例 ID（省略时自动生成）。
            channel_id:  通道标识符。
            channel_type: 用户交互渠道。
            channel_protocol: 底层通信协议。
            user_id:     终端用户标识符。
            agent_type:  Agent 在层级中的角色。
            parent_trace_id: 嵌套调用的父 trace_id。
            metadata:    额外的键值对。

        Returns:
            一个新的、不可变的 Identity。
        """
        meta_tuple = tuple(metadata.items()) if metadata else ()
        kwargs: dict[str, Any] = {
            "agent_type": agent_type,
            "channel_type": channel_type,
            "channel_protocol": channel_protocol,
            "metadata": meta_tuple,
        }
        if session_id is not None:
            kwargs["session_id"] = session_id
        if trace_id is not None:
            kwargs["trace_id"] = trace_id
        if agent_id is not None:
            kwargs["agent_id"] = agent_id
        if channel_id is not None:
            kwargs["channel_id"] = channel_id
        if user_id is not None:
            kwargs["user_id"] = user_id
        if parent_trace_id is not None:
            kwargs["parent_trace_id"] = parent_trace_id

        return Identity(**kwargs)

    def derive(self, **overrides: Any) -> Identity:
        """从当前活跃身份派生子身份。

        如果没有活跃身份则抛出 ValueError。
        """
        current = self.current
        if current is None:
            raise ValueError("没有活跃的身份可供派生")
        return current.derive(**overrides)

    # ---- 激活 / 停用 -----------------------------------------

    def activate(self, identity: Identity) -> None:
        """将 identity 设为当前上下文的活跃身份。

        同时将其注册到以 trace_id 为键的内部注册表中。
        """
        self._active_identities[identity.trace_id] = identity
        set_current_identity(identity)

    def deactivate(self, identity: Optional[Identity] = None) -> Optional[Identity]:
        """清除活跃身份并从注册表中移除。

        Args:
            identity: 要停用的身份。如果为 None，则停用当前活跃身份。

        Returns:
            被停用的身份，如果没有活跃身份则返回 None。
        """
        if identity is None:
            identity = get_current_identity()
        if identity is not None:
            self._active_identities.pop(identity.trace_id, None)
            set_current_identity(None)
        return identity

    # ---- 查询 -------------------------------------------------------------

    @property
    def current(self) -> Optional[Identity]:
        """绑定到当前异步上下文的身份。"""
        return get_current_identity()

    def get_by_trace(self, trace_id: str) -> Optional[Identity]:
        """根据 trace_id 查找已注册的身份。"""
        return self._active_identities.get(trace_id)

    def get_by_trace_id(self, trace_id: str) -> Optional[Identity]:
        """根据 trace_id 查找已注册的身份（get_by_trace 的别名）。"""
        return self.get_by_trace(trace_id)

    def get_active_identities(self) -> list[Identity]:
        """返回所有当前已注册的身份（跨上下文）。"""
        return list(self._active_identities.values())

# 模块级便捷访问器
_manager: Optional[IdentityManager] = None

def get_identity_manager() -> IdentityManager:
    """返回全局 IdentityManager 单例。"""
    global _manager
    if _manager is None:
        _manager = IdentityManager()
    return _manager
