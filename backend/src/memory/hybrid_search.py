"""Hybrid search combining vector and text similarity.

This module provides:
- Text similarity search using TF-IDF/BM25
- Vector similarity search integration
- Hybrid search combining both methods
- Result ranking and pagination
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..utils.logger import get_logger
from .models import MemoryContentType, MemoryEntry

logger = get_logger(__name__)


@dataclass
class SearchOptions:
    """Options for search operations.
    
    Attributes:
        limit: Maximum number of results
        offset: Pagination offset
        content_type: Filter by content type
        min_score: Minimum score threshold
    """
    limit: int = 10
    offset: int = 0
    content_type: MemoryContentType | None = None
    min_score: float = 0.0


@dataclass
class SearchResult:
    """Result from hybrid search.
    
    Attributes:
        entry: The memory entry
        score: Combined score (0-1)
        vector_score: Vector similarity score
        text_score: Text similarity score
    """
    entry: MemoryEntry
    score: float = 0.0
    vector_score: float = 0.0
    text_score: float = 0.0
    
    def calculate_combined_score(self, vector_weight: float = 0.7, text_weight: float = 0.3) -> None:
        """Calculate combined score from vector and text scores.
        
        Args:
            vector_weight: Weight for vector score (default: 0.7)
            text_weight: Weight for text score (default: 0.3)
        """
        self.score = vector_weight * self.vector_score + text_weight * self.text_score


class TextSimilaritySearch:
    """Text-based similarity search using TF-IDF.
    
    Implements text similarity using term frequency-inverse document
    frequency (TF-IDF) scoring for keyword matching.
    """
    
    # Chinese and English stop words
    STOP_WORDS = {
        # Chinese
        "的", "是", "在", "了", "和", "与", "或", "有", "这", "那",
        "就", "也", "都", "而", "及", "着", "或", "但", "如", "等",
        # English
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "shall",
        "can", "need", "dare", "ought", "used", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below",
        "between", "under", "again", "further", "then", "once",
    }
    
    def __init__(self) -> None:
        """Initialize text search."""
        self._idf_cache: dict[str, float] = {}
        self._doc_count = 0
        
    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms.
        
        Handles both Chinese and English text.
        
        Args:
            text: Input text
            
        Returns:
            List of tokens
        """
        # Convert to lowercase
        text = text.lower()
        
        # Extract words (English words and Chinese characters)
        # English words
        english_words = re.findall(r'\b[a-z]+\b', text)
        
        # Chinese characters (each character as a token for simplicity)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        
        # Also extract Chinese words (2-4 character combinations)
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        
        tokens = english_words + chinese_chars + chinese_words
        
        # Remove stop words
        tokens = [t for t in tokens if t not in self.STOP_WORDS]
        
        return tokens
    
    def compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """Compute term frequency.
        
        Args:
            tokens: List of tokens
            
        Returns:
            Dictionary of term frequencies
        """
        if not tokens:
            return {}
            
        counter = Counter(tokens)
        total = len(tokens)
        
        return {term: count / total for term, count in counter.items()}
    
    def compute_idf(self, term: str, doc_count: int, doc_freq: int) -> float:
        """Compute inverse document frequency.
        
        Args:
            term: The term
            doc_count: Total number of documents
            doc_freq: Number of documents containing the term
            
        Returns:
            IDF score
        """
        if doc_freq == 0:
            return 0.0
            
        return math.log((doc_count + 1) / (doc_freq + 1)) + 1
    
    def compute_tf_idf(self, text: str) -> dict[str, float]:
        """Compute TF-IDF vector for text.
        
        Args:
            text: Input text
            
        Returns:
            Dictionary of TF-IDF scores
        """
        tokens = self.tokenize(text)
        tf = self.compute_tf(tokens)
        
        # For single document, use simplified IDF
        # In practice, IDF would be computed across all documents
        return {term: freq * (1 + math.log(1)) for term, freq in tf.items()}
    
    def cosine_similarity(self, vec1: dict[str, float], vec2: dict[str, float]) -> float:
        """Compute cosine similarity between two TF-IDF vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score (0-1)
        """
        if not vec1 or not vec2:
            return 0.0
        
        # Find common terms
        common_terms = set(vec1.keys()) & set(vec2.keys())
        
        if not common_terms:
            return 0.0
        
        # Compute dot product
        dot_product = sum(vec1[term] * vec2[term] for term in common_terms)
        
        # Compute magnitudes
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    def search(
        self,
        query: str,
        entries: list[MemoryEntry],
        options: SearchOptions | None = None,
    ) -> list[SearchResult]:
        """Search entries using text similarity.
        
        Args:
            query: Search query
            entries: List of memory entries to search
            options: Search options
            
        Returns:
            List of search results sorted by score
        """
        if not query or not entries:
            return []
        
        options = options or SearchOptions()
        
        # Compute query TF-IDF
        query_tfidf = self.compute_tf_idf(query)
        
        results: list[SearchResult] = []
        
        for entry in entries:
            # Apply content type filter
            if options.content_type and entry.content_type != options.content_type:
                continue
            
            # Compute entry TF-IDF
            entry_tfidf = self.compute_tf_idf(entry.content)
            
            # Compute similarity
            score = self.cosine_similarity(query_tfidf, entry_tfidf)
            
            # Apply minimum score filter
            if score < options.min_score:
                continue
            
            results.append(SearchResult(
                entry=entry,
                score=score,
                vector_score=0.0,
                text_score=score,
            ))
        
        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply pagination
        return results[options.offset:options.offset + options.limit]


