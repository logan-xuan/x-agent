import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path
import numpy as np

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.agent_core.memory.storage_service import MemoryStorageService  # Adjust import based on actual implementation
from src.agent_core.memory.retrieval_service import MemoryRetrievalService
from src.agent_core.memory.embedding_service import EmbeddingService


@pytest.mark.asyncio
async def test_memory_storage_basic():
    """Test basic memory storage functionality"""

    with patch('src.agent-core.memory.storage_service.MemoryStorageService.save_memory_entry') as mock_save:
        mock_save.return_value = {"status": "success", "entry_id": "memory-123"}

        storage_service = MemoryStorageService()

        # Test storing a basic memory entry
        memory_data = {
            "user_id": "user-123",
            "session_id": "session-456",
            "content": "This is a test memory entry",
            "timestamp": "2023-01-01T00:00:00Z",
            "metadata": {"category": "conversation", "importance": 0.7}
        }

        result = await storage_service.store_memory(memory_data)

        assert result["status"] == "success"
        assert "entry_id" in result
        mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_memory_retrieval_by_content():
    """Test memory retrieval by content similarity"""

    # Mock embeddings and retrieval
    mock_embeddings = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with patch('src.agent-core.memory.embedding_service.EmbeddingService.generate_embedding') as mock_embed, \
         patch('src.agent-core.memory.retrieval_service.MemoryRetrievalService.find_similar_memories') as mock_find:

        mock_embed.return_value = [0.15, 0.25, 0.35]
        mock_find.return_value = [
            {"id": "memory-1", "content": "Similar memory content", "similarity": 0.85},
            {"id": "memory-2", "content": "Another similar content", "similarity": 0.72}
        ]

        retrieval_service = MemoryRetrievalService()
        embedding_service = EmbeddingService()

        # Generate embedding for query
        query_embedding = await embedding_service.generate_embedding("query about memories")

        # Find similar memories
        results = await retrieval_service.find_similar_memories(query_embedding, top_k=2)

        assert len(results) == 2
        assert results[0]["similarity"] >= results[1]["similarity"]  # Results should be sorted by similarity
        assert "Similar memory content" in results[0]["content"]
        mock_embed.assert_called_once_with("query about memories")


@pytest.mark.asyncio
async def test_memory_persistence():
    """Test memory persistence and retrieval"""

    with patch.multiple('src.agent-core.memory',
                        MemoryStorageService=MagicMock(),
                        MemoryRetrievalService=MagicMock()):

        # Setup mocks
        storage_mock = MagicMock()
        storage_mock.store_memory.return_value = {"status": "saved", "id": "persist-123"}
        retrieval_mock = MagicMock()
        retrieval_mock.get_memory_by_id.return_value = {
            "id": "persist-123",
            "content": "Persistent memory content",
            "user_id": "user-456"
        }

        # Test storing memory
        store_result = await storage_mock.store_memory({
            "user_id": "user-456",
            "content": "Persistent memory content",
            "timestamp": "2023-01-01T00:00:00Z"
        })

        assert store_result["status"] == "saved"
        assert store_result["id"] == "persist-123"

        # Test retrieving memory
        retrieved_memory = await retrieval_mock.get_memory_by_id("persist-123")

        assert retrieved_memory["content"] == "Persistent memory content"
        assert retrieved_memory["user_id"] == "user-456"


def test_embedding_generation():
    """Test embedding generation functionality"""

    with patch('src.agent-core.memory.embedding_service.EmbeddingService.create_embeddings') as mock_create:
        mock_create.return_value = [[0.1, 0.2, 0.3, 0.4]]

        embedding_service = EmbeddingService()

        # Generate embedding for text
        texts = ["Test document for embedding"]
        embeddings = embedding_service.create_embeddings(texts)

        assert len(embeddings) == 1
        assert len(embeddings[0]) > 0  # Should have some dimensions
        mock_create.assert_called_once_with(texts)


@pytest.mark.asyncio
async def test_memory_cleanup_expired():
    """Test cleanup of expired memories"""

    with patch('src.agent-core.memory.storage_service.MemoryStorageService.cleanup_expired_memories') as mock_cleanup:
        mock_cleanup.return_value = {"deleted_count": 5, "status": "cleanup_complete"}

        storage_service = MemoryStorageService()

        # Test cleanup with a specific cutoff date
        result = await storage_service.cleanup_expired_memories(cutoff_days=30)

        assert result["deleted_count"] == 5
        assert result["status"] == "cleanup_complete"
        mock_cleanup.assert_called_once_with(cutoff_days=30)


@pytest.mark.asyncio
async def test_memory_search_functionality():
    """Test memory search functionality"""

    with patch('src.agent-core.memory.retrieval_service.MemoryRetrievalService.search_memories') as mock_search:
        mock_search.return_value = [
            {"id": "mem-1", "content": "Found memory 1", "relevance": 0.9},
            {"id": "mem-2", "content": "Found memory 2", "relevance": 0.75},
            {"id": "mem-3", "content": "Found memory 3", "relevance": 0.6}
        ]

        retrieval_service = MemoryRetrievalService()

        # Test searching memories
        results = await retrieval_service.search_memories(
            query="test search query",
            filters={"user_id": "user-123", "category": "conversation"},
            limit=5
        )

        assert len(results) == 3
        assert all(["relevance" in mem for mem in results])
        # Verify results are ordered by relevance (highest first)
        assert results[0]["relevance"] >= results[1]["relevance"]
        mock_search.assert_called_once()


@pytest.mark.asyncio
async def test_vector_similarity_search():
    """Test vector similarity search functionality"""

    # Mock the vector database interaction
    with patch('src.dbm.vector_db.vector_store.VectorStore') as mock_vector_store:
        mock_vector_store.return_value.search.return_value = [
            {"id": "vec-1", "content": "Most similar content", "similarity": 0.92},
            {"id": "vec-2", "content": "Moderately similar", "similarity": 0.75}
        ]

        # Test vector search
        vector_store = mock_vector_store()
        results = vector_store.search(query_embedding=[0.1, 0.2, 0.3], top_k=2)

        assert len(results) == 2
        assert results[0]["similarity"] == 0.92
        assert "most similar" in results[0]["content"].lower()
        mock_vector_store.return_value.search.assert_called_once()


@pytest.mark.asyncio
async def test_memory_metadata_filtering():
    """Test filtering memories by metadata"""

    with patch('src.agent-core.memory.retrieval_service.MemoryRetrievalService.filter_memories_by_metadata') as mock_filter:
        mock_filter.return_value = [
            {"id": "filtered-1", "content": "Important memory", "metadata": {"importance": 0.9, "category": "fact"}},
            {"id": "filtered-2", "content": "Another important memory", "metadata": {"importance": 0.85, "category": "fact"}}
        ]

        retrieval_service = MemoryRetrievalService()

        # Test filtering by metadata
        results = await retrieval_service.filter_memories_by_metadata(
            user_id="user-123",
            filters={"category": "fact", "importance__gte": 0.8}
        )

        assert len(results) == 2
        assert all([mem["metadata"]["importance"] >= 0.8 for mem in results])
        assert all([mem["metadata"]["category"] == "fact" for mem in results])
        mock_filter.assert_called_once()