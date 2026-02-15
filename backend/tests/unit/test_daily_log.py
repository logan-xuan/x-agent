"""Unit tests for DailyLog and MemoryEntry functionality."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.memory.md_sync import MarkdownSync
from src.memory.models import DailyLog, MemoryEntry, MemoryContentType


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


class TestMemoryEntry:
    """Tests for MemoryEntry model."""

    def test_create_memory_entry(self):
        """Test creating a memory entry with default values."""
        entry = MemoryEntry(content="Test content")
        
        assert entry.content == "Test content"
        assert entry.content_type == MemoryContentType.CONVERSATION
        assert entry.id is not None
        assert entry.created_at is not None

    def test_create_memory_entry_with_type(self):
        """Test creating a memory entry with specific type."""
        entry = MemoryEntry(
            content="User decided to use React",
            content_type=MemoryContentType.DECISION
        )
        
        assert entry.content_type == MemoryContentType.DECISION

    def test_memory_entry_types(self):
        """Test all memory entry content types."""
        types = [
            MemoryContentType.CONVERSATION,
            MemoryContentType.DECISION,
            MemoryContentType.SUMMARY,
            MemoryContentType.MANUAL,
        ]
        
        for content_type in types:
            entry = MemoryEntry(content="Test", content_type=content_type)
            assert entry.content_type == content_type

    def test_update_timestamp(self):
        """Test updating timestamp."""
        entry = MemoryEntry(content="Test")
        original_time = entry.updated_at
        
        entry.update_timestamp()
        
        assert entry.updated_at >= original_time

    def test_metadata(self):
        """Test memory entry with metadata."""
        entry = MemoryEntry(
            content="Test",
            metadata={"session_id": "test-123", "tags": ["important"]}
        )
        
        assert entry.metadata["session_id"] == "test-123"
        assert "important" in entry.metadata["tags"]


class TestDailyLog:
    """Tests for DailyLog model."""

    def test_create_daily_log(self):
        """Test creating a daily log."""
        log = DailyLog(date="2026-02-14")
        
        assert log.date == "2026-02-14"
        assert log.entries == []
        assert log.summary == ""

    def test_daily_log_with_entries(self):
        """Test daily log with entry IDs."""
        log = DailyLog(
            date="2026-02-14",
            entries=["entry-1", "entry-2"],
            summary="Test summary"
        )
        
        assert len(log.entries) == 2
        assert log.summary == "Test summary"


class TestDailyLogManager:
    """Tests for daily log management in MarkdownSync."""

    def test_load_nonexistent_daily_log(self, md_sync):
        """Test loading a daily log that doesn't exist."""
        log = md_sync.load_daily_log("2026-02-14")
        
        assert log is None

    def test_append_memory_entry_creates_file(self, md_sync, temp_workspace):
        """Test that appending entry creates daily log file."""
        entry = MemoryEntry(
            content="Test memory entry",
            content_type=MemoryContentType.CONVERSATION
        )
        
        result = md_sync.append_memory_entry(entry)
        
        assert result is True
        
        # Check file was created
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        assert log_file.exists()

    def test_append_multiple_entries(self, md_sync, temp_workspace):
        """Test appending multiple entries to same daily log."""
        entry1 = MemoryEntry(content="First entry")
        entry2 = MemoryEntry(content="Second entry")
        
        md_sync.append_memory_entry(entry1)
        md_sync.append_memory_entry(entry2)
        
        date_str = entry1.created_at.strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        
        content = log_file.read_text()
        assert "First entry" in content
        assert "Second entry" in content

    def test_append_decision_entry(self, md_sync, temp_workspace):
        """Test appending a decision entry."""
        entry = MemoryEntry(
            content="User decided to use SQLite for database",
            content_type=MemoryContentType.DECISION
        )
        
        result = md_sync.append_memory_entry(entry)
        
        assert result is True
        
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        content = log_file.read_text()
        
        assert "decision" in content.lower()
        assert "SQLite" in content

    def test_load_daily_log_content(self, md_sync, temp_workspace):
        """Test loading a daily log with content."""
        # Create entries
        entry = MemoryEntry(content="Test entry content")
        md_sync.append_memory_entry(entry)
        
        # Load the log
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log = md_sync.load_daily_log(date_str)
        
        assert log is not None
        assert log.date == date_str

    def test_entry_format_in_file(self, md_sync, temp_workspace):
        """Test that entry is formatted correctly in file."""
        entry = MemoryEntry(
            content="Test entry for format check",
            content_type=MemoryContentType.DECISION
        )
        md_sync.append_memory_entry(entry)
        
        date_str = entry.created_at.strftime("%Y-%m-%d")
        log_file = Path(temp_workspace) / "memory" / f"{date_str}.md"
        content = log_file.read_text()
        
        # Should have header
        assert "# " in content
        assert "日志" in content
        
        # Should have entry section
        assert "###" in content
        assert "Test entry for format check" in content


class TestMemoryEntryValidation:
    """Tests for memory entry validation."""

    def test_content_required(self):
        """Test that content is required."""
        with pytest.raises(Exception):
            MemoryEntry()  # Missing content

    def test_content_max_length(self):
        """Test content maximum length validation."""
        long_content = "x" * 10000
        entry = MemoryEntry(content=long_content)
        
        assert len(entry.content) == 10000

    def test_valid_content_types(self):
        """Test that only valid content types are accepted."""
        valid_types = ["conversation", "decision", "summary", "manual"]
        
        for type_name in valid_types:
            entry = MemoryEntry(
                content="Test",
                content_type=MemoryContentType(type_name)
            )
            assert entry.content_type == type_name


class TestDailyLogIntegration:
    """Integration tests for daily log with context builder."""

    def test_daily_log_in_context(self, temp_workspace):
        """Test that daily log is included in context."""
        from src.memory.context_builder import ContextBuilder
        
        # Create a daily log entry
        md_sync = MarkdownSync(temp_workspace)
        entry = MemoryEntry(content="Test context entry")
        md_sync.append_memory_entry(entry)
        
        # Build context
        builder = ContextBuilder(temp_workspace)
        context = builder.build_context()
        
        # Check that recent logs are loaded
        assert context.recent_logs is not None
