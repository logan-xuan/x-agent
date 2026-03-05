"""Session management API endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...conversation.session import SessionManager
from ...services.storage import StorageService
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _get_session_manager() -> SessionManager:
    """Get a SessionManager instance."""
    return SessionManager(StorageService())


class CreateSessionRequest(BaseModel):
    """Request body for creating a session."""
    title: str | None = None


@router.get("")
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all sessions ordered by update time.

    Args:
        limit: Maximum number of sessions to return
        offset: Pagination offset

    Returns:
        Dictionary with items and total count
    """
    session_manager = _get_session_manager()
    sessions = await session_manager.list_sessions(limit=limit + offset)

    paginated = sessions[offset:offset + limit]

    return {
        "success": True,
        "data": {
            "items": [s.to_dict() for s in paginated],
            "total": len(sessions),
        },
    }


@router.post("")
async def create_session(request: CreateSessionRequest) -> dict:
    """Create a new chat session.

    Args:
        request: Session creation request with optional title

    Returns:
        Created session data
    """
    session_manager = _get_session_manager()
    session = await session_manager.create_session(title=request.title)

    logger.info(
        "Session created via API",
        extra={"session_id": session.id, "title": session.title},
    )

    return {
        "success": True,
        "data": session.to_dict(),
    }


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get a session with all its messages.

    Args:
        session_id: Session UUID

    Returns:
        Dictionary with session and messages
    """
    session_manager = _get_session_manager()
    
    # 先尝试获取 session，如果不存在则自动创建（兼容旧数据）
    session = await session_manager.ensure_session(session_id)
    messages = await session_manager.get_messages(session_id)

    return {
        "success": True,
        "data": {
            "session": session.to_dict(),
            "messages": [msg.to_dict() for msg in messages],
        },
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Delete a session and all its messages.

    Args:
        session_id: Session UUID

    Returns:
        Success status
    """
    session_manager = _get_session_manager()
    deleted = await session_manager.delete_session(session_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")

    logger.info("Session deleted via API", extra={"session_id": session_id})

    return {
        "success": True,
        "data": None,
    }


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None, description="Cursor for pagination"),
) -> dict:
    """List messages for a session.

    Args:
        session_id: Session UUID
        limit: Maximum number of messages to return
        before: Message ID cursor for pagination (not yet implemented)

    Returns:
        Dictionary with message items and hasMore flag
    """
    session_manager = _get_session_manager()

    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = await session_manager.get_messages(session_id, limit=limit + 1)

    has_more = len(messages) > limit
    result_messages = messages[:limit]

    return {
        "success": True,
        "data": {
            "items": [msg.to_dict() for msg in result_messages],
            "hasMore": has_more,
        },
    }
