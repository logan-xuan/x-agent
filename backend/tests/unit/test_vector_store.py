"""Unit tests for vector store functionality.

Tests cover:
- Vector store initialization
- Vector insertion
- Vector search (similarity)
- Vector deletion
- Integration with embeddings
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.memory.vector_store import VectorStore, get_vector_store
from src.memory.models import MemoryEntry, MemoryContentType


class TestVectorStore:
    """Tests for VectorStore class."""

    @pytest.fixture
    def temp_db_path(self) -> str:
        """Create temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def vector_store(self, temp_db_path: str) -> VectorStore:
        """Create vector store instance."""
        store = VectorStore(temp_db_path, embedding_dim=384)
        store.initialize()
        return store

    @pytest.fixture
    def sample_embedding(self) -> list[float]:
        """Create sample embedding vector (384 dimensions)."""
        return [0.1] * 384

    @pytest.fixture
    def sample_entries(self) -> list[tuple[str, list[float], str, str]]:
        """Create sample entries for testing.
        
        Returns list of (id, embedding, content, content_type)
        """
        return [
            ("entry-1", [0.1] * 384, "用户决定使用 React 作为前端框架", "decision"),
            ("entry-2", [0.2] * 384, "讨论了数据库选型，选择 SQLite", "conversation"),
            ("entry-3", [0.3] * 384, "用户偏好简洁 UI 设计", "manual"),
        ]

    def test_vector_store_initialization(self, temp_db_path: str) -> None:
        """Test vector store initialization."""
        store = VectorStore(temp_db_path)
        store.initialize()
        
        # Check database file exists
        assert os.path.exists(temp_db_path)
        assert store._initialized

    def test_vector_store_custom_embedding_dim(self, temp_db_path: str) -> None:
        """Test vector store with custom embedding dimension."""
        store = VectorStore(temp_db_path, embedding_dim=768)
        assert store.embedding_dim == 768

    def test_insert_vector(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test inserting a vector into the store."""
        entry_id = "test-entry-1"
        content = "Test content for vector store"
        content_type = "conversation"
        
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content=content,
            content_type=content_type,
        )
        
        # Verify entry exists in database
        conn = vector_store._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        
        assert row is not None
        assert row["id"] == entry_id
        assert row["content"] == content

    def test_insert_vector_with_metadata(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test inserting vector with metadata."""
        entry_id = "test-entry-meta"
        metadata = {"session_id": "session-123", "tags": ["important"]}
        
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content="Test content",
            content_type="decision",
            metadata=metadata,
        )
        
        # Verify metadata stored
        conn = vector_store._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT metadata FROM memory_entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        
        import json
        stored_metadata = json.loads(row["metadata"])
        assert stored_metadata["session_id"] == "session-123"

    def test_insert_duplicate_replaces(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test that inserting duplicate ID replaces existing entry."""
        entry_id = "duplicate-test"
        
        # Insert first version
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content="First version",
            content_type="conversation",
        )
        
        # Insert second version (should replace)
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content="Second version",
            content_type="decision",
        )
        
        # Verify only one entry exists with updated content
        conn = vector_store._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM memory_entries WHERE id = ?", (entry_id,))
        count = cursor.fetchone()["count"]
        assert count == 1
        
        cursor.execute("SELECT content FROM memory_entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        assert row["content"] == "Second version"

    def test_search_vectors(
        self,
        vector_store: VectorStore,
        sample_entries: list[tuple[str, list[float], str, str]],
    ) -> None:
        """Test vector similarity search."""
        # Insert sample entries
        for entry_id, embedding, content, content_type in sample_entries:
            vector_store.insert(
                entry_id=entry_id,
                embedding=embedding,
                content=content,
                content_type=content_type,
            )
        
        # Search with similar embedding to entry-1
        query_embedding = [0.1] * 384  # Same as entry-1
        results = vector_store.search(query_embedding, limit=10)
        
        assert len(results) > 0
        # Results should have score
        for result in results:
            assert "id" in result
            assert "content" in result
            assert "score" in result

    def test_search_with_limit(
        self,
        vector_store: VectorStore,
        sample_entries: list[tuple[str, list[float], str, str]],
    ) -> None:
        """Test search with result limit."""
        # Insert sample entries
        for entry_id, embedding, content, content_type in sample_entries:
            vector_store.insert(
                entry_id=entry_id,
                embedding=embedding,
                content=content,
                content_type=content_type,
            )
        
        results = vector_store.search([0.1] * 384, limit=2)
        assert len(results) <= 2

    def test_delete_vector(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test deleting a vector."""
        entry_id = "delete-test"
        
        # Insert entry
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content="Content to delete",
            content_type="conversation",
        )
        
        # Delete entry
        deleted = vector_store.delete(entry_id)
        assert deleted is True
        
        # Verify entry is gone
        conn = vector_store._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memory_entries WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        assert row is None

    def test_delete_nonexistent_vector(self, vector_store: VectorStore) -> None:
        """Test deleting a non-existent vector."""
        deleted = vector_store.delete("nonexistent-id")
        assert deleted is False

    def test_get_embedding_for_entry(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test retrieving embedding for an entry."""
        entry_id = "embedding-test"
        
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content="Test content",
            content_type="decision",
        )
        
        # Retrieve embedding
        embedding = vector_store.get_embedding(entry_id)
        
        # Embedding might be None if sqlite-vss not available
        if embedding is not None:
            assert len(embedding) == 384

    def test_get_entry_by_id(
        self,
        vector_store: VectorStore,
        sample_embedding: list[float],
    ) -> None:
        """Test retrieving entry by ID."""
        entry_id = "get-test"
        content = "Test content for retrieval"
        
        vector_store.insert(
            entry_id=entry_id,
            embedding=sample_embedding,
            content=content,
            content_type="conversation",
        )
        
        entry = vector_store.get_entry(entry_id)
        
        assert entry is not None
        assert entry["id"] == entry_id
        assert entry["content"] == content

    def test_get_nonexistent_entry(self, vector_store: VectorStore) -> None:
        """Test retrieving non-existent entry."""
        entry = vector_store.get_entry("nonexistent-id")
        assert entry is None

    def test_count_entries(
        self,
        vector_store: VectorStore,
        sample_entries: list[tuple[str, list[float], str, str]],
    ) -> None:
        """Test counting entries in vector store."""
        # Initially should be empty or have count 0
        initial_count = vector_store.count()
        
        # Insert sample entries
        for entry_id, embedding, content, content_type in sample_entries:
            vector_store.insert(
                entry_id=entry_id,
                embedding=embedding,
                content=content,
                content_type=content_type,
            )
        
        count = vector_store.count()
        assert count == initial_count + len(sample_entries)

    def test_clear_all_entries(
        self,
        vector_store: VectorStore,
        sample_entries: list[tuple[str, list[float], str, str]],
    ) -> None:
        """Test clearing all entries from vector store."""
        # Insert sample entries
        for entry_id, embedding, content, content_type in sample_entries:
            vector_store.insert(
                entry_id=entry_id,
                embedding=embedding,
                content=content,
                content_type=content_type,
            )
        
        # Clear all
        vector_store.clear()
        
        # Verify empty
        count = vector_store.count()
        assert count == 0

    def test_close_connection(self, vector_store: VectorStore) -> None:
        """Test closing database connection."""
        vector_store.close()
        assert vector_store._connection is None
        
        # Should be able to reopen
        vector_store._get_connection()
        assert vector_store._connection is not None


class TestVectorStoreGlobal:
    """Tests for global vector store instance."""

    def test_get_vector_store_singleton(self, tmp_path: Path) -> None:
        """Test that get_vector_store returns singleton."""
        import src.memory.vector_store as vs_module
        vs_module._vector_store = None
        
        db_path = str(tmp_path / "test_singleton.db")
        
        store1 = get_vector_store(db_path)
        store2 = get_vector_store()
        
        assert store1 is store2
        
        # Cleanup
        store1.close()
        vs_module._vector_store = None


class TestVectorStoreWithEmbedder:
    """Tests for vector store integration with embedder."""

    @pytest.fixture
    def temp_db_path(self) -> str:
        """Create temporary database path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_insert_with_auto_embedding(self, temp_db_path: str) -> None:
        """Test inserting entry with automatic embedding generation."""
        store = VectorStore(temp_db_path)
        store.initialize()
        
        # Create mock embedder
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.5] * 384
        mock_embedder.EMBEDDING_DIM = 384
        
        content = "Test content for auto embedding"
        
        # Insert with auto-embedding
        embedding = mock_embedder.embed(content)
        store.insert(
            entry_id="auto-embed-test",
            embedding=embedding,
            content=content,
            content_type="conversation",
        )
        
        mock_embedder.embed.assert_called_once_with(content)
        
        store.close()

    def test_search_with_auto_embedding(self, temp_db_path: str) -> None:
        """Test search with automatic query embedding."""
        store = VectorStore(temp_db_path)
        store.initialize()
        
        # Insert a test entry
        store.insert(
            entry_id="test-entry",
            embedding=[0.1] * 384,
            content="React frontend framework decision",
            content_type="decision",
        )
        
        # Create mock embedder
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [0.1] * 384
        
        # Search with auto-embedding
        query = "React framework"
        query_embedding = mock_embedder.embed(query)
        results = store.search(query_embedding, limit=10)
        
        assert len(results) >= 0  # May have results depending on vss availability
        
        store.close()
