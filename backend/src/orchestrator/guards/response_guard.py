"""Response guard for enforcing response-related policies.

This guard enforces rules about response formatting:
- Merge fragmented responses (avoid triple-hits)
- Limit emoji count
- Filter sensitive information
"""

import re
from collections import deque
from typing import Any

from ..policy_parser import Rule, RuleType
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ResponseGuard:
    """Guard for response formatting policy enforcement.
    
    Enforces rules like:
    - Avoid sending multiple short messages (triple-hit rule)
    - Limit emoji count to 1 per message
    - Filter sensitive information (credit cards, IDs, etc.)
    
    Example:
        guard = ResponseGuard()
        processed = guard.process(response, soft_guidelines)
        # processed response has limited emojis, merged fragments, etc.
    """
    
    # Patterns for sensitive information
    SENSITIVE_PATTERNS = [
        # Credit card numbers
        (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD_NUMBER]'),
        # ID card numbers (Chinese)
        (r'\b\d{17}[\dXx]\b', '[ID_NUMBER]'),
        # Email addresses (partial masking)
        (r'\b([A-Za-z0-9._%+-]{2})[A-Za-z0-9._%+-]+@', r'\1***@'),
        # Phone numbers (Chinese mobile)
        (r'\b1[3-9]\d{9}\b', '[PHONE_NUMBER]'),
    ]
    
    def __init__(self, max_recent_responses: int = 5) -> None:
        """Initialize the response guard.
        
        Args:
            max_recent_responses: Number of recent responses to track
        """
        self._recent_responses: deque[str] = deque(maxlen=max_recent_responses)
        self._last_response_time: float = 0
        
        logger.debug("ResponseGuard initialized")
    
    def process(
        self,
        response: str,
        soft_guidelines: list[Rule],
    ) -> str:
        """Process response according to soft guidelines.
        
        Args:
            response: The response to process
            soft_guidelines: List of soft guideline rules
            
        Returns:
            Processed response
        """
        processed = response
        
        # Apply each soft guideline
        for rule in soft_guidelines:
            if self._is_response_rule(rule):
                processed = self._apply_rule(processed, rule)
        
        # Track this response
        self._recent_responses.append(processed)
        
        return processed
    
    def _is_response_rule(self, rule: Rule) -> bool:
        """Check if a rule affects response formatting.
        
        Args:
            rule: The rule to check
            
        Returns:
            True if the rule affects response behavior
        """
        response_keywords = [
            "三连击", "碎片", "表情", "emoji",
            "响应", "回复", "敏感", "隐私",
        ]
        
        content_lower = rule.content.lower()
        section_lower = rule.source_section.lower()
        
        for keyword in response_keywords:
            if keyword in content_lower or keyword in section_lower:
                return True
        
        return False
    
    def _apply_rule(self, response: str, rule: Rule) -> str:
        """Apply a specific rule to the response.
        
        Args:
            response: The response to modify
            rule: The rule to apply
            
        Returns:
            Modified response
        """
        section = rule.source_section
        
        # Emoji limiting
        if "表情" in section or "emoji" in section.lower():
            response = self._limit_emojis(response)
        
        # Fragment merging
        if "三连击" in section or "碎片" in section:
            response = self._check_fragment(response)
        
        # Sensitive info filtering (always apply for safety rules)
        if "安全" in section or "隐私" in section or "私有" in section:
            response = self._filter_sensitive(response)
        
        return response
    
    def _limit_emojis(self, response: str, max_emojis: int = 1) -> str:
        """Limit the number of emojis in response.
        
        Args:
            response: The response text
            max_emojis: Maximum number of emojis to allow
            
        Returns:
            Response with limited emojis
        """
        # Find all emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )
        
        emojis = emoji_pattern.findall(response)
        
        if len(emojis) > max_emojis:
            # Keep only the first emoji
            first_emoji = emojis[0]
            
            # Remove all emojis
            response_no_emoji = emoji_pattern.sub('', response)
            
            # Add back only the first emoji
            # Find position of first emoji and insert it there
            match = emoji_pattern.search(response)
            if match:
                pos = match.start()
                response = response_no_emoji[:pos] + first_emoji + response_no_emoji[pos:]
            
            logger.debug(
                "Emojis limited",
                extra={
                    "original_count": len(emojis),
                    "kept": first_emoji,
                }
            )
        
        return response
    
    def _check_fragment(self, response: str) -> str:
        """Check if response is a fragment that should be merged.
        
        This is a hint for the streaming system - actual merging
        happens at the WebSocket level.
        
        Args:
            response: The response text
            
        Returns:
            Response (potentially with merge hint)
        """
        # Check if this is a very short response
        is_short = len(response.strip()) < 50
        
        # Check if recent responses were also short
        recent_short_count = sum(
            1 for r in self._recent_responses if len(r.strip()) < 50
        )
        
        if is_short and recent_short_count >= 2:
            logger.info(
                "Potential fragment detected",
                extra={
                    "response_length": len(response),
                    "recent_short_count": recent_short_count,
                }
            )
            # Add metadata hint (not modifying content)
            # The actual merge decision is made by the streaming handler
        
        return response
    
    def _filter_sensitive(self, response: str) -> str:
        """Filter sensitive information from response.
        
        Args:
            response: The response text
            
        Returns:
            Response with sensitive info masked
        """
        filtered = response
        
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            filtered = re.sub(pattern, replacement, filtered)
        
        if filtered != response:
            logger.info(
                "Sensitive information filtered",
                extra={"pattern_count": len(re.findall(pattern, response))}
            )
        
        return filtered
    
    def reset(self) -> None:
        """Reset the guard state."""
        self._recent_responses.clear()
        self._last_response_time = 0
