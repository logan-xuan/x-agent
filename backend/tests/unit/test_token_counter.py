"""Unit tests for TokenCounter."""

import pytest
from src.services.compression.token_counter import TokenCounter


class TestTokenCounter:
    """Token counter tests."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.counter = TokenCounter()
    
    def test_count_single_message(self):
        """Test counting single message."""
        messages = [{"role": "user", "content": "Hello world"}]
        count = self.counter.count_messages(messages)
        assert count > 0
        assert isinstance(count, int)
    
    def test_count_multiple_messages(self):
        """Test counting multiple messages."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        count = self.counter.count_messages(messages)
        single = self.counter.count_messages([messages[0]])
        assert count > single
    
    def test_count_chinese_text(self):
        """Test counting Chinese text."""
        messages = [{"role": "user", "content": "你好世界，这是一个测试"}]
        count = self.counter.count_messages(messages)
        assert count > 0
    
    def test_count_empty_messages(self):
        """Test counting empty message list."""
        count = self.counter.count_messages([])
        assert count == 2  # Format overhead only
    
    def test_count_text(self):
        """Test counting plain text."""
        text = "Hello world"
        count = self.counter.count_text(text)
        assert count > 0
        assert isinstance(count, int)
    
    def test_count_empty_text(self):
        """Test counting empty text."""
        count = self.counter.count_text("")
        assert count == 0
    
    def test_count_long_text(self):
        """Test counting long text."""
        text = "This is a very long text. " * 100
        count = self.counter.count_text(text)
        assert count > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
