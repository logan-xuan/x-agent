"""Agent 自动触发器。

AgentInvoker 是非用户发起的 Agent 对话的统一入口。
当 Cron 定时任务、外部 Webhook 或系统事件需要触发 Agent 思考时，
通过 AgentInvoker 执行完整的 agent_loop 流程。

与 NotifyTool 的区别：
- NotifyTool: Agent 自己在对话中调用，直接推送文本，不经过 agent_loop
- AgentInvoker: 外部触发，经过完整 agent_loop（加载上下文、技能、工具等）

完整链路：
1. Session 解析（ActiveSessionResolver）
2. 构建 Identity（ChannelProtocol.INTERNAL）
3. 从配置精准加载目标 Agent 的完整信息（workspace、persona、type 等）
4. 设置 AgentContext + contextvars
5. 确保 Session 存在
6. 创建 Agent + 加载历史（基于 agent_id 加载独有的上下文文件）
7. 执行 agent_loop
8. 持久化消息
9. 推送到 ConnectionRegistry / 暂存到 Outbox
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ..conversation.context import AgentContext, set_current_context
from ..conversation.dao.models import Agent as AgentORM
from ..conversation.identity import ChannelType
from ..runtime.adapters import GatewayAdapter as RuntimeGatewayAdapter
from .agent_bridge import AgentBridge
from .agent_info import AgentInfo
from .dispatcher import GatewayDispatcher
from .message_bus import OutboundMessage, get_message_bus
from .response import GatewayEventType
from .session_resolver import ActiveSessionResolver

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class InvokeSource(StrEnum):
    """触发来源。"""

    CRON = "cron"
    WEBHOOK = "webhook"
    AGENT = "agent"
    SYSTEM = "system"


@dataclass
class InvokeResult:
    """触发结果。

    Attributes:
        session_id: 使用的会话 ID。
        trace_id: 本次调用的追踪 ID。
        delivered: 是否实时推送成功。
        queued: 是否暂存到 outbox。
        response: Agent 的回复内容。
        error: 错误信息（如有）。
    """

    session_id: str = ""
    trace_id: str = ""
    delivered: bool = False
    queued: bool = False
    response: str | None = None
    error: str | None = None


class AgentInvoker:
    """Agent 自动触发器 — 非用户发起的 Agent 对话统一入口。

    使用场景：
    1. Cron 定时任务触发 Agent 思考并推送结果
    2. 外部事件（webhook）触发 Agent 响应
    3. Agent 工具中触发另一个 Agent 对话（多 Agent 协作）
    4. 系统级通知需要 Agent 润色后推送

    典型用法::

        invoker = AgentInvoker()

        # Cron 触发（必须指定 agent_id）
        result = await invoker.invoke(
            content="请总结今天的待办事项",
            agent_id="agent-daily",
            source=InvokeSource.CRON,
        )

        # Webhook 触发指定 Agent
        result = await invoker.invoke(
            content="有新的 PR 需要 review",
            agent_id="agent-review",
            channel_type=ChannelType.WEB_CHAT,
            source=InvokeSource.WEBHOOK,
        )
    """

    def __init__(
        self,
        bridge: AgentBridge | None = None,
        dispatcher: GatewayDispatcher | None = None,
    ) -> None:
        self._bridge = bridge or AgentBridge()
        self._dispatcher = dispatcher or GatewayDispatcher(self._bridge)
        self._runtime_gateway_adapter = RuntimeGatewayAdapter(
            orchestrator=self._bridge.runtime_session_orchestrator,
        )

    def _sanitize_runtime_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        """Drop reserved runtime/context keys before splatting metadata into context constructors."""
        reserved = {"source", "agent_id", "session_id", "channel_type"}
        return {key: value for key, value in dict(metadata or {}).items() if key not in reserved}

    def _canonicalize_agent_id(self, agent_id: str) -> str:
        """将别名 Agent ID 归一化为配置中的标准 ID。"""
        from ..config.manager import get_config

        return get_config().multi_agent.resolve_agent_id(agent_id) or agent_id

    async def invoke(
        self,
        content: str,
        *,
        agent_id: str,
        session_id: str | None = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        source: InvokeSource = InvokeSource.CRON,
        metadata: dict[str, Any] | None = None,
    ) -> InvokeResult:
        """触发一次完整的 Agent 对话。

        多 Agent 模式下，每个 Agent 拥有独立的工作空间目录和个性文件
        （identity.md、spirit.md、owner.md、agents.md、tools.md 以及 memory 文件），
        因此 agent_id 是必需参数，用于精准加载目标 Agent 的配置和上下文。

        Args:
            content: 触发消息内容（作为 user prompt 传入 agent_loop）。
            agent_id: 目标 Agent ID（必需）。每个 Agent 有独立的工作空间和个性文件，
                      必须显式指定才能正确加载 identity/spirit/owner/tools/memory 等。
            session_id: 目标会话 ID（可选，未传入时自动解析）。
            channel_type: 目标渠道类型。
            source: 触发来源。
            metadata: 附加元数据。

        Returns:
            触发结果。
        """
        trace_id = str(uuid4())
        canonical_agent_id = self._canonicalize_agent_id(agent_id)

        logger.info(
            "AgentInvoker.invoke started",
            extra={
                "content_length": len(content),
                "agent_id": canonical_agent_id,
                "channel_type": channel_type.value,
                "source": source.value,
                "trace_id": trace_id,
            },
        )

        try:
            # 1. Session 解析
            resolved_session_id = await self._resolve_session(
                session_id,
                canonical_agent_id,
                channel_type,
            )

            # 2. 构建 Identity + AgentContext
            context_metadata = self._sanitize_runtime_metadata(metadata)
            context = AgentContext.for_internal(
                session_id=resolved_session_id,
                source=source.value,
                agent_id=canonical_agent_id,
                channel_type=channel_type,
                **context_metadata,
            )
            set_current_context(context)

            # 3. 从配置精准加载目标 Agent 的完整信息
            agent_info = self._resolve_agent_info(canonical_agent_id)

            # 4. 确保 Session 存在
            await self._dispatcher.ensure_session(
                resolved_session_id,
                agent_info,
            )

            # 5. 创建 Agent + 加载历史
            agent = self._bridge.create_agent(agent_info=agent_info)

            logger.info(
                "[AgentInvoker] Agent created, system_prompt preview",
                extra={
                    "agent_id": agent_info.agent_id,
                    "workspace": agent_info.workspace,
                    "system_prompt_length": len(agent._system_prompt)
                    if hasattr(agent, "_system_prompt")
                    else 0,
                    "system_prompt_head": (
                        agent._system_prompt[:200]
                        if hasattr(agent, "_system_prompt") and agent._system_prompt
                        else ""
                    ),
                },
            )

            await self._bridge.load_session_history(agent, resolved_session_id)

            # 6. 执行 agent_loop 并收集响应
            response_content = await self._run_and_collect(
                agent=agent,
                content=content,
                session_id=resolved_session_id,
                agent_info=agent_info,
            )

            # 7. 推送结果到客户端
            delivered, queued = await self._push_response(
                session_id=resolved_session_id,
                response=response_content,
                source=source,
            )

            logger.info(
                "AgentInvoker.invoke completed",
                extra={
                    "session_id": resolved_session_id,
                    "trace_id": trace_id,
                    "response_length": len(response_content) if response_content else 0,
                    "delivered": delivered,
                    "queued": queued,
                },
            )

            return InvokeResult(
                session_id=resolved_session_id,
                trace_id=trace_id,
                delivered=delivered,
                queued=queued,
                response=response_content,
            )

        except Exception as exc:
            logger.exception(
                "AgentInvoker.invoke failed",
                extra={
                    "agent_id": agent_id,
                    "canonical_agent_id": canonical_agent_id,
                    "source": source.value,
                    "error": str(exc),
                },
            )
            return InvokeResult(
                session_id=session_id or "",
                trace_id=trace_id,
                delivered=False,
                error=str(exc),
            )

    def _resolve_agent_info(self, agent_id: str) -> AgentInfo:
        """从配置精准加载目标 Agent 的完整信息。

        通过 AgentORM.from_config() 从 x-agent.yaml 加载 Agent 的完整配置，
        包括 workspace、persona、type、feature 等字段，确保 AgentBridge
        能正确解析 agent 独有的工作空间并加载对应的上下文文件
        （IDENTITY.md、SPIRIT.md、OWNER.md、AGENTS.md、TOOLS.md、MEMORY.md 等）。

        Args:
            agent_id: 目标 Agent ID。

        Returns:
            包含完整配置信息的 AgentInfo 值对象。

        Raises:
            ValueError: agent_id 在配置中不存在。
        """
        agent_orm = AgentORM.from_config(agent_id)
        if agent_orm is None:
            raise ValueError(
                f"Agent not found in configuration: agent_id={agent_id}. "
                f"Please check x-agent.yaml multi_agent.agents section."
            )

        agent_info = AgentInfo.from_orm(agent_orm)

        logger.info(
            "[AgentInvoker] Agent info resolved from config",
            extra={
                "agent_id": agent_info.agent_id,
                "agent_name": agent_info.agent_name,
                "agent_type": agent_info.agent_type,
                "workspace": agent_info.workspace,
                "feature": agent_info.feature,
            },
        )

        return agent_info

    async def _resolve_session(
        self,
        session_id: str | None,
        agent_id: str,
        channel_type: ChannelType,
    ) -> str:
        """解析目标 session_id。

        Args:
            session_id: 显式传入的 session_id。
            agent_id: Agent ID。
            channel_type: 渠道类型。

        Returns:
            解析后的 session_id。
        """
        if session_id:
            return session_id

        resolver = ActiveSessionResolver()
        return await resolver.resolve(
            agent_id=agent_id,
            channel_type=channel_type,
            auto_create=True,
        )

    async def _run_and_collect(
        self,
        agent,
        content: str,
        session_id: str,
        agent_info: AgentInfo,
    ) -> str:
        """执行 agent_loop 并收集完整响应文本。

        必须消费完整个事件流，不能提前 return，否则 async generator
        会被关闭，导致 agent_loop 中 yield 之后的清理逻辑（如
        log_llm_call_end）无法执行，Trace 面板会显示 LLM 调用
        一直"进行中"。

        Args:
            agent: Agent 实例。
            content: 用户消息。
            session_id: 会话 ID。
            agent_info: Agent 信息。

        Returns:
            Agent 的完整回复文本。
        """
        response_parts: list[str] = []
        final_content: str | None = None

        async for event in self._bridge.run(
            agent=agent,
            content=content,
            session_id=session_id,
            agent_info=agent_info,
            persist_user_message=False,
        ):
            if event.type == GatewayEventType.TEXT_CHUNK:
                chunk = event.data.get("content", "")
                if chunk:
                    response_parts.append(chunk)
            elif event.type == GatewayEventType.MESSAGE_END:
                full_content = event.data.get("content", "")
                if full_content:
                    final_content = full_content

        return final_content or "".join(response_parts)

    async def _push_response(
        self,
        session_id: str,
        response: str,
        source: InvokeSource,
    ) -> tuple[bool, bool]:
        """将 Agent 响应推送到客户端。

        注意：消息持久化已在 agent_bridge.py 的 _persist_assistant_messages()
        中完成（AgentEndEvent 时自动触发），此处只需负责实时推送。

        Args:
            session_id: 会话 ID。
            response: Agent 回复内容。
            source: 触发来源。

        Returns:
            (delivered, queued) 元组。
        """
        if not response:
            return False, False

        # 实时推送到客户端
        bus = get_message_bus()
        outbound = OutboundMessage(
            session_id=session_id,
            message_type="conversation",
            content={
                "content": response,
                "source": source.value,
            },
            source=source.value,
        )

        result = await bus.send(session_id, outbound)
        return result.delivered, result.queued

    async def prepare_runtime_turn(
        self,
        content: str,
        *,
        agent_id: str,
        session_id: str | None = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        source: InvokeSource = InvokeSource.CRON,
        metadata: dict[str, Any] | None = None,
    ):
        """Prepare a runtime turn request for internal triggers without invoking legacy agent_loop."""
        canonical_agent_id = self._canonicalize_agent_id(agent_id)
        resolved_session_id = await self._resolve_session(
            session_id, canonical_agent_id, channel_type
        )
        context_metadata = self._sanitize_runtime_metadata(metadata)
        context = AgentContext.for_internal(
            session_id=resolved_session_id,
            source=source.value,
            agent_id=canonical_agent_id,
            channel_type=channel_type,
            **context_metadata,
        )
        set_current_context(context)
        agent_info = self._resolve_agent_info(canonical_agent_id)
        await self._dispatcher.ensure_session(resolved_session_id, agent_info)
        payload = {
            "session_id": resolved_session_id,
            "content": content,
            "channel": channel_type.value,
            "user_id": None,
            "channel_id": None,
            "metadata": {
                **context_metadata,
                "source": source.value,
                "agent_id": canonical_agent_id,
                "persist_user_message": False,
            },
            "lane": "cron" if source == InvokeSource.CRON else "background_tool",
        }
        return await self._runtime_gateway_adapter.prepare_turn(payload, user_input=content)

    async def execute_runtime_turn(
        self,
        content: str,
        *,
        agent_id: str,
        session_id: str | None = None,
        channel_type: ChannelType = ChannelType.WEB_CHAT,
        source: InvokeSource = InvokeSource.CRON,
        metadata: dict[str, Any] | None = None,
        controller=None,
    ):
        """Prepare and execute a runtime turn for internal triggers."""
        _, request = await self.prepare_runtime_turn(
            content,
            agent_id=agent_id,
            session_id=session_id,
            channel_type=channel_type,
            source=source,
            metadata=metadata,
        )
        return await self._bridge.run_runtime_turn(request, controller=controller)
