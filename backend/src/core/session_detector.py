"""Session detector for determining session type.

This module provides:
- Automatic detection of session type (main vs shared)
- Channel-based inference
- User count analysis
"""

from enum import Enum
from typing import Any

from ..memory.models import SessionType
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ChannelType(str, Enum):
    """Type of communication channel."""
    DIRECT = "direct"        # Direct 1:1 chat
    GROUP = "group"          # Local group chat
    DISCORD = "discord"      # Discord server
    SLACK = "slack"          # Slack workspace
    WECHAT = "wechat"        # WeChat group
    WEB = "web"              # Web UI
    CLI = "cli"              # Command line interface
    API = "api"              # REST API call


class SessionDetectRequest:
    """Request for session type detection."""
    
    def __init__(
        self,
        channel_type: ChannelType | str,
        user_count: int = 1,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Initialize detection request.
        
        Args:
            channel_type: Type of communication channel
            user_count: Number of participants
            metadata: Additional channel metadata
        """
        if isinstance(channel_type, str):
            try:
                self.channel_type = ChannelType(channel_type.lower())
            except ValueError:
                self.channel_type = ChannelType.DIRECT
        else:
            self.channel_type = channel_type
        
        self.user_count = user_count
        self.metadata = metadata or {}


class SessionDetectResponse:
    """Response for session type detection."""
    
    def __init__(
        self,
        session_type: SessionType,
        confidence: float = 1.0,
        reasoning: str = ""
    ) -> None:
        """Initialize detection response.
        
        Args:
            session_type: Detected session type
            confidence: Detection confidence (0-1)
            reasoning: Explanation for the detection
        """
        self.session_type = session_type
        self.confidence = confidence
        self.reasoning = reasoning
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_type": self.session_type.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class SessionDetector:
    """Detector for session type based on interaction mode.
    
    Determines whether a session is a "main" session (single user,
    private context) or "shared" context (multi-user, privacy protected).
    """
    
    # Channels that are always shared context
    SHARED_CHANNELS = {
        ChannelType.GROUP,
        ChannelType.DISCORD,
        ChannelType.SLACK,
        ChannelType.WECHAT,
    }
    
    # Channels that are always main sessions
    MAIN_CHANNELS = {
        ChannelType.DIRECT,
        ChannelType.WEB,
        ChannelType.CLI,
    }
    
    def __init__(self) -> None:
        """Initialize session detector."""
        logger.info("SessionDetector initialized")
    
    def detect(
        self,
        channel_type: ChannelType | str,
        user_count: int = 1,
        metadata: dict[str, Any] | None = None
    ) -> SessionDetectResponse:
        """Detect session type from interaction parameters.
        
        Args:
            channel_type: Type of communication channel
            user_count: Number of participants
            metadata: Additional channel metadata
            
        Returns:
            SessionDetectResponse with detected type and reasoning
        """
        # Normalize channel type
        if isinstance(channel_type, str):
            try:
                channel = ChannelType(channel_type.lower())
            except ValueError:
                channel = ChannelType.DIRECT
        else:
            channel = channel_type
        
        # Detection logic based on channel type and user count
        if channel in self.SHARED_CHANNELS:
            return SessionDetectResponse(
                session_type=SessionType.SHARED,
                confidence=0.95,
                reasoning=f"Channel type '{channel.value}' is inherently shared (multi-user)"
            )
        
        if channel in self.MAIN_CHANNELS and user_count == 1:
            return SessionDetectResponse(
                session_type=SessionType.MAIN,
                confidence=0.95,
                reasoning=f"Single-user direct channel '{channel.value}'"
            )
        
        # User count based detection
        if user_count > 1:
            return SessionDetectResponse(
                session_type=SessionType.SHARED,
                confidence=0.85,
                reasoning=f"Multiple participants ({user_count} users) indicate shared context"
            )
        
        # Default to main session for single-user scenarios
        if user_count == 1:
            return SessionDetectResponse(
                session_type=SessionType.MAIN,
                confidence=0.80,
                reasoning=f"Single participant, defaulting to main session"
            )
        
        # Fallback to main (safe default)
        return SessionDetectResponse(
            session_type=SessionType.MAIN,
            confidence=0.50,
            reasoning="Unable to determine, defaulting to main session"
        )
    
    def detect_from_metadata(self, metadata: dict[str, Any]) -> SessionDetectResponse:
        """Detect session type from metadata dictionary.
        
        Args:
            metadata: Dictionary containing channel info
            
        Returns:
            SessionDetectResponse
        """
        channel_type = metadata.get("channel_type", "direct")
        user_count = metadata.get("user_count", 1)
        
        return self.detect(
            channel_type=channel_type,
            user_count=user_count,
            metadata=metadata
        )


# Global session detector instance
_session_detector: SessionDetector | None = None


def get_session_detector() -> SessionDetector:
    """Get or create global session detector instance.
    
    Returns:
        SessionDetector instance
    """
    global _session_detector
    if _session_detector is None:
        _session_detector = SessionDetector()
    return _session_detector
