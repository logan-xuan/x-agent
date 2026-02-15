"""Importance detection for memory entries.

This module provides automatic detection of important content in conversations
that should be recorded as memory entries.

Detection Strategy (Hybrid Mode):
1. Keyword matching for explicit importance markers
2. Content pattern recognition for decisions and commitments
3. Context-based inference from conversation flow
"""

import re
from datetime import datetime
from typing import Any

from .models import MemoryContentType
from ..utils.logger import get_logger

logger = get_logger(__name__)


# Importance indicators - keywords and phrases that suggest important content
IMPORTANCE_KEYWORDS = [
    # Explicit importance markers
    "重要", "记得", "记住", "别忘了", "关键", "核心",
    "important", "remember", "don't forget", "key", "critical",
    
    # Decision markers
    "决定", "选定", "选择", "确认", "定下来",
    "decided", "selected", "chosen", "confirmed", "agreed",
    
    # Commitment markers
    "承诺", "保证", "约定", "计划", "目标", "deadline",
    "promise", "commit", "plan", "goal", "target",
    
    # Preference markers
    "喜欢", "不喜欢", "偏好", "习惯",
    "prefer", "like", "dislike", "habit",
    
    # Identity markers
    "我是", "我叫", "我的职业", "我从事",
    "I am", "my name is", "I work as", "my job is",
]

# Patterns that indicate important decisions
DECISION_PATTERNS = [
    r"我们?决定(.+)",
    r"最终选择(.+)",
    r"确定使用(.+)",
    r"就选(.+)了",
    r"we decided (.+)",
    r"we chose (.+)",
    r"let's use (.+)",
    r"we will go with (.+)",
]

# Patterns that indicate commitments or plans
COMMITMENT_PATTERNS = [
    r"下周(.+)",
    r"明天(.+)",
    r"下个月(.+)",
    r"计划(.+)",
    r"要去做(.+)",
    r"next week (.+)",
    r"tomorrow (.+)",
    r"plan to (.+)",
    r"will do (.+)",
]

# Patterns that indicate user preferences
PREFERENCE_PATTERNS = [
    r"我喜欢(.+)",
    r"我不喜欢(.+)",
    r"我偏好(.+)",
    r"我的习惯是(.+)",
    r"I like (.+)",
    r"I don't like (.+)",
    r"I prefer (.+)",
    r"my preference is (.+)",
]

# Patterns that indicate identity information
IDENTITY_PATTERNS = [
    r"我叫(.+)",
    r"我是(.+)",
    r"我的职业是(.+)",
    r"我从事(.+)",
    r"my name is (.+)",
    r"I am a (.+)",
    r"I work as a (.+)",
    r"my job is (.+)",
]


