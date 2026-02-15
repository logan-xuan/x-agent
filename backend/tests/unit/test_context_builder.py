"""Unit tests for ContextBuilder.

Tests for:
- Multi-level context loading
- Spirit/Owner/Tools loading
- Recent logs loading
- Cache management
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.memory.context_builder import ContextBuilder
from src.memory.models import (
    ContextBundle,
    OwnerProfile,
    SpiritConfig,
    ToolDefinition,
)


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestContextBuilder:
    """Tests for ContextBuilder class."""
    
    def test_build_context_empty(self, temp_workspace):
        """Should return empty context when no files exist."""
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        assert context is not None
        assert isinstance(context, ContextBundle)
        assert context.spirit is None
        assert context.owner is None
    
    def test_build_context_with_identity(self, temp_workspace):
        """Should load identity files in context."""
        # Create identity files
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="助手",
            personality="友好",
            values=["诚实"],
            behavior_rules=["遵循指令"],
        ))
        sync.save_owner(OwnerProfile(
            name="张三",
            occupation="工程师",
        ))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        assert context.spirit is not None
        assert context.spirit.role == "助手"
        assert context.owner is not None
        assert context.owner.name == "张三"
    
    def test_build_context_with_tools(self, temp_workspace):
        """Should load tool definitions in context."""
        # Create TOOLS.md
        tools_path = Path(temp_workspace) / "TOOLS.md"
        tools_path.write_text("""# 工具定义

## 文件操作
- `read_file`: 读取文件
- `write_file`: 写入文件
""")
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        builder._load_tools()
        tools = builder._tools
        
        assert len(tools) >= 1
        assert any(t.name == "read_file" for t in tools)
    
    def test_context_caching(self, temp_workspace):
        """Should cache context and not reload unchanged files."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="测试"))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        
        # First load
        context1 = builder.build_context()
        
        # Second load should use cache
        context2 = builder.build_context()
        
        assert context1.loaded_at == context2.loaded_at
    
    def test_clear_cache(self, temp_workspace):
        """Should clear cache and reload files."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="初始"))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        context1 = builder.build_context()
        
        # Modify file
        sync.save_spirit(SpiritConfig(role="修改后"))
        
        # Clear cache and reload
        builder.clear_cache()
        context2 = builder.build_context()
        
        assert context2.spirit.role == "修改后"
    
    def test_format_context_for_prompt(self, temp_workspace):
        """Should format context for AI prompt."""
        from src.memory.md_sync import MarkdownSync
        
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="助手",
            personality="友好",
            values=["诚实"],
            behavior_rules=["遵循指令"],
        ))
        sync.save_owner(OwnerProfile(
            name="张三",
            occupation="工程师",
        ))
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        prompt = builder.format_context_for_prompt(context)
        
        assert "张三" in prompt
        assert "助手" in prompt
        assert "工程师" in prompt
    
    def test_load_recent_logs(self, temp_workspace):
        """Should load recent daily logs."""
        # Create today's log
        memory_dir = Path(temp_workspace) / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        log_path = memory_dir / f"{today}.md"
        log_path.write_text(f"# {today} 日志\n\n## 记录条目\n\n### 10:00 - conversation\n测试内容\n")
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        logs = builder._load_recent_logs(days=1)
        
        assert len(logs) >= 1
    
    def test_get_memory_context(self, temp_workspace):
        """Should return memory context string."""
        from src.memory.md_sync import MarkdownSync
        
        # Create MEMORY.md
        memory_path = Path(temp_workspace) / "MEMORY.md"
        memory_path.write_text("""# 长期记忆

## 记忆条目
- 重要事项1
""")
        
        builder = ContextBuilder(workspace_path=temp_workspace)
        memory = builder._load_long_term_memory()
        
        assert "长期记忆" in memory or len(memory) > 0
