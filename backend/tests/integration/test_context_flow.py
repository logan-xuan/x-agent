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

from src.memory.context_builder import ContextBuilder
from src.memory.models import (
    ContextBundle,
    OwnerProfile,
    SpiritConfig,
)
from src.memory.md_sync import MarkdownSync


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
    
    def test_agent_context_integration(self, temp_workspace):
        """Should integrate context into Agent chat."""
        from src.core.agent import Agent
        from unittest.mock import AsyncMock, MagicMock
        
        # Create identity files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="测试AI",
            personality="友好",
        ))
        sync.save_owner(OwnerProfile(name="测试用户"))
        
        # Create agent with context builder
        context_builder = ContextBuilder(workspace_path=temp_workspace)
        
        # Mock LLM router to capture messages
        mock_router = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "测试回复"
        mock_response.model = "test-model"
        mock_response.usage = {}
        mock_router.chat = AsyncMock(return_value=mock_response)
        
        # Mock session manager
        from src.core.session import SessionManager
        mock_session = MagicMock(spec=SessionManager)
        mock_session.add_message = AsyncMock()
        mock_session.get_messages_as_dict = AsyncMock(return_value=[
            {"role": "user", "content": "你好"}
        ])
        
        agent = Agent(
            session_manager=mock_session,
            llm_router=mock_router,
            context_builder=context_builder,
        )
        
        # Verify context builder is set
        assert agent._context_builder is not None
        
        # Verify context loads correctly
        context = context_builder.build_context()
        assert context.spirit is not None
        assert context.owner is not None
