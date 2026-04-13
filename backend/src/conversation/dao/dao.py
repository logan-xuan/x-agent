"""核心实体数据访问层（DAO）。

为 User 提供异步 CRUD 操作，基于 StorageService 的 async session 实现。

Agent 和 Channel 已改为配置驱动（从 x-agent.yaml 加载），不再持久化到数据库。
Session 相关操作已迁移到 SessionManager（backend/src/conversation/session.py）。

典型用法::

    from ..services.storage import get_storage_service

    storage = get_storage_service()
    user_dao = UserDAO(storage)
    user = await user_dao.create(name="玄哥")
"""

from __future__ import annotations

from sqlalchemy import select

from ...services.storage import StorageService
from ...utils.logger import get_logger
from .models import User

logger = get_logger(__name__)


class UserDAO:
    """用户数据访问对象。"""

    def __init__(self, storage: StorageService) -> None:
        self._storage = storage

    async def create(self, name: str, user_id: str | None = None) -> User:
        """创建用户。

        Args:
            name: 用户名称。
            user_id: 可选的用户 ID，省略时自动生成。

        Returns:
            创建的 User 实例。
        """
        user = User(name=name)
        if user_id is not None:
            user.user_id = user_id

        async with self._storage.session() as db_session:
            db_session.add(user)
            await db_session.flush()
            await db_session.refresh(user)

        logger.info("创建用户", extra={"user_id": user.user_id, "name": name})
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        """根据 ID 获取用户。"""
        async with self._storage.session() as db_session:
            return await db_session.get(User, user_id)

    async def list_all(self, limit: int = 100) -> list[User]:
        """列出所有用户，按创建时间倒序。"""
        async with self._storage.session() as db_session:
            result = await db_session.execute(
                select(User).order_by(User.create_time.desc()).limit(limit)
            )
            return list(result.scalars().all())

    async def update_name(self, user_id: str, name: str) -> User | None:
        """更新用户名称。

        Args:
            user_id: 用户 ID。
            name: 新名称。

        Returns:
            更新后的 User，不存在时返回 None。
        """
        async with self._storage.session() as db_session:
            user = await db_session.get(User, user_id)
            if user is None:
                return None
            user.name = name
            await db_session.flush()
            await db_session.refresh(user)

        logger.info("更新用户名称", extra={"user_id": user_id, "name": name})
        return user

    async def delete(self, user_id: str) -> bool:
        """删除用户。

        Returns:
            是否成功删除（用户不存在时返回 False）。
        """
        async with self._storage.session() as db_session:
            user = await db_session.get(User, user_id)
            if user is None:
                return False
            await db_session.delete(user)

        logger.info("删除用户", extra={"user_id": user_id})
        return True
