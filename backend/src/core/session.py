"""Session management for chat conversations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.message import Message
from ..models.session import Session
from ..services.storage import StorageService
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages chat sessions and their messages."""
    
    def __init__(self, storage: StorageService | None = None) -> None:
        """Initialize session manager.
        
        Args:
            storage: Storage service instance
        """
        self._storage = storage or StorageService()
    
    async def create_session(self, title: str | None = None) -> Session:
        """Create a new chat session.
        
        Args:
            title: Optional session title
            
        Returns:
            Created session
        """
        session = Session(
            id=str(uuid.uuid4()),
            title=title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=0,
        )
        
        async with self._storage.session() as db_session:
            db_session.add(session)
            await db_session.commit()
            await db_session.refresh(session)
        
        logger.info(
            "Created session",
            extra={
                "session_id": session.id,
                "title": session.title,
            }
        )
        return session
    
    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID.
        
        Args:
            session_id: Session UUID
            
        Returns:
            Session if found, None otherwise
        """
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Session).where(Session.id == session_id)
            )
            return result.scalar_one_or_none()
    
    async def list_sessions(self, limit: int = 100) -> list[Session]:
        """List all sessions ordered by update time.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of sessions
        """
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Session)
                .order_by(Session.updated_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> Message:
        """Add a message to a session.
        
        Args:
            session_id: Session UUID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
            
        Returns:
            Created message
        """
        message = Message(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.utcnow(),
        )
        
        if metadata:
            message.set_metadata(metadata)
        
        async with self._storage.session() as db_session:
            db_session.add(message)
            
            # Update session message count and timestamp
            session = await db_session.get(Session, session_id)
            if session:
                session.message_count += 1
                session.updated_at = datetime.utcnow()
            
            await db_session.commit()
            await db_session.refresh(message)
        
        logger.debug(
            "Added message to session",
            extra={
                "session_id": session_id,
                "message_id": message.id,
                "role": role,
                "content_length": len(content),
            }
        )
        return message
    
    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[Message]:
        """Get messages for a session.
        
        Args:
            session_id: Session UUID
            limit: Maximum number of messages
            offset: Number of messages to skip
            
        Returns:
            List of messages
        """
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.asc())
                .offset(offset)
                .limit(limit)
            )
            messages = list(result.scalars().all())
        
        logger.debug(
            "Retrieved messages for session",
            extra={
                "session_id": session_id,
                "message_count": len(messages),
                "limit": limit,
                "offset": offset,
            }
        )
        return messages
    
    async def get_messages_as_dict(
        self,
        session_id: str,
        limit: int = 100
    ) -> list[dict[str, str]]:
        """Get messages formatted for LLM API.
        
        Args:
            session_id: Session UUID
            limit: Maximum number of messages
            
        Returns:
            List of messages in OpenAI format
        """
        messages = await self.get_messages(session_id, limit=limit)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages.
        
        Args:
            session_id: Session UUID
            
        Returns:
            True if deleted, False if not found
        """
        async with self._storage.session() as db_session:
            session = await db_session.get(Session, session_id)
            if not session:
                return False
            
            await db_session.delete(session)
            await db_session.commit()
        
        logger.info(
            "Deleted session",
            extra={
                "session_id": session_id,
            }
        )
        return True
