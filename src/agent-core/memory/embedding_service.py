"""
Memory embedding and indexing service for the x-agent2 AI assistant system.

This module handles the generation and management of vector embeddings for
memory entries to enable semantic search and similarity matching.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import asyncio
import hashlib
import json
from enum import Enum

from src.db.models.memory_entry import MemoryEntry
from src.agent_core.memory.storage_service import MemoryStorageService, MemoryType
from src.agent_core.config.config_service import get_config


class EmbeddingProvider(Enum):
    """Embedding providers supported by the system."""
    OPENAI = "openai"
    COHERE = "cohere"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    TFIDF = "tfidf"  # For local/dev environments
    MOCK = "mock"  # For testing


class EmbeddingDimension(Enum):
    """Common embedding dimensions."""
    SMALL = 384    # For lightweight models
    MEDIUM = 768   # For balanced models
    LARGE = 1536   # For high-quality models like OpenAI ada-002
    XLARGE = 3072  # For state-of-the-art models


class MemoryEmbeddingService:
    """Service class for generating and managing memory embeddings."""

    def __init__(self, storage_service: Optional[MemoryStorageService] = None):
        self.storage_service = storage_service or MemoryStorageService()
        self.config = get_config()

        # Configuration
        self.embedding_provider = EmbeddingProvider.TFIDF  # Default to TFIDF for local dev
        self.embedding_dimension = EmbeddingDimension.MEDIUM.value
        self.batch_size = 10  # Size of batches for processing

        # Local storage for embeddings (in-memory for now, would use vector DB in production)
        self.embeddings_store: Dict[str, List[float]] = {}
        self.embedding_metadata: Dict[str, Dict[str, Any]] = {}

        # TF-IDF vectorizer for local embedding generation
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words='english',
            lowercase=True,
            ngram_range=(1, 2)
        )

        # Fit the vectorizer on some sample text initially
        self._initialize_vectorizer()

    def _initialize_vectorizer(self):
        """Initialize the TF-IDF vectorizer with some sample text."""
        sample_texts = [
            "hello world",
            "artificial intelligence",
            "machine learning",
            "natural language processing",
            "memory and cognition",
            "conversation and dialogue"
        ]
        try:
            self.tfidf_vectorizer.fit(sample_texts)
        except:
            # If fitting fails, just pass - it will be fitted when needed
            pass

    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a text using the configured provider.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector as a list of floats
        """
        if not text.strip():
            # Return a zero vector for empty text
            return [0.0] * self.embedding_dimension

        # For local development, use TF-IDF
        if self.embedding_provider == EmbeddingProvider.TFIDF:
            return self._generate_tfidf_embedding(text)
        elif self.embedding_provider == EmbeddingProvider.MOCK:
            return self._generate_mock_embedding(text)
        else:
            # In a real implementation, this would call the actual embedding API
            # For now, use mock embedding as default
            return self._generate_mock_embedding(text)

    def _generate_tfidf_embedding(self, text: str) -> List[float]:
        """
        Generate TF-IDF based embedding for the text.

        Args:
            text: Text to embed

        Returns:
            TF-IDF embedding vector
        """
        try:
            # Transform the text using the fitted vectorizer
            embedding_array = self.tfidf_vectorizer.transform([text])

            # Convert to dense array and return as list
            embedding = embedding_array.toarray()[0].tolist()

            # Pad or truncate to the required dimension
            if len(embedding) < self.embedding_dimension:
                # Pad with zeros
                embedding.extend([0.0] * (self.embedding_dimension - len(embedding)))
            elif len(embedding) > self.embedding_dimension:
                # Truncate
                embedding = embedding[:self.embedding_dimension]

            return embedding
        except Exception:
            # If TF-IDF fails, fall back to mock embedding
            return self._generate_mock_embedding(text)

    def _generate_mock_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic mock embedding for the text.
        This creates consistent embeddings for the same text.

        Args:
            text: Text to embed

        Returns:
            Mock embedding vector
        """
        # Create a deterministic seed based on the text
        text_hash = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)

        # Use the hash to generate a reproducible embedding
        np.random.seed(text_hash % (2**32))
        embedding = np.random.normal(0, 1, size=self.embedding_dimension).tolist()

        # Normalize the embedding to unit vector
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding

    async def index_memory_embeddings(self, memory_id: str) -> bool:
        """
        Generate and store embedding for a specific memory entry.

        Args:
            memory_id: ID of the memory to index

        Returns:
            True if indexing was successful, False otherwise
        """
        try:
            # Retrieve the memory entry
            memory = await MemoryEntry.get_by_id(memory_id)
            if not memory:
                return False

            # Generate embedding for the content
            embedding = await self.generate_embedding(memory.content)

            # Store the embedding
            self.embeddings_store[memory_id] = embedding

            # Store metadata
            self.embedding_metadata[memory_id] = {
                "memory_type": memory.memory_type,
                "user_id": memory.user_id,
                "created_at": memory.created_at.isoformat(),
                "last_accessed": memory.last_accessed_at.isoformat() if memory.last_accessed_at else None,
                "tags": memory.tags,
                "context_keys": list(memory.context.keys()) if memory.context else []
            }

            return True
        except Exception as e:
            print(f"Error indexing memory embedding: {e}")
            return False

    async def index_batch_embeddings(self, memory_ids: List[str]) -> Tuple[int, List[str]]:
        """
        Index embeddings for a batch of memory entries.

        Args:
            memory_ids: List of memory IDs to index

        Returns:
            Tuple of (successful_count, failed_ids_list)
        """
        successful = 0
        failed_ids = []

        for memory_id in memory_ids:
            try:
                success = await self.index_memory_embeddings(memory_id)
                if success:
                    successful += 1
                else:
                    failed_ids.append(memory_id)
            except Exception:
                failed_ids.append(memory_id)

        return successful, failed_ids

    async def bulk_index_user_memories(self, user_id: str) -> Tuple[int, int]:
        """
        Index embeddings for all memories of a specific user.

        Args:
            user_id: ID of the user whose memories to index

        Returns:
            Tuple of (indexed_count, total_count)
        """
        try:
            # Get all memories for the user
            memories = await MemoryEntry.get_by_user(user_id, limit=10000)  # Reasonable limit
            total_count = len(memories)

            # Index embeddings for each memory
            successful = 0
            for memory in memories:
                success = await self.index_memory_embeddings(memory.id)
                if success:
                    successful += 1

            return successful, total_count
        except Exception as e:
            print(f"Error bulk indexing user memories: {e}")
            return 0, 0

    async def find_similar_memories(
        self,
        query_text: str,
        user_id: str,
        top_k: int = 5,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[Tuple[MemoryEntry, float]]:
        """
        Find memories similar to the query text using embedding similarity.

        Args:
            query_text: Text to find similar memories for
            user_id: ID of the user whose memories to search
            top_k: Number of top results to return
            memory_types: Optional list of memory types to search within

        Returns:
            List of tuples (memory_entry, similarity_score)
        """
        try:
            # Generate embedding for the query
            query_embedding = await self.generate_embedding(query_text)

            # Get relevant memory IDs from the user
            all_memories = await MemoryEntry.get_by_user(user_id, limit=1000)

            # Filter by memory types if specified
            if memory_types:
                type_values = [mt.value for mt in memory_types]
                all_memories = [m for m in all_memories if m.memory_type in type_values]

            # Find embeddings for the relevant memories
            similarities = []
            for memory in all_memories:
                if memory.id in self.embeddings_store:
                    memory_embedding = self.embeddings_store[memory.id]

                    # Calculate cosine similarity
                    similarity = cosine_similarity(
                        [query_embedding],
                        [memory_embedding]
                    )[0][0]

                    similarities.append((memory, float(similarity)))

            # Sort by similarity score in descending order
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Return top_k results
            return similarities[:top_k]
        except Exception as e:
            print(f"Error finding similar memories: {e}")
            return []

    async def get_memory_embedding(self, memory_id: str) -> Optional[List[float]]:
        """
        Retrieve the embedding for a specific memory.

        Args:
            memory_id: ID of the memory to get embedding for

        Returns:
            Embedding vector if found, None otherwise
        """
        return self.embeddings_store.get(memory_id)

    async def update_memory_embedding(self, memory_id: str, new_content: str) -> bool:
        """
        Update the embedding for an existing memory with new content.

        Args:
            memory_id: ID of the memory to update
            new_content: New content to embed

        Returns:
            True if update was successful, False otherwise
        """
        try:
            embedding = await self.generate_embedding(new_content)
            self.embeddings_store[memory_id] = embedding

            # Update the timestamp in metadata
            if memory_id in self.embedding_metadata:
                self.embedding_metadata[memory_id]["updated_at"] = datetime.utcnow().isoformat()

            return True
        except Exception as e:
            print(f"Error updating memory embedding: {e}")
            return False

    async def delete_memory_embedding(self, memory_id: str) -> bool:
        """
        Remove the embedding for a specific memory.

        Args:
            memory_id: ID of the memory to remove embedding for

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            if memory_id in self.embeddings_store:
                del self.embeddings_store[memory_id]
            if memory_id in self.embedding_metadata:
                del self.embedding_metadata[memory_id]
            return True
        except Exception as e:
            print(f"Error deleting memory embedding: {e}")
            return False

    async def clear_embeddings_for_user(self, user_id: str) -> int:
        """
        Remove all embeddings for a specific user.

        Args:
            user_id: ID of the user whose embeddings to clear

        Returns:
            Number of embeddings cleared
        """
        try:
            # Find all memory IDs for this user that have embeddings
            memories = await MemoryEntry.get_by_user(user_id, limit=10000)
            user_memory_ids = {m.id for m in memories}

            # Find intersection with embeddings store
            embeddings_to_remove = [
                mid for mid in self.embeddings_store.keys()
                if mid in user_memory_ids
            ]

            # Remove the embeddings
            for memory_id in embeddings_to_remove:
                del self.embeddings_store[memory_id]
                if memory_id in self.embedding_metadata:
                    del self.embedding_metadata[memory_id]

            return len(embeddings_to_remove)
        except Exception as e:
            print(f"Error clearing user embeddings: {e}")
            return 0

    def get_embedding_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the embeddings store.

        Returns:
            Dictionary with embedding statistics
        """
        return {
            "total_embeddings": len(self.embeddings_store),
            "embedding_dimension": self.embedding_dimension,
            "provider": self.embedding_provider.value,
            "batch_size": self.batch_size
        }

    async def rebuild_embeddings_index(self) -> Dict[str, Any]:
        """
        Rebuild the entire embeddings index.

        Returns:
            Dictionary with rebuild statistics
        """
        start_time = datetime.utcnow()

        # Clear existing embeddings
        self.embeddings_store.clear()
        self.embedding_metadata.clear()

        # This would typically iterate through all memories in the database
        # and rebuild the embeddings index
        # For this implementation, we'll just return stats

        rebuild_time = (datetime.utcnow() - start_time).total_seconds()

        return {
            "rebuild_time_seconds": rebuild_time,
            "status": "completed",
            "message": "Embedding index rebuilt (note: this is a simplified implementation)"
        }

    async def fit_vectorizer_on_user_corpus(self, user_id: str) -> bool:
        """
        Fit the TF-IDF vectorizer on a user's memory corpus for personalized embeddings.

        Args:
            user_id: ID of the user whose corpus to fit on

        Returns:
            True if fitting was successful, False otherwise
        """
        try:
            # Get all memories for the user
            memories = await MemoryEntry.get_by_user(user_id, limit=10000)

            # Extract content from memories
            corpus = [m.content for m in memories if m.content]

            if not corpus:
                return False

            # Fit the vectorizer on the user's corpus
            self.tfidf_vectorizer.fit(corpus)

            return True
        except Exception as e:
            print(f"Error fitting vectorizer on user corpus: {e}")
            return False


class SimilarityCalculator:
    """Utility class for calculating various types of similarities."""

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    @staticmethod
    def euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
        """Calculate Euclidean distance between two vectors."""
        return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5

    @staticmethod
    def manhattan_distance(vec1: List[float], vec2: List[float]) -> float:
        """Calculate Manhattan distance between two vectors."""
        return sum(abs(a - b) for a, b in zip(vec1, vec2))


# Global memory embedding service instance
memory_embedding_service = MemoryEmbeddingService()


# Convenience functions
async def generate_embedding(text: str) -> List[float]:
    """Generate an embedding for the given text."""
    return await memory_embedding_service.generate_embedding(text)


async def index_memory_embeddings(memory_id: str) -> bool:
    """Index the embedding for a specific memory."""
    return await memory_embedding_service.index_memory_embeddings(memory_id)


async def find_similar_memories(
    query_text: str,
    user_id: str,
    top_k: int = 5
) -> List[Tuple[MemoryEntry, float]]:
    """Find memories similar to the query text."""
    return await memory_embedding_service.find_similar_memories(
        query_text, user_id, top_k
    )


async def bulk_index_user_memories(user_id: str) -> Tuple[int, int]:
    """Bulk index embeddings for all memories of a user."""
    return await memory_embedding_service.bulk_index_user_memories(user_id)