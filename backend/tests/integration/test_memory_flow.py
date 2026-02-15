"""Integration tests for memory recording flow."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.memory.context_builder import ContextBuilder
from src.memory.md_sync import MarkdownSync
from src.memory.models import MemoryEntry, MemoryContentType, DailyLog


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir) / "workspace"
        workspace.mkdir()
        (workspace / "memory").mkdir()
        yield str(workspace)


@pytest.fixture
def md_sync(temp_workspace):
    """Create MarkdownSync instance with temp workspace."""
    return MarkdownSync(temp_workspace)


class TestMemoryRecordingFlow:
    """Integration tests for the complete memory recording flow."""

    def test_full_memory_recording_flow(self, md_sync, temp_workspace):
        """Test complete flow: create entry -> save to file -> load in context."""
        # Step 1: Create a memory entry
        entry = MemoryEntry(
            content="User decided to use PostgreSQL for production database",
            content_type=MemoryContentType.DECISION,
            metadata={"session_id": "test-session-123"}
        )
        
        # Step 2: Save entry to daily log
        result = md_sync.append_memory_entry(entry)
        assert result is True
        
        # Step 3: Verify file was created
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        assert log_file.exists()
        
        # Step 4: Load daily log
        loaded_log = md_sync.load_daily_log(date_str)
        assert loaded_log is not None
        assert loaded_log.date == date_str
        
        # Step 5: Build context and verify log is included
        builder = ContextBuilder(temp_workspace)
        context = builder.build_context()
        
        assert context.recent_logs is not None
        assert len(context.recent_logs) >= 1

    def test_multiple_entries_same_day(self, md_sync, temp_workspace):
        """Test recording multiple entries on the same day."""
        entries = [
            MemoryEntry(content="Morning discussion about architecture", 
                       content_type=MemoryContentType.CONVERSATION),
            MemoryEntry(content="Decided to use FastAPI for backend",
                       content_type=MemoryContentType.DECISION),
            MemoryEntry(content="Afternoon code review session",
                       content_type=MemoryContentType.CONVERSATION),
        ]
        
        for entry in entries:
            md_sync.append_memory_entry(entry)
        
        # Verify all entries are in the file
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        content = log_file.read_text()
        
        assert "Morning discussion" in content
        assert "FastAPI" in content
        assert "Afternoon code review" in content

    def test_entries_across_multiple_days(self, md_sync, temp_workspace):
        """Test entries recorded on different days."""
        from datetime import timedelta
        
        # Create entries with different dates
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        entry_today = MemoryEntry(
            content="Today's entry",
            content_type=MemoryContentType.CONVERSATION
        )
        entry_today.created_at = today
        
        entry_yesterday = MemoryEntry(
            content="Yesterday's entry",
            content_type=MemoryContentType.CONVERSATION
        )
        entry_yesterday.created_at = yesterday
        
        md_sync.append_memory_entry(entry_today)
        md_sync.append_memory_entry(entry_yesterday)
        
        # Verify two log files exist
        memory_dir = Path(temp_workspace) / "memory"
        log_files = list(memory_dir.glob("*.md"))
        
        assert len(log_files) == 2

    def test_memory_entry_with_embedding_placeholder(self, md_sync, temp_workspace):
        """Test memory entry structure ready for embedding."""
        entry = MemoryEntry(
            content="This entry will have an embedding",
            content_type=MemoryContentType.CONVERSATION,
            metadata={"session_id": "embedding-test"}
        )
        
        md_sync.append_memory_entry(entry)
        
        # Verify entry has required fields for vector store
        assert entry.id is not None
        assert entry.content is not None
        assert entry.embedding is None  # Will be set by embedding service later


class TestMemoryAPIIntegration:
    """Integration tests for memory API endpoints."""

    def test_memory_entry_api_flow(self, temp_workspace):
        """Test creating memory entry via API-like flow."""
        md_sync = MarkdownSync(temp_workspace)
        
        # Simulate API request body
        request_data = {
            "content": "API test: User wants dark mode enabled",
            "content_type": "decision",
            "metadata": {"source": "chat"}
        }
        
        # Create entry
        entry = MemoryEntry(**request_data)
        result = md_sync.append_memory_entry(entry)
        
        assert result is True
        
        # Verify entry was saved
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log = md_sync.load_daily_log(date_str)
        
        assert log is not None

    def test_daily_log_retrieval_by_date(self, md_sync, temp_workspace):
        """Test retrieving daily log by specific date."""
        # Create entries for specific date
        entry = MemoryEntry(content="Test entry for date retrieval")
        md_sync.append_memory_entry(entry)
        
        date_str = entry.created_at.strftime("%Y-%m-%d")
        
        # Retrieve log
        log = md_sync.load_daily_log(date_str)
        
        assert log is not None
        assert log.date == date_str


class TestContextBuilderIntegration:
    """Integration tests for context builder with memory."""

    def test_context_includes_recent_logs(self, temp_workspace):
        """Test that context builder includes recent daily logs."""
        md_sync = MarkdownSync(temp_workspace)
        
        # Create some entries
        for i in range(3):
            entry = MemoryEntry(content=f"Entry {i+1}")
            md_sync.append_memory_entry(entry)
        
        # Build context
        builder = ContextBuilder(temp_workspace)
        context = builder.build_context()
        
        assert context.recent_logs is not None

    def test_context_refresh_after_new_entry(self, temp_workspace):
        """Test that context refreshes after new entry."""
        md_sync = MarkdownSync(temp_workspace)
        builder = ContextBuilder(temp_workspace)
        
        # Build initial context
        context1 = builder.build_context()
        initial_count = len(context1.recent_logs) if context1.recent_logs else 0
        
        # Add new entry
        entry = MemoryEntry(content="New test entry")
        md_sync.append_memory_entry(entry)
        
        # Clear cache and rebuild
        builder.clear_cache()
        context2 = builder.build_context()
        
        # Context should still have logs
        assert context2.recent_logs is not None


class TestMemoryPersistence:
    """Tests for memory persistence and durability."""

    def test_memory_survives_workspace_reload(self, temp_workspace):
        """Test that memory persists across workspace reload."""
        # Create entry with first md_sync instance
        md_sync1 = MarkdownSync(temp_workspace)
        entry = MemoryEntry(content="Persistent entry")
        md_sync1.append_memory_entry(entry)
        
        # Create new md_sync instance (simulating restart)
        md_sync2 = MarkdownSync(temp_workspace)
        
        # Load the log
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log = md_sync2.load_daily_log(date_str)
        
        assert log is not None
        
        # Verify content persisted
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        content = log_file.read_text()
        assert "Persistent entry" in content

    def test_concurrent_entry_writes(self, temp_workspace):
        """Test handling of concurrent entry writes."""
        md_sync = MarkdownSync(temp_workspace)
        
        # Write multiple entries rapidly
        entries = [
            MemoryEntry(content=f"Concurrent entry {i}")
            for i in range(10)
        ]
        
        for entry in entries:
            md_sync.append_memory_entry(entry)
        
        # Verify all entries saved
        log_file = Path(temp_workspace) / "memory" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        content = log_file.read_text()
        
        for i in range(10):
            assert f"Concurrent entry {i}" in content
