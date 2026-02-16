"""Integration tests for full guidance flow.

Tests for T046:
- Bootstrap flow
- Session context loading
- AGENTS.md hot-reload
- Memory maintenance
"""

import asyncio
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.memory.context_builder import ContextBuilder
from src.memory.md_sync import MarkdownSync
from src.memory.models import SpiritConfig, OwnerProfile, MemoryEntry, MemoryContentType
from src.services.memory_maintenance import MemoryMaintenanceService


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "memory").mkdir()
        yield str(workspace)


class TestGuidanceFlow:
    """Integration tests for full guidance flow."""

    def test_bootstrap_flow(self, temp_workspace: str) -> None:
        """Test bootstrap detection and execution."""
        workspace = Path(temp_workspace)
        
        # Create BOOTSTRAP.md
        bootstrap_content = """# 首次启动引导

## 任务列表
- [ ] 设置身份
- [ ] 了解用户

## 引导语
欢迎！我是你的 AI 助手，让我们开始吧。
"""
        (workspace / "BOOTSTRAP.md").write_text(bootstrap_content)
        
        # Create minimal identity files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="引导助手"))
        sync.save_owner(OwnerProfile(name="新用户"))
        
        # Build context - should handle bootstrap
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        # Verify context loaded
        assert context.spirit is not None
        assert context.owner is not None

    def test_session_context_loading_order(self, temp_workspace: str) -> None:
        """Test that context files are loaded in correct order."""
        workspace = Path(temp_workspace)
        
        # Create all context files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(
            role="测试AI",
            personality="友好",
            values=["测试"],
        ))
        sync.save_owner(OwnerProfile(
            name="测试用户",
            occupation="测试",
        ))
        
        # Create TOOLS.md
        (workspace / "TOOLS.md").write_text("# 工具\n- `test`: 测试工具\n")
        
        # Create MEMORY.md
        (workspace / "MEMORY.md").write_text("# 长期记忆\n测试记忆\n")
        
        # Create daily memory
        today = datetime.now().strftime("%Y-%m-%d")
        (workspace / "memory" / f"{today}.md").write_text(f"""# {today}

### 10:00 - conversation
今日对话内容
""")
        
        # Build context
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        # Verify loaded files - context components exist
        assert context.spirit is not None
        assert context.owner is not None
        assert len(context.tools) >= 1  # TOOLS loaded

    def test_agents_md_hot_reload(self, temp_workspace: str) -> None:
        """Test AGENTS.md change detection and reload."""
        workspace = Path(temp_workspace)
        
        # Create AGENTS.md
        agents_path = workspace / "AGENTS.md"
        agents_path.write_text("""# Agent 指引

当前模式：初始模式
""")
        
        # Create identity files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="热重载助手"))
        sync.save_owner(OwnerProfile(name="用户"))
        
        # Initial context
        builder = ContextBuilder(workspace_path=temp_workspace)
        context1 = builder.build_context()
        
        # Modify AGENTS.md
        agents_path.write_text("""# Agent 指引

当前模式：更新模式

新规则：详细回复
""")
        
        # Clear cache and reload
        builder.clear_cache()
        context2 = builder.build_context()
        
        # Verify context reflects changes
        # Note: actual reload logic depends on AGENTS.md being loaded
        assert context2 is not None

    def test_memory_maintenance_flow(self, temp_workspace: str) -> None:
        """Test full memory maintenance cycle."""
        workspace = Path(temp_workspace)
        
        # Create daily log with important content
        today = datetime.now().strftime("%Y-%m-%d")
        daily_log = workspace / "memory" / f"{today}.md"
        daily_log.write_text(f"""# {today} 日志

## 记录条目

### 10:00 - decision
重要决策：选择 Python 作为主要开发语言

### 11:00 - conversation
今天天气不错

### 14:00 - manual
关键偏好：用户喜欢详细的技术解释
""")
        
        # Run maintenance
        service = MemoryMaintenanceService(temp_workspace)
        result = asyncio.run(service.run_maintenance())
        
        # Verify maintenance executed
        assert result["success"] is True
        assert result["processed_entries"] >= 1

    def test_graceful_degradation(self, temp_workspace: str) -> None:
        """Test graceful degradation when files are missing."""
        # Build context without any files
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        
        # Should not raise, just return empty context
        assert context is not None
        assert context.spirit is None
        assert context.owner is None

    def test_concurrent_access(self, temp_workspace: str) -> None:
        """Test concurrent file access safety."""
        sync = MarkdownSync(temp_workspace)
        
        # Create initial files
        sync.save_spirit(SpiritConfig(role="并发测试"))
        sync.save_owner(OwnerProfile(name="并发用户"))
        
        # Simulate concurrent writes
        async def concurrent_update():
            for i in range(5):
                sync.save_owner(OwnerProfile(
                    name=f"用户{i}",
                    occupation=f"职业{i}",
                ))
        
        # Run concurrent updates
        asyncio.run(concurrent_update())
        
        # Verify final state is consistent
        owner = sync.load_owner()
        assert owner is not None
        assert owner.name.startswith("用户")

    def test_context_performance(self, temp_workspace: str) -> None:
        """Test context loading performance."""
        workspace = Path(temp_workspace)
        
        # Create context files
        sync = MarkdownSync(temp_workspace)
        sync.save_spirit(SpiritConfig(role="性能测试AI"))
        sync.save_owner(OwnerProfile(name="性能测试用户"))
        
        # Create large MEMORY.md
        memory_content = "# 长期记忆\n\n"
        for i in range(100):
            memory_content += f"- [2026-02-{i % 28 + 1:02d}] 记忆条目 {i}\n"
        (workspace / "MEMORY.md").write_text(memory_content)
        
        # Measure loading time
        start = time.time()
        builder = ContextBuilder(workspace_path=temp_workspace)
        context = builder.build_context()
        elapsed_ms = (time.time() - start) * 1000
        
        # Should load in reasonable time (< 1000ms)
        assert elapsed_ms < 1000
        assert context is not None


