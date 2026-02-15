"""Unit tests for ContextLoader.

Tests for:
- BOOTSTRAP.md detection
- Bootstrap initialization flow
- Context loading with session types
- AGENTS.md hot-reload
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.core.context_loader import (
    ContextLoader,
    BootstrapStatus,
    get_context_loader,
)
from src.memory.models import SessionType, SpiritConfig, OwnerProfile
from src.memory.md_sync import MarkdownSync
from src.services.template_service import TemplateService


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def context_loader(temp_workspace):
    """Create ContextLoader with temporary workspace."""
    return ContextLoader(workspace_path=temp_workspace)


class TestBootstrapDetection:
    """Tests for BOOTSTRAP.md detection (T014)."""
    
    def test_check_bootstrap_not_exists(self, context_loader, temp_workspace):
        """Should return False when BOOTSTRAP.md doesn't exist."""
        status = context_loader.check_bootstrap()
        
        assert isinstance(status, BootstrapStatus)
        assert status.exists is False
        assert status.content == ""
    
    def test_check_bootstrap_exists(self, context_loader, temp_workspace):
        """Should return True when BOOTSTRAP.md exists."""
        # Create BOOTSTRAP.md
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text("# Bootstrap\n\n初始化内容")
        
        status = context_loader.check_bootstrap()
        
        assert status.exists is True
        assert "初始化内容" in status.content
    
    def test_check_bootstrap_content(self, context_loader, temp_workspace):
        """Should return full content of BOOTSTRAP.md."""
        content = "# Welcome\n\nPlease initialize me."
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text(content)
        
        status = context_loader.check_bootstrap()
        
        assert status.content == content


class TestBootstrapInitialization:
    """Tests for bootstrap initialization flow (T015)."""
    
    def test_execute_bootstrap_no_file(self, context_loader, temp_workspace):
        """Should succeed when no BOOTSTRAP.md exists."""
        result = context_loader.execute_bootstrap()
        
        assert result is True
    
    def test_execute_bootstrap_creates_missing_files(self, context_loader, temp_workspace):
        """Should create missing required files during bootstrap."""
        # Create BOOTSTRAP.md
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text("# Bootstrap")
        
        result = context_loader.execute_bootstrap()
        
        assert result is True
        # Check required files were created
        assert (Path(temp_workspace) / "AGENTS.md").exists()
        assert (Path(temp_workspace) / "SPIRIT.md").exists()
        assert (Path(temp_workspace) / "OWNER.md").exists()
    
    def test_execute_bootstrap_deletes_file(self, context_loader, temp_workspace):
        """Should delete BOOTSTRAP.md after successful initialization."""
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text("# Bootstrap")
        
        result = context_loader.execute_bootstrap()
        
        assert result is True
        assert not bootstrap_path.exists()
    
    def test_execute_bootstrap_preserves_existing_files(self, context_loader, temp_workspace):
        """Should not overwrite existing files during bootstrap."""
        # Create existing SPIRIT.md
        spirit_path = Path(temp_workspace) / "SPIRIT.md"
        original_content = "# Original Spirit"
        spirit_path.write_text(original_content)
        
        # Create BOOTSTRAP.md
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text("# Bootstrap")
        
        context_loader.execute_bootstrap()
        
        # Original file should be preserved
        assert spirit_path.read_text() == original_content
    
    def test_bootstrap_creates_memory_directory(self, context_loader, temp_workspace):
        """Should create memory directory during bootstrap."""
        bootstrap_path = Path(temp_workspace) / "BOOTSTRAP.md"
        bootstrap_path.write_text("# Bootstrap")
        
        context_loader.execute_bootstrap()
        
        memory_dir = Path(temp_workspace) / "memory"
        assert memory_dir.exists()


