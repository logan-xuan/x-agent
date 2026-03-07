"""Unit tests for ContextCompressor."""

import pytest
from unittest.mock import Mock, AsyncMock

from src.services.compression.compressor import ContextCompressor, CompressionResult
from src.services.compression.token_counter import TokenCounter


class TestContextCompressor:
    """Context compressor tests."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_summary_fn = AsyncMock(return_value="Summary content")
        self.mock_token_counter = Mock(spec=TokenCounter)
        self.mock_token_counter.count_messages = Mock(return_value=100)
        self.compressor = ContextCompressor(self.mock_summary_fn, self.mock_token_counter)

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
    async def test_compress_with_system_message(self):
        """Test compression preserves system message."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            *[{"role": "user", "content": f"Message {i}"} for i in range(100)],
        ]

        result = await self.compressor.compress(messages, retention_count=50)

        assert isinstance(result, CompressionResult)
        # System message + summary + 50 retained
        assert result.compressed_messages[0]["role"] == "system"
        assert result.compressed_messages[0]["content"] == "You are a helpful assistant."
        assert len(result.recent_messages) == 50

    def test_build_compressed_messages_without_system(self):
        """Test building compressed message list without system message."""
        recent = [
            {"role": "user", "content": "Recent message 1"},
            {"role": "assistant", "content": "Response 1"},
        ]
        summary = "This is the summary"

        compressed = self.compressor._build_compressed_messages(None, recent, summary)

        assert len(compressed) == 3
        assert compressed[0]["role"] == "system"
        assert "历史对话摘要" in compressed[0]["content"]
        assert "This is the summary" in compressed[0]["content"]
        assert compressed[1] == recent[0]
        assert compressed[2] == recent[1]

    def test_build_compressed_messages_with_system(self):
        """Test building compressed message list with system message preserved."""
        system_msg = {"role": "system", "content": "You are a helpful assistant."}
        recent = [
            {"role": "user", "content": "Recent message 1"},
            {"role": "assistant", "content": "Response 1"},
        ]
        summary = "This is the summary"

        compressed = self.compressor._build_compressed_messages(system_msg, recent, summary)

        assert len(compressed) == 4
        assert compressed[0] == system_msg
        assert compressed[1]["role"] == "system"
        assert "历史对话摘要" in compressed[1]["content"]
        assert compressed[2] == recent[0]
        assert compressed[3] == recent[1]

    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """Test summary generation via summary_fn callback."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        summary = await self.compressor._generate_summary(messages)

        assert isinstance(summary, str)
        assert len(summary) > 0
        self.mock_summary_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_fallback_on_error(self):
        """Test summary generation falls back on error."""
        self.mock_summary_fn.side_effect = Exception("LLM error")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        summary = await self.compressor._generate_summary(messages)

        assert "对话历史摘要" in summary
        assert "2" in summary  # 2 messages

    def test_safe_split_point_no_tool_messages(self):
        """Test safe split point with no tool messages."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "Good"},
        ]

        split = self.compressor._find_safe_split_point(messages, 2)
        assert split == 2

    def test_safe_split_point_tool_at_boundary(self):
        """Test safe split point when tool message is at split boundary."""
        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "file content"},
            {"role": "assistant", "content": "Here is the file"},
            {"role": "user", "content": "Thanks"},
        ]

        # Initial split at index 2 would put tool message at start of retention
        split = self.compressor._find_safe_split_point(messages, 2)
        # Should move back to include the assistant with tool_calls
        assert split == 1

    def test_safe_split_point_multiple_tool_results(self):
        """Test safe split point with multiple consecutive tool results."""
        messages = [
            {"role": "user", "content": "Do two things"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "tool_a", "arguments": "{}"}},
                {"id": "2", "type": "function", "function": {"name": "tool_b", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "1", "content": "result a"},
            {"role": "tool", "tool_call_id": "2", "content": "result b"},
            {"role": "assistant", "content": "Done"},
            {"role": "user", "content": "Great"},
        ]

        # Split at index 3 would put second tool at start of retention
        split = self.compressor._find_safe_split_point(messages, 3)
        assert split == 1  # Should include assistant with tool_calls

        # Split at index 2 would put first tool at start of retention
        split = self.compressor._find_safe_split_point(messages, 2)
        assert split == 1

    @pytest.mark.asyncio
    async def test_compress_preserves_tool_pairs(self):
        """Test that compression doesn't break tool_calls/tool pairs."""
        messages = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(8)
        ]
        # Insert a tool_calls/tool pair near the split boundary
        messages.extend([
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": "file content"},
            {"role": "assistant", "content": "Here is the result"},
            {"role": "user", "content": "Thanks"},
        ])

        result = await self.compressor.compress(messages, retention_count=4)

        # Verify no tool message appears without its preceding assistant
        for idx, msg in enumerate(result.compressed_messages):
            if msg.get("role") == "tool":
                # There must be a preceding assistant with tool_calls
                found_assistant = False
                for prev_idx in range(idx - 1, -1, -1):
                    prev = result.compressed_messages[prev_idx]
                    if prev.get("role") == "assistant" and prev.get("tool_calls"):
                        found_assistant = True
                        break
                    if prev.get("role") in ("user", "system"):
                        break
                assert found_assistant, f"Tool message at index {idx} has no preceding assistant with tool_calls"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
