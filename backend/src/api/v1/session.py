"""Session API endpoints for session type detection.

This module provides REST API endpoints for:
- Detecting session type (main vs shared)
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/session", tags=["session"])


# ============ Request/Response Models ============

class SessionDetectRequest(BaseModel):
    """Request for session type detection."""
    channel_type: str = Field(description="通道类型: direct, group, discord, slack, wechat, web, cli, api")
    user_count: int = Field(default=1, description="当前参与用户数")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外的通道元数据")


class SessionDetectResponse(BaseModel):
    """Response for session type detection."""
    session_type: str = Field(description="检测到的会话类型: main 或 shared")
    confidence: float = Field(description="检测置信度 (0-1)", ge=0, le=1)
    reasoning: str = Field(description="判定理由")


# ============ Endpoints ============

@router.post("/detect", response_model=SessionDetectResponse)
async def detect_session_type(request: SessionDetectRequest) -> SessionDetectResponse:
    """Detect session type based on interaction parameters.
    
    Automatically determines whether a session is a "main" session
    (single user, can load MEMORY.md) or "shared" context
    (multi-user, privacy protected, blocks MEMORY.md).
    
    Detection logic:
    - Group channels (discord, slack, wechat, group) → SHARED
    - Single-user direct channels → MAIN
    - Multiple participants → SHARED
    - Default for single participant → MAIN
    """
    from ...core.session_detector import get_session_detector
    
    logger.info(
        "Detecting session type",
        extra={
            "channel_type": request.channel_type,
            "user_count": request.user_count
        }
    )
    
    try:
        detector = get_session_detector()
        result = detector.detect(
            channel_type=request.channel_type,
            user_count=request.user_count,
            metadata=request.metadata
        )
        
        logger.info(
            "Session type detected",
            extra={
                "session_type": result.session_type.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning
            }
        )
        
        return SessionDetectResponse(
            session_type=result.session_type.value,
            confidence=result.confidence,
            reasoning=result.reasoning
        )
        
    except Exception as e:
        logger.error(
            "Failed to detect session type",
            extra={
                "channel_type": request.channel_type,
                "error": str(e)
            }
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
async def list_session_types() -> dict[str, list[str]]:
    """List all available session types and channel types.
    
    Returns:
        Dictionary with session_types and channel_types lists
    """
    from ...core.session_detector import ChannelType
    from ...memory.models import SessionType
    
    return {
        "session_types": [s.value for s in SessionType],
        "channel_types": [c.value for c in ChannelType]
    }
