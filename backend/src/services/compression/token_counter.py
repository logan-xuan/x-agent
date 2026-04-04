"""Token counter for prompt budget accounting."""

from __future__ import annotations

import json
from typing import Any

import tiktoken


class TokenCounter:
    """Prompt token counter using tiktoken.

    Notes:
    - This is still an approximation for non-OpenAI models.
    - Count all payload parts that are actually sent to the provider, not just
      plain text content, otherwise runtime budget checks can be far too low.
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        """Initialize token counter.

        Args:
            encoding_name: The encoding to use (default: cl100k_base for GPT-4)
        """
        self.encoding = tiktoken.get_encoding(encoding_name)

    def _encode_len(self, text: str) -> int:
        """Count encoded length for a normalized string."""
        if not text:
            return 0
        return len(self.encoding.encode(text))

    def _serialize_value(self, value: Any) -> str:
        """Serialize structured payloads into a stable JSON string."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(value)

    def _count_value(self, value: Any) -> int:
        """Count tokens for an arbitrary payload value."""
        return self._encode_len(self._serialize_value(value))

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens in a list of messages (OpenAI format).

        Args:
            messages: List of message dicts with 'role' and 'content' keys

        Returns:
            Total token count
        """
        total = 0
        for msg in messages:
            # Base overhead per message
            total += 4

            # Role tokens
            total += self._count_value(msg.get("role", ""))

            # Count fields that are actually sent in OpenAI-compatible payloads.
            for field in ("content", "name", "tool_call_id"):
                if field in msg:
                    total += self._count_value(msg.get(field))

            for field in ("tool_calls", "function_call", "audio", "refusal"):
                if field in msg:
                    total += self._count_value(msg.get(field))

        # Format overhead
        total += 2
        return total

    def count_tool_definitions(self, tools: list[dict[str, Any]] | None) -> int:
        """Count tokens for tool/function schemas."""
        if not tools:
            return 0
        return sum(self._count_value(tool) for tool in tools)

    def count_text(self, text: str) -> int:
        """Count tokens in a text string.

        Args:
            text: Text to count

        Returns:
            Token count
        """
        return self._encode_len(text)
