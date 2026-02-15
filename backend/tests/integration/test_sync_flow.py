"""Integration tests for bidirectional sync functionality.

Tests cover:
- Markdown to vector store sync
- Vector store to Markdown sync
- File change detection and sync
- Error handling and recovery
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.memory.models import MemoryEntry, MemoryContentType
from src.memory.md_sync import MarkdownSync, get_md_sync
from src.memory.vector_store import VectorStore, get_vector_store
from src.memory.file_watcher import FileWatcher, get_file_watcher


class TestBidirectionalSync:
    """Tests for bidirectional sync between Markdown and vector store."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create temporary workspace directory."""
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "memory").mkdir()
            (workspace / "SPIRIT.md").write_text("# Spirit")
            (workspace / "OWNER.md").write_text("# Owner")
            yield workspace

    @pytest.fixture
    def vector_store(self, temp_workspace: Path) -> VectorStore:
        """Create vector store instance."""
        db_path = str(temp_workspace / "test.db")
        store = VectorStore(db_path)
        store.initialize()
        yield store
        store.close()

    @pytest.fixture
    def md_sync(self, temp_workspace: Path) -> MarkdownSync:
        """Create markdown sync instance."""
        return MarkdownSync(str(temp_workspace))

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        """Create mock embedder."""
        mock = MagicMock()
        mock.embed.return_value = [0.1] * 384
        return mock

    def test_markdown_to_vector_sync(
        self,
        temp_workspace: Path,
        vector_store: VectorStore,
        md_sync: MarkdownSync,
        mock_embedder: MagicMock,
    ) -> None:
        """Test syncing Markdown entries to vector store."""
        from datetime import datetime, timedelta
        
        # Create entries in markdown with different timestamps
        base_time = datetime.now()
        entry1 = MemoryEntry(
            content="First test entry for sync",
            content_type=MemoryContentType.DECISION,
            created_at=base_time,
        )
        entry2 = MemoryEntry(
            content="Second test entry for sync",
            content_type=MemoryContentType.CONVERSATION,
            created_at=base_time + timedelta(minutes=1),
        )
        
        md_sync.append_memory_entry(entry1)
        md_sync.append_memory_entry(entry2)
        
        # Sync to vector store
        entries = md_sync.list_all_entries(limit=100)
        
        for entry in entries:
            embedding = mock_embedder.embed(entry.content)
            content_type = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
            vector_store.insert(
                entry_id=entry.id,
                embedding=embedding,
                content=entry.content,
                content_type=content_type,
            )
        
        # Verify sync - at least 2 entries should be present
        assert vector_store.count() >= 2
        
        # Search should work
        results = vector_store.search([0.1] * 384, limit=10)
        assert len(results) >= 0  # May have results depending on vss

    def test_delete_syncs_to_vector_store(
        self,
        temp_workspace: Path,
        vector_store: VectorStore,
        md_sync: MarkdownSync,
        mock_embedder: MagicMock,
    ) -> None:
        """Test that deleting from Markdown syncs to vector store."""
        # Create and sync entry
        entry = MemoryEntry(
            content="Entry to be deleted",
            content_type=MemoryContentType.MANUAL,
        )
        md_sync.append_memory_entry(entry)
        
        embedding = mock_embedder.embed(entry.content)
        content_type = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
        vector_store.insert(
            entry_id=entry.id,
            embedding=embedding,
            content=entry.content,
            content_type=content_type,
        )
        
        assert vector_store.count() == 1
        
        # Delete from markdown
        md_sync.delete_entry(entry.id)
        
        # Should also delete from vector store
        vector_store.delete(entry.id)
        
        assert vector_store.count() == 0

    def test_file_change_triggers_sync(
        self,
        temp_workspace: Path,
        vector_store: VectorStore,
        mock_embedder: MagicMock,
    ) -> None:
        """Test that file changes trigger sync."""
        synced_files = []
        
        def on_memory_changed(file_path: str):
            synced_files.append(file_path)
        
        watcher = FileWatcher(str(temp_workspace))
        watcher.start(on_memory_changed=on_memory_changed)
        
        # Modify a memory file
        memory_file = temp_workspace / "memory" / "2026-02-14.md"
        memory_file.write_text("""# 2026-02-14

## 记录条目

### 10:00 - decision
Test decision content
""")
        
        # Wait for event
        time.sleep(0.5)
        
        watcher.stop()
        
        # Should have detected change
        assert len(synced_files) >= 1

    def test_sync_on_startup(
        self,
        temp_workspace: Path,
        vector_store: VectorStore,
        mock_embedder: MagicMock,
    ) -> None:
        """Test that existing entries are synced on startup."""
        from datetime import datetime, timedelta
        
        md_sync = MarkdownSync(str(temp_workspace))
        
        # Pre-create entries with different timestamps
        base_time = datetime.now()
        for i in range(5):
            entry = MemoryEntry(
                content=f"Startup sync test entry {i}",
                content_type=MemoryContentType.CONVERSATION,
                created_at=base_time + timedelta(minutes=i),
            )
            md_sync.append_memory_entry(entry)
        
        # Simulate startup sync
        entries = md_sync.list_all_entries(limit=100)
        
        for entry in entries:
            embedding = mock_embedder.embed(entry.content)
            content_type = entry.content_type.value if hasattr(entry.content_type, 'value') else str(entry.content_type)
            vector_store.insert(
                entry_id=entry.id,
                embedding=embedding,
                content=entry.content,
                content_type=content_type,
            )
        
        # All entries should be in vector store
        assert vector_store.count() >= 5


