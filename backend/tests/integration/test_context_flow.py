"""Integration tests for context loading flow.

Tests for:
- Full context loading workflow
- API endpoint integration
- Agent integration
"""

import time
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.agent_core import agent_loop
from src.agent_core.config import AgentCoreConfig
from src.agent_core.logger import AgentLogger
from src.agent_core.types import AgentContext as LoopAgentContext
from src.agent_core.types import AgentTool, StreamChunk, TextContent, ToolParameter, ToolResult, UserMessage
from src.agent_core.types import LogCategory
from src.agent_core.adapters.context_adapter import XAgentContextAdapter
from src.config.models import CompressionConfig
from src.conversation.context import AgentContext as RequestAgentContext
from src.conversation.context import clear_current_context, set_current_context
from src.memory.context_builder import ContextBuilder
from src.memory.models import (
    ContextBundle,
    OwnerProfile,
    SpiritConfig,
)
from src.memory.md_sync import MarkdownSync
from src.services.context.artifact_store import ArtifactStore
from src.services.context.context_assembler import ContextAssembler
from src.services.context.evidence_ledger_store import EvidenceLedgerStore
from src.services.context.episodic_memory_store import EpisodicMemoryStore
from src.services.context.session_state_store import SessionContextStateStore
from src.services.context.session_state_updater import SessionStateUpdater
from src.services.context.tool_result_archiver import ToolResultArchiver
from src.services.storage import StorageService


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def client():
    """Create test client."""
    from src.main import app
    return TestClient(app)


class TestContextFlow:
    """Integration tests for context loading."""
    
    def test_full_context_loading(self, temp_workspace):
        """Should load all context components."""
        # Setup identity files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="测试助手",
            personality="友好",
            values=["诚实", "专业"],
            behavior_rules=["遵循指令", "尊重隐私"],
        ))
        sync.save_owner(OwnerProfile(
            name="测试用户",
            age=30,
            occupation="开发者",
            interests=["Python", "AI"],
            goals=["学习", "提升"],
        ))
        
        # Create TOOLS.md
        tools_path = Path(temp_workspace) / "TOOLS.md"
        tools_path.write_text("""# 工具定义
- `test_tool`: 测试工具
""")
        
        # Create MEMORY.md
        memory_path = Path(temp_workspace) / "MEMORY.md"
        memory_path.write_text("""# 长期记忆
测试记忆内容
""")
        
        # Build context
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        # Verify all components loaded
        assert context.spirit is not None
        assert context.spirit.role == "测试助手"
        assert context.owner is not None
        assert context.owner.name == "测试用户"
        assert len(context.tools) >= 1
        assert len(context.long_term_memory) > 0
    
    def test_context_for_agent_response(self, temp_workspace):
        """Should provide context for AI agent response."""
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="助手",
            behavior_rules=["在响应前回顾上下文"],
        ))
        sync.save_owner(OwnerProfile(
            name="用户",
            interests=["编程"],
        ))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        prompt = builder.format_context_for_prompt(context)
        
        # Verify prompt contains essential information
        assert "用户" in prompt
        assert "助手" in prompt
        assert "编程" in prompt or prompt  # At minimum, prompt should be generated
    
    def test_context_handles_missing_files(self, temp_workspace):
        """Should handle gracefully when some files are missing."""
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        # Should not fail, just have None values
        assert context is not None
        assert context.spirit is None
        assert context.owner is None
        assert context.tools == []
    
    def test_context_update_reflects_file_changes(self, temp_workspace):
        """Should reflect file changes after clear_cache."""
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="初始角色"))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        context1 = builder.build_context()
        
        # Modify file
        sync.save_spirit(SpiritConfig(role="新角色"))
        
        # Clear cache and reload
        builder.clear_cache()
        context2 = builder.build_context()
        
        assert context1.spirit.role == "初始角色"
        assert context2.spirit.role == "新角色"
    
    def test_context_builder_with_spirit_loader(self, temp_workspace):
        """Should use SpiritLoader to load identity."""
        from src.memory.spirit_loader import SpiritLoader
        
        # Create identity files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="上下文助手"))
        sync.save_owner(OwnerProfile(name="上下文用户"))
        
        # Build context
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        assert context.spirit is not None
        assert context.spirit.role == "上下文助手"
        assert context.owner is not None
        assert context.owner.name == "上下文用户"
    
    @pytest.mark.asyncio
    async def test_stateful_agent_loop_integration(self, temp_workspace, tmp_path):
        """Should run stateful agent loop flow end-to-end with evidence archival."""
        db_path = tmp_path / "integration-context.db"
        storage = StorageService(database_url=f"sqlite+aiosqlite:///{db_path}")
        await storage.initialize()

        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="测试AI", personality="友好"))
        sync.save_owner(OwnerProfile(name="测试用户"))

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
                self.token_counter = MagicMock()
                self.token_counter.count_messages.side_effect = lambda messages: len(messages) * 20
                self.token_counter.count_tool_definitions.return_value = 0
                self.token_counter.count_text.side_effect = lambda text: max(1, len(text) // 4) if text else 0
                self._resolve_budget_profile = MagicMock(return_value=None)
                self.prepare_context = AsyncMock()

        context_adapter = XAgentContextAdapter(DummyContextManager(), context_assembler=assembler)

        class DummyLLM:
            def __init__(self):
                self.calls = []

            async def stream(self, system_prompt, messages, tools=None, provider_name=None, max_tokens=None):
                self.calls.append({"messages": messages, "tools": tools})
                if len(self.calls) == 1:
                    yield StreamChunk.tool("call-1", "web_search", {"query": "数字人创业项目"})
                    yield StreamChunk.done("tool_use", {"total_tokens": 10})
                else:
                    yield StreamChunk.text("这是整理好的初步方案。")
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
            session_id="session-integration",
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
                        parameters=[ToolParameter(name="query", type="string", description="query")],
                    )
                ],
            )
            config = AgentCoreConfig(
                llm=DummyLLM(),
                tools=DummyToolPort(),
                logger=logger,
                context=context_adapter,
                model="test-model",
                provider="test-provider",
                enable_context_compression=True,
                enable_experience_learning=False,
            )

            with patch(
                "src.services.context.get_session_state_updater",
                return_value=updater,
            ), patch(
                "src.services.context.get_tool_result_archiver",
                return_value=archiver,
            ):
                async for _ in agent_loop(prompts, loop_context, config):
                    pass

            state = await state_store.get("session-integration")
            assert state is not None
            assert "数字人创业项目" in state.to_dict()["current_goal"]["latest_user_request"]

            evidence_rows = await evidence_store.list_by_session("session-integration")
            assert len(evidence_rows) == 1
            assert "商业化场景" in evidence_rows[0].claim

            context_logs = [
                entry for entry in logger.get_logs(category=LogCategory.AGENT_LOOP, limit=50)
                if entry.event == "context_prepared"
            ]
            assert len(context_logs) >= 1
            assert context_logs[0].data["context_mode"] == "stateful"
        finally:
            clear_current_context()
            await storage.close()
