"""Unit tests for runtime gateway bridge helpers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.agent_core.adapters.llm_adapter import XAgentLLMAdapter
from src.agent_core.api.dev_routes import get_logger as get_agent_logger
from src.agent_core.config import AgentCoreConfig
from src.agent_core.types import AssistantMessage, MessageEndEvent, TextContent, UserMessage
from src.conversation.context import (
    AgentContext,
    clear_current_context,
    get_current_context,
    set_current_context,
)
from src.conversation.identity import ChannelProtocol, ChannelType
from src.gateway.agent_bridge import AgentBridge
from src.gateway.agent_invoker import AgentInvoker, InvokeSource
from src.gateway.dispatcher import GatewayDispatcher
from src.gateway.envelope import Envelope
from src.gateway.response import GatewayEventType
from src.gateway.tool_result_normalizer import RuntimeToolResultNormalizer
from src.runtime.adapters import GatewayAdapter
from src.runtime.repositories import (
    ResumeSessionState,
    StateSnapshotRecord,
    SummaryRecord,
    TranscriptEntry,
)
from src.runtime.routing import RouteDecision
from src.runtime.turn.state import TurnState
from src.runtime.types import (
    CompactResult,
    GovernedToolPlan,
    RouteMeta,
    SessionDescriptor,
    TaskFrame,
    ToolCallSpec,
    ToolExecutionPlan,
    TurnRequest,
    TurnResult,
)


@pytest.mark.asyncio
async def test_runtime_gateway_adapter_prepares_turn_from_envelope():
    adapter = GatewayAdapter(orchestrator=AgentBridge().runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="hello runtime",
        session_id="sess-1",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        user_id="user-1",
        channel_id="channel-1",
        metadata={"origin": "web"},
    )

    session, request = await adapter.prepare_turn(
        envelope,
        task_frame=TaskFrame(objective="custom objective"),
        metadata={"extra": "value"},
    )

    assert session.session_id == "sess-1"
    assert request.task_frame.objective == "custom objective"
    assert request.route.channel == "web_chat"
    assert request.route.user_id == "user-1"
    assert request.metadata["origin"] == "web"
    assert request.metadata["extra"] == "value"
    assert request.metadata["runtime_timeout_ms"] == 180000
    assert request.metadata["_runtime_budget_profile"] is not None


def test_agent_bridge_does_not_preload_skill_registry_without_agent_context(monkeypatch):
    def fail_if_called(agent_id=None):
        _ = agent_id
        raise AssertionError("Skill registry should not be resolved during AgentBridge initialization")

    monkeypatch.setattr("src.gateway.agent_bridge.get_skill_registry", fail_if_called)

    AgentBridge()


@pytest.mark.asyncio
async def test_runtime_gateway_adapter_normalizes_none_content_to_empty_string():
    adapter = GatewayAdapter(orchestrator=AgentBridge().runtime_session_orchestrator)

    session, request = await adapter.prepare_turn({"session_id": "sess-none", "content": None})

    assert session.session_id == "sess-none"
    assert request.user_input == ""


@pytest.mark.asyncio
async def test_runtime_gateway_adapter_prepares_resumed_turn_from_snapshot_state():
    adapter = GatewayAdapter(orchestrator=AgentBridge().runtime_session_orchestrator)
    resumed_session = SessionDescriptor(
        session_key="sess-resume",
        session_id="sess-resume",
    )
    adapter.orchestrator.resume_session = AsyncMock(  # type: ignore[method-assign]
        return_value=ResumeSessionState(
            session=resumed_session,
            latest_snapshot=StateSnapshotRecord(
                snapshot_id="snap-1",
                session_id="sess-resume",
                task_frame=TaskFrame(objective="resume objective", active_artifacts=["artifact-1"]),
            ),
            latest_summary=SummaryRecord(
                summary_id="sum-1",
                session_id="sess-resume",
                summary_type="collapse",
                summary="summary",
            ),
            summary_chain=[
                SummaryRecord(
                    summary_id="sum-1",
                    session_id="sess-resume",
                    summary_type="collapse",
                    summary="summary",
                )
            ],
            recent_entries=[
                TranscriptEntry(
                    entry_id="entry-1",
                    session_id="sess-resume",
                    turn_index=0,
                    kind="assistant_message",
                    text="hello",
                )
            ],
        )
    )

    session, request = await adapter.prepare_resumed_turn(
        "sess-resume",
        {"metadata": {"origin": "resume"}},
        user_input="continue",
    )

    assert session.session_id == "sess-resume"
    assert request.task_frame.objective == "resume objective"
    assert request.task_frame.active_artifacts == ["artifact-1"]
    assert request.metadata["resume"] is True
    assert request.metadata["summary_chain_count"] == 1
    assert request.metadata["recent_entry_count"] == 1
    assert request.metadata["runtime_timeout_ms"] == 180000


@pytest.mark.asyncio
async def test_runtime_gateway_adapter_drains_announcements_into_request_metadata():
    adapter = GatewayAdapter(orchestrator=AgentBridge().runtime_session_orchestrator)
    adapter.orchestrator.consume_announcements = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"target_session_key": "sess-ann", "summary": "child done"}]
    )

    _, request = await adapter.prepare_turn({"session_id": "sess-ann", "content": "resume parent"})

    assert request.metadata["runtime_announcements"] == [
        {"target_session_key": "sess-ann", "summary": "child done"}
    ]


@pytest.mark.asyncio
async def test_gateway_dispatcher_prepare_runtime_turn_returns_runtime_request():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    dispatcher._resolve_agent = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-1", "agent_name": "Agent 1", "agent_type": "main"},
        )()
    )
    dispatcher.ensure_session = AsyncMock()  # type: ignore[method-assign]
    dispatcher.touch_session = AsyncMock()  # type: ignore[method-assign]
    envelope = Envelope.create_chat(
        content="runtime path",
        session_id="sess-2",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )

    session, request = await dispatcher.prepare_runtime_turn(envelope, metadata={"mode": "runtime"})

    assert session.session_id == "sess-2"
    assert request.user_input == "runtime path"
    assert request.metadata["mode"] == "runtime"
    assert request.metadata["agent_id"] == "agent-1"
    dispatcher.ensure_session.assert_awaited_once()
    dispatcher.touch_session.assert_awaited_once_with("sess-2")


@pytest.mark.asyncio
async def test_gateway_dispatcher_chat_dispatch_uses_runtime_turn_controller_by_default():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    dispatcher._resolve_agent = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-1", "agent_name": "Agent 1", "agent_type": "main"},
        )()
    )
    dispatcher._bridge.run = AsyncMock()  # type: ignore[method-assign]
    dispatcher._bridge.run_runtime_turn = AsyncMock(  # type: ignore[method-assign]
        return_value=TurnResult(
            kind="final",
            finish_reason="done_definition_satisfied",
            output_text="runtime default path",
            metadata={"model": "runtime-model"},
        )
    )
    envelope = Envelope.create_chat(
        content="runtime path",
        session_id="sess-chat-runtime",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )

    events = [event async for event in dispatcher.dispatch(envelope)]

    dispatcher._bridge.run.assert_not_awaited()  # type: ignore[attr-defined]
    dispatcher._bridge.run_runtime_turn.assert_awaited_once()  # type: ignore[attr-defined]
    assert any(event.type == GatewayEventType.MESSAGE_END for event in events)
    assert events[-2].data["content"] == "runtime default path"


@pytest.mark.asyncio
async def test_gateway_dispatcher_execute_runtime_turn_enqueues_session_lane_before_controller():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    envelope = Envelope.create_chat(
        content="runtime path",
        session_id="sess-chat-enqueue",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )
    session = SessionDescriptor(session_key="sess-chat-enqueue", session_id="sess-chat-enqueue")
    request = TurnRequest(
        session=session,
        user_input="runtime path",
        task_frame=TaskFrame(objective="runtime path"),
        route=RouteMeta(channel="web_chat"),
    )
    dispatcher.prepare_runtime_turn = AsyncMock(return_value=(session, request))  # type: ignore[method-assign]
    dispatcher._runtime_gateway_adapter.enqueue = AsyncMock(return_value=request)  # type: ignore[method-assign]
    dispatcher._bridge.run_runtime_turn = AsyncMock(  # type: ignore[method-assign]
        return_value=TurnResult(kind="final", finish_reason="done_definition_satisfied", output_text="ok")
    )

    await dispatcher.execute_runtime_turn(envelope)
    dispatcher._runtime_gateway_adapter.enqueue.assert_awaited_once_with(session, request)  # type: ignore[attr-defined]
    dispatcher._bridge.run_runtime_turn.assert_awaited_once_with(request, controller=None)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_runtime_controller_planner_forces_delegate_task_for_explicit_delegate_intent(monkeypatch):
    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-delegate", session_id="sess-delegate"),
        user_input="让研究分析员查询今天上海的天气，只需一句话回复。",
        task_frame=TaskFrame(objective="delegate weather"),
        route=RouteMeta(channel="web_chat"),
        metadata={},
    )
    state = TurnState.from_request(request)

    async def fake_bootstrap(state):
        state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
        state.metadata["runtime_config"] = SimpleNamespace(
            tools=SimpleNamespace(
                get_tools=lambda: [SimpleNamespace(name="delegate_task"), SimpleNamespace(name="web_search")]
            )
        )

    monkeypatch.setattr(bridge, "_ensure_runtime_turn_bootstrap", fake_bootstrap)
    monkeypatch.setattr(
        "src.gateway.agent_bridge.AgentORM.list_all",
        lambda: [
            SimpleNamespace(agent_id="main-agent", agent_name="主助手"),
            SimpleNamespace(agent_id="research-agent", agent_name="研究分析员"),
        ],
    )

    async def fail_if_called(state):
        _ = state
        raise AssertionError("LLM should not be called for explicit delegate intent")

    monkeypatch.setattr(bridge, "_runtime_invoke_model_once", fail_if_called)

    plan = await bridge._runtime_controller_planner(state)

    assert plan is not None
    assert len(plan.calls) == 1
    assert plan.calls[0].tool_name == "delegate_task"
    assert plan.calls[0].arguments["agent_id"] == "research-agent"
    assert plan.calls[0].arguments["task"] == "查询今天上海的天气，只需一句话回复。"


@pytest.mark.asyncio
async def test_runtime_controller_planner_consumes_intent_router_decision_before_llm(monkeypatch):
    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-router", session_id="sess-router"),
        user_input="生成一只戴眼镜的白色猫咪",
        task_frame=TaskFrame(objective="generate image"),
        route=RouteMeta(channel="web_chat"),
        metadata={},
    )
    state = TurnState.from_request(request)

    async def fake_bootstrap(state):
        state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
        state.metadata["runtime_config"] = SimpleNamespace(
            tools=SimpleNamespace(
                get_tools=lambda: [
                    SimpleNamespace(name="generate_image"),
                    SimpleNamespace(name="web_search"),
                ]
            )
        )

    monkeypatch.setattr(bridge, "_ensure_runtime_turn_bootstrap", fake_bootstrap)
    bridge._intent_router = SimpleNamespace(
        decide=lambda **kwargs: RouteDecision(
            policy_id="skill:imagegen",
            tool_plan=ToolExecutionPlan(
                calls=[ToolCallSpec(tool_name="generate_image", arguments={"prompt": kwargs["user_input"]})]
            ),
        )
    )

    async def fail_if_called(state):
        _ = state
        raise AssertionError("LLM should not be called when IntentRouter returns a decision")

    monkeypatch.setattr(bridge, "_runtime_invoke_model_once", fail_if_called)

    plan = await bridge._runtime_controller_planner(state)

    assert plan is not None
    assert len(plan.calls) == 1
    assert plan.calls[0].tool_name == "generate_image"
    assert plan.calls[0].arguments == {"prompt": "生成一只戴眼镜的白色猫咪"}


@pytest.mark.asyncio
async def test_runtime_controller_planner_forces_generate_image_for_explicit_image_intent(
    monkeypatch,
):
    bridge = AgentBridge()
    user_input = "生成一个图片，这是在沙滩，美女穿着比基尼在沙滩日光浴。"
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-image", session_id="sess-image"),
        user_input=user_input,
        task_frame=TaskFrame(objective="generate beach image"),
        route=RouteMeta(channel="web_chat"),
        metadata={},
    )
    state = TurnState.from_request(request)

    async def fake_bootstrap(state):
        state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
        state.metadata["runtime_config"] = SimpleNamespace(
            tools=SimpleNamespace(
                get_tools=lambda: [
                    SimpleNamespace(name="generate_image"),
                    SimpleNamespace(name="web_search"),
                ]
            )
        )

    monkeypatch.setattr(bridge, "_ensure_runtime_turn_bootstrap", fake_bootstrap)

    async def fail_if_called(state):
        _ = state
        raise AssertionError("LLM should not be called for explicit image intent")

    monkeypatch.setattr(bridge, "_runtime_invoke_model_once", fail_if_called)

    plan = await bridge._runtime_controller_planner(state)

    assert plan is not None
    assert len(plan.calls) == 1
    assert plan.calls[0].tool_name == "generate_image"
    assert plan.calls[0].arguments == {"prompt": user_input}


@pytest.mark.asyncio
async def test_runtime_controller_planner_forces_generate_image_for_implicit_image_intent(
    monkeypatch,
):
    bridge = AgentBridge()
    user_input = "生成一只戴眼镜的白色猫咪"
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-image-implicit", session_id="sess-image-implicit"),
        user_input=user_input,
        task_frame=TaskFrame(objective="generate cat image"),
        route=RouteMeta(channel="web_chat"),
        metadata={},
    )
    state = TurnState.from_request(request)

    async def fake_bootstrap(state):
        state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
        state.metadata["runtime_config"] = SimpleNamespace(
            tools=SimpleNamespace(
                get_tools=lambda: [
                    SimpleNamespace(name="generate_image"),
                    SimpleNamespace(name="web_search"),
                ]
            )
        )

    monkeypatch.setattr(bridge, "_ensure_runtime_turn_bootstrap", fake_bootstrap)

    async def fail_if_called(state):
        _ = state
        raise AssertionError("LLM should not be called for implicit image intent")

    monkeypatch.setattr(bridge, "_runtime_invoke_model_once", fail_if_called)

    plan = await bridge._runtime_controller_planner(state)

    assert plan is not None
    assert len(plan.calls) == 1
    assert plan.calls[0].tool_name == "generate_image"
    assert plan.calls[0].arguments == {"prompt": user_input}


@pytest.mark.asyncio
async def test_runtime_controller_planner_does_not_force_generate_image_for_non_image_generation(
    monkeypatch,
):
    bridge = AgentBridge()
    user_input = "生成一个 cron 表达式，每5分钟执行一次"
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-non-image", session_id="sess-non-image"),
        user_input=user_input,
        task_frame=TaskFrame(objective="generate cron expression"),
        route=RouteMeta(channel="web_chat"),
        metadata={},
    )
    state = TurnState.from_request(request)

    async def fake_bootstrap(state):
        state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
        state.metadata["runtime_config"] = SimpleNamespace(
            tools=SimpleNamespace(
                get_tools=lambda: [
                    SimpleNamespace(name="generate_image"),
                    SimpleNamespace(name="run_in_terminal"),
                ]
            )
        )

    monkeypatch.setattr(bridge, "_ensure_runtime_turn_bootstrap", fake_bootstrap)
    llm_called = False

    async def fake_runtime_invoke_model_once(state):
        nonlocal llm_called
        _ = state
        llm_called = True
        return AssistantMessage(
            content=[TextContent(text="*/5 * * * *")],
            model="test-model",
            provider="test-provider",
            stop_reason="end_turn",
        )

    monkeypatch.setattr(bridge, "_runtime_invoke_model_once", fake_runtime_invoke_model_once)

    plan = await bridge._runtime_controller_planner(state)

    assert llm_called is True
    assert plan is not None
    assert plan.calls == []
    assert state.metadata["final_candidate_ready"] is True
    assert state.metadata["final_output_text"] == "*/5 * * * *"


@pytest.mark.asyncio
async def test_gateway_dispatcher_turn_result_emits_runtime_tool_feedback_before_final_message():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    agent_info = type(
        "AgentInfoStub",
        (),
        {"agent_id": "agent-1", "agent_name": "Agent 1", "agent_type": "main"},
    )()
    events = [
        event
        async for event in dispatcher._turn_result_events(
            TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="final answer",
                metadata={
                    "model": "runtime-model",
                    "runtime_event_timeline": [
                        {
                            "type": "tool_call",
                            "payload": {
                                "tool_call_id": "tool-1",
                                "name": "web_search",
                                "arguments": {"query": "sleep"},
                            },
                        },
                        {
                            "type": "tool_result",
                            "payload": {
                                "tool_call_id": "tool-1",
                                "name": "web_search",
                                "result": "search result",
                                "is_error": False,
                                "details": {"source": "runtime"},
                                "duration_ms": 123.0,
                            },
                        },
                    ],
                },
            ),
            agent_info=agent_info,
        )
    ]

    event_types = [event.type for event in events]
    assert GatewayEventType.TOOL_CALL in event_types
    assert GatewayEventType.TOOL_RESULT in event_types
    assert GatewayEventType.MESSAGE_END in event_types
    assert event_types.index(GatewayEventType.TOOL_CALL) < event_types.index(GatewayEventType.MESSAGE_END)
    assert event_types.index(GatewayEventType.TOOL_RESULT) < event_types.index(GatewayEventType.MESSAGE_END)
    tool_result = next(event for event in events if event.type == GatewayEventType.TOOL_RESULT)
    assert tool_result.data["details"] == {"source": "runtime"}
    assert tool_result.data["duration_ms"] == 123.0


@pytest.mark.asyncio
async def test_gateway_dispatcher_prepare_runtime_turn_overrides_spoofed_agent_id():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    dispatcher._resolve_agent = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-real", "agent_name": "Agent Real", "agent_type": "main"},
        )()
    )
    dispatcher.ensure_session = AsyncMock()  # type: ignore[method-assign]
    dispatcher.touch_session = AsyncMock()  # type: ignore[method-assign]
    envelope = Envelope.create_chat(
        content="runtime path",
        session_id="sess-2b",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )

    _, request = await dispatcher.prepare_runtime_turn(envelope, metadata={"agent_id": "agent-spoofed"})

    assert request.metadata["agent_id"] == "agent-real"


@pytest.mark.asyncio
async def test_agent_invoker_prepare_runtime_turn_uses_internal_metadata():
    clear_current_context()
    invoker = AgentInvoker(bridge=AgentBridge())
    invoker._resolve_session = AsyncMock(return_value="sess-3")  # type: ignore[method-assign]
    invoker._resolve_agent_info = Mock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-cron", "agent_name": "Agent Cron", "agent_type": "main"},
        )()
    )
    invoker._dispatcher.ensure_session = AsyncMock()  # type: ignore[method-assign]

    session, request = await invoker.prepare_runtime_turn(
        "scheduled task",
        agent_id="agent-cron",
        channel_type=ChannelType.CLI,
        source=InvokeSource.CRON,
        metadata={"job": "daily"},
    )

    assert session.session_id == "sess-3"
    assert request.user_input == "scheduled task"
    assert request.metadata["source"] == "cron"
    assert request.metadata["agent_id"] == "agent-cron"
    assert request.metadata["job"] == "daily"
    invoker._dispatcher.ensure_session.assert_awaited_once()
    assert get_current_context() is not None
    assert get_current_context().agent_id == "agent-cron"
    clear_current_context()


@pytest.mark.asyncio
async def test_agent_invoker_prepare_runtime_turn_strips_reserved_metadata_keys():
    clear_current_context()
    invoker = AgentInvoker(bridge=AgentBridge())
    invoker._resolve_session = AsyncMock(return_value="sess-3b")  # type: ignore[method-assign]
    invoker._resolve_agent_info = Mock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-cron", "agent_name": "Agent Cron", "agent_type": "main"},
        )()
    )
    invoker._dispatcher.ensure_session = AsyncMock()  # type: ignore[method-assign]

    session, request = await invoker.prepare_runtime_turn(
        "scheduled task",
        agent_id="agent-cron",
        channel_type=ChannelType.CLI,
        source=InvokeSource.CRON,
        metadata={"job": "daily", "source": "override", "agent_id": "spoofed"},
    )

    assert session.session_id == "sess-3b"
    assert request.metadata["source"] == "cron"
    assert request.metadata["agent_id"] == "agent-cron"
    assert request.metadata["job"] == "daily"
    clear_current_context()


@pytest.mark.asyncio


@pytest.mark.asyncio
async def test_agent_bridge_runtime_controller_compact_wraps_compression_result_from_pipeline():
    from src.runtime.context.compression_pipeline import CompressionResult
    from src.runtime.types import ArtifactRef

    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-compact-wrap", session_id="sess-compact-wrap"),
        user_input="compress now",
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["gap-1"]),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.active_messages = [
        {"role": "user", "content": "history message"},
        {"role": "assistant", "content": "history answer"},
    ]
    state.active_artifact_refs = []

    bridge._runtime_compression_pipeline.run = AsyncMock(  # type: ignore[method-assign]
        return_value=CompressionResult(
            messages=[{"role": "system", "content": "[Collapsed history] compacted"}],
            active_artifacts=[
                ArtifactRef(id="artifact-1", kind="tool", title="Artifact", preview="preview")
            ],
            estimated_input_tokens=32,
            operations=["collapse", "autocompact"],
            metadata={"fallback_summary_used": True},
        )
    )

    result = await bridge._runtime_controller_compact(state, "budget_compact")

    assert isinstance(result, CompactResult)
    assert result.active_messages == [{"role": "system", "content": "[Collapsed history] compacted"}]
    assert result.active_artifact_refs[0].id == "artifact-1"
    assert result.task_frame is state.task_frame
    assert result.metadata["compaction_source"] == "pipeline"
    assert result.metadata["compression_operations"] == ["collapse", "autocompact"]
    assert result.metadata["fallback_summary_used"] is True


@pytest.mark.asyncio
async def test_agent_bridge_runtime_controller_compact_returns_compact_result_from_pipeline():
    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-compact", session_id="sess-compact"),
        user_input="compress now",
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["gap-1"]),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.active_messages = [
        {"role": "user", "content": "history message"},
        {"role": "assistant", "content": "history answer"},
    ]
    state.active_artifact_refs = []

    expected = CompactResult(
        active_messages=[{"role": "system", "content": "[Collapsed history] compacted"}],
        active_artifact_refs=[],
        output_text="compacted output",
        task_frame=TaskFrame(objective="Ship runtime", unresolved=["gap-2"]),
        metadata={"compaction_source": "pipeline"},
    )

    bridge._runtime_compression_pipeline.run = AsyncMock(return_value=expected)  # type: ignore[method-assign]

    result = await bridge._runtime_controller_compact(state, "budget_compact")

    assert result is expected
    bridge._runtime_compression_pipeline.run.assert_awaited_once()  # type: ignore[attr-defined]
    assert state.metadata["last_compaction_reason"] == "budget_compact"
    assert state.metadata["compaction_count"] == 1
    assert state.metadata["request_compact"] is False
    bridge = AgentBridge()
    bridge.runtime_session_orchestrator.resume_session = AsyncMock(  # type: ignore[method-assign]
        return_value=ResumeSessionState(
            session=SessionDescriptor(session_key="sess-runtime", session_id="sess-runtime"),
            latest_snapshot=StateSnapshotRecord(
                snapshot_id="snap-runtime",
                session_id="sess-runtime",
                task_frame=TaskFrame(objective="old objective"),
                tool_usage_json={"web_search": 2},
            ),
            summary_chain=[
                SummaryRecord(
                    summary_id="summary-runtime",
                    session_id="sess-runtime",
                    summary_type="collapse",
                    summary="older summary",
                    recent_failures=["fetch timeout"],
                )
            ],
            recent_entries=[
                TranscriptEntry(
                    entry_id="entry-user",
                    session_id="sess-runtime",
                    turn_index=0,
                    kind="user_message",
                    role="user",
                    text="old user",
                ),
                TranscriptEntry(
                    entry_id="entry-assistant",
                    session_id="sess-runtime",
                    turn_index=0,
                    kind="assistant_message",
                    role="assistant",
                    text="old assistant",
                ),
            ],
        )
    )
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-runtime", session_id="sess-runtime"),
        user_input="new question",
        task_frame=TaskFrame(objective="new question"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)

    await bridge._ensure_runtime_turn_bootstrap(state)

    assert [message.role for message in state.active_messages] == ["user", "assistant", "user"]
    assert state.active_messages[0].content[0].text == "old user"
    assert state.active_messages[1].get_text() == "old assistant"
    assert state.active_messages[2].content[0].text == "new question"
    assert state.session_tool_usage == {"web_search": 2}
    assert state.metadata["runtime_summary_chain_messages"][0]["content"].startswith("[collapse summary]")
    assert state.metadata["runtime_recent_failures"] == ["fetch timeout"]
    assert state.metadata.get("runtime_history_source") != "legacy_memory_fallback"


@pytest.mark.asyncio
async def test_agent_bridge_runtime_bootstrap_imports_legacy_history_into_runtime_transcript():
    bridge = AgentBridge()
    bridge.runtime_session_orchestrator.resume_session = AsyncMock(  # type: ignore[method-assign]
        return_value=ResumeSessionState(
            session=SessionDescriptor(session_key="sess-import", session_id="sess-import"),
            latest_snapshot=StateSnapshotRecord(
                snapshot_id="snap-import",
                session_id="sess-import",
                task_frame=TaskFrame(objective="import"),
            ),
            recent_entries=[],
        )
    )
    bridge.runtime_session_orchestrator.append_transcript_entry = AsyncMock()  # type: ignore[method-assign]
    bridge._runtime_load_legacy_history_messages = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            UserMessage.from_text("legacy user"),
            AssistantMessage(
                content=[TextContent(text="legacy assistant")],
                model="legacy-model",
                provider="legacy-provider",
                stop_reason="end_turn",
            ),
        ]
    )
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-import", session_id="sess-import"),
        user_input="new question",
        task_frame=TaskFrame(objective="new question"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)

    await bridge._ensure_runtime_turn_bootstrap(state)

    assert state.metadata["runtime_history_source"] == "legacy_memory_imported"
    assert [message.role for message in state.active_messages] == ["user", "assistant", "user"]
    assert bridge.runtime_session_orchestrator.append_transcript_entry.await_count == 3  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_agent_bridge_runtime_model_call_uses_runtime_context_pipeline_not_legacy_adapter(monkeypatch):
    bridge = AgentBridge()
    bridge.runtime_session_orchestrator.append_transcript_entry = AsyncMock()  # type: ignore[method-assign]
    bridge.runtime_session_orchestrator.append_compression_event = AsyncMock()  # type: ignore[method-assign]
    agent_logger = get_agent_logger()
    current_context = AgentContext.for_cli()
    current_context.trace_id = "runtime-trace-test"
    current_context.session_id = "sess-runtime-ctx"
    set_current_context(current_context)

    class ExplodingContext:
        async def prepare_context(self, *args, **kwargs):
            raise AssertionError("legacy context adapter should not be called")

    class StubBuilder:
        async def build(self, request):
            from src.runtime.context.builder import ContextBuildResult

            return ContextBuildResult(
                system_prompt="runtime prompt",
                active_messages=[{"role": "user", "content": "hello runtime"}],
                active_artifacts=[],
                estimated_input_tokens=12,
            )

    class StubPipeline:
        async def run(self, ctx):
            from src.runtime.context.compression_pipeline import CompressionResult

            _ = ctx
            return CompressionResult(
                messages=[{"role": "user", "content": "hello runtime"}],
                active_artifacts=[],
                estimated_input_tokens=12,
                operations=["microcompact"],
            )

    async def fake_stream_assistant_response(**kwargs):
        _ = kwargs
        yield MessageEndEvent(
            message=AssistantMessage(
                content=[TextContent(text="runtime final")],
                model="runtime-model",
                provider="runtime-provider",
                stop_reason="end_turn",
            )
        )

    import importlib

    agent_loop_module = importlib.import_module("src.agent_core.agent_loop")

    monkeypatch.setattr(agent_loop_module, "_stream_assistant_response", fake_stream_assistant_response)
    bridge._runtime_context_builder = StubBuilder()
    bridge._runtime_compression_pipeline = StubPipeline()

    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-runtime-ctx", session_id="sess-runtime-ctx"),
        user_input="hello runtime",
        task_frame=TaskFrame(objective="hello runtime"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.active_messages = [UserMessage.from_text("hello runtime")]
    state.metadata["runtime_config"] = AgentCoreConfig(
        llm=Mock(),
        tools=None,
        logger=None,
        context=ExplodingContext(),
        system_prompt="legacy prompt",
        model="runtime-model",
        provider="runtime-provider",
    )
    state.metadata["runtime_system_prompt"] = "legacy prompt"
    state.metadata["runtime_prompt_mode"] = "full"

    message = await bridge._runtime_invoke_model_once(state)

    assert message.get_text() == "runtime final"
    assert state.metadata["runtime_context_summary"] == "microcompact"
    assert agent_logger.llm_call_count == 1
    assert len(agent_logger.get_llm_calls_by_trace("runtime-trace-test")) == 1
    context_logs = [
        entry
        for entry in agent_logger.get_logs(trace_id="runtime-trace-test", limit=100)
        if entry.event == "runtime_context_prepared"
    ]
    assert context_logs
    assert context_logs[0].data["runtime_model_budget"]["max_context_tokens"] == 200000
    assert context_logs[0].data["runtime_model_budget"]["discounted_context_window"] == 114800
    bridge.runtime_session_orchestrator.append_transcript_entry.assert_awaited_once()  # type: ignore[attr-defined]
    bridge.runtime_session_orchestrator.append_compression_event.assert_awaited_once()  # type: ignore[attr-defined]
    clear_current_context()


@pytest.mark.asyncio
async def test_runtime_prepare_model_input_exposes_memory_flush_placeholder_to_llm():
    bridge = AgentBridge()

    class StubBuilder:
        async def build(self, request):
            from src.runtime.context.builder import ContextBuildResult

            history_messages = [
                {"role": "user", "content": "请生成一个PPT模板"},
                {"role": "assistant", "content": "我先查一些模版参考"},
                {
                    "role": "tool",
                    "tool_name": "web_search",
                    "content": "杭州明天中雨，18到24度。" + ("x" * 20000),
                },
            ]
            history_messages.extend(
                {"role": "assistant", "content": f"中间过程消息 {index}"}
                for index in range(11)
            )
            history_messages.append({"role": "user", "content": "继续"})
            return ContextBuildResult(
                system_prompt="runtime prompt",
                active_messages=history_messages,
                active_artifacts=[],
                estimated_input_tokens=6206,
            )

    bridge._runtime_context_builder = StubBuilder()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-runtime-flush", session_id="sess-runtime-flush"),
        user_input="请生成一个PPT模板",
        task_frame=TaskFrame(objective="请生成一个PPT模板"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.active_messages = [UserMessage.from_text("请生成一个PPT模板")]
    state.metadata["runtime_prompt_mode"] = "full"

    _system_prompt, llm_messages = await bridge._runtime_prepare_model_input(
        state,
        system_prompt="legacy prompt",
        available_tools=[],
    )

    flushed = [
        message
        for message in llm_messages
        if str(message.get("content", "")).startswith("[Memory-flushed tool result]")
    ]
    assert len(flushed) == 1
    assert flushed[0]["role"] == "tool"
    assert "Artifact: artifact:1" in flushed[0]["content"]
    assert state.metadata["compression_operations"] == ["memory_flush"]


@pytest.mark.asyncio
async def test_runtime_executor_normalizes_terminal_tool_result_before_transcript(monkeypatch):
    bridge = AgentBridge()
    bridge._runtime_tool_result_normalizer = RuntimeToolResultNormalizer(
        terminal_head_chars=20,
        terminal_tail_chars=10,
    )
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-runtime-normalize", session_id="sess-runtime-normalize"),
        user_input="run command",
        task_frame=TaskFrame(objective="run command"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.metadata["runtime_config"] = AgentCoreConfig(
        llm=Mock(),
        tools=SimpleNamespace(get_tools=lambda: [SimpleNamespace(name="run_in_terminal")]),
        logger=None,
        context=None,
        system_prompt="runtime prompt",
    )
    state.metadata["runtime_agent_info"] = SimpleNamespace(agent_id="main-agent")
    bridge.runtime_session_orchestrator.append_transcript_entry = AsyncMock()  # type: ignore[method-assign]

    async def fake_execute_tool_calls(**kwargs):
        from src.agent_core.types import ToolExecutionEndEvent, ToolResult

        _ = kwargs
        yield ToolExecutionEndEvent(
            tool_call_id="tool-1",
            tool_name="run_in_terminal",
            result=ToolResult.from_text(
                "STDOUT:\n" + ("A" * 200) + "\nSTDERR:\n" + ("B" * 200),
                details={"returncode": 0},
            ),
            duration_ms=10.0,
        )

    monkeypatch.setattr("src.agent_core.tool_executor.execute_tool_calls", fake_execute_tool_calls)
    plan = GovernedToolPlan(
        calls=[ToolCallSpec(tool_name="run_in_terminal", arguments={"command": "echo hi"})],
        max_parallelism=1,
    )

    observed = await bridge._runtime_controller_executor(plan, state)

    assert observed[0].tool_name == "run_in_terminal"
    assert observed[0].output.startswith("[run_in_terminal]")
    transcript_entry = bridge.runtime_session_orchestrator.append_transcript_entry.await_args.args[0]  # type: ignore[attr-defined]
    assert transcript_entry.text.startswith("[run_in_terminal]")
    assert "[... " in transcript_entry.text


@pytest.mark.asyncio
async def test_runtime_executor_forces_delegate_synthesis_without_more_tools():
    bridge = AgentBridge()
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-delegate", session_id="sess-delegate"),
        user_input="delegate",
        task_frame=TaskFrame(objective="delegate"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False},
    )
    state = TurnState.from_request(request)
    state.metadata["runtime_config"] = AgentCoreConfig(
        llm=Mock(),
        tools=SimpleNamespace(
            get_tools=lambda: [
                SimpleNamespace(name="delegate_task"),
                SimpleNamespace(name="web_search"),
            ]
        ),
        logger=None,
        context=None,
        system_prompt="runtime prompt",
    )
    state.metadata["disabled_tool_names"] = set()

    class Result:
        def __init__(self):
            self.content = [TextContent(text="Error: delegated timeout")]
            self.details = {
                "delegate_terminal": True,
                "delegate_terminal_reason": "timeout",
                "child_trace_id": "child-trace-1",
                "error": "delegated timeout",
            }

    async def fake_execute_tool_calls(**kwargs):
        _ = kwargs
        from src.agent_core.types import ToolExecutionEndEvent

        yield ToolExecutionEndEvent(
            tool_call_id="runtime-tool-delegate",
            tool_name="delegate_task",
            result=Result(),
            is_error=True,
            duration_ms=123.0,
        )

    from unittest.mock import patch

    with patch("src.agent_core.tool_executor.execute_tool_calls", fake_execute_tool_calls):
        observed = await bridge._runtime_controller_executor(
            SimpleNamespace(calls=[SimpleNamespace(tool_name="delegate_task", arguments={})]),
            state,
        )

    assert observed[0].success is False
    assert "不要继续调用任何工具" in state.metadata["runtime_synthesis_instruction"]
    assert "web_search" in state.metadata["disabled_tool_names"]


def test_agent_bridge_skips_empty_assistant_message_end_events():
    bridge = AgentBridge()

    event = MessageEndEvent(
        message=AssistantMessage(
            content=[],
            model="",
            provider="",
            stop_reason="end_turn",
        )
    )

    converted = bridge._convert_agent_event(event)

    assert converted is None


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_honors_max_tokens_override():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-max-tokens",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_disable_tools": True, "runtime_max_tokens": 48},
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={"runtime_disable_tools": True, "runtime_max_tokens": 48},
    )

    runtime_config = bridge._build_runtime_agent_config(request, bridge._resolve_runtime_agent_info(request))

    assert isinstance(runtime_config, AgentCoreConfig)
    assert runtime_config.max_tokens == 48
    assert runtime_config.tools is None


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_honors_temperature_override():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-temperature",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_disable_tools": True, "runtime_temperature": 0.2},
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={"runtime_disable_tools": True, "runtime_temperature": 0.2},
    )

    runtime_config = bridge._build_runtime_agent_config(request, bridge._resolve_runtime_agent_info(request))

    assert isinstance(runtime_config, AgentCoreConfig)
    assert runtime_config.temperature == 0.2
    assert runtime_config.tools is None


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_can_force_non_streaming():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-non-stream",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_disable_tools": True, "runtime_force_non_streaming": True},
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={"runtime_disable_tools": True, "runtime_force_non_streaming": True},
    )

    runtime_config = bridge._build_runtime_agent_config(request, bridge._resolve_runtime_agent_info(request))

    assert isinstance(runtime_config, AgentCoreConfig)
    assert isinstance(runtime_config.llm, XAgentLLMAdapter)
    assert runtime_config.llm._force_non_streaming is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_agent_bridge_runtime_bootstrap_can_skip_history_load():
    bridge = AgentBridge()
    bridge.runtime_session_orchestrator.resume_session = AsyncMock()  # type: ignore[method-assign]
    bridge._runtime_load_legacy_history_messages = AsyncMock()  # type: ignore[method-assign]
    request = TurnRequest(
        session=SessionDescriptor(session_key="sess-skip-history", session_id="sess-skip-history"),
        user_input="runtime execute",
        task_frame=TaskFrame(objective="runtime execute"),
        route=RouteMeta(channel="web_chat"),
        metadata={"persist_user_message": False, "runtime_skip_history_load": True},
    )
    state = TurnState.from_request(request)

    await bridge._ensure_runtime_turn_bootstrap(state)

    bridge.runtime_session_orchestrator.resume_session.assert_not_awaited()  # type: ignore[attr-defined]
    bridge._runtime_load_legacy_history_messages.assert_not_awaited()  # type: ignore[attr-defined]
    assert state.metadata["runtime_history_source"] == "empty"
    assert [message.role for message in state.active_messages] == ["user"]


@pytest.mark.asyncio
async def test_agent_bridge_run_propagates_abort_event():
    bridge = AgentBridge()
    bridge._inject_skill_prompt = Mock()  # type: ignore[method-assign]
    bridge._persist_user_message = AsyncMock(return_value=None)  # type: ignore[method-assign]

    class AbortableAgent:
        def __init__(self):
            self._original_system_prompt = "base prompt"
            self._system_prompt = "base prompt"
            self._abort_event = None
            self.abort_calls = 0

        def abort(self):
            self.abort_calls += 1
            if self._abort_event is not None:
                self._abort_event.set()

        async def prompt(self, content, images=None):
            _ = content
            _ = images
            self._abort_event = __import__("asyncio").Event()
            while not self._abort_event.is_set():
                await __import__("asyncio").sleep(0.01)
            if False:
                yield

    agent = AbortableAgent()
    abort_event = __import__("asyncio").Event()

    async def _consume():
        return [event async for event in bridge.run(
            agent=agent,
            content="hello",
            session_id="sess-abort",
            abort_event=abort_event,
        )]

    task = __import__("asyncio").create_task(_consume())
    await __import__("asyncio").sleep(0.02)
    abort_event.set()
    events = await task

    assert events == []
    assert agent.abort_calls == 1

@pytest.mark.asyncio
async def test_agent_bridge_restores_system_prompt_after_runtime_error():
    bridge = AgentBridge()

    class ExplodingAgent:
        def __init__(self):
            self._original_system_prompt = "base prompt"
            self._system_prompt = "base prompt"

        async def prompt(self, content, images=None):
            _ = content
            _ = images
            raise RuntimeError("boom")
            yield  # pragma: no cover

    agent = ExplodingAgent()
    bridge._inject_skill_prompt = lambda agent, content: setattr(agent, "_system_prompt", "mutated prompt")  # type: ignore[method-assign]
    bridge._persist_user_message = AsyncMock(return_value=None)  # type: ignore[method-assign]
    bridge._persist_partial_response = AsyncMock()  # type: ignore[method-assign]

    events = [event async for event in bridge.run(agent=agent, content="hello", session_id="sess-err")]

    assert agent._system_prompt == "base prompt"
    assert len(events) == 1
    assert events[0].type == "error"


@pytest.mark.asyncio
async def test_gateway_dispatcher_execute_runtime_turn_uses_runtime_controller():
    dispatcher = GatewayDispatcher(bridge=AgentBridge())
    dispatcher._resolve_agent = AsyncMock(  # type: ignore[method-assign]
        return_value=type(
            "AgentInfoStub",
            (),
            {"agent_id": "agent-1", "agent_name": "Agent 1", "agent_type": "main"},
        )()
    )
    envelope = Envelope.create_chat(
        content="runtime dispatch execute",
        session_id="sess-5",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )

    class FakeController:
        async def run(self, request):
            return TurnResult(kind="final", finish_reason="done_definition_satisfied", output_text=request.user_input)

    result = await dispatcher.execute_runtime_turn(envelope, controller=FakeController())

    assert result.kind == "final"
    assert result.output_text == "runtime dispatch execute"


@pytest.mark.asyncio
async def test_agent_invoker_execute_runtime_turn_uses_runtime_controller():
    clear_current_context()
    invoker = AgentInvoker(bridge=AgentBridge())
    invoker._resolve_session = AsyncMock(return_value="sess-6")  # type: ignore[method-assign]
    invoker._resolve_agent_info = lambda _agent_id: type(  # type: ignore[method-assign]
        "AgentInfoStub",
        (),
        {"agent_id": "agent-cron", "agent_name": "Cron Agent", "agent_type": "main"},
    )()
    invoker._dispatcher.ensure_session = AsyncMock()  # type: ignore[method-assign]

    class FakeController:
        async def run(self, request):
            return TurnResult(kind="final", finish_reason="done_definition_satisfied", output_text=request.user_input)

    result = await invoker.execute_runtime_turn(
        "scheduled runtime execute",
        agent_id="agent-cron",
        channel_type=ChannelType.CLI,
        source=InvokeSource.CRON,
        metadata={"job": "daily"},
        controller=FakeController(),
    )

    assert result.kind == "final"
    assert result.output_text == "scheduled runtime execute"
    invoker._dispatcher.ensure_session.assert_awaited_once()
    assert get_current_context() is not None
    assert get_current_context().agent_id == "agent-cron"
    clear_current_context()
