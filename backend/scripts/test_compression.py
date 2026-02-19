"""
Manual test script for context compression functionality.

Usage:
    cd backend
    python scripts/test_compression.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.compression.token_counter import TokenCounter
from src.config.models import CompressionConfig


def test_token_counter():
    """Test TokenCounter."""
    print("=" * 50)
    print("Testing TokenCounter")
    print("=" * 50)
    
    counter = TokenCounter()
    
    # Test English
    text_en = "Hello world, this is a test message."
    count_en = counter.count_text(text_en)
    print(f"English text: '{text_en}'")
    print(f"Token count: {count_en}")
    
    # Test Chinese
    text_cn = "你好世界，这是一个测试消息。"
    count_cn = counter.count_text(text_cn)
    print(f"\nChinese text: '{text_cn}'")
    print(f"Token count: {count_cn}")
    
    # Test message list
    messages = [
        {"role": "system", "content": "You are an assistant"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hello! How can I help you?"},
    ]
    count_msg = counter.count_messages(messages)
    print(f"\nMessage list token count: {count_msg}")


def test_compression_scenarios():
    """Test different compression scenarios."""
    print("\n" + "=" * 50)
    print("Testing Compression Scenarios")
    print("=" * 50)
    
    config = CompressionConfig(
        threshold_rounds=10,
        threshold_tokens=1000,
        retention_count=5
    )
    
    # Scenario 1: Message count below threshold
    print("\nScenario 1: Message count below threshold (5 < 10)")
    messages_small = [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"Message {i}"}
        for i in range(5)
    ]
    counter = TokenCounter()
    token_count = counter.count_messages(messages_small)
    print(f"Message count: {len(messages_small)}, Token count: {token_count}")
    needs_compression = (
        len(messages_small) > config.threshold_rounds or
        token_count > config.threshold_tokens
    )
    print(f"Needs compression: {needs_compression}")
    
    # Scenario 2: Message count above threshold
    print("\nScenario 2: Message count above threshold (12 > 10)")
    messages_large = [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": f"This is message {i} with some content for token counting."}
        for i in range(12)
    ]
    token_count = counter.count_messages(messages_large)
    print(f"Message count: {len(messages_large)}, Token count: {token_count}")
    needs_compression = (
        len(messages_large) > config.threshold_rounds or
        token_count > config.threshold_tokens
    )
    print(f"Needs compression: {needs_compression}")
    
    # Scenario 3: Token count above threshold
    print("\nScenario 3: Token count above threshold")
    messages_tokens = [
        {"role": "user" if i % 2 == 0 else "assistant",
         "content": "This is a very long text, " * 50}  # Long text
        for i in range(5)
    ]
    token_count = counter.count_messages(messages_tokens)
    print(f"Message count: {len(messages_tokens)}, Token count: {token_count}")
    needs_compression = (
        len(messages_tokens) > config.threshold_rounds or
        token_count > config.threshold_tokens
    )
    print(f"Needs compression: {needs_compression}")


def main():
    """Main test function."""
    print("Context Compression System Test")
    print("=" * 50)
    
    test_token_counter()
    test_compression_scenarios()
    
    print("\n" + "=" * 50)
    print("Test completed")
    print("=" * 50)


if __name__ == "__main__":
    main()