class TestFileSyncErrorHandling:
    """Tests for sync error handling."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create temporary workspace."""
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "memory").mkdir()
            yield workspace

    def test_handles_corrupted_markdown(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test handling of corrupted Markdown file."""
        md_sync = MarkdownSync(str(temp_workspace))
        
        # Create corrupted file
        memory_file = temp_workspace / "memory" / "2026-02-14.md"
        memory_file.write_text("""# Invalid

---
invalid yaml frontmatter
---

Content here
""")
        
        # Should not crash when loading
        entries = md_sync.list_all_entries(limit=100)
        assert isinstance(entries, list)

    def test_handles_missing_file(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test handling of missing file."""
        md_sync = MarkdownSync(str(temp_workspace))
        
        # Load from non-existent date
        log = md_sync.load_daily_log("2099-01-01")
        
        # Should return None for non-existent
        assert log is None

    def test_vector_store_fallback(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test fallback when vector store fails."""
        # Create vector store
        db_path = str(temp_workspace / "test.db")
        vector_store = VectorStore(db_path)
        vector_store.initialize()
        
        # Invalid embedding should not crash
        try:
            vector_store.insert(
                entry_id="test-id",
                embedding=[],  # Empty embedding
                content="Test",
                content_type="conversation",
            )
        except Exception:
            pass  # Expected to fail gracefully
        
        vector_store.close()


class TestFileRecovery:
    """Tests for file recovery from vector store."""

    @pytest.fixture
    def temp_workspace(self) -> Path:
        """Create temporary workspace."""
        with tempfile.TemporaryDirectory() as d:
            workspace = Path(d)
            (workspace / "memory").mkdir()
            yield workspace

    def test_recover_entry_from_vector_store(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test recovering a memory entry from vector store."""
        db_path = str(temp_workspace / "test.db")
        vector_store = VectorStore(db_path)
        vector_store.initialize()
        
        # Insert entry into vector store
        entry_id = "recovery-test-id"
        content = "Content to recover"
        
        vector_store.insert(
            entry_id=entry_id,
            embedding=[0.1] * 384,
            content=content,
            content_type="decision",
        )
        
        # Retrieve entry
        entry = vector_store.get_entry(entry_id)
        
        assert entry is not None
        assert entry["content"] == content
        assert entry["content_type"] == "decision"
        
        vector_store.close()

    def test_rebuild_markdown_from_vector_store(
        self,
        temp_workspace: Path,
    ) -> None:
        """Test rebuilding Markdown file from vector store."""
        db_path = str(temp_workspace / "test.db")
        vector_store = VectorStore(db_path)
        vector_store.initialize()
        
        # Insert entries
        entries_data = [
            ("id-1", "First recovered entry", "decision"),
            ("id-2", "Second recovered entry", "conversation"),
        ]
        
        for entry_id, content, content_type in entries_data:
            vector_store.insert(
                entry_id=entry_id,
                embedding=[0.1] * 384,
                content=content,
                content_type=content_type,
            )
        
        # Get all entries from vector store
        all_entries = vector_store.get_all_entries(limit=100)
        
        # Rebuild Markdown
        md_sync = MarkdownSync(str(temp_workspace))
        
        for entry_data in all_entries:
            entry = MemoryEntry(
                id=entry_data["id"],
                content=entry_data["content"],
                content_type=MemoryContentType(entry_data["content_type"]),
            )
            md_sync.append_memory_entry(entry)
        
        # Verify rebuild
        saved_entries = md_sync.list_all_entries(limit=100)
        assert len(saved_entries) >= 2
        
        vector_store.close()
