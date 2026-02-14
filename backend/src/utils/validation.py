"""Input validation utilities."""

import re
from dataclasses import dataclass
from typing import Optional

from ..utils.errors import MessageError, ErrorCode


@dataclass
class MessageValidation:
    """Message validation result."""
    is_valid: bool
    error_message: Optional[str] = None
    error_code: Optional[ErrorCode] = None


# Validation constants
MAX_MESSAGE_LENGTH = 10000  # Characters
MIN_MESSAGE_LENGTH = 1


def validate_message_content(content: str) -> MessageValidation:
    """Validate message content.
    
    Args:
        content: Message content to validate
        
    Returns:
        MessageValidation with result
    """
    # Check for empty or whitespace-only
    if not content or not content.strip():
        return MessageValidation(
            is_valid=False,
            error_message="消息不能为空",
            error_code=ErrorCode.MESSAGE_EMPTY,
        )
    
    # Check length
    if len(content) > MAX_MESSAGE_LENGTH:
        return MessageValidation(
            is_valid=False,
            error_message=f"消息长度超过限制（最大 {MAX_MESSAGE_LENGTH} 字符）",
            error_code=ErrorCode.MESSAGE_TOO_LONG,
        )
    
    # Check for potentially harmful patterns (basic)
    # This is not comprehensive - just basic checks
    harmful_patterns = [
        r'<script\b[^>]*>.*?</script>',  # Script tags
        r'javascript:',  # JavaScript URLs
    ]
    
    for pattern in harmful_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return MessageValidation(
                is_valid=False,
                error_message="消息包含不允许的内容",
                error_code=ErrorCode.MESSAGE_INVALID,
            )
    
    return MessageValidation(is_valid=True)


def validate_session_id(session_id: str) -> MessageValidation:
    """Validate session ID format.
    
    Args:
        session_id: Session ID to validate
        
    Returns:
        MessageValidation with result
    """
    if not session_id:
        return MessageValidation(
            is_valid=False,
            error_message="Session ID 不能为空",
            error_code=ErrorCode.SESSION_INVALID,
        )
    
    # UUID format check
    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    if not re.match(uuid_pattern, session_id, re.IGNORECASE):
        return MessageValidation(
            is_valid=False,
            error_message="Session ID 格式无效",
            error_code=ErrorCode.SESSION_INVALID,
        )
    
    return MessageValidation(is_valid=True)
