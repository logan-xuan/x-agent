"""Unit tests for ContextCompressor."""

import pytest
from unittest.mock import Mock, AsyncMock

from src.services.compression.compressor import ContextCompressor, CompressionResult
from src.services.compression.token_counter import TokenCounter


class TestContextCompressor:
    """Context compressor tests."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = Mock()
        self.mock_llm.complete = AsyncMock(return_value=Mock(content="Summary content"))
        self.mock_token_counter = Mock()
        self.mock_token_counter.count_messages = Mock(return_value=100)
        self.compressor = ContextCompressor(self.mock_llm, self.mock_token_counter)
    
    @pytest.mark.asyncio
    async def test_compress_basic(self):
        """Test basic compression."""
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(100)
        ]
        
        result = await self.compressor.compress(messages, retention_count=50)
        
        assert isinstance(result, CompressionResult)
        assert len(result.recent_messages) == 50
        assert len(result.archived_messages) == 50
        assert result.summary is not None
        assert len(result.compressed_messages) == 51  # Summary + 50 retained
    
    @pytest.mark.asyncio
    async def test_compress_less_than_retention(self):
        """Test compression with fewer messages than retention count."""
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(30)
        ]
        
        result = await self.compressor.compress(messages, retention_count=50)
        
        # No archiving, all messages retained
        assert len(result.archived_messages) == 0
        assert len(result.recent_messages) == 30
        assert result.summary == ""
    
    @pytest.mark.asyncio
    async def test_build_compressed_messages(self):
        """Test building compressed message list."""
        recent = [
            {"role": "user", "content": "Recent message 1"},
            {"role": "assistant", "content": "Response 1"},
        ]
        summary = "This is the summary"
        
        compressed = self.compressor._build_compressed_messages(recent, summary)
        
        assert len(compressed) == 3
        assert compressed[0]["role"] == "system"
        assert "历史对话摘要" in compressed[0]["content"]
        assert "This is the summary" in compressed[0]["content"]
        assert compressed[1] == recent[0]
        assert compressed[2] == recent[1]
    
    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """Test summary generation."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        summary = await self.compressor._generate_summary(messages)
        
        assert isinstance(summary, str)
        assert len(summary) > 0
    
    @pytest.mark.asyncio
    async def test_extract_key_facts(self):
        """Test key facts extraction."""
        messages = [
            {"role": "user", "content": "I like Python"},
            {"role": "assistant", "content": "Great choice!"},
        ]
        
        facts = await self.compressor._extract_key_facts(messages)
        
        assert isinstance(facts, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
