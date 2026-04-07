"""Gateway 请求分发器。

GatewayDispatcher 是 Gateway 的核心编排组件，负责：
1. Agent 解析：根据 Envelope 中的 agent_id / agent_name 路由到目标 Agent
2. Identity 构建：为每个请求创建 AgentContext（含 Identity）
3. Session 管理：确保 Session 存在（首次自动创建，重连时重新激活）
4. 请求分发：将 Envelope 转换为 AgentBridge.run() 调用，产出 GatewayEvent 流

从 agent_core/api/websocket.py 中的以下逻辑迁移而来：
- agent_websocket() 中的 Session 管理
- AgentContext.for_websocket() 的 Identity 构建
- Agent 实例创建和历史加载

设计原则：
- 协议无关：不依赖 WebSocket/HTTP 等具体协议
- 输入 Envelope，输出 AsyncGenerator[GatewayEvent]
- 多 Agent 路由：agent_id > agent_name > DEFAULT_AGENT_ID
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Optional

from .agent_bridge import AgentBridge
from .agent_info import AgentInfo
from ..runtime.adapters import GatewayAdapter as RuntimeGatewayAdapter

from ..agent_core.agent import Agent
from .envelope import Envelope, EnvelopeIntent
from .response import GatewayEvent, GatewayEventType
from .errors import (
    AgentNotFoundError,
    DispatchError,
    EnvelopeValidationError,
    SessionNotFoundError,
)

from ..conversation.identity import (
    AgentType,
    ChannelProtocol,
    ChannelType,
    Identity,
    IdentityManager,
    get_identity_manager,
)
from ..conversation.context import (
    AgentContext,
    get_current_context,
    set_current_context,
)
from ..conversation.dao import (
    DEFAULT_AGENT_ID,
    DEFAULT_CHANNEL_ID,
    DEFAULT_USER_ID,
)
from ..conversation.dao.models import (
    Agent as AgentORM,
)

try:
    from ..utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def _get_storage_service():
    """获取 StorageService 实例。"""
    from ..services.storage import get_storage_service
    return get_storage_service()


class GatewayDispatcher:
    """Gateway 请求分发器。

    编排 Envelope → Agent 解析 → Identity 构建 → Session 管理 → AgentBridge.run()
    的完整流程，产出协议无关的 GatewayEvent 流。

    典型用法::

        dispatcher = GatewayDispatcher()
        envelope = Envelope.create_chat(
            session_id="sess-123",
            content="你好",
            channel_type=ChannelType.WEB_CHAT,
            channel_protocol=ChannelProtocol.WEBSOCKET,
        )
        async for event in dispatcher.dispatch(envelope):
            # 各端点负责将 GatewayEvent 转换为自己的协议格式
            print(event)
    """

    def __init__(self, bridge: AgentBridge | None = None) -> None:
        self._bridge = bridge or AgentBridge()
        self._runtime_gateway_adapter = RuntimeGatewayAdapter(
            orchestrator=self._bridge.runtime_session_orchestrator,
        )

    async def dispatch(
        self,
        envelope: Envelope,
        *,
        abort_event: asyncio.Event | None = None,
        agent: Optional[Agent] = None,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """分发 Envelope 请求。

        完整流程：
        1. 验证 Envelope
        2. 解析目标 Agent（agent_id > agent_name > DEFAULT_AGENT_ID）
        3. 构建 Identity 和 AgentContext
        4. 确保 Session 存在
        5. 根据 intent 分发到对应处理器

        Args:
            envelope: 统一消息信封。
            abort_event: 中止事件。
            agent: 可选的已有 Agent 实例。有状态协议（如 WebSocket）
                   在连接级别创建 Agent 并缓存，每条消息复用同一实例，
                   避免重复加载历史。无状态协议（如 REST/SSE）不传此参数，
                   由 dispatcher 内部创建新实例。

        Yields:
            GatewayEvent 事件流。
        """
        # 1. 验证 Envelope
        self._validate_envelope(envelope)

        # 2. 解析目标 Agent
        agent_info = await self._resolve_agent(envelope)

        # 3. 构建 Identity 和 AgentContext
        context = self._build_context(envelope, agent_info)
        set_current_context(context)

        logger.info(
            "Gateway dispatch started",
            extra={
                "session_id": envelope.session_id,
                "intent": envelope.intent.value,
                "agent_id": agent_info.agent_id,
                "agent_name": agent_info.agent_name,
                "channel_type": envelope.channel_type.value,
            },
        )

        # 4. 根据 intent 分发
        if envelope.intent == EnvelopeIntent.PING:
            yield GatewayEvent.pong(
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )
            return

        if envelope.intent == EnvelopeIntent.ABORT:
            yield GatewayEvent.error(
                message="Abort acknowledged",
                error_type="AbortError",
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )
            return

        if envelope.intent == EnvelopeIntent.CHAT:
            async for event in self._dispatch_chat(
                envelope, agent_info,
                abort_event=abort_event,
                agent=agent,
            ):
                yield event
            return

        yield GatewayEvent.error(
            message=f"Unknown intent: {envelope.intent.value}",
            error_type="EnvelopeValidationError",
            agent_id=agent_info.agent_id,
            agent_name=agent_info.agent_name,
        )

    async def ensure_session(
        self,
        session_id: str,
        agent_info: AgentInfo,
        *,
        user_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        """确保 Session 存在（首次自动创建，重连时重新激活）。

        Args:
            session_id: 会话 ID。
            agent_info: 目标 Agent 信息。
            user_id: 用户 ID，默认使用 DEFAULT_USER_ID。
            channel_id: 渠道 ID，默认使用 DEFAULT_CHANNEL_ID。
        """
        from ..conversation.session import SessionManager

        session_manager = SessionManager()

        # 确保 sessions 表中存在
        existing = await session_manager.get_session(session_id)
        if existing is None:
            # 使用 Agent 名称作为会话标题
            from ..conversation.dao.models import Agent
            agent = Agent.from_config(agent_info.agent_id)
            title = f"{agent.agent_name} 对话" if agent else "Agent 对话"
            await session_manager.ensure_session(
                session_id,
                title=title,
                agent_id=agent_info.agent_id,
            )
            logger.info(
                "Session auto-created",
                extra={"session_id": session_id, "agent_id": agent_info.agent_id},
            )
        elif existing.status != "active":
            await session_manager.reactivate_session(session_id)
            logger.info("Session reactivated", extra={"session_id": session_id})

    async def close_session(self, session_id: str) -> None:
        """关闭 Session。

        Args:
            session_id: 会话 ID。
        """
        from ..conversation.session import SessionManager

        session_manager = SessionManager()
        await session_manager.close_session(session_id)

        logger.info("Session closed", extra={"session_id": session_id})

    async def touch_session(self, session_id: str) -> None:
        """更新 Session 活跃时间。

        Args:
            session_id: 会话 ID。
        """
        from ..conversation.session import SessionManager

        session_manager = SessionManager()
        await session_manager.touch_session(session_id)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _validate_envelope(self, envelope: Envelope) -> None:
        """验证 Envelope 的必要字段。

        委托给 Envelope.validate() 作为唯一验证入口，
        将返回的错误列表转换为 EnvelopeValidationError 异常。

        Args:
            envelope: 待验证的 Envelope。

        Raises:
            EnvelopeValidationError: 验证失败。
        """
        errors = envelope.validate()
        if errors:
            raise EnvelopeValidationError(errors)

    async def _resolve_agent(self, envelope: Envelope) -> AgentInfo:
        """解析目标 Agent。

        路由优先级：
        1. agent_id（显式指定）
        2. agent_name（按名称查找）
        3. bindings（通过 channel + peer 匹配）
        4. channel.agent_id（向后兼容）
        5. DEFAULT_AGENT_ID（默认）

        Args:
            envelope: 消息信封。

        Returns:
            解析到的 AgentInfo。

        Raises:
            AgentNotFoundError: 指定的 Agent 不存在。
        """
        from ..config.manager import get_config

        config = get_config()

        # 优先级 1: 通过 agent_id 查找
        if envelope.agent_id:
            agent = AgentORM.from_config(envelope.agent_id)
            if agent is None:
                raise AgentNotFoundError(
                    f"Agent not found: agent_id={envelope.agent_id}"
                )
            return AgentInfo.from_orm(agent)

        # 优先级 2: 通过 agent_name 查找
        if envelope.agent_name:
            agent = self._find_agent_by_name(envelope.agent_name)
            if agent is None:
                raise AgentNotFoundError(
                    f"Agent not found: agent_name={envelope.agent_name}"
                )
            return AgentInfo.from_orm(agent)

        # 优先级 3: 通过 bindings 解析（channel + peer -> agent）
        if envelope.channel_id:
            agent_id = config.multi_agent.resolve_agent_for_channel(
                envelope.channel_id,
                envelope.peer_id,
                envelope.peer_kind,
            )
            if agent_id:
                agent = AgentORM.from_config(agent_id)
                if agent:
                    return AgentInfo.from_orm(agent)

        # 优先级 4: 使用 channel.agent_id（向后兼容）
        if envelope.channel_id:
            channel = config.multi_agent.get_channel(envelope.channel_id)
            if channel and channel.agent_id:
                agent = AgentORM.from_config(channel.agent_id)
                if agent:
                    return AgentInfo.from_orm(agent)

        # 优先级 5: 通过 session_id 从数据库查找 agent_id
        # 当 envelope 没有携带 agent_id/agent_name/channel 信息时（如 cron 任务），
        # 通过 session 记录反查出该 session 归属的 agent，确保加载正确的上下文。
        if envelope.session_id:
            agent_info = await self._resolve_agent_from_session(envelope.session_id)
            if agent_info is not None:
                return agent_info

        # 优先级 6: 使用默认 Agent
        agent = AgentORM.from_config(DEFAULT_AGENT_ID)
        if agent is None:
            return AgentInfo.default()

        return AgentInfo.from_orm(agent)

    async def _resolve_agent_from_session(self, session_id: str) -> Optional[AgentInfo]:
        """通过 session_id 从数据库查找对应的 agent_id，并加载完整 AgentInfo。

        当 Envelope 没有携带 agent_id/agent_name/channel 信息时（如 cron 任务触发），
        通过 session 记录反查出该 session 归属的 agent，确保加载正确的工作空间和上下文。

        Args:
            session_id: 会话 ID。

        Returns:
            解析到的 AgentInfo，未找到时返回 None。
        """
        try:
            from ..conversation.session import SessionManager

            session_manager = SessionManager()
            session = await session_manager.get_session(session_id)

            if session is None or not session.agent_id:
                return None

            agent = AgentORM.from_config(session.agent_id)
            if agent is None:
                logger.warning(
                    "Session has agent_id but config not found",
                    extra={"session_id": session_id, "agent_id": session.agent_id},
                )
                return None

            agent_info = AgentInfo.from_orm(agent)
            logger.info(
                "Agent resolved from session",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_info.agent_id,
                    "agent_name": agent_info.agent_name,
                    "workspace": agent_info.workspace,
                },
            )
            return agent_info

        except Exception as exc:
            logger.warning(
                "Failed to resolve agent from session",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return None

    def _find_agent_by_name(self, agent_name: str) -> Optional[AgentORM]:
        """通过 agent_name 查找 Agent（从配置加载）。

        Args:
            agent_name: Agent 名称。

        Returns:
            Agent 实例，未找到时返回 None。
        """
        all_agents = AgentORM.list_all()
        return next((a for a in all_agents if a.agent_name == agent_name), None)

    def _build_context(
        self,
        envelope: Envelope,
        agent_info: AgentInfo,
    ) -> AgentContext:
        """构建 AgentContext（含 Identity）。

        Args:
            envelope: 消息信封。
            agent_info: 目标 Agent 信息。

        Returns:
            配置好的 AgentContext。
        """
        identity_manager = get_identity_manager()

        # 将 AgentInfo 的 agent_type 映射到 Identity 的 AgentType
        agent_type_mapping = {
            "main": AgentType.MAIN,
            "partner": AgentType.PARTNER,
            "sub": AgentType.SUB,
        }
        agent_type = agent_type_mapping.get(agent_info.agent_type, AgentType.MAIN)

        identity = identity_manager.create(
            session_id=envelope.session_id,
            agent_id=agent_info.agent_id,
            channel_id=envelope.channel_id,
            user_id=envelope.user_id,
            agent_type=agent_type,
            channel_type=envelope.channel_type,
            channel_protocol=envelope.channel_protocol,
        )

        context = AgentContext(identity=identity)
        identity_manager.activate(identity)

        logger.debug(
            "AgentContext built",
            extra=identity.to_dict(),
        )
        return context

    async def _dispatch_chat(
        self,
        envelope: Envelope,
        agent_info: AgentInfo,
        *,
        abort_event: asyncio.Event | None = None,
        agent: Optional[Agent] = None,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """分发 CHAT 意图的请求，默认走 runtime controller 主链路。"""
        try:
            result = await self.execute_runtime_turn(
                envelope,
                metadata={"persist_user_message": True},
            )
            async for event in self._turn_result_events(result, agent_info=agent_info):
                yield event

        except Exception as exc:
            logger.exception(
                "Error dispatching chat",
                extra={
                    "session_id": envelope.session_id,
                    "error": str(exc),
                },
            )
            yield GatewayEvent.error(
                message=str(exc),
                error_type=type(exc).__name__,
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )

    async def _turn_result_events(
        self,
        result,
        *,
        agent_info: AgentInfo,
    ) -> AsyncGenerator[GatewayEvent, None]:
        """Convert a runtime TurnResult into gateway events for clients."""
        current_context = get_current_context()
        if current_context is not None and current_context.trace_id:
            yield GatewayEvent.agent_start(
                trace_id=current_context.trace_id,
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )

        for runtime_event in list(result.metadata.get("runtime_event_timeline", []) or []):
            if not isinstance(runtime_event, dict):
                continue
            event_type = runtime_event.get("type")
            payload = runtime_event.get("payload")
            if not isinstance(payload, dict):
                continue
            if event_type == "tool_call":
                yield GatewayEvent.tool_call(
                    tool_call_id=str(payload.get("tool_call_id", "")),
                    name=str(payload.get("name", "")),
                    arguments=dict(payload.get("arguments", {}) or {}),
                    agent_id=agent_info.agent_id,
                    agent_name=agent_info.agent_name,
                )
            elif event_type == "tool_result":
                yield GatewayEvent(
                    type=GatewayEventType.TOOL_RESULT,
                    data={
                        "tool_call_id": str(payload.get("tool_call_id", "")),
                        "name": str(payload.get("name", "")),
                        "result": str(payload.get("result", "")),
                        "is_error": bool(payload.get("is_error", False)),
                        "details": dict(payload.get("details", {}) or {}),
                        "duration_ms": payload.get("duration_ms"),
                    },
                    agent_id=agent_info.agent_id,
                    agent_name=agent_info.agent_name,
                )

        output_text = result.output_text or ""
        if output_text:
            yield GatewayEvent.message_end(
                content=output_text,
                model=str(result.metadata.get("model", "")),
                stop_reason=result.finish_reason or "",
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )
        elif result.kind == "abort":
            yield GatewayEvent.error(
                message=result.finish_reason or "runtime turn aborted",
                error_type="RuntimeTurnAbort",
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )

        if current_context is not None and current_context.trace_id:
            yield GatewayEvent.agent_end(
                trace_id=current_context.trace_id,
                total_duration_ms=float(
                    result.metadata.get("budget", {}).get("elapsed_ms", 0)
                    or result.metadata.get("runtime_diagnostics", {})
                    .get("milestones_ms", {})
                    .get("completed", 0)
                    or result.metadata.get("runtime_diagnostics", {})
                    .get("milestones_ms", {})
                    .get("timed_out", 0)
                    or 0
                ),
                message_count=1 if output_text else 0,
                agent_id=agent_info.agent_id,
                agent_name=agent_info.agent_name,
            )

    async def prepare_runtime_turn(
        self,
        envelope: Envelope,
        *,
        metadata: dict[str, object] | None = None,
    ):
        """Prepare runtime session + turn request without replacing the legacy dispatch path."""
        agent_info = await self._resolve_agent(envelope)
        current_context = get_current_context()
        if (
            current_context is None
            or current_context.session_id != envelope.session_id
            or current_context.agent_id != agent_info.agent_id
        ):
            context = self._build_context(envelope, agent_info)
            set_current_context(context)
        await self.ensure_session(
            envelope.session_id,
            agent_info,
            user_id=envelope.user_id,
            channel_id=envelope.channel_id,
        )
        await self.touch_session(envelope.session_id)
        return await self._runtime_gateway_adapter.prepare_turn(
            envelope,
            metadata={
                **dict(metadata or {}),
                "agent_id": agent_info.agent_id,
                "persist_user_message": True,
            },
        )

    async def execute_runtime_turn(
        self,
        envelope: Envelope,
        *,
        metadata: dict[str, object] | None = None,
        controller=None,
    ):
        """Prepare and execute a runtime turn without switching the default dispatch path."""
        session, request = await self.prepare_runtime_turn(envelope, metadata=metadata)
        request = await self._runtime_gateway_adapter.enqueue(session, request)
        return await self._bridge.run_runtime_turn(request, controller=controller)
