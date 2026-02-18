"""Token counter for precise token counting."""

import tiktoken


class TokenCounter:
    """Precise token counter using tiktoken."""
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        """Initialize token counter.
        
        Args:
            encoding_name: The encoding to use (default: cl100k_base for GPT-4)
        """
        self.encoding = tiktoken.get_encoding(encoding_name)
    
    def count_messages(self, messages: list[dict]) -> int:
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
            # Content tokens
            content = msg.get("content", "")
            if content:
                total += len(self.encoding.encode(content))
            # Role tokens
            role = msg.get("role", "")
            if role:
                total += len(self.encoding.encode(role))
        # Format overhead
        total += 2
        return total
    
    def count_text(self, text: str) -> int:
        """Count tokens in a text string.
        
        Args:
            text: Text to count
            
        Returns:
            Token count
        """
        if not text:
            return 0
        return len(self.encoding.encode(text))
