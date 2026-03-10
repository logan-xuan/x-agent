"""Session management for chat conversations."""

import asyncio
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.message import Message
from ..models.session import Session, SessionStatus
from ..services.storage import StorageService
from ..utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Manages chat sessions and their messages."""

    # 类级别的去重集合，跨实例共享，防止同一个会话被重复总结
    _summarized_session_ids: set[str] = set()
    
    def __init__(self, storage: StorageService | None = None) -> None:
        """Initialize session manager.
        
        Args:
            storage: Storage service instance
        """
        self._storage = storage or StorageService()
    
    async def create_session(
        self,
        title: str | None = None,
        agent_id: str | None = None,
        close_existing: bool = False,
    ) -> Session:
        """Create a new chat session.

        创建新会话后，异步触发对最近一个有消息的会话进行 LLM 总结，
        将关键信息写入 MEMORY.md 长期记忆。

        Args:
            title: Optional session title
            agent_id: Optional agent ID to associate with this session
            close_existing: If True, close all existing active sessions for this agent
                before creating the new one. Should only be set when the user explicitly
                requests a new session (e.g. clicks "New Session" button).

        Returns:
            Created session
        """
        # 创建前先获取最近的会话列表，用于后续总结
        previous_sessions = await self.list_sessions(limit=5)

        # 仅在用户主动新建会话时才关闭旧 session，切换 agent 时不关闭
        if close_existing and agent_id:
            await self._close_active_sessions_for_agent(agent_id)

        session = Session(
            id=str(uuid.uuid4()),
            title=title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            agent_id=agent_id,
            status=SessionStatus.ACTIVE.value,
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
            extra={"session_id": session.id, "title": session.title, "agent_id": agent_id},
        )

        # 异步触发：总结最近一个有消息的会话到长期记忆
        self._trigger_history_summarization(previous_sessions, session.id)

        return session

    async def _close_active_sessions_for_agent(self, agent_id: str) -> int:
        """关闭同一 agent 的所有 active session。

        确保每个 agent 在 webchat 上只有一个有效 session。
        创建新 session 前调用，将旧的 active session 标记为 closed。

        Args:
            agent_id: Agent ID

        Returns:
            关闭的 session 数量
        """
        closed_count = 0
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Session).where(
                    Session.agent_id == agent_id,
                    Session.status == SessionStatus.ACTIVE.value,
                )
            )
            active_sessions = list(result.scalars().all())
            for session in active_sessions:
                session.status = SessionStatus.CLOSED.value
                session.updated_at = datetime.utcnow()
                closed_count += 1
            if closed_count > 0:
                await db_session.commit()
                logger.info(
                    "Closed active sessions for agent before creating new session",
                    extra={"agent_id": agent_id, "closed_count": closed_count},
                )
        return closed_count

    def _trigger_history_summarization(
        self,
        previous_sessions: list[Session],
        new_session_id: str,
    ) -> None:
        """异步触发历史会话总结，不阻塞会话创建.

        查找最近一个有消息的会话，通过 MemoryManager 进行 LLM 总结。

        Args:
            previous_sessions: 之前的会话列表（按更新时间倒序）
            new_session_id: 新创建的会话 ID（排除用）
        """
        # 找到最近一个有消息的会话
        target_session_id = None
        for prev_session in previous_sessions:
            if prev_session.id != new_session_id and prev_session.message_count > 0:
                target_session_id = prev_session.id
                break

        if not target_session_id:
            return

        # 幂等保护：同一个会话只总结一次，防止前端重复调用 create_session
        if target_session_id in self._summarized_session_ids:
            logger.debug(
                "Session already summarized, skipping",
                extra={"session_id": target_session_id},
            )
            return
        self._summarized_session_ids.add(target_session_id)

        asyncio.create_task(
            self._summarize_previous_session(target_session_id),
            name=f"summarize-{target_session_id[:8]}",
        )

    async def _summarize_previous_session(self, session_id: str) -> None:
        """总结指定会话的历史消息到长期记忆.

        Args:
            session_id: 要总结的会话 ID
        """
        try:
            from ..memory.manager import get_memory_manager
            memory_manager = get_memory_manager()
            summary = await memory_manager.summarize_recent_history(
                session_id=session_id,
            )
            if summary:
                logger.info(
                    "Previous session summarized on new session creation",
                    extra={
                        "summarized_session_id": session_id,
                        "summary_length": len(summary),
                    },
                )
        except RuntimeError:
            # MemoryManager not initialized yet — skip silently
            pass
        except Exception as exc:
            logger.warning(
                "Failed to summarize previous session (non-fatal)",
                extra={
                    "session_id": session_id,
                    "error": str(exc),
                },
            )
    
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
    
    async def ensure_session(
        self,
        session_id: str,
        title: str | None = None,
        agent_id: str | None = None,
    ) -> Session:
        """Ensure a session exists, creating it if necessary.
        
        Args:
            session_id: Session UUID
            title: Optional title for new session
            agent_id: Optional agent ID to associate with this session
            
        Returns:
            Existing or newly created session
        """
        async with self._storage.session() as db_session:
            session = await db_session.get(Session, session_id)
            if session:
                return session
            
            session = Session(
                id=session_id,
                title=title or "Agent 对话",
                agent_id=agent_id,
                status=SessionStatus.ACTIVE.value,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                message_count=0,
            )
            db_session.add(session)
            await db_session.commit()
            await db_session.refresh(session)
        
        logger.info(
            "Auto-created session",
            extra={"session_id": session_id, "title": session.title},
        )
        return session

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> Message:
        """Add a message to a session.
        
        If the session does not exist, it will be auto-created.
        
        Args:
            session_id: Session UUID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata
            
        Returns:
            Created message
        """
        # Ensure session exists before adding message
        await self.ensure_session(session_id)
        
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
        offset: int = 0,
    ) -> list[Message]:
        """Get messages for a session (from earliest).
        
        Args:
            session_id: Session UUID
            limit: Maximum number of messages
            offset: Pagination offset
            
        Returns:
            List of messages ordered by created_at ascending
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
    
    async def get_latest_messages(
        self,
        session_id: str,
        limit: int = 30,
    ) -> list[Message]:
        """Get the latest messages for a session (most recent N messages).

        先按时间倒序取最后 N 条，再反转为正序返回，适用于总结最后几轮对话。

        Args:
            session_id: Session UUID
            limit: Maximum number of messages to return

        Returns:
            List of messages ordered by created_at ascending (oldest first)
        """
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            messages = list(result.scalars().all())

        # 反转为时间正序
        messages.reverse()

        logger.debug(
            "Retrieved latest messages for session",
            extra={
                "session_id": session_id,
                "message_count": len(messages),
                "limit": limit,
            },
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
    
    async def reactivate_session(self, session_id: str) -> bool:
        """重新激活一个已关闭的 session。

        WebSocket 重连时，如果 session 存在但状态不是 active，则重新激活。

        Args:
            session_id: Session UUID

        Returns:
            True if reactivated, False if not found
        """
        async with self._storage.session() as db_session:
            session = await db_session.get(Session, session_id)
            if not session:
                return False
            if session.status != SessionStatus.ACTIVE.value:
                session.status = SessionStatus.ACTIVE.value
                session.updated_at = datetime.utcnow()
                await db_session.commit()
                logger.info("Session reactivated", extra={"session_id": session_id})
        return True

    async def touch_session(self, session_id: str) -> bool:
        """更新 session 的活跃时间。

        每次消息时调用，更新 updated_at 时间戳。

        Args:
            session_id: Session UUID

        Returns:
            True if touched, False if not found
        """
        async with self._storage.session() as db_session:
            session = await db_session.get(Session, session_id)
            if not session:
                return False
            session.updated_at = datetime.utcnow()
            await db_session.commit()
        return True

    async def get_active_session_by_agent(self, agent_id: str) -> Session | None:
        """获取指定 agent 最新的 active session。

        用于通知系统和 session_resolver 查找有效 session。

        Args:
            agent_id: Agent ID

        Returns:
            最新的 active Session，没有则返回 None
        """
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(Session)
                .where(
                    Session.agent_id == agent_id,
                    Session.status == SessionStatus.ACTIVE.value,
                )
                .order_by(Session.updated_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def close_session(self, session_id: str) -> bool:
        """关闭指定 session，将状态标记为 closed。

        WebSocket 断开时由 dispatcher 调用，同步关闭 sessions 表中的记录。

        Args:
            session_id: Session UUID

        Returns:
            True if closed, False if not found
        """
        async with self._storage.session() as db_session:
            session = await db_session.get(Session, session_id)
            if not session:
                return False
            session.status = SessionStatus.CLOSED.value
            session.updated_at = datetime.utcnow()
            await db_session.commit()

        logger.info("Session closed", extra={"session_id": session_id})
        return True

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