class TestContextLoading:
    """Tests for context loading functionality."""
    
    def test_load_context_creates_context_bundle(self, context_loader, temp_workspace):
        """Should create ContextBundle on load."""
        context = context_loader.load_context(
            session_id="test-session",
            session_type=SessionType.MAIN
        )
        
        assert context is not None
        assert context.session_id == "test-session"
        assert context.session_type == SessionType.MAIN
    
    def test_load_context_main_session_loads_memory(self, context_loader, temp_workspace):
        """Should load MEMORY.md in main session."""
        # Create MEMORY.md
        memory_path = Path(temp_workspace) / "MEMORY.md"
        memory_path.write_text("# Memory\n\nImportant content")
        
        context = context_loader.load_context(
            session_id="test-session",
            session_type=SessionType.MAIN
        )
        
        # In main session, memory should be loaded
        assert "Important content" in context.long_term_memory or context.long_term_memory != ""
    
    def test_load_context_shared_session_excludes_memory(self, context_loader, temp_workspace):
        """Should NOT load MEMORY.md in shared context."""
        # Create MEMORY.md with sensitive content
        memory_path = Path(temp_workspace) / "MEMORY.md"
        memory_path.write_text("# Memory\n\nSECRET DATA")
        
        context = context_loader.load_context(
            session_id="test-session",
            session_type=SessionType.SHARED
        )
        
        # In shared context, memory should be cleared (privacy)
        assert context.long_term_memory == ""
    
    def test_load_context_tracks_loaded_files(self, context_loader, temp_workspace):
        """Should track which files were loaded."""
        # Create some files
        (Path(temp_workspace) / "SPIRIT.md").write_text("# Spirit")
        (Path(temp_workspace) / "OWNER.md").write_text("# Owner")
        
        context = context_loader.load_context(
            session_id="test-session",
            session_type=SessionType.MAIN
        )
        
        assert len(context.loaded_files) > 0
    
    def test_load_context_records_load_time(self, context_loader, temp_workspace):
        """Should record load time in milliseconds."""
        context = context_loader.load_context(
            session_id="test-session",
            session_type=SessionType.MAIN
        )
        
        assert context.load_time_ms >= 0


class TestAgentsReload:
    """Tests for AGENTS.md hot-reload functionality."""
    
    def test_load_agents_content(self, context_loader, temp_workspace):
        """Should load AGENTS.md content."""
        agents_path = Path(temp_workspace) / "AGENTS.md"
        agents_path.write_text("# AGENTS\n\nGuidance content")
        
        content, reloaded = context_loader.load_agents_content()
        
        assert "Guidance content" in content
        assert reloaded is True
    
    def test_load_agents_uses_cache(self, context_loader, temp_workspace):
        """Should use cached content on second load."""
        agents_path = Path(temp_workspace) / "AGENTS.md"
        agents_path.write_text("# AGENTS\n\nContent")
        
        # First load
        content1, reloaded1 = context_loader.load_agents_content()
        
        # Second load (should use cache)
        content2, reloaded2 = context_loader.load_agents_content()
        
        assert content1 == content2
        assert reloaded1 is True
        assert reloaded2 is False
    
    def test_load_agents_detects_changes(self, context_loader, temp_workspace):
        """Should detect file changes and reload."""
        agents_path = Path(temp_workspace) / "AGENTS.md"
        agents_path.write_text("# AGENTS\n\nOriginal")
        
        # First load
        content1, _ = context_loader.load_agents_content()
        
        # Modify file
        import time
        time.sleep(0.1)  # Ensure mtime changes
        agents_path.write_text("# AGENTS\n\nModified")
        
        # Second load (should detect change)
        content2, reloaded = context_loader.load_agents_content()
        
        assert "Modified" in content2
        assert reloaded is True
    
    def test_reload_if_changed_performance(self, context_loader, temp_workspace):
        """Should reload within performance target (<1000ms)."""
        agents_path = Path(temp_workspace) / "AGENTS.md"
        agents_path.write_text("# AGENTS\n\n" + "x" * 1000)
        
        content, reloaded, reload_time_ms = context_loader.reload_agents_if_changed()
        
        assert reload_time_ms < 1000  # SC-004 requirement
        assert len(content) > 0
    
    def test_load_agents_creates_if_missing(self, context_loader, temp_workspace):
        """Should create AGENTS.md if missing (graceful degradation)."""
        agents_path = Path(temp_workspace) / "AGENTS.md"
        assert not agents_path.exists()
        
        content, reloaded = context_loader.load_agents_content()
        
        # File should be created
        assert agents_path.exists()
        assert len(content) > 0


class TestGetContextLoader:
    """Tests for global context loader instance."""
    
    def test_get_context_loader_singleton(self):
        """Should return same instance on multiple calls."""
        import src.core.context_loader as module
        module._context_loader = None  # Reset
        
        loader1 = get_context_loader()
        loader2 = get_context_loader()
        
        assert loader1 is loader2
    
    def test_get_context_loader_custom_path(self):
        """Should create loader with custom workspace path."""
        import src.core.context_loader as module
        module._context_loader = None  # Reset
        
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = get_context_loader(tmpdir)
            assert str(loader.workspace_path) == tmpdir