class HybridSearch:
    """Hybrid search combining vector and text similarity.
    
    Implements the research decision of 0.7 vector + 0.3 text scoring
    for optimal search results.
    
    Note: When using MockEmbedder (no semantic meaning), automatically
    adjusts weights to 100% text search.
    """
    
    def __init__(
        self,
        vector_store: Any = None,
        embedder: Any = None,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> None:
        """Initialize hybrid search.
        
        Args:
            vector_store: Vector store instance for vector search
            embedder: Embedder instance for query embedding
            vector_weight: Weight for vector score (default: 0.7)
            text_weight: Weight for text score (default: 0.3)
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.text_search = TextSimilaritySearch()
        
        # Detect if using MockEmbedder and adjust weights accordingly
        self._using_mock_embedder = self._is_mock_embedder(embedder)
        
        if self._using_mock_embedder:
            # MockEmbedder has no semantic meaning, use 100% text search
            self.vector_weight = 0.0
            self.text_weight = 1.0
            logger.warning(
                "MockEmbedder detected, adjusting to 100% text search",
                extra={
                    "reason": "MockEmbedder generates random vectors without semantic meaning",
                    "vector_weight": 0.0,
                    "text_weight": 1.0,
                }
            )
        else:
            self.vector_weight = vector_weight
            self.text_weight = text_weight
        
        logger.info(
            "HybridSearch initialized",
            extra={
                "vector_weight": self.vector_weight,
                "text_weight": self.text_weight,
                "embedder_type": "MockEmbedder" if self._using_mock_embedder else "Real",
            }
        )
    
    def _is_mock_embedder(self, embedder: Any) -> bool:
        """Check if the embedder is a MockEmbedder.
        
        Args:
            embedder: Embedder instance to check
            
        Returns:
            True if embedder is MockEmbedder or mock-like
        """
        if embedder is None:
            return True
        
        # Check by class name
        class_name = type(embedder).__name__
        if "Mock" in class_name or "mock" in class_name.lower():
            return True
        
        # Check by module
        module_name = getattr(type(embedder), "__module__", "")
        if "mock" in module_name.lower():
            return True
        
        # Check if it has the MockEmbedder marker attribute
        if hasattr(embedder, "_is_mock"):
            return embedder._is_mock
        
        return False
    
    def _get_vector_results(
        self,
        query: str,
        limit: int,
    ) -> dict[str, dict[str, Any]]:
        """Get vector search results.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            Dictionary mapping entry ID to result info
        """
        if not self.vector_store or not self.embedder:
            return {}
        
        try:
            # Get query embedding
            query_embedding = self.embedder.embed(query)
            
            # Search vector store
            results = self.vector_store.search(query_embedding, limit=limit * 2)
            
            return {
                r["id"]: {
                    "content": r.get("content", ""),
                    "content_type": r.get("content_type", ""),
                    "vector_score": r.get("score", 0.0),
                }
                for r in results
            }
        except Exception as e:
            logger.error(
                "Vector search failed",
                extra={"error": str(e)}
            )
            return {}
    
    def search(
        self,
        query: str,
        entries: list[MemoryEntry],
        limit: int = 10,
        offset: int = 0,
        content_type: MemoryContentType | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Perform hybrid search.
        
        Combines vector similarity and text similarity scores.
        
        Args:
            query: Search query
            entries: List of memory entries to search
            limit: Maximum number of results
            offset: Pagination offset
            content_type: Filter by content type
            min_score: Minimum combined score threshold
            
        Returns:
            List of search results sorted by combined score
        """
        if not query:
            return []
        
        # Get vector search results
        vector_results = self._get_vector_results(query, limit)
        
        # Get text search results
        options = SearchOptions(
            limit=limit * 2,
            content_type=content_type,
            min_score=0.0,  # Don't filter at text level
        )
        text_results = self.text_search.search(query, entries, options)
        
        # Combine results
        combined: dict[str, SearchResult] = {}
        
        # Add vector results
        for entry_id, info in vector_results.items():
            # Find matching entry
            matching_entries = [e for e in entries if e.id == entry_id]
            if matching_entries:
                entry = matching_entries[0]
                
                # Apply content type filter
                if content_type and entry.content_type != content_type:
                    continue
                
                combined[entry_id] = SearchResult(
                    entry=entry,
                    vector_score=info["vector_score"],
                    text_score=0.0,
                )
        
        # Add/update with text scores
        for result in text_results:
            entry_id = result.entry.id
            
            if entry_id in combined:
                # Update text score
                combined[entry_id].text_score = result.text_score
            else:
                # New entry from text search
                combined[entry_id] = SearchResult(
                    entry=result.entry,
                    vector_score=0.0,
                    text_score=result.text_score,
                )
        
        # Calculate combined scores
        for result in combined.values():
            result.calculate_combined_score(
                vector_weight=self.vector_weight,
                text_weight=self.text_weight,
            )
        
        # Convert to list and sort
        results = list(combined.values())
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply minimum score filter
        if min_score > 0:
            results = [r for r in results if r.score >= min_score]
        
        # Apply pagination
        return results[offset:offset + limit]
    
    def find_similar(
        self,
        entry_id: str,
        entries: list[MemoryEntry],
        limit: int = 5,
    ) -> list[SearchResult]:
        """Find entries similar to a specific entry.
        
        Args:
            entry_id: ID of entry to find similar entries for
            entries: List of all memory entries
            limit: Maximum number of results
            
        Returns:
            List of similar entries
        """
        # Find the target entry
        target_entry = None
        for entry in entries:
            if entry.id == entry_id:
                target_entry = entry
                break
        
        if target_entry is None:
            return []
        
        # Use the entry's content as query
        return self.search(
            query=target_entry.content,
            entries=[e for e in entries if e.id != entry_id],  # Exclude self
            limit=limit,
        )


# Global hybrid search instance
_hybrid_search: HybridSearch | None = None


def get_hybrid_search(
    vector_store: Any = None,
    embedder: Any = None,
    vector_weight: float | None = None,
    text_weight: float | None = None,
) -> HybridSearch:
    """Get or create global hybrid search instance.
    
    Args:
        vector_store: Optional vector store instance
        embedder: Optional embedder instance
        vector_weight: Optional weight for vector score (overrides config)
        text_weight: Optional weight for text score (overrides config)
        
    Returns:
        HybridSearch instance
    """
    global _hybrid_search
    if _hybrid_search is None:
        # Try to load weights from config
        if vector_weight is None or text_weight is None:
            try:
                from ..config import get_config
                config = get_config()
                if vector_weight is None:
                    vector_weight = config.search.vector_weight
                if text_weight is None:
                    text_weight = config.search.text_weight
            except Exception:
                # Fallback to defaults
                vector_weight = vector_weight or 0.7
                text_weight = text_weight or 0.3
        
        _hybrid_search = HybridSearch(
            vector_store=vector_store,
            embedder=embedder,
            vector_weight=vector_weight,
            text_weight=text_weight,
        )
    return _hybrid_search


def init_hybrid_search(
    vector_store: Any,
    embedder: Any,
    vector_weight: float | None = None,
    text_weight: float | None = None,
) -> HybridSearch:
    """Initialize hybrid search with dependencies.
    
    Args:
        vector_store: Vector store instance
        embedder: Embedder instance
        vector_weight: Optional weight for vector score (overrides config)
        text_weight: Optional weight for text score (overrides config)
        
    Returns:
        Initialized HybridSearch instance
    """
    global _hybrid_search
    
    # Try to load weights from config
    if vector_weight is None or text_weight is None:
        try:
            from ..config import get_config
            config = get_config()
            if vector_weight is None:
                vector_weight = config.search.vector_weight
            if text_weight is None:
                text_weight = config.search.text_weight
        except Exception:
            # Fallback to defaults
            vector_weight = vector_weight or 0.7
            text_weight = text_weight or 0.3
    
    _hybrid_search = HybridSearch(
        vector_store=vector_store,
        embedder=embedder,
        vector_weight=vector_weight,
        text_weight=text_weight,
    )
    return _hybrid_search
