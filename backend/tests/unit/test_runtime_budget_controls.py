"""Unit tests for runtime prompt budget controls."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.agent_core import agent_loop
from src.agent_core.config import AgentCoreConfig
from src.agent_core.logger import AgentLogger
from src.agent_core.types import AgentContext as LoopAgentContext
from src.agent_core.types import AgentTool, StreamChunk, TextContent, ToolParameter, ToolResult, UserMessage
from src.agent_core.types import LogCategory
from src.agent_core.adapters.llm_adapter import XAgentLLMAdapter
from src.agent_core.adapters.context_adapter import XAgentContextAdapter
from src.agent_core.adapters.tool_middleware_adapter import create_tool_middleware_adapter
from src.agent_core.types import StreamChunkType
from src.config.models import CompressionConfig
from src.conversation.context import AgentContext as RequestAgentContext
from src.conversation.context import clear_current_context, set_current_context
from src.gateway.agent_bridge import AgentBridge
from src.gateway.agent_info import AgentInfo
from src.services.compression.compressor import CompressionResult
from src.services.compression.manager import (
    CompressionBudgetProfile,
    ContextCompressionManager,
    PreparedContext as CompressionPreparedContext,
    _CompressionCache,
)
from src.services.context.artifact_store import ArtifactStore
from src.services.context.context_assembler import ContextAssembler
from src.services.context.episodic_memory_store import EpisodicMemoryStore
from src.services.context.evidence_ledger_store import EvidenceLedgerStore
from src.services.context.mode_detector import ModeDetector
from src.services.context.session_state_store import SessionContextStateStore
from src.services.context.session_state_updater import SessionStateUpdater
from src.services.context.tool_result_archiver import ToolResultArchiver
from src.services.context.types import ContextBuildRequest
from src.services.llm.provider import LLMResponse, StreamingLLMResponse
from src.services.llm.bailian_provider import BailianProvider
from src.services.llm.openai_provider import OpenAIProvider
from src.services.storage import StorageService


class TestRuntimeBudgetControls:
    """Tests for prompt budget and retry propagation fixes."""

    @pytest.mark.asyncio
    async def test_total_token_budget_forces_compression(self, tmp_path):
        """Compression should trigger when total context exceeds the hard cap."""
        config = CompressionConfig(
            threshold_rounds=100,
            threshold_tokens=8000,
            max_context_tokens=2000,
            retention_count=10,
            max_tool_message_chars=4000,
        )
        manager = ContextCompressionManager(
            config=config,
            workspace_path=str(tmp_path),
            summary_fn=None,
        )

        session_id = "session-1"
        current_messages = [
            {"role": "user", "content": "old-1"},
            {"role": "assistant", "content": "old-2"},
            {"role": "user", "content": "new"},
        ]
        manager._compression_cache[session_id] = _CompressionCache(
            compressed_message_count=2,
            summary="cached summary",
            compressed_messages=current_messages[:2],
        )

        manager.token_counter = Mock()

        def fake_count_messages(messages):
            if len(messages) == 1:
                return 100
            if len(messages) == 3:
                return 2500
            return 500

        manager.token_counter.count_messages.side_effect = fake_count_messages
        manager.token_counter.count_text.return_value = 0
        manager.token_counter.count_tool_definitions.return_value = 0
        manager._compress_context = AsyncMock(
            return_value=CompressionPreparedContext(
                messages=[{"role": "system", "content": "compressed"}],
                summary="compressed summary",
                total_tokens=500,
            )
        )

        result = await manager.prepare_context(
            session_id=session_id,
            current_messages=current_messages,
            system_prompt="",
        )

        manager._compress_context.assert_awaited_once()
        assert result.summary == "compressed summary"
        assert result.messages == [{"role": "system", "content": "compressed"}]

    @pytest.mark.asyncio
    async def test_context_adapter_truncates_large_tool_messages(self):
        """Tool messages should be truncated before being passed back to the LLM."""

        class DummyManager:
            def __init__(self):
                self.config = CompressionConfig(
                    max_context_tokens=12000,
                    max_tool_message_chars=200,
                )
                self.token_counter = Mock()
                self.token_counter.count_messages.return_value = 1
                self.token_counter.count_tool_definitions.return_value = 0
                self.token_counter.count_text.return_value = 0

            async def prepare_context(self, session_id, current_messages, system_prompt="", tools=None):
                return SimpleNamespace(
                    messages=current_messages,
                    summary=None,
                    total_tokens=1,
                )

        adapter = XAgentContextAdapter(DummyManager())
        result = await adapter.prepare_context(
            session_id="session-2",
            messages=[
                {"role": "tool", "content": "x" * 400, "tool_call_id": "tool-1"},
                {"role": "user", "content": "keep me"},
            ],
            system_prompt="",
        )

        tool_message = result.messages[0]
        assert tool_message["role"] == "tool"
        assert len(tool_message["content"]) <= 200
        assert "tool output truncated" in tool_message["content"]
        assert result.messages[1]["content"] == "keep me"

    @pytest.mark.asyncio
    async def test_context_adapter_hybrid_mode_uses_context_assembler(self):
        """Hybrid mode should assemble stateful fragments before compression manager runs."""

        class DummyManager:
            def __init__(self):
                self.config = CompressionConfig(
                    max_context_tokens=12000,
                    max_tool_message_chars=200,
                    mode="hybrid",
                )
                self.token_counter = Mock()
                self.token_counter.count_messages.return_value = 10
                self.token_counter.count_tool_definitions.return_value = 0
                self.token_counter.count_text.return_value = 0
                self._resolve_budget_profile = Mock(return_value=None)
                self.prepare_context = AsyncMock(
                    return_value=SimpleNamespace(
                        messages=[{"role": "system", "content": "compressed"}],
                        summary="hybrid summary",
                        total_tokens=10,
                    )
                )

        assembler = SimpleNamespace(
            build=AsyncMock(
                return_value=SimpleNamespace(
                    messages=[{"role": "system", "content": "[Session State]\nassembled"}],
                )
            )
        )

        adapter = XAgentContextAdapter(DummyManager(), context_assembler=assembler)
        result = await adapter.prepare_context(
            session_id="session-hybrid",
            messages=[{"role": "user", "content": "请调研数字人项目"}],
            system_prompt="",
            tools=[],
        )

        assembler.build.assert_awaited_once()
        adapter._manager.prepare_context.assert_awaited_once()
        assert adapter._manager.prepare_context.call_args.kwargs["current_messages"][0]["content"].startswith("[Session State]")
        assert result.summary == "hybrid summary"

    @pytest.mark.asyncio
    async def test_context_adapter_stateful_mode_bypasses_legacy_compression(self):
        """Stateful mode should return assembler output without calling legacy compression manager."""

        class DummyManager:
            def __init__(self):
                self.config = CompressionConfig(
                    max_context_tokens=12000,
                    max_tool_message_chars=200,
                    mode="stateful",
                )
                self.token_counter = Mock()
                self.token_counter.count_messages.side_effect = lambda messages: len(messages) * 10
                self.token_counter.count_tool_definitions.return_value = 0
                self.token_counter.count_text.return_value = 0
                self._resolve_budget_profile = Mock(return_value=None)
                self.prepare_context = AsyncMock()

        assembler = SimpleNamespace(
            build=AsyncMock(
                return_value=SimpleNamespace(
                    messages=[{"role": "system", "content": "[Session State]\nassembled"}],
                    session_state_text="assembled",
                    token_breakdown={"session_state": 10},
                    used_fallback=False,
                )
            )
        )

        adapter = XAgentContextAdapter(DummyManager(), context_assembler=assembler)
        result = await adapter.prepare_context(
            session_id="session-stateful",
            messages=[{"role": "user", "content": "请调研数字人项目"}],
            system_prompt="",
            tools=[],
        )

        assembler.build.assert_awaited_once()
        adapter._manager.prepare_context.assert_not_called()
        assert result.messages[0]["content"].startswith("[Session State]")
        assert result.summary == "assembled"
        assert result.was_compressed is True

    @pytest.mark.asyncio
    async def test_dynamic_budget_profile_can_force_compression(self, tmp_path):
        """Dynamic budget profiles should trigger compression before the static hard cap."""
        config = CompressionConfig(
            threshold_rounds=100,
            threshold_tokens=8000,
            max_context_tokens=12000,
            retention_count=10,
            max_tool_message_chars=4000,
        )
        manager = ContextCompressionManager(
            config=config,
            workspace_path=str(tmp_path),
            summary_fn=None,
            budget_resolver=lambda: CompressionBudgetProfile(
                provider_name="primary",
                model_id="glm-5",
                model_context_limit_tokens=200000,
                model_output_limit_tokens=128000,
                reserved_output_tokens=20000,
                safety_margin_tokens=6000,
                hard_context_limit_tokens=12000,
                trigger_tokens=9000,
            ),
        )

        manager.token_counter = Mock()
        manager.token_counter.count_messages.side_effect = [100, 9500]
        manager.token_counter.count_text.return_value = 0
        manager.token_counter.count_tool_definitions.return_value = 0
        manager._compress_context = AsyncMock(
            return_value=CompressionPreparedContext(
                messages=[{"role": "system", "content": "compressed"}],
                summary="compressed summary",
                total_tokens=400,
            )
        )

        result = await manager.prepare_context(
            session_id="session-3",
            current_messages=[{"role": "user", "content": "payload"}],
            system_prompt="",
        )

        manager._compress_context.assert_awaited_once()
        assert result.summary == "compressed summary"

    @pytest.mark.asyncio
    async def test_tool_budget_middleware_blocks_excessive_web_search_calls(self):
        adapter = create_tool_middleware_adapter(
            enable_timing=False,
            enable_logging=False,
            max_tool_calls_total=10,
            max_tool_calls_by_name={"web_search": 3},
            default_repeat_signature_limit=2,
            repeat_signature_limit_by_name={"web_search": 3},
        )
        req_ctx = RequestAgentContext.for_websocket(
            session_id="session-budget",
            agent_id="main-agent",
        )
        req_ctx.trace_id = "trace-budget-web-search"
        set_current_context(req_ctx)

        async def tool_executor(tool_name: str, arguments: dict[str, object]):
            return {"tool_name": tool_name, "arguments": arguments}

        for index in range(3):
            result, is_error, metadata = await adapter.execute(
                tool_name="web_search",
                tool_call_id=f"tool-{index}",
                arguments={"query": f"query-{index}", "max_results": 5},
                tool_executor=tool_executor,
            )
            assert is_error is False
            assert metadata["tool_budget_per_tool_calls"]["web_search"] == index + 1

        result, is_error, metadata = await adapter.execute(
            tool_name="web_search",
            tool_call_id="tool-blocked",
            arguments={"query": "query-4", "max_results": 5},
            tool_executor=tool_executor,
        )

        assert is_error is True
        assert "budget exhausted" in str(result["error"])
        assert metadata["force_finalize"] is True
        assert metadata["budget_exhausted"] is True
        clear_current_context()

    @pytest.mark.asyncio
    async def test_agent_loop_forces_final_answer_after_web_search_budget_exhaustion(self):
        class DummyLLM:
            def __init__(self) -> None:
                self.calls: list[dict[str, int]] = []

            async def stream(self, system_prompt: str, messages: list[dict], tools=None):
                _ = system_prompt
                _ = messages
                self.calls.append({"tools_count": len(tools or [])})
                if len(self.calls) == 1:
                    for index in range(4):
                        yield StreamChunk.tool(
                            f"tool-{index}",
                            "web_search",
                            {"query": f"query-{index}", "max_results": 5},
                        )
                    yield StreamChunk.done("tool_use")
                    return

                if tools:
                    yield StreamChunk.tool(
                        "tool-repeat",
                        "web_search",
                        {"query": "should-not-run", "max_results": 5},
                    )
                    yield StreamChunk.done("tool_use")
                    return

                yield StreamChunk.text("基于现有资料，给出最终总结。")
                yield StreamChunk.done("end_turn", {"total_tokens": 1})

        class DummyToolPort:
            def __init__(self) -> None:
                self.executions: list[tuple[str, dict[str, object]]] = []

            async def execute(self, tool_name: str, arguments: dict[str, object], abort_event=None):
                _ = abort_event
                self.executions.append((tool_name, arguments))
                return ToolResult.from_text(f"result for {arguments['query']}")

        req_ctx = RequestAgentContext.for_websocket(
            session_id="session-finalize",
            agent_id="main-agent",
        )
        req_ctx.trace_id = "trace-finalize-budget"
        set_current_context(req_ctx)

        llm = DummyLLM()
        tool_port = DummyToolPort()
        middleware = create_tool_middleware_adapter(
            enable_timing=False,
            enable_logging=False,
            max_tool_calls_total=10,
            max_tool_calls_by_name={"web_search": 3},
            default_repeat_signature_limit=2,
            repeat_signature_limit_by_name={"web_search": 3},
        )
        tool = AgentTool(
            name="web_search",
            label="web_search",
            description="search",
            parameters=[],
        )
        config = AgentCoreConfig(
            llm=llm,
            tools=tool_port,
            tool_middleware_pipeline=middleware.pipeline,
            max_turns=12,
        )
        context = LoopAgentContext(system_prompt="system", messages=[], tools=[tool])

        events = [
            event
            async for event in agent_loop(
                prompts=[UserMessage.from_text("做 AI 创业方向调研")],
                context=context,
                config=config,
            )
        ]

        assert len(tool_port.executions) == 3
        assert llm.calls[0]["tools_count"] == 1
        assert llm.calls[1]["tools_count"] == 0
        agent_end = next(event for event in reversed(events) if getattr(event, "type", "") == "agent_end")
        assistant_messages = [msg for msg in agent_end.messages if getattr(msg, "role", None) == "assistant"]
        assert assistant_messages[-1].get_text() == "基于现有资料，给出最终总结。"
        clear_current_context()

    @pytest.mark.asyncio
    async def test_agent_loop_can_still_use_non_search_tools_after_search_budget_exhaustion(self):
        class DummyLLM:
            def __init__(self) -> None:
                self.calls: list[dict[str, int]] = []

            async def stream(self, system_prompt: str, messages: list[dict], tools=None):
                _ = system_prompt
                _ = messages
                self.calls.append({"tools_count": len(tools or [])})
                if len(self.calls) == 1:
                    for index in range(4):
                        yield StreamChunk.tool(
                            f"tool-search-{index}",
                            "web_search",
                            {"query": f"query-{index}", "max_results": 5},
                        )
                    yield StreamChunk.done("tool_use")
                    return

                if len(self.calls) == 2:
                    yield StreamChunk.tool(
                        "tool-write",
                        "write_file",
                        {"file_path": "/tmp/report.html", "content": "<html>ok</html>"},
                    )
                    yield StreamChunk.done("tool_use")
                    return

                yield StreamChunk.text("HTML 页面已生成。")
                yield StreamChunk.done("end_turn", {"total_tokens": 1})

        class DummyToolPort:
            def __init__(self) -> None:
                self.executions: list[tuple[str, dict[str, object]]] = []

            async def execute(self, tool_name: str, arguments: dict[str, object], abort_event=None):
                _ = abort_event
                self.executions.append((tool_name, arguments))
                return ToolResult.from_text(f"executed {tool_name}")

        req_ctx = RequestAgentContext.for_websocket(
            session_id="session-deliverable",
            agent_id="main-agent",
        )
        req_ctx.trace_id = "trace-deliverable-budget"
        set_current_context(req_ctx)

        llm = DummyLLM()
        tool_port = DummyToolPort()
        middleware = create_tool_middleware_adapter(
            enable_timing=False,
            enable_logging=False,
            max_tool_calls_total=10,
            max_tool_calls_by_name={"web_search": 3},
            default_repeat_signature_limit=2,
            repeat_signature_limit_by_name={"web_search": 3},
        )
        tools = [
            AgentTool(name="web_search", label="web_search", description="search", parameters=[]),
            AgentTool(name="write_file", label="write_file", description="write", parameters=[]),
        ]
        config = AgentCoreConfig(
            llm=llm,
            tools=tool_port,
            tool_middleware_pipeline=middleware.pipeline,
            max_turns=12,
        )
        context = LoopAgentContext(system_prompt="system", messages=[], tools=tools)

        events = [
            event
            async for event in agent_loop(
                prompts=[UserMessage.from_text("做 AI 创业方向调研并输出 HTML")],
                context=context,
                config=config,
            )
        ]

        assert [name for name, _ in tool_port.executions].count("web_search") == 3
        assert ("write_file", {"file_path": "/tmp/report.html", "content": "<html>ok</html>"}) in tool_port.executions
        assert llm.calls[1]["tools_count"] == 1
        agent_end = next(event for event in reversed(events) if getattr(event, "type", "") == "agent_end")
        assistant_messages = [msg for msg in agent_end.messages if getattr(msg, "role", None) == "assistant"]
        assert assistant_messages[-1].get_text() == "HTML 页面已生成。"
        clear_current_context()

    @pytest.mark.asyncio
    async def test_quality_gate_rejects_low_value_compression(self, tmp_path):
        """Quality gate should reject compression results that save too few tokens."""
        config = CompressionConfig(
            threshold_rounds=10,
            threshold_tokens=1000,
            max_context_tokens=2000,
            retention_count=5,
            max_tool_message_chars=4000,
            compression_quality_gate_enabled=True,
            min_compression_ratio=0.2,
            min_token_savings=50,
        )
        manager = ContextCompressionManager(
            config=config,
            workspace_path=str(tmp_path),
            summary_fn=None,
        )

        manager.token_counter = Mock()
        manager.token_counter.count_messages.side_effect = [5000, 5000, 5000]
        manager.token_counter.count_text.return_value = 0
        manager.token_counter.count_tool_definitions.return_value = 0
        manager._archive_before_compression = AsyncMock()
        manager.compressor = SimpleNamespace(
            compress=AsyncMock(
                return_value=CompressionResult(
                    compressed_messages=[{"role": "system", "content": "summary"}],
                    recent_messages=[{"role": "user", "content": "recent"}],
                    archived_messages=[{"role": "user", "content": "old"}],
                    summary="too small",
                    original_token_count=100,
                    compressed_token_count=95,
                )
            )
        )
        manager._store_compression_event = AsyncMock()

        result = await manager.prepare_context(
            session_id="session-qgate",
            current_messages=[{"role": "user", "content": f"payload-{i}"} for i in range(12)],
            system_prompt="",
        )

        manager._store_compression_event.assert_not_awaited()
        assert result.messages == [{"role": "user", "content": f"payload-{i}"} for i in range(12)]
        assert result.summary is None

    @pytest.mark.asyncio
    async def test_tool_schema_tokens_are_included_in_runtime_budget(self, tmp_path):
        """Compression should trigger when tool schemas push the payload past the budget."""
        config = CompressionConfig(
            threshold_rounds=100,
            threshold_tokens=8000,
            max_context_tokens=32000,
            retention_count=10,
            max_tool_message_chars=4000,
        )
        manager = ContextCompressionManager(
            config=config,
            workspace_path=str(tmp_path),
            summary_fn=None,
            budget_resolver=lambda: CompressionBudgetProfile(
                provider_name="primary",
                model_id="glm-5",
                model_context_limit_tokens=200000,
                model_output_limit_tokens=128000,
                reserved_output_tokens=20000,
                safety_margin_tokens=6000,
                hard_context_limit_tokens=32000,
                trigger_tokens=23040,
            ),
        )

        manager.token_counter = Mock()
        manager.token_counter.count_messages.side_effect = [20850, 20850]
        manager.token_counter.count_text.return_value = 0
        manager.token_counter.count_tool_definitions.return_value = 4000
        manager._compress_context = AsyncMock(
            return_value=CompressionPreparedContext(
                messages=[{"role": "system", "content": "compressed"}],
                summary="compressed summary",
                total_tokens=12000,
            )
        )

        result = await manager.prepare_context(
            session_id="session-4",
            current_messages=[{"role": "user", "content": "payload"}],
            system_prompt="",
            tools=[{"type": "function", "function": {"name": "write_file"}}],
        )

        manager._compress_context.assert_awaited_once()
        assert result.summary == "compressed summary"
        assert result.total_tokens == 16000

    @pytest.mark.asyncio
    async def test_llm_adapter_forwards_provider_and_max_tokens_in_non_streaming_tool_mode(self):
        """LLM adapter should pass selected provider and output cap down to the router."""

        class DummyRouter:
            def __init__(self):
                self.chat = AsyncMock(
                    return_value=LLMResponse(
                        content="ok",
                        model="glm-5",
                        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    )
                )

        class DummyTool:
            def to_llm_tool(self):
                return {
                    "type": "function",
                    "function": {
                        "name": "dummy",
                        "description": "dummy tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }

        adapter = XAgentLLMAdapter(DummyRouter())
        chunks = []
        async for chunk in adapter.stream(
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
            tools=[DummyTool()],
            provider_name="primary",
            max_tokens=4096,
        ):
            chunks.append(chunk)

        adapter._router.chat.assert_awaited_once()
        assert adapter._router.chat.call_args.kwargs["preferred_provider"] == "primary"
        assert adapter._router.chat.call_args.kwargs["max_tokens"] == 4096
        assert chunks[-1].type == StreamChunkType.DONE

    @pytest.mark.asyncio
    async def test_llm_adapter_forwards_provider_and_max_tokens_in_streaming_mode(self):
        """Streaming text mode should also forward provider selection and output cap."""

        class DummyStream:
            def __aiter__(self):
                self._chunks = iter(
                    [
                        StreamingLLMResponse(content="hi", is_finished=False),
                        StreamingLLMResponse(content="", is_finished=True, usage={"total_tokens": 1}),
                    ]
                )
                return self

            async def __anext__(self):
                try:
                    return next(self._chunks)
                except StopIteration:
                    raise StopAsyncIteration

        class DummyRouter:
            def __init__(self):
                self.chat = AsyncMock(return_value=DummyStream())

        adapter = XAgentLLMAdapter(DummyRouter())
        chunks = []
        async for chunk in adapter.stream(
            system_prompt="system",
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
            provider_name="primary",
            max_tokens=2048,
        ):
            chunks.append(chunk)

        adapter._router.chat.assert_awaited_once()
        assert adapter._router.chat.call_args.kwargs["preferred_provider"] == "primary"
        assert adapter._router.chat.call_args.kwargs["max_tokens"] == 2048
        assert chunks[-1].type == StreamChunkType.DONE

    @pytest.mark.asyncio
    async def test_stateful_context_stores_round_trip(self, tmp_path):
        """Phase 2 stores should support basic create/get/list flows."""
        db_path = tmp_path / "stateful-context.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        episodic_store = EpisodicMemoryStore(storage)
        evidence_store = EvidenceLedgerStore(storage)
        artifact_store = ArtifactStore(storage)

        state = await state_store.upsert(
            "session-phase2",
            mode="research",
            summary_text="状态摘要",
            token_estimate=1234,
            current_goal={"task": "写方案"},
            open_questions=["是否要灰度"],
            metadata={"source": "test"},
        )
        assert state.session_id == "session-phase2"

        loaded_state = await state_store.get("session-phase2")
        assert loaded_state is not None
        assert loaded_state.to_dict()["current_goal"]["task"] == "写方案"
        assert loaded_state.to_dict()["open_questions"] == ["是否要灰度"]

        event = await episodic_store.create_event(
            session_id="session-phase2",
            event_type="decision",
            title="确认方案",
            summary="采用 stateful context 方案",
            details={"decision": "stateful"},
            tags=["architecture"],
            importance=0.8,
        )
        assert event.title == "确认方案"
        events = await episodic_store.list_by_session("session-phase2")
        assert len(events) == 1
        assert events[0].to_dict()["details"]["decision"] == "stateful"

        evidence = await evidence_store.create_entry(
            session_id="session-phase2",
            topic="context compression",
            claim="Compaction 应优先保留可推理状态",
            source_url="https://developers.openai.com/api/docs/guides/compaction",
            source_title="OpenAI Compaction Guide",
            confidence=0.9,
            freshness_at=datetime.now(),
        )
        assert evidence.topic == "context compression"
        evidence_rows = await evidence_store.list_by_session("session-phase2")
        assert len(evidence_rows) == 1
        assert evidence_rows[0].source_title == "OpenAI Compaction Guide"

        artifact = await artifact_store.create_artifact(
            session_id="session-phase2",
            kind="report",
            title="设计文档",
            content_path=str(tmp_path / "report.md"),
            preview_text="设计文档预览",
            metadata={"format": "md"},
        )
        assert artifact.kind == "report"
        artifacts = await artifact_store.list_by_session("session-phase2")
        assert len(artifacts) == 1
        assert artifacts[0].to_dict()["metadata"]["format"] == "md"

        await storage.close()

    def test_mode_detector_prefers_research_and_writing_signals(self):
        """Mode detector should infer coarse task mode from recent content."""
        detector = ModeDetector()

        mode = detector.detect(
            messages=[{"role": "user", "content": "请调研数字人行业并输出分析报告"}],
            tools=[{"type": "function", "function": {"name": "web_search"}}],
        )
        assert mode == "research"

        mode = detector.detect(
            messages=[{"role": "user", "content": "请撰写一份PRD文档"}],
            tools=[{"type": "function", "function": {"name": "write_file"}}],
        )
        assert mode == "writing"

    @pytest.mark.asyncio
    async def test_session_state_updater_and_context_assembler_build_bundle(self, tmp_path):
        """State updater and assembler should produce structured prompt fragments."""
        db_path = tmp_path / "assembler.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        episodic_store = EpisodicMemoryStore(storage)
        evidence_store = EvidenceLedgerStore(storage)
        artifact_store = ArtifactStore(storage)

        updater = SessionStateUpdater(state_store)
        await updater.update_after_turn(
            session_id="session-assemble",
            agent_id="main-agent",
            mode="research",
            new_messages=[
                {"role": "user", "content": "请调研数字人创业项目并整理方案"},
                {"role": "assistant", "content": "我会先从市场、竞品和商业模式三个方向展开。"},
            ],
            tool_results=[
                {"tool_name": "web_search", "artifact_ref": "artifact:web-search-001"},
            ],
            delegate_results=[
                {"agent_id": "research-agent", "status": "completed"},
            ],
        )

        await episodic_store.create_event(
            session_id="session-assemble",
            event_type="decision",
            title="确定调研范围",
            summary="聚焦数字人创业项目的市场、竞品和商业模式",
            details={"scope": "research"},
            tags=["research", "scope"],
            importance=0.7,
        )
        await evidence_store.create_entry(
            session_id="session-assemble",
            topic="digital-human",
            claim="数字人创业需优先验证商业化场景",
            source_title="Internal Research",
            confidence=0.8,
        )
        await artifact_store.create_artifact(
            session_id="session-assemble",
            kind="report",
            title="调研草稿",
            content_path=str(tmp_path / "report.md"),
            preview_text="调研草稿摘要",
        )

        assembler = ContextAssembler(
            session_state_store=state_store,
            episodic_store=episodic_store,
            evidence_store=evidence_store,
            artifact_store=artifact_store,
        )
        bundle = await assembler.build(
            ContextBuildRequest(
                session_id="session-assemble",
                agent_id="main-agent",
                mode="research",
                current_messages=[
                    {"role": "user", "content": "继续给我方案"},
                    {"role": "assistant", "content": "好的，我继续细化。"},
                ],
                max_prompt_tokens=12000,
            )
        )

        assert bundle.messages[0]["role"] == "system"
        assert "[Session State]" in bundle.messages[0]["content"]
        assert any("[Evidence Ledger]" in message["content"] for message in bundle.messages if message["role"] == "system")
        assert any("[Episodic Memory]" in message["content"] for message in bundle.messages if message["role"] == "system")
        assert any("[Artifact References]" in message["content"] for message in bundle.messages if message["role"] == "system")
        assert bundle.token_breakdown["total_messages"] >= bundle.token_breakdown["working_set"]
        assert "数字人创业项目" in bundle.session_state_text

        await storage.close()

    @pytest.mark.asyncio
    async def test_session_state_updater_extracts_questions_constraints_and_preferences(self, tmp_path):
        """Updater should extract open questions, constraints, and preferences from user text."""
        db_path = tmp_path / "state-updater-rich.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        updater = SessionStateUpdater(state_store)

        await updater.update_after_turn(
            session_id="session-state-rich",
            agent_id="main-agent",
            mode="research",
            new_messages=[
                {
                    "role": "user",
                    "content": "请调研数字人创业项目。不要讲空话，必须给出商业模式。你更偏向结构清晰的汇报方式吗？我喜欢结论先行。",
                },
                {
                    "role": "assistant",
                    "content": "我会先分析市场，再给出商业模式建议。",
                },
            ],
            tool_results=[],
            delegate_results=[],
        )

        state = await state_store.get("session-state-rich")
        assert state is not None
        payload = state.to_dict()
        assert any("结构清晰" in item for item in payload["open_questions"])
        assert any("不要讲空话" in item for item in payload["constraints"])
        assert any("喜欢结论先行" in item for item in payload["user_preferences"])
        assert any("商业模式" in item for item in payload["decisions"])

        await storage.close()

    @pytest.mark.asyncio
    async def test_session_state_updater_deduplicates_repeated_state_items(self, tmp_path):
        """Updater should deduplicate repeated questions and planned subtasks."""
        db_path = tmp_path / "state-updater-dedupe.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        updater = SessionStateUpdater(state_store)

        payload = [
            {"role": "user", "content": "这个项目怎么商业化？"},
            {"role": "assistant", "content": "我会先分析市场，然后分析竞品。"},
        ]

        await updater.update_after_turn(
            session_id="session-dedupe",
            agent_id="main-agent",
            mode="research",
            new_messages=payload,
            tool_results=[],
            delegate_results=[],
        )
        await updater.update_after_turn(
            session_id="session-dedupe",
            agent_id="main-agent",
            mode="research",
            new_messages=payload,
            tool_results=[],
            delegate_results=[],
        )

        state = await state_store.get("session-dedupe")
        assert state is not None
        payload = state.to_dict()
        assert len(payload["open_questions"]) == 1
        assistant_plans = [item for item in payload["active_subtasks"] if item.get("kind") == "assistant_plan"]
        assert len(assistant_plans) == 1

        await storage.close()

    @pytest.mark.asyncio
    async def test_session_state_updater_keeps_primary_goal_on_progress_query(self, tmp_path):
        """Progress questions should not overwrite the primary goal."""
        db_path = tmp_path / "state-updater-progress.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        updater = SessionStateUpdater(state_store)

        await updater.update_after_turn(
            session_id="session-progress",
            agent_id="main-agent",
            mode="research",
            new_messages=[
                {"role": "user", "content": "请调研数字人创业项目，并输出完整方案"},
                {"role": "assistant", "content": "我会先调研市场，再分析商业模式。"},
            ],
            tool_results=[],
            delegate_results=[],
        )
        await updater.update_after_turn(
            session_id="session-progress",
            agent_id="main-agent",
            mode="research",
            new_messages=[
                {"role": "user", "content": "你在处理吗？"},
                {"role": "assistant", "content": "我正在处理，会继续推进。"},
            ],
            tool_results=[],
            delegate_results=[],
        )

        state = await state_store.get("session-progress")
        assert state is not None
        payload = state.to_dict()
        assert payload["current_goal"]["primary_goal"] == "请调研数字人创业项目，并输出完整方案"
        assert payload["current_goal"]["latest_user_request"] == "你在处理吗？"
        assert payload["current_goal"]["is_progress_query"] is True

        await storage.close()

    @pytest.mark.asyncio
    async def test_context_assembler_applies_entry_and_working_set_budgets(self, tmp_path):
        """Context assembler should trim retrieved entries and working set within budgets."""
        db_path = tmp_path / "assembler-budget.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        episodic_store = EpisodicMemoryStore(storage)
        evidence_store = EvidenceLedgerStore(storage)
        artifact_store = ArtifactStore(storage)

        await state_store.upsert(
            "session-budget",
            mode="research",
            summary_text="这是一个很长的状态摘要 " * 50,
            token_estimate=5000,
        )

        for idx in range(5):
            await evidence_store.create_entry(
                session_id="session-budget",
                topic=f"topic-{idx}",
                claim=("evidence " * 80) + str(idx),
                source_title=f"source-{idx}",
            )
            await episodic_store.create_event(
                session_id="session-budget",
                event_type="decision",
                title=f"event-{idx}",
                summary=("episodic " * 70) + str(idx),
                details={"idx": idx},
            )
            await artifact_store.create_artifact(
                session_id="session-budget",
                kind="report",
                title=f"artifact-{idx}",
                content_path=f"/tmp/artifact-{idx}.md",
                preview_text="preview",
            )

        assembler = ContextAssembler(
            session_state_store=state_store,
            episodic_store=episodic_store,
            evidence_store=evidence_store,
            artifact_store=artifact_store,
        )

        bundle = await assembler.build(
            ContextBuildRequest(
                session_id="session-budget",
                agent_id="main-agent",
                mode="research",
                current_messages=[
                    {"role": "user", "content": "message one " * 50},
                    {"role": "assistant", "content": "message two " * 50},
                    {"role": "user", "content": "message three " * 50},
                ],
                max_prompt_tokens=400,
                reserved_output_tokens=100,
                session_state_budget_tokens=40,
                evidence_budget_tokens=40,
                episodic_budget_tokens=40,
                artifact_budget_tokens=20,
                max_working_set_messages=3,
            )
        )

        assert bundle.token_breakdown["session_state"] <= 60
        assert bundle.token_breakdown["evidence"] <= 60
        assert bundle.token_breakdown["episodic"] <= 60
        assert bundle.token_breakdown["artifacts"] <= 40
        assert bundle.token_breakdown["total_messages"] <= 400
        assert len(bundle.evidence_entries) <= 5
        assert len(bundle.episodic_entries) <= 5
        assert len(bundle.messages) >= 1

        await storage.close()

    def test_compression_config_defaults_to_stateful_mode(self):
        """New architecture should be the default context mode."""
        config = CompressionConfig()
        assert config.mode == "stateful"

    @pytest.mark.asyncio
    async def test_tool_result_archiver_persists_web_search_evidence(self, tmp_path):
        """Web search tool results should be archived into evidence ledger."""
        db_path = tmp_path / "archiver-evidence.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        archiver = ToolResultArchiver(
            artifact_store=ArtifactStore(storage),
            evidence_store=EvidenceLedgerStore(storage),
        )
        enriched = await archiver.archive(
            session_id="session-archiver",
            tool_name="web_search",
            result_text="search output",
            details={
                "query": "数字人创业项目",
                "structured_results": [
                    {
                        "title": "数字人行业观察",
                        "snippet": "数字人创业需先验证商业化场景",
                        "url": "https://example.com/article",
                    }
                ],
            },
        )

        evidence_rows = await EvidenceLedgerStore(storage).list_by_session("session-archiver")
        assert len(evidence_rows) == 1
        assert evidence_rows[0].topic == "数字人创业项目"
        assert "商业化场景" in evidence_rows[0].claim
        assert enriched["evidence_count"] == 1

        await storage.close()

    @pytest.mark.asyncio
    async def test_tool_result_archiver_persists_fetch_web_content_artifact(self, tmp_path):
        """Fetch web content results should be archived as artifacts and return artifact refs."""
        db_path = tmp_path / "archiver-artifact.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        archiver = ToolResultArchiver(
            artifact_store=ArtifactStore(storage),
            evidence_store=EvidenceLedgerStore(storage),
        )
        enriched = await archiver.archive(
            session_id="session-archiver",
            tool_name="fetch_web_content",
            result_text="[Markdown content saved]",
            details={
                "title": "数字人文章",
                "url": "https://example.com/digital-human",
                "metadata": {
                    "markdown_path": str(tmp_path / "fetched.md"),
                },
            },
        )

        artifacts = await ArtifactStore(storage).list_by_session("session-archiver")
        assert len(artifacts) == 1
        assert artifacts[0].kind == "web_content"
        assert enriched["artifact_ref"].startswith("artifact:")

        await storage.close()

    @pytest.mark.asyncio
    async def test_agent_loop_stateful_end_to_end_flow(self, tmp_path):
        """End-to-end: agent loop should update state, archive evidence, and emit context logs."""
        db_path = tmp_path / "agent-loop-e2e.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        episodic_store = EpisodicMemoryStore(storage)
        evidence_store = EvidenceLedgerStore(storage)
        artifact_store = ArtifactStore(storage)
        updater = SessionStateUpdater(state_store)
        archiver = ToolResultArchiver(
            artifact_store=artifact_store,
            evidence_store=evidence_store,
        )
        assembler = ContextAssembler(
            session_state_store=state_store,
            episodic_store=episodic_store,
            evidence_store=evidence_store,
            artifact_store=artifact_store,
        )

        class DummyContextManager:
            def __init__(self):
                self.config = CompressionConfig(mode="stateful")
                self.token_counter = Mock()
                self.token_counter.count_messages.side_effect = lambda messages: len(messages) * 20
                self.token_counter.count_tool_definitions.return_value = 0
                self.token_counter.count_text.side_effect = lambda text: max(1, len(text) // 4) if text else 0
                self._resolve_budget_profile = Mock(return_value=None)
                self.prepare_context = AsyncMock()

        context_adapter = XAgentContextAdapter(DummyContextManager(), context_assembler=assembler)

        class DummyLLM:
            def __init__(self):
                self.calls = []

            async def stream(self, system_prompt, messages, tools=None, provider_name=None, max_tokens=None):
                self.calls.append({
                    "system_prompt": system_prompt,
                    "messages": messages,
                    "tools": tools,
                })
                if len(self.calls) == 1:
                    yield StreamChunk.tool("tool-call-1", "web_search", {"query": "数字人创业项目"})
                    yield StreamChunk.done("tool_use", {"total_tokens": 10})
                else:
                    yield StreamChunk.text("我已经整理出数字人创业项目的初步方案。")
                    yield StreamChunk.done("end_turn", {"total_tokens": 20})

        class DummyToolPort:
            async def execute(self, tool_name, arguments, abort_event=None, on_progress=None):
                assert tool_name == "web_search"
                return ToolResult.from_text(
                    "search output",
                    details={
                        "query": arguments["query"],
                        "structured_results": [
                            {
                                "title": "数字人行业观察",
                                "snippet": "数字人创业需先验证商业化场景",
                                "url": "https://example.com/article",
                            }
                        ],
                    },
                )

            def get_tools(self):
                return []

        logger = AgentLogger()
        logger.clear()

        req_ctx = RequestAgentContext.for_internal(
            session_id="session-e2e",
            agent_id="main-agent",
        )
        set_current_context(req_ctx)

        try:
            prompts = [UserMessage.from_text("请调研数字人创业项目，并给我一份初步方案")]
            loop_context = LoopAgentContext(
                system_prompt="You are a helpful assistant.",
                messages=[],
                tools=[
                    AgentTool(
                        name="web_search",
                        label="web_search",
                        description="Search the web",
                        parameters=[
                            ToolParameter(
                                name="query",
                                type="string",
                                description="query",
                            )
                        ],
                    )
                ],
            )
            dummy_llm = DummyLLM()
            config = AgentCoreConfig(
                llm=dummy_llm,
                tools=DummyToolPort(),
                logger=logger,
                context=context_adapter,
                model="test-model",
                provider="test-provider",
                enable_context_compression=True,
                enable_experience_learning=False,
            )

            events = []
            with patch(
                "src.services.context.get_session_state_updater",
                return_value=updater,
            ), patch(
                "src.services.context.get_tool_result_archiver",
                return_value=archiver,
            ):
                async for event in agent_loop(prompts, loop_context, config):
                    events.append(event)

            state = await state_store.get("session-e2e")
            assert state is not None
            state_dict = state.to_dict()
            assert "数字人创业项目" in state_dict["current_goal"]["latest_user_request"]
            assert any(item.get("name") == "web_search" for item in state_dict["active_subtasks"])

            evidence_rows = await evidence_store.list_by_session("session-e2e")
            assert len(evidence_rows) == 1
            assert "商业化场景" in evidence_rows[0].claim

            context_logs = [
                entry for entry in logger.get_logs(category=LogCategory.AGENT_LOOP, limit=50)
                if entry.event == "context_prepared"
            ]
            assert len(context_logs) >= 1
            assert context_logs[0].data["context_mode"] == "stateful"
            assert len(dummy_llm.calls) == 2
            assert any(
                "[Evidence Ledger]" in str(message.get("content", ""))
                for message in dummy_llm.calls[1]["messages"]
                if isinstance(message, dict)
            )

            assert any(getattr(event, "type", "") == "agent_end" for event in events)
        finally:
            clear_current_context()
            await storage.close()

    @pytest.mark.asyncio
    async def test_agent_bridge_schedules_auto_resume_after_status_reply(self, tmp_path):
        """Status reply should trigger a background continuation for the preserved primary goal."""
        db_path = tmp_path / "bridge-auto-resume.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        state_store = SessionContextStateStore(storage)
        await state_store.upsert(
            "session-auto-resume",
            mode="research",
            summary_text="state",
            token_estimate=10,
            current_goal={
                "primary_goal": "请调研数字人创业项目，并输出完整方案",
                "latest_user_request": "你在处理吗？",
                "is_progress_query": True,
            },
            metadata={},
        )

        class FakeAgent:
            _original_system_prompt = "base"
            _system_prompt = "base"

            async def prompt(self, content, images=None):
                from src.agent_core.types import AgentEndEvent, AssistantMessage, MessageUpdateEvent

                msg = AssistantMessage(content=[TextContent(text="我正在处理，会继续推进主任务。")])
                yield MessageUpdateEvent(message=msg, delta="我正在处理，会继续推进主任务。", delta_type="text")
                yield AgentEndEvent(messages=[], trace_id="trace-auto", total_duration_ms=1)

        bridge = AgentBridge()
        agent_info = AgentInfo(
            agent_id="research-agent",
            agent_name="研究分析员",
            agent_type="specialized",
            model_name="primary",
            temperature=0.5,
            max_tokens=None,
            workspace="",
            feature="",
        )

        req_ctx = RequestAgentContext.for_internal(
            session_id="session-auto-resume",
            agent_id="research-agent",
        )
        set_current_context(req_ctx)

        try:
            with patch.object(bridge, "_persist_user_message", AsyncMock(return_value=None)), \
                 patch.object(bridge, "_persist_assistant_messages", AsyncMock(return_value=None)), \
                 patch("src.gateway.agent_invoker.AgentInvoker.invoke", new_callable=AsyncMock) as mock_invoke:
                async for _ in bridge.run(
                    agent=FakeAgent(),
                    content="你在处理吗？",
                    session_id="session-auto-resume",
                    agent_info=agent_info,
                    persist_user_message=False,
                    allow_auto_resume=True,
                ):
                    pass

                await asyncio.sleep(0)
                mock_invoke.assert_awaited_once()
                kwargs = mock_invoke.await_args.kwargs
                assert kwargs["agent_id"] == "research-agent"
                assert kwargs["session_id"] == "session-auto-resume"
                assert "继续执行当前主任务" in kwargs["content"]
                assert "数字人创业项目" in kwargs["content"]
        finally:
            clear_current_context()
            await storage.close()

    @pytest.mark.parametrize(
        ("provider_cls", "patch_target", "base_url"),
        [
            (
                OpenAIProvider,
                "src.services.llm.openai_provider.AsyncOpenAI",
                "https://api.openai.com/v1",
            ),
            (
                BailianProvider,
                "src.services.llm.bailian_provider.AsyncOpenAI",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        ],
    )
    def test_provider_passes_configured_max_retries(
        self,
        provider_cls,
        patch_target,
        base_url,
    ):
        """Provider clients should propagate configured retry counts to the SDK."""
        with patch(patch_target) as mock_client:
            provider = provider_cls(
                {
                    "name": "test",
                    "provider": "custom",
                    "api_key": "sk-test12345678901234567890",
                    "base_url": base_url,
                    "model_id": "test-model",
                    "timeout": 60.0,
                    "max_retries": 4,
                }
            )

            provider._get_client()

            assert mock_client.call_args is not None
            assert mock_client.call_args.kwargs["max_retries"] == 4
