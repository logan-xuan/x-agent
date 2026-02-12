"""
Memory retrieval service for the x-agent2 AI assistant system.

This module handles the retrieval and search of memory entries using vector embeddings
and semantic search capabilities.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
import numpy as np
from scipy.spatial.distance import cosine
import asyncio
from enum import Enum

from src.db.models.memory_entry import MemoryEntry
from src.agent_core.memory.storage_service import MemoryStorageService, MemoryType
from src.agent_core.config.config_service import get_config


class RetrievalMethod(Enum):
    """Methods for retrieving memories."""
    EXACT_MATCH = "exact_match"
    SEMANTIC_SEARCH = "semantic_search"
    KEYWORD_SEARCH = "keyword_search"
    HYBRID = "hybrid"
    CONTEXTUAL = "contextual"


class MemoryRetrievalService:
    """Service class for retrieving and searching memory entries."""

    def __init__(self, storage_service: Optional[MemoryStorageService] = None):
        self.storage_service = storage_service or MemoryStorageService()
        self.config = get_config()

        # Initialize embedding dimensions based on configuration
        self.embedding_dim = 1536  # Default for OpenAI ada-002

        # In-memory cache for embeddings to improve performance
        self._embedding_cache: Dict[str, List[float]] = {}

    async def retrieve_by_similarity(
        self,
        user_id: str,
        query: str,
        top_k: int = 10,
        memory_types: Optional[List[MemoryType]] = None,
        context_filter: Optional[Dict[str, Any]] = None
    ) -> List[MemoryEntry]:
        """
        Retrieve memories similar to the query using semantic similarity.

        Args:
            user_id: ID of the user whose memories to search
            query: Query text to find similar memories
            top_k: Number of top results to return
            memory_types: Optional list of memory types to search within
            context_filter: Optional context filters

        Returns:
            List of memory entries ranked by similarity
        """
        # Get embeddings for the query
        query_embedding = await self._get_embedding(query)

        # Get all relevant memories for the user
        all_memories = await self.storage_service.retrieve_memories_by_type(
            user_id,
            memory_types[0] if memory_types else MemoryType.SEMANTIC,  # Default to semantic
            limit=1000  # Limit to avoid loading too much
        ) if memory_types else await MemoryEntry.get_by_user(user_id, limit=1000)

        # Filter by memory types if specified
        if memory_types:
            type_values = [mt.value for mt in memory_types]
            all_memories = [m for m in all_memories if m.memory_type in type_values]

        # Filter by context if specified
        if context_filter:
            all_memories = [
                m for m in all_memories
                if all(str(context_filter[k]) in str(m.context.get(k, "")) for k in context_filter)
            ]

        # Calculate similarity scores
        scored_memories = []
        for memory in all_memories:
            # Get embedding for memory content
            memory_embedding = await self._get_embedding(memory.content)

            # Calculate cosine similarity
            similarity = 1 - cosine(query_embedding, memory_embedding)

            scored_memories.append((memory, similarity))

        # Sort by similarity score in descending order
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        # Return top_k results
        return [memory for memory, score in scored_memories[:top_k]]

    async def retrieve_by_keywords(
        self,
        user_id: str,
        keywords: List[str],
        memory_types: Optional[List[MemoryType]] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[MemoryEntry]:
        """
        Retrieve memories based on keyword matching.

        Args:
            user_id: ID of the user whose memories to search
            keywords: List of keywords to search for
            memory_types: Optional list of memory types to search within
            tags: Optional list of tags to filter by
            limit: Maximum number of results to return

        Returns:
            List of matching memory entries
        """
        # Build search query from keywords
        query = " ".join(keywords)

        # Use the storage service's search functionality
        memories = await self.storage_service.search_memories(
            user_id,
            query,
            memory_types,
            tags,
            limit
        )

        # Additional keyword matching for more precise results
        keyword_matched = []
        keywords_lower = [kw.lower() for kw in keywords]

        for memory in memories:
            content_lower = memory.content.lower()
            if any(keyword in content_lower for keyword in keywords_lower):
                keyword_matched.append(memory)

        return keyword_matched[:limit]

    async def retrieve_contextual(
        self,
        user_id: str,
        current_context: Dict[str, Any],
        session_id: Optional[str] = None,
        time_range: Optional[timedelta] = None,
        top_k: int = 10
    ) -> List[MemoryEntry]:
        """
        Retrieve memories relevant to the current context.

        Args:
            user_id: ID of the user whose memories to search
            current_context: Current context information
            session_id: Optional session ID to narrow search
            time_range: Optional time range to limit search
            top_k: Number of top results to return

        Returns:
            List of contextually relevant memory entries
        """
        # Build a query from the current context
        context_query_parts = []

        for key, value in current_context.items():
            if isinstance(value, str):
                context_query_parts.append(value)
            elif isinstance(value, (list, tuple)):
                context_query_parts.extend([str(item) for item in value])
            else:
                context_query_parts.append(str(value))

        context_query = " ".join(context_query_parts)

        # Get memories by type and context
        type_filters = None
        if current_context.get("intent") == "factual_recall":
            type_filters = [MemoryType.SEMANTIC]
        elif current_context.get("intent") == "procedural_task":
            type_filters = [MemoryType.PROCEDURAL]
        elif current_context.get("intent") == "personal_fact":
            type_filters = [MemoryType.EPISODIC]

        # Adjust the time range filter based on context
        memories = await MemoryEntry.get_by_user(user_id, limit=200)

        # Filter by session if provided
        if session_id:
            memories = [m for m in memories if m.metadata.get("session_id") == session_id]

        # Filter by time range if provided
        if time_range:
            cutoff_time = datetime.utcnow() - time_range
            memories = [m for m in memories if m.created_at > cutoff_time]

        # Filter by type if specified
        if type_filters:
            type_values = [tf.value for tf in type_filters]
            memories = [m for m in memories if m.memory_type in type_values]

        # Calculate contextual relevance using embeddings
        if context_query.strip():
            query_embedding = await self._get_embedding(context_query)

            scored_memories = []
            for memory in memories:
                memory_embedding = await self._get_embedding(memory.content)
                similarity = 1 - cosine(query_embedding, memory_embedding)
                scored_memories.append((memory, similarity))

            # Sort by relevance
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            return [memory for memory, score in scored_memories[:top_k]]
        else:
            # If no context query, return recent memories
            memories.sort(key=lambda x: x.last_accessed_at or x.created_at, reverse=True)
            return memories[:top_k]

    async def retrieve_working_memory(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        max_age: timedelta = timedelta(minutes=30)
    ) -> List[MemoryEntry]:
        """
        Retrieve working memory (short-term) for the current session.

        Args:
            user_id: ID of the user whose memories to retrieve
            session_id: Optional session ID to limit to current session
            max_age: Maximum age of memories to retrieve

        Returns:
            List of working memory entries
        """
        cutoff_time = datetime.utcnow() - max_age

        # Get working memories
        working_memories = await self.storage_service.retrieve_memories_by_type(
            user_id,
            MemoryType.WORKING
        )

        # Filter by session if provided
        if session_id:
            working_memories = [
                m for m in working_memories
                if m.metadata.get("session_id") == session_id
            ]

        # Filter by age
        working_memories = [
            m for m in working_memories
            if m.created_at > cutoff_time
        ]

        # Sort by recency
        working_memories.sort(key=lambda x: x.created_at, reverse=True)

        return working_memories

    async def retrieve_episodic_memory(
        self,
        user_id: str,
        date_range: Optional[tuple[datetime, datetime]] = None,
        tags: Optional[List[str]] = None
    ) -> List[MemoryEntry]:
        """
        Retrieve episodic memories (personal experiences).

        Args:
            user_id: ID of the user whose memories to retrieve
            date_range: Optional date range to limit results
            tags: Optional tags to filter by

        Returns:
            List of episodic memory entries
        """
        # Get episodic memories
        episodic_memories = await self.storage_service.retrieve_memories_by_type(
            user_id,
            MemoryType.EPISODIC
        )

        # Filter by date range if provided
        if date_range:
            start_date, end_date = date_range
            episodic_memories = [
                m for m in episodic_memories
                if start_date <= m.created_at <= end_date
            ]

        # Filter by tags if provided
        if tags:
            episodic_memories = [
                m for m in episodic_memories
                if any(tag in m.tags for tag in tags)
            ]

        # Sort by date
        episodic_memories.sort(key=lambda x: x.created_at, reverse=True)

        return episodic_memories

    async def get_memory_summary(
        self,
        user_id: str,
        time_range: timedelta = timedelta(days=7)
    ) -> Dict[str, Any]:
        """
        Get a summary of the user's memories.

        Args:
            user_id: ID of the user whose memory summary to get
            time_range: Time range to summarize

        Returns:
            Dictionary with memory summary
        """
        cutoff_time = datetime.utcnow() - time_range

        # Get all memories for the user in the time range
        all_memories = await MemoryEntry.get_by_user(user_id, limit=10000)
        recent_memories = [m for m in all_memories if m.created_at > cutoff_time]

        # Calculate statistics
        memory_types_count = {}
        total_tokens = 0
        tags_used = set()

        for memory in recent_memories:
            # Count memory types
            if memory.memory_type not in memory_types_count:
                memory_types_count[memory.memory_type] = 0
            memory_types_count[memory.memory_type] += 1

            # Count tokens approximately
            total_tokens += len(memory.content.split())

            # Collect tags
            tags_used.update(memory.tags)

        return {
            "total_memories": len(recent_memories),
            "memory_types_distribution": memory_types_count,
            "total_tokens": total_tokens,
            "unique_tags_count": len(tags_used),
            "tags_used": list(tags_used)[:20],  # First 20 tags
            "date_range": {
                "start": cutoff_time.isoformat(),
                "end": datetime.utcnow().isoformat()
            }
        }

    async def find_related_memories(
        self,
        memory_id: str,
        user_id: str,
        top_k: int = 5
    ) -> List[MemoryEntry]:
        """
        Find memories related to a specific memory.

        Args:
            memory_id: ID of the reference memory
            user_id: ID of the user whose memories to search
            top_k: Number of related memories to return

        Returns:
            List of related memory entries
        """
        # Get the reference memory
        reference_memory = await self.storage_service.retrieve_memory(memory_id, user_id)
        if not reference_memory:
            return []

        # Get embedding for the reference memory
        reference_embedding = await self._get_embedding(reference_memory.content)

        # Get other memories for the user
        all_memories = await MemoryEntry.get_by_user(user_id, limit=1000)
        other_memories = [m for m in all_memories if m.id != memory_id]

        # Calculate similarity with the reference memory
        scored_memories = []
        for memory in other_memories:
            memory_embedding = await self._get_embedding(memory.content)
            similarity = 1 - cosine(reference_embedding, memory_embedding)
            scored_memories.append((memory, similarity))

        # Sort by similarity and return top_k
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        return [memory for memory, score in scored_memories[:top_k]]

    async def _get_embedding(self, text: str) -> List[float]:
        """
        Get embedding for text. Uses cached values when available.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as a list of floats
        """
        # Use cache if available
        text_hash = hash(text)
        if text_hash in self._embedding_cache:
            return self._embedding_cache[text_hash]

        # Generate a deterministic embedding based on the text content
        # In a real implementation, this would call an embedding API
        embedding = self._generate_deterministic_embedding(text)

        # Cache the embedding (with size limit to prevent memory issues)
        if len(self._embedding_cache) < 10000:
            self._embedding_cache[text_hash] = embedding

        return embedding

    def _generate_deterministic_embedding(self, text: str) -> List[float]:
        """
        Generate a deterministic embedding for text (mock implementation).
        In a real implementation, this would call an embedding API like OpenAI.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as a list of floats
        """
        # Create a deterministic pseudo-embedding based on text content
        # This is a simplified approach for demonstration
        embedding = [0.0] * self.embedding_dim

        # Hash the text to get a consistent value
        text_hash = hash(text) % (2**32)

        # Distribute the hash value across the embedding vector
        for i in range(min(len(str(text_hash)), self.embedding_dim)):
            char_val = ord(text[i % len(text)]) if i < len(text) else 0
            embedding[i] = ((text_hash >> (i % 32)) ^ char_val) / (1 << 16)

        # Normalize the embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding

    async def clear_cache(self):
        """Clear the embedding cache."""
        self._embedding_cache.clear()


class MemorySearchOptimizer:
    """Optimizes memory search performance."""

    def __init__(self, retrieval_service: MemoryRetrievalService):
        self.retrieval_service = retrieval_service
        self.query_cache: Dict[str, List[MemoryEntry]] = {}
        self.cache_size_limit = 100

    async def search_with_optimization(
        self,
        user_id: str,
        query: str,
        method: RetrievalMethod = RetrievalMethod.HYBRID,
        **kwargs
    ) -> List[MemoryEntry]:
        """
        Perform optimized memory search using caching and hybrid methods.

        Args:
            user_id: ID of the user whose memories to search
            query: Search query
            method: Retrieval method to use
            **kwargs: Additional parameters for the search

        Returns:
            List of relevant memory entries
        """
        # Create cache key
        cache_key = f"{user_id}:{query}:{method.value}:{hash(str(kwargs))}"

        # Check cache first
        if cache_key in self.query_cache:
            return self.query_cache[cache_key]

        # Perform search based on method
        if method == RetrievalMethod.SEMANTIC_SEARCH:
            results = await self.retrieval_service.retrieve_by_similarity(
                user_id, query, **kwargs
            )
        elif method == RetrievalMethod.KEYWORD_SEARCH:
            # Extract keywords from query
            keywords = query.lower().split()
            results = await self.retrieval_service.retrieve_by_keywords(
                user_id, keywords, **kwargs
            )
        elif method == RetrievalMethod.HYBRID:
            # Perform both semantic and keyword search, then combine
            semantic_results = await self.retrieval_service.retrieve_by_similarity(
                user_id, query, top_k=kwargs.get('top_k', 10)
            )

            keywords = query.lower().split()
            keyword_results = await self.retrieval_service.retrieve_by_keywords(
                user_id, keywords, limit=kwargs.get('top_k', 10)
            )

            # Combine results, prioritizing semantic matches but including keyword matches
            combined_results = list(set(semantic_results + keyword_results))

            # Re-rank based on a combination of factors
            results = self._rerank_results(combined_results, query)
        elif method == RetrievalMethod.CONTEXTUAL:
            # Use contextual retrieval
            results = await self.retrieval_service.retrieve_contextual(
                user_id, kwargs.get('current_context', {}), **kwargs
            )
        else:  # EXACT_MATCH
            # Perform exact match search
            results = await self.retrieval_service.retrieve_by_keywords(
                user_id, [query], **kwargs
            )

        # Cache the results (with size limit)
        if len(self.query_cache) >= self.cache_size_limit:
            # Remove oldest cached item
            oldest_key = next(iter(self.query_cache))
            del self.query_cache[oldest_key]

        self.query_cache[cache_key] = results

        return results

    def _rerank_results(self, results: List[MemoryEntry], query: str) -> List[MemoryEntry]:
        """Re-rank search results based on multiple factors."""
        # In a real implementation, this would implement a more sophisticated ranking algorithm
        # For now, just return the results in their original order
        return results

    def clear_cache(self):
        """Clear the search result cache."""
        self.query_cache.clear()


# Global memory retrieval service instance
memory_retrieval_service = MemoryRetrievalService()
memory_search_optimizer = MemorySearchOptimizer(memory_retrieval_service)


# Convenience functions
async def retrieve_by_similarity(
    user_id: str,
    query: str,
    top_k: int = 10,
    memory_types: Optional[List[MemoryType]] = None
) -> List[MemoryEntry]:
    """Retrieve memories by semantic similarity."""
    return await memory_retrieval_service.retrieve_by_similarity(
        user_id, query, top_k, memory_types
    )


async def retrieve_by_keywords(
    user_id: str,
    keywords: List[str],
    memory_types: Optional[List[MemoryType]] = None
) -> List[MemoryEntry]:
    """Retrieve memories by keyword matching."""
    return await memory_retrieval_service.retrieve_by_keywords(
        user_id, keywords, memory_types
    )


async def retrieve_contextual(
    user_id: str,
    current_context: Dict[str, Any],
    top_k: int = 10
) -> List[MemoryEntry]:
    """Retrieve contextually relevant memories."""
    return await memory_retrieval_service.retrieve_contextual(
        user_id, current_context, top_k=top_k
    )