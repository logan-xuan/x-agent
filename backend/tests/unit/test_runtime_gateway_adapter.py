"""Unit tests for runtime gateway bridge helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.agent_core.adapters.llm_adapter import XAgentLLMAdapter
from src.agent_core.config import AgentCoreConfig
from src.conversation.context import clear_current_context, get_current_context
from src.conversation.identity import ChannelProtocol, ChannelType
from src.gateway.agent_bridge import AgentBridge
from src.gateway.agent_invoker import AgentInvoker, InvokeSource
from src.gateway.dispatcher import GatewayDispatcher
from src.gateway.envelope import Envelope
from src.gateway.response import GatewayEvent, GatewayEventType
from src.runtime.adapters import GatewayAdapter
from src.runtime.types import TaskFrame, TurnResult


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


@pytest.mark.asyncio
async def test_runtime_gateway_adapter_normalizes_none_content_to_empty_string():
    adapter = GatewayAdapter(orchestrator=AgentBridge().runtime_session_orchestrator)

    session, request = await adapter.prepare_turn({"session_id": "sess-none", "content": None})

    assert session.session_id == "sess-none"
    assert request.user_input == ""


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
async def test_agent_bridge_runs_runtime_turn_with_injected_controller():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-4",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )
    _, request = await adapter.prepare_turn(envelope)

    class FakeController:
        async def run(self, request):
            return TurnResult(kind="final", finish_reason="done_definition_satisfied", output_text=request.user_input)

    result = await bridge.run_runtime_turn(request, controller=FakeController())

    assert result.kind == "final"
    assert result.output_text == "runtime execute"


@pytest.mark.asyncio
async def test_agent_bridge_runs_runtime_turn_via_legacy_bridge_by_default():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-legacy",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
    )
    _, request = await adapter.prepare_turn(envelope)
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]
    bridge.run = Mock(  # type: ignore[method-assign]
        return_value=_gateway_events(
            GatewayEvent.text_chunk("runtime "),
            GatewayEvent.message_end("runtime execute"),
        )
    )

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "final"
    assert result.finish_reason == "done_definition_satisfied"
    assert result.output_text == "runtime execute"
    assert result.metadata["legacy_bridge"] is True
    diagnostics = result.metadata["runtime_diagnostics"]
    assert diagnostics["phase"] == "completed"
    assert diagnostics["events_seen"] == 2
    assert diagnostics["text_chunks"] == 1
    assert diagnostics["event_counts"]["text_chunk"] == 1
    assert diagnostics["event_counts"]["message_end"] == 1
    assert diagnostics["milestones_ms"]["agent_resolved"] >= 0
    assert diagnostics["milestones_ms"]["completed"] >= diagnostics["milestones_ms"]["agent_resolved"]


@pytest.mark.asyncio
async def test_agent_bridge_runtime_legacy_path_respects_timeout():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-timeout",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_timeout_ms": 1},
    )
    _, request = await adapter.prepare_turn(envelope, metadata={"runtime_timeout_ms": 1})
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]

    async def slow_events():
        await __import__("asyncio").sleep(0.05)
        yield GatewayEvent.text_chunk("late")

    bridge.run = Mock(return_value=slow_events())  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "abort"
    assert result.finish_reason == "max_wall_time"
    assert result.output_text == (
        "[runtime-turn timeout after 1ms] "
        "phase=timeout, last_event=none, events_seen=0"
    )
    assert result.metadata["timeout_ms"] == 1
    diagnostics = result.metadata["runtime_diagnostics"]
    assert diagnostics["phase"] == "timeout"
    assert diagnostics["events_seen"] == 0
    assert diagnostics["last_progress"] == "timed_out"
    assert diagnostics["milestones_ms"]["timed_out"] >= diagnostics["milestones_ms"]["event_stream_started"]


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_timeout_uses_richer_fallback_text():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-timeout",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_timeout_ms": 1, "runtime_disable_tools": True},
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={"runtime_timeout_ms": 1, "runtime_disable_tools": True},
    )
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]

    async def slow_events():
        await __import__("asyncio").sleep(0.05)
        yield GatewayEvent.text_chunk("late")

    bridge.run = Mock(return_value=slow_events())  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "abort"
    assert result.output_text == (
        "[runtime fast mode timeout after 1ms] "
        'request="runtime execute". bridge ok, waiting for provider content. '
        "phase=timeout, last_event=none, events_seen=0"
    )
    assert result.metadata["synthetic_fallback"] is True


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_timeout_after_agent_start_mentions_probe():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-timeout-started",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_timeout_ms": 1, "runtime_disable_tools": True},
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={"runtime_timeout_ms": 1, "runtime_disable_tools": True},
    )
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]

    async def stalled_after_start():
        yield GatewayEvent(type=GatewayEventType.AGENT_START, data={"trace_id": "trace-1"})
        await __import__("asyncio").sleep(0.05)

    bridge.run = Mock(return_value=stalled_after_start())  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "abort"
    assert result.output_text == (
        "[runtime fast mode timeout after 1ms] "
        'request="runtime execute". provider emitted no content chunk before timeout. '
        "Try /api/v1/dev/llm-stream-probe or increase runtime_timeout_ms. "
        "phase=timeout, last_event=agent_start, events_seen=1"
    )
    assert result.metadata["synthetic_fallback"] is True


@pytest.mark.asyncio
async def test_agent_bridge_runtime_fast_mode_can_finalize_timeout_fallback():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-fast-timeout-final",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={
            "runtime_timeout_ms": 1,
            "runtime_disable_tools": True,
            "runtime_timeout_fallback_mode": "final",
        },
    )
    _, request = await adapter.prepare_turn(
        envelope,
        metadata={
            "runtime_timeout_ms": 1,
            "runtime_disable_tools": True,
            "runtime_timeout_fallback_mode": "final",
        },
    )
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]

    async def slow_events():
        await __import__("asyncio").sleep(0.05)
        yield GatewayEvent.text_chunk("late")

    bridge.run = Mock(return_value=slow_events())  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "final"
    assert result.finish_reason == "max_wall_time"
    assert result.metadata["synthetic_fallback"] is True
    assert result.metadata["timeout_fallback_mode"] == "final"


@pytest.mark.asyncio
async def test_agent_bridge_runtime_legacy_path_can_disable_tools():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-no-tools",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_disable_tools": True},
    )
    _, request = await adapter.prepare_turn(envelope, metadata={"runtime_disable_tools": True})
    bridge.create_config = Mock()  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]
    captured_config: dict[str, object] = {}
    captured_run_kwargs: dict[str, object] = {}

    def _create_agent(*, config=None, agent_info=None):
        captured_config["config"] = config
        captured_config["agent_info"] = agent_info
        return object()

    bridge.create_agent = Mock(side_effect=_create_agent)  # type: ignore[method-assign]

    def _run(*args, **kwargs):
        captured_run_kwargs.update(kwargs)
        return _gateway_events(GatewayEvent.message_end("runtime execute"))

    bridge.run = Mock(side_effect=_run)  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "final"
    runtime_config = captured_config["config"]
    assert isinstance(runtime_config, AgentCoreConfig)
    assert runtime_config.tools is None
    assert runtime_config.context is None
    assert runtime_config.enable_context_compression is False
    assert runtime_config.enable_experience_learning is False
    assert runtime_config.temperature == 0.0
    assert runtime_config.max_tokens == 64
    bridge.create_config.assert_not_called()  # type: ignore[attr-defined]
    assert captured_run_kwargs["disable_skills"] is False


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
async def test_agent_bridge_runtime_legacy_path_can_disable_skills():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-no-skills",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_disable_skills": True},
    )
    _, request = await adapter.prepare_turn(envelope, metadata={"runtime_disable_skills": True})
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]
    captured_run_kwargs: dict[str, object] = {}

    def _run(*args, **kwargs):
        captured_run_kwargs.update(kwargs)
        return _gateway_events(GatewayEvent.message_end("runtime execute"))

    bridge.run = Mock(side_effect=_run)  # type: ignore[method-assign]

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "final"
    assert captured_run_kwargs["disable_skills"] is True


@pytest.mark.asyncio
async def test_agent_bridge_runtime_legacy_path_can_skip_history_load():
    bridge = AgentBridge()
    adapter = GatewayAdapter(orchestrator=bridge.runtime_session_orchestrator)
    envelope = Envelope.create_chat(
        content="runtime execute",
        session_id="sess-skip-history",
        channel_type=ChannelType.WEB_CHAT,
        channel_protocol=ChannelProtocol.WEBSOCKET,
        metadata={"runtime_skip_history_load": True},
    )
    _, request = await adapter.prepare_turn(envelope, metadata={"runtime_skip_history_load": True})
    bridge.create_agent = Mock(return_value=object())  # type: ignore[method-assign]
    bridge.load_session_history = AsyncMock()  # type: ignore[method-assign]
    bridge.run = Mock(  # type: ignore[method-assign]
        return_value=_gateway_events(
            GatewayEvent.message_end("runtime execute"),
        )
    )

    result = await bridge.run_runtime_turn(request)

    assert result.kind == "final"
    bridge.load_session_history.assert_not_awaited()
    diagnostics = result.metadata["runtime_diagnostics"]
    assert "history_skipped" in diagnostics["milestones_ms"]


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


async def _gateway_events(*events):
    for event in events:
        yield event


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
