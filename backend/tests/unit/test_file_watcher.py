"""Unit tests for file watcher functionality.

Tests cover:
- File event detection
- Callback triggering
- Memory file sync integration
"""

import pytest
import tempfile
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

# Direct imports to avoid circular import via __init__.py
from src.memory.file_watcher import (
    FileWatcher,
    MemoryFileHandler,
    get_file_watcher,
)
from src.memory.models import MemoryEntry, MemoryContentType


class TestMemoryFileHandler:
    """Tests for MemoryFileHandler."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def handler(self) -> MemoryFileHandler:
        """Create file handler with mock callbacks."""
        return MemoryFileHandler(
            on_spirit_changed=MagicMock(),
            on_owner_changed=MagicMock(),
            on_tools_changed=MagicMock(),
            on_memory_changed=MagicMock(),
            on_agents_changed=MagicMock(),
        )

    def test_handler_initialization(self, handler: MemoryFileHandler) -> None:
        """Test handler initialization."""
        assert handler.on_spirit_changed is not None
        assert handler.on_owner_changed is not None
        assert handler.on_tools_changed is not None
        assert handler.on_memory_changed is not None
        assert handler.on_agents_changed is not None

    def test_ignores_directories(self, handler: MemoryFileHandler) -> None:
        """Test that directory events are ignored."""
        from watchdog.events import DirModifiedEvent
        
        event = DirModifiedEvent("/some/path")
        handler.on_modified(event)
        
        handler.on_spirit_changed.assert_not_called()

    def test_ignores_non_md_files(self, handler: MemoryFileHandler) -> None:
        """Test that non-.md files are ignored."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/some/path/file.txt")
        handler.on_modified(event)
        
        handler.on_spirit_changed.assert_not_called()
        handler.on_owner_changed.assert_not_called()

    def test_handles_spirit_md_modified(self, handler: MemoryFileHandler) -> None:
        """Test SPIRIT.md modification triggers callback."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/workspace/SPIRIT.md")
        handler.on_modified(event)
        
        handler.on_spirit_changed.assert_called_once()

    def test_handles_owner_md_modified(self, handler: MemoryFileHandler) -> None:
        """Test OWNER.md modification triggers callback."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/workspace/OWNER.md")
        handler.on_modified(event)
        
        handler.on_owner_changed.assert_called_once()

    def test_handles_tools_md_modified(self, handler: MemoryFileHandler) -> None:
        """Test TOOLS.md modification triggers callback."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/workspace/TOOLS.md")
        handler.on_modified(event)
        
        handler.on_tools_changed.assert_called_once()

    def test_handles_agents_md_modified(self, handler: MemoryFileHandler) -> None:
        """Test AGENTS.md modification triggers callback (T030)."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/workspace/AGENTS.md")
        handler.on_modified(event)
        
        handler.on_agents_changed.assert_called_once()

    def test_handles_memory_file_modified(self, handler: MemoryFileHandler) -> None:
        """Test memory/*.md modification triggers callback."""
        from watchdog.events import FileModifiedEvent
        
        event = FileModifiedEvent("/workspace/memory/2026-02-14.md")
        handler.on_modified(event)
        
        handler.on_memory_changed.assert_called_once_with("/workspace/memory/2026-02-14.md")

    def test_handles_file_created(self, handler: MemoryFileHandler) -> None:
        """Test file creation event."""
        from watchdog.events import FileCreatedEvent
        
        event = FileCreatedEvent("/workspace/SPIRIT.md")
        handler.on_created(event)
        
        handler.on_spirit_changed.assert_called_once()

    def test_handles_file_deleted(self, handler: MemoryFileHandler) -> None:
        """Test file deletion event logs warning."""
        from watchdog.events import FileDeletedEvent
        
        event = FileDeletedEvent("/workspace/memory/2026-02-14.md")
        # Should not raise, just log warning
        handler.on_deleted(event)

    def test_agents_reload_performance(self, handler: MemoryFileHandler) -> None:
        """Test AGENTS.md reload detection performance (T031).
        
        Verifies that file event detection completes within acceptable time.
        The actual reload performance (<1000ms) is tested in test_context_loader.py.
        """
        import time
        from watchdog.events import FileModifiedEvent
        
        start_time = time.time()
        
        # Simulate multiple rapid file events
        for _ in range(10):
            event = FileModifiedEvent("/workspace/AGENTS.md")
            handler.on_modified(event)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Event processing should be very fast (< 100ms for 10 events)
        assert elapsed_ms < 100