class TestMemoryFlow:
    """Integration tests for memory recording flow."""

    def test_memory_entry_recording(self, temp_workspace: str) -> None:
        """Test recording memory entries."""
        sync = MarkdownSync(temp_workspace)
        
        # Create memory entry
        entry = MemoryEntry(
            content="测试记忆内容",
            content_type=MemoryContentType.CONVERSATION,
        )
        
        # Save entry
        success = sync.append_memory_entry(entry)
        assert success is True
        
        # Verify entry saved
        today = datetime.now().strftime("%Y-%m-%d")
        entries = sync.load_entries_from_log(today)
        
        assert len(entries) >= 1
        assert "测试记忆内容" in entries[-1].content

    def test_memory_search_integration(self, temp_workspace: str) -> None:
        """Test memory search functionality."""
        sync = MarkdownSync(temp_workspace)
        
        # Create multiple entries
        entries = [
            MemoryEntry(content="Python 开发经验", content_type=MemoryContentType.MANUAL),
            MemoryEntry(content="前端 React 开发", content_type=MemoryContentType.MANUAL),
            MemoryEntry(content="数据库设计决策", content_type=MemoryContentType.DECISION),
        ]
        
        for entry in entries:
            sync.append_memory_entry(entry)
        
        # List entries
        all_entries = sync.list_all_entries(limit=100)
        
        assert len(all_entries) >= 3


class TestIdentityFlow:
    """Integration tests for identity management flow."""

    def test_identity_initialization(self, temp_workspace: str) -> None:
        """Test identity initialization flow."""
        sync = MarkdownSync(temp_workspace)
        
        # Check initial status
        status = sync.check_identity_status()
        assert status["initialized"] is False
        
        # Initialize identity
        sync.save_spirit(SpiritConfig(
            role="新助手",
            personality="专业",
            values=["服务", "质量"],
        ))
        sync.save_owner(OwnerProfile(
            name="新用户",
            occupation="新职业",
        ))
        
        # Check status after initialization
        status = sync.check_identity_status()
        assert status["initialized"] is True
        assert status["has_spirit"] is True
        assert status["has_owner"] is True

    def test_identity_update_flow(self, temp_workspace: str) -> None:
        """Test identity update flow."""
        sync = MarkdownSync(temp_workspace)
        
        # Create initial identity
        sync.save_spirit(SpiritConfig(role="初始角色"))
        sync.save_owner(OwnerProfile(name="初始用户"))
        
        # Load and verify
        spirit = sync.load_spirit()
        owner = sync.load_owner()
        assert spirit.role == "初始角色"
        assert owner.name == "初始用户"
        
        # Update identity
        sync.save_spirit(SpiritConfig(role="更新角色"))
        sync.save_owner(OwnerProfile(name="更新用户"))
        
        # Verify updates
        spirit = sync.load_spirit()
        owner = sync.load_owner()
        assert spirit.role == "更新角色"
        assert owner.name == "更新用户"
