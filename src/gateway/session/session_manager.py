"""
Session management module for the x-agent2 AI assistant system.

This module handles user sessions, including:
- Session creation and retrieval
- Session persistence to database
- Session lifecycle management
- User association with sessions
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
from src.db.models.session import Session as SessionModel
from src.db.models.user import User


class SessionManager:
    """Base session manager interface."""

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a session by ID."""
        raise NotImplementedError

    async def create_session(self, user_id: Optional[str] = None) -> SessionModel:
        """Create a new session."""
        raise NotImplementedError

    async def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session data."""
        raise NotImplementedError

    async def end_session(self, session_id: str) -> bool:
        """End a session."""
        raise NotImplementedError


class InMemorySessionManager(SessionManager):
    """Simple in-memory session manager for development."""

    def __init__(self):
        self.sessions = {}

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a session by ID from memory."""
        return self.sessions.get(session_id)

    async def create_session(self, user_id: Optional[str] = None) -> SessionModel:
        """Create a new session in memory."""
        session_id = str(uuid.uuid4())
        session = SessionModel(
            id=session_id,
            user_id=user_id,
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            data={}
        )
        self.sessions[session_id] = session
        return session

    async def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session data in memory."""
        session = self.sessions.get(session_id)
        if session:
            for key, value in kwargs.items():
                setattr(session, key, value)
            session.last_activity = datetime.utcnow()
            return True
        return False

    async def end_session(self, session_id: str) -> bool:
        """Remove a session from memory."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False


class DatabaseSessionManager(SessionManager):
    """Database-backed session manager for production."""

    def __init__(self):
        # Session inactivity timeout (24 hours)
        self.session_timeout = timedelta(hours=24)

    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        """Retrieve a session from the database."""
        try:
            session = await SessionModel.get_by_id(session_id)
            if session:
                # Update last activity if needed
                time_since_activity = datetime.utcnow() - session.last_activity
                if time_since_activity < self.session_timeout:
                    # Extend session if it's still valid
                    await session.update(last_activity=datetime.utcnow())
                    return session
                else:
                    # Session has expired, delete it
                    await session.delete()
                    return None
            return None
        except Exception as e:
            print(f"Error retrieving session {session_id}: {str(e)}")
            return None

    async def create_session(self, user_id: Optional[str] = None) -> SessionModel:
        """Create a new session in the database."""
        session_id = str(uuid.uuid4())

        # Verify user exists if user_id provided
        if user_id:
            try:
                user = await User.get_by_id(user_id)
                if not user:
                    user_id = None  # Invalid user_id, ignore it
            except:
                user_id = None  # User lookup failed, ignore user_id

        session = SessionModel(
            id=session_id,
            user_id=user_id,
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            data={}
        )

        await session.save()
        return session

    async def update_session(self, session_id: str, **kwargs) -> bool:
        """Update session data in the database."""
        try:
            session = await self.get_session(session_id)
            if session:
                await session.update(**kwargs)
                return True
            return False
        except Exception as e:
            print(f"Error updating session {session_id}: {str(e)}")
            return False

    async def end_session(self, session_id: str) -> bool:
        """End a session by deleting it from the database."""
        try:
            session = await SessionModel.get_by_id(session_id)
            if session:
                await session.delete()
                return True
            return False
        except Exception as e:
            print(f"Error ending session {session_id}: {str(e)}")
            return False

    async def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions from the database."""
        try:
            expired_before = datetime.utcnow() - self.session_timeout
            # Note: We'd need to implement a method in SessionModel to find and delete expired sessions
            # This is a placeholder implementation
            return 0
        except Exception as e:
            print(f"Error cleaning up expired sessions: {str(e)}")
            return 0


class SessionContext:
    """Provides contextual information for a session."""

    def __init__(self, session: SessionModel):
        self.session = session
        self.user = None
        self.conversation_history = []
        self.preferences = {}

    async def load_user(self):
        """Load user information if session has an associated user."""
        if self.session.user_id:
            try:
                self.user = await User.get_by_id(self.session.user_id)
            except Exception:
                self.user = None

    async def get_recent_messages(self, limit: int = 10) -> list:
        """Get recent messages from this session."""
        # Placeholder implementation - would integrate with Message model
        return []

    def get_preference(self, key: str, default=None):
        """Get a session preference."""
        return self.session.data.get(key, default)

    async def set_preference(self, key: str, value):
        """Set a session preference."""
        self.session.data[key] = value
        await self.session.update(data=self.session.data)


# Global session manager instance
session_manager = DatabaseSessionManager()