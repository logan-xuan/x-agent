"""Unit tests for hybrid search functionality.

Tests cover:
- Text similarity search (BM25/TF-IDF)
- Vector similarity search
- Hybrid search scoring (0.7 vector + 0.3 text)
- Result ranking and pagination
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.memory.models import MemoryEntry, MemoryContentType
from src.memory.hybrid_search import (
    HybridSearch,
    TextSimilaritySearch,
    SearchResult,
    SearchOptions,
)


class TestTextSimilaritySearch:
    """Tests for text-based similarity search."""

    @pytest.fixture
    def text_search(self) -> TextSimilaritySearch:
        """Create text search instance."""
        return TextSimilaritySearch()

    @pytest.fixture
    def sample_entries(self) -> list[MemoryEntry]:
        """Create sample memory entries for testing."""
        return [
            MemoryEntry(
                id="entry-1",
                content="用户决定使用 React 作为前端框架，因为团队熟悉 React 生态",
                content_type=MemoryContentType.DECISION,
                source_file="memory/2026-02-14.md",
                created_at=datetime(2026, 2, 14, 10, 30),
            ),
            MemoryEntry(
                id="entry-2",
                content="讨论了数据库选型，最终选择 SQLite 作为本地存储",
                content_type=MemoryContentType.CONVERSATION,
                source_file="memory/2026-02-14.md",
                created_at=datetime(2026, 2, 14, 14, 0),
            ),
            MemoryEntry(
                id="entry-3",
                content="用户偏好简洁的 UI 设计风格",
                content_type=MemoryContentType.MANUAL,
                source_file="memory/2026-02-13.md",
                created_at=datetime(2026, 2, 13, 9, 0),
            ),
        ]

    def test_text_search_initialization(self, text_search: TextSimilaritySearch) -> None:
        """Test text search initialization."""
        assert text_search is not None

    def test_compute_tf_idf(self, text_search: TextSimilaritySearch) -> None:
        """Test TF-IDF computation."""
        text = "React 前端框架 React 团队"
        tfidf = text_search.compute_tf_idf(text)
        
        assert isinstance(tfidf, dict)
        # React appears twice, should have higher weight
        assert "react" in tfidf
        assert tfidf["react"] > 0

    def test_text_search_ranking(
        self,
        text_search: TextSimilaritySearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test text search ranking."""
        query = "React 前端框架"
        results = text_search.search(query, sample_entries)
        
        assert len(results) > 0
        # First result should be most relevant (entry-1 about React)
        assert results[0].entry.id == "entry-1"
        assert results[0].text_score > 0

    def test_text_search_empty_query(
        self,
        text_search: TextSimilaritySearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test text search with empty query."""
        results = text_search.search("", sample_entries)
        assert results == []

    def test_text_search_empty_entries(self, text_search: TextSimilaritySearch) -> None:
        """Test text search with no entries."""
        results = text_search.search("React", [])
        assert results == []


class TestHybridSearch:
    """Tests for hybrid search functionality."""

    @pytest.fixture
    def mock_vector_store(self) -> MagicMock:
        """Create mock vector store."""
        mock = MagicMock()
        mock.search.return_value = [
            {
                "id": "entry-1",
                "content": "用户决定使用 React 作为前端框架",
                "content_type": "decision",
                "score": 0.85,
            },
            {
                "id": "entry-2",
                "content": "讨论了数据库选型",
                "content_type": "conversation",
                "score": 0.45,
            },
        ]
        return mock

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        """Create mock embedder."""
        mock = MagicMock()
        mock.embed.return_value = [0.1] * 384  # Mock embedding
        return mock

    @pytest.fixture
    def hybrid_search(self, mock_vector_store: MagicMock, mock_embedder: MagicMock) -> HybridSearch:
        """Create hybrid search instance with mocks."""
        return HybridSearch(
            vector_store=mock_vector_store,
            embedder=mock_embedder,
        )

    @pytest.fixture
    def sample_entries(self) -> list[MemoryEntry]:
        """Create sample memory entries."""
        return [
            MemoryEntry(
                id="entry-1",
                content="用户决定使用 React 作为前端框架",
                content_type=MemoryContentType.DECISION,
                source_file="memory/2026-02-14.md",
                created_at=datetime(2026, 2, 14, 10, 30),
            ),
            MemoryEntry(
                id="entry-2",
                content="讨论了数据库选型，选择 SQLite",
                content_type=MemoryContentType.CONVERSATION,
                source_file="memory/2026-02-14.md",
                created_at=datetime(2026, 2, 14, 14, 0),
            ),
            MemoryEntry(
                id="entry-3",
                content="用户偏好简洁 UI 设计",
                content_type=MemoryContentType.MANUAL,
                source_file="memory/2026-02-13.md",
                created_at=datetime(2026, 2, 13, 9, 0),
            ),
        ]

    def test_hybrid_search_initialization(self, hybrid_search: HybridSearch) -> None:
        """Test hybrid search initialization."""
        assert hybrid_search is not None
        assert hybrid_search.vector_weight == 0.7
        assert hybrid_search.text_weight == 0.3

    def test_hybrid_search_custom_weights(self, mock_vector_store: MagicMock, mock_embedder: MagicMock) -> None:
        """Test hybrid search with custom weights."""
        search = HybridSearch(
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            vector_weight=0.8,
            text_weight=0.2,
        )
        assert search.vector_weight == 0.8
        assert search.text_weight == 0.2

    def test_hybrid_search_combines_scores(
        self,
        hybrid_search: HybridSearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test that hybrid search combines vector and text scores."""
        results = hybrid_search.search("React 框架", sample_entries)
        
        assert len(results) > 0
        # Each result should have both scores
        for result in results:
            assert hasattr(result, "score")
            assert hasattr(result, "vector_score")
            assert hasattr(result, "text_score")
            # Combined score should follow weight ratio
            expected = 0.7 * result.vector_score + 0.3 * result.text_score
            assert abs(result.score - expected) < 0.001

    def test_hybrid_search_ranking(
        self,
        hybrid_search: HybridSearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test that results are ranked by combined score."""
        results = hybrid_search.search("React 框架", sample_entries)
        
        # Results should be sorted by score descending
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_hybrid_search_limit(
        self,
        hybrid_search: HybridSearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test search result limit."""
        results = hybrid_search.search("React", sample_entries, limit=2)
        assert len(results) <= 2

    def test_hybrid_search_content_type_filter(
        self,
        hybrid_search: HybridSearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test search with content type filter."""
        results = hybrid_search.search(
            "React",
            sample_entries,
            content_type=MemoryContentType.DECISION,
        )
        
        for result in results:
            assert result.entry.content_type == MemoryContentType.DECISION

    def test_hybrid_search_pagination(
        self,
        hybrid_search: HybridSearch,
        sample_entries: list[MemoryEntry],
    ) -> None:
        """Test search pagination."""
        # First page
        page1 = hybrid_search.search("React", sample_entries, limit=1, offset=0)
        # Second page
        page2 = hybrid_search.search("React", sample_entries, limit=1, offset=1)
        
        # Pages should have different results
        if len(page1) > 0 and len(page2) > 0:
            assert page1[0].entry.id != page2[0].entry.id

    def test_hybrid_search_empty_query(self, hybrid_search: HybridSearch, sample_entries: list[MemoryEntry]) -> None:
        """Test search with empty query."""
        results = hybrid_search.search("", sample_entries)
        assert results == []

    def test_hybrid_search_empty_entries(self, hybrid_search: HybridSearch) -> None:
        """Test search with no entries."""
        results = hybrid_search.search("React", [])
        assert results == []


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_search_result_creation(self) -> None:
        """Test search result creation."""
        entry = MemoryEntry(
            id="test-id",
            content="Test content",
            content_type=MemoryContentType.CONVERSATION,
            source_file="memory/test.md",
            created_at=datetime(2026, 2, 14),
        )
        
        result = SearchResult(
            entry=entry,
            score=0.85,
            vector_score=0.9,
            text_score=0.75,
        )
        
        assert result.entry.id == "test-id"
        assert result.score == 0.85
        assert result.vector_score == 0.9
        assert result.text_score == 0.75

    def test_search_result_score_calculation(self) -> None:
        """Test that combined score is calculated correctly."""
        entry = MemoryEntry(
            id="test-id",
            content="Test",
            content_type=MemoryContentType.CONVERSATION,
            source_file="test.md",
            created_at=datetime(2026, 2, 14),
        )
        
        # With default weights (0.7 vector + 0.3 text)
        result = SearchResult(
            entry=entry,
            score=0.0,  # Will be calculated
            vector_score=0.8,
            text_score=0.6,
        )
        
        result.calculate_combined_score(vector_weight=0.7, text_weight=0.3)
        expected = 0.7 * 0.8 + 0.3 * 0.6  # = 0.74
        assert abs(result.score - expected) < 0.001


class TestSearchOptions:
    """Tests for SearchOptions model."""

    def test_default_options(self) -> None:
        """Test default search options."""
        options = SearchOptions()
        assert options.limit == 10
        assert options.offset == 0
        assert options.content_type is None
        assert options.min_score == 0.0

    def test_custom_options(self) -> None:
        """Test custom search options."""
        options = SearchOptions(
            limit=20,
            offset=5,
            content_type=MemoryContentType.DECISION,
            min_score=0.5,
        )
        assert options.limit == 20
        assert options.offset == 5
        assert options.content_type == MemoryContentType.DECISION
        assert options.min_score == 0.5