class ImportanceDetector:
    """Detector for identifying important content in conversations.
    
    Uses a hybrid approach combining:
    1. Keyword matching (fast, explicit markers)
    2. Pattern recognition (structured information)
    3. Content analysis (context inference)
    """
    
    def __init__(self) -> None:
        """Initialize importance detector."""
        self.keywords = IMPORTANCE_KEYWORDS
        self.decision_patterns = [re.compile(p, re.IGNORECASE) for p in DECISION_PATTERNS]
        self.commitment_patterns = [re.compile(p, re.IGNORECASE) for p in COMMITMENT_PATTERNS]
        self.preference_patterns = [re.compile(p, re.IGNORECASE) for p in PREFERENCE_PATTERNS]
        self.identity_patterns = [re.compile(p, re.IGNORECASE) for p in IDENTITY_PATTERNS]
    
    def is_important(self, content: str) -> bool:
        """Check if content contains important information.
        
        Args:
            content: Text content to analyze
            
        Returns:
            True if content appears to be important
        """
        # Check keywords
        content_lower = content.lower()
        for keyword in self.keywords:
            if keyword.lower() in content_lower:
                logger.debug(
                    "Importance detected via keyword",
                    extra={"keyword": keyword}
                )
                return True
        
        # Check patterns
        if self._match_patterns(content, self.decision_patterns):
            return True
        if self._match_patterns(content, self.commitment_patterns):
            return True
        if self._match_patterns(content, self.preference_patterns):
            return True
        if self._match_patterns(content, self.identity_patterns):
            return True
        
        return False
    
    def detect_content_type(self, content: str) -> MemoryContentType:
        """Detect the most appropriate content type for the content.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Most appropriate MemoryContentType
        """
        # Check for decision patterns
        if self._match_patterns(content, self.decision_patterns):
            return MemoryContentType.DECISION
        
        # Check for commitment/plan patterns
        if self._match_patterns(content, self.commitment_patterns):
            return MemoryContentType.DECISION
        
        # Check for preference/identity patterns
        if self._match_patterns(content, self.preference_patterns):
            return MemoryContentType.MANUAL
        
        if self._match_patterns(content, self.identity_patterns):
            return MemoryContentType.MANUAL
        
        # Default to conversation
        return MemoryContentType.CONVERSATION
    
    def extract_important_info(self, content: str) -> dict[str, Any]:
        """Extract structured important information from content.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Dictionary with extracted information
        """
        info: dict[str, Any] = {
            "is_important": False,
            "content_type": MemoryContentType.CONVERSATION.value,
            "matched_keywords": [],
            "matched_patterns": [],
            "extracted_entities": [],
        }
        
        content_lower = content.lower()
        
        # Find matched keywords
        for keyword in self.keywords:
            if keyword.lower() in content_lower:
                info["matched_keywords"].append(keyword)
                info["is_important"] = True
        
        # Find matched patterns and extract entities
        for pattern in self.decision_patterns:
            match = pattern.search(content)
            if match:
                info["matched_patterns"].append("decision")
                info["is_important"] = True
                if match.groups():
                    info["extracted_entities"].append({
                        "type": "decision",
                        "content": match.group(1).strip(),
                    })
        
        for pattern in self.commitment_patterns:
            match = pattern.search(content)
            if match:
                info["matched_patterns"].append("commitment")
                info["is_important"] = True
                if match.groups():
                    info["extracted_entities"].append({
                        "type": "commitment",
                        "content": match.group(1).strip(),
                    })
        
        for pattern in self.preference_patterns:
            match = pattern.search(content)
            if match:
                info["matched_patterns"].append("preference")
                info["is_important"] = True
                if match.groups():
                    info["extracted_entities"].append({
                        "type": "preference",
                        "content": match.group(1).strip(),
                    })
        
        for pattern in self.identity_patterns:
            match = pattern.search(content)
            if match:
                info["matched_patterns"].append("identity")
                info["is_important"] = True
                if match.groups():
                    info["extracted_entities"].append({
                        "type": "identity",
                        "content": match.group(1).strip(),
                    })
        
        # Determine content type
        info["content_type"] = self.detect_content_type(content).value
        
        return info
    
    def _match_patterns(self, content: str, patterns: list[re.Pattern]) -> bool:
        """Check if content matches any of the patterns.
        
        Args:
            content: Text to check
            patterns: List of compiled regex patterns
            
        Returns:
            True if any pattern matches
        """
        for pattern in patterns:
            if pattern.search(content):
                return True
        return False
    
    def analyze_conversation_turn(
        self,
        user_message: str,
        assistant_message: str,
    ) -> dict[str, Any]:
        """Analyze a conversation turn for important content.
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
            
        Returns:
            Analysis results with recommendations
        """
        user_info = self.extract_important_info(user_message)
        assistant_info = self.extract_important_info(assistant_message)
        
        # Combine importance from both sides
        is_important = user_info["is_important"] or assistant_info["is_important"]
        
        # Prefer user content type
        content_type = user_info["content_type"]
        if content_type == "conversation":
            content_type = assistant_info["content_type"]
        
        return {
            "is_important": is_important,
            "content_type": content_type,
            "user_analysis": user_info,
            "assistant_analysis": assistant_info,
            "recommendation": "record" if is_important else "skip",
        }


# Global detector instance
_detector: ImportanceDetector | None = None


def get_importance_detector() -> ImportanceDetector:
    """Get or create global importance detector instance.
    
    Returns:
        ImportanceDetector instance
    """
    global _detector
    if _detector is None:
        _detector = ImportanceDetector()
    return _detector