class TestFileWatcher:
    """Tests for FileWatcher class."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create temporary workspace directory."""
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "memory").mkdir()
            yield workspace

    @pytest.fixture
    def file_watcher(self, temp_workspace: Path) -> FileWatcher:
        """Create file watcher instance."""
        return FileWatcher(str(temp_workspace))

    def test_watcher_initialization(self, temp_workspace: Path) -> None:
        """Test file watcher initialization."""
        watcher = FileWatcher(str(temp_workspace))
        
        assert watcher.workspace_path == temp_workspace
        assert not watcher.is_running()

    def test_watcher_start(self, file_watcher: FileWatcher) -> None:
        """Test starting file watcher."""
        file_watcher.start(
            on_spirit_changed=lambda: None,
            on_owner_changed=lambda: None,
        )
        
        assert file_watcher.is_running()
        
        # Cleanup
        file_watcher.stop()

    def test_watcher_stop(self, file_watcher: FileWatcher) -> None:
        """Test stopping file watcher."""
        file_watcher.start(
            on_spirit_changed=lambda: None,
        )
        
        file_watcher.stop()
        
        assert not file_watcher.is_running()

    def test_double_start_warning(self, file_watcher: FileWatcher) -> None:
        """Test that starting twice logs warning."""
        file_watcher.start(on_spirit_changed=lambda: None)
        
        # Second start should be ignored
        file_watcher.start(on_spirit_changed=lambda: None)
        
        assert file_watcher.is_running()
        
        file_watcher.stop()

    def test_detects_file_modification(
        self,
        file_watcher: FileWatcher,
        temp_workspace: Path,
    ) -> None:
        """Test that file modifications are detected."""
        callback_called = []
        
        def on_spirit_changed():
            callback_called.append(True)
        
        file_watcher.start(on_spirit_changed=on_spirit_changed)
        
        # Create and modify SPIRIT.md
        spirit_path = temp_workspace / "SPIRIT.md"
        spirit_path.write_text("# Test")
        time.sleep(0.1)  # Wait for file system event
        spirit_path.write_text("# Modified")
        
        # Wait for event to be processed
        time.sleep(0.5)
        
        file_watcher.stop()
        
        # Callback should have been called (at least once due to multiple events)
        assert len(callback_called) >= 1


class TestFileWatcherGlobal:
    """Tests for global file watcher instance."""

    def test_get_file_watcher_singleton(self, tmp_path: Path) -> None:
        """Test that get_file_watcher returns singleton."""
        import src.memory.file_watcher as fw_module
        fw_module._file_watcher = None
        
        watcher1 = get_file_watcher(str(tmp_path))
        watcher2 = get_file_watcher()
        
        assert watcher1 is watcher2
        
        # Cleanup
        if watcher1.is_running():
            watcher1.stop()
        fw_module._file_watcher = None


class TestMemoryFileSync:
    """Tests for memory file sync functionality."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create temporary workspace with memory directory."""
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "memory").mkdir()
            yield workspace

    def test_sync_entry_to_vector_store(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test syncing a memory entry to vector store."""
        from src.memory.md_sync import MarkdownSync
        from src.memory.vector_store import VectorStore
        
        # Create a memory entry
        md_sync = MarkdownSync(str(temp_workspace))
        entry = MemoryEntry(
            content="Test content for vector store sync",
            content_type=MemoryContentType.DECISION,
        )
        
        # Save to markdown
        md_sync.append_memory_entry(entry)
        
        # Create vector store
        db_path = str(temp_workspace / "test.db")
        vector_store = VectorStore(db_path)
        vector_store.initialize()
        
        # Mock embedder
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384
        
        # Sync to vector store
        embedding = mock_embedder.embed(entry.content)
        vector_store.insert(
            entry_id=entry.id,
            embedding=embedding,
            content=entry.content,
            content_type=entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type),
        )
        
        # Verify entry is in vector store
        count = vector_store.count()
        assert count == 1
        
        vector_store.close()

    def test_sync_existing_entries_on_startup(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test that existing markdown entries are synced on startup."""
        from src.memory.md_sync import MarkdownSync
        from src.memory.vector_store import VectorStore
        from datetime import datetime, timedelta
        
        md_sync = MarkdownSync(str(temp_workspace))
        
        # Create multiple entries with different timestamps to avoid ID collision
        base_time = datetime.now()
        for i in range(3):
            entry = MemoryEntry(
                content=f"Test entry {i}",
                content_type=MemoryContentType.CONVERSATION,
                created_at=base_time + timedelta(minutes=i),  # Different minutes
            )
            md_sync.append_memory_entry(entry)
        
        # Get all entries
        entries = md_sync.list_all_entries(limit=100)
        assert len(entries) >= 3
        
        # Simulate startup sync
        db_path = str(temp_workspace / "test.db")
        vector_store = VectorStore(db_path)
        vector_store.initialize()
        
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384
        
        for entry in entries:
            embedding = mock_embedder.embed(entry.content)
            vector_store.insert(
                entry_id=entry.id,
                embedding=embedding,
                content=entry.content,
                content_type=entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type),
            )
        
        # Verify all synced
        count = vector_store.count()
        assert count == len(entries)
        
        vector_store.close()
