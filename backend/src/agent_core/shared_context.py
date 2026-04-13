"""多 Agent 共享上下文实现.

提供多 Agent 协同工作时的共享数据空间和消息板。

设计原则：
- 零外部依赖，仅使用 Python 标准库
- 使用 dataclass 定义所有类型
- 提供版本控制和冲突检测
- 支持并发控制锁

Example:
    # 创建共享上下文
    ctx = SharedContext(creator_agent_id="leader-001")

    # 添加参与者
    ctx.add_participant("worker-001")
    ctx.add_participant("worker-002")

    # 设置共享数据
    await ctx.set("task_plan", {"steps": [...]}, agent_id="leader-001")

    # 乐观锁更新
    entry = await ctx.get_entry("task_plan")
    success = await ctx.compare_and_set(
        "task_plan", entry.version, new_value, agent_id="worker-001"
    )

    # 发布消息到消息板
    await ctx.post_message("leader-001", "开始执行阶段1", tags=["decision"])

    # 获取消息
    messages = await ctx.get_messages(limit=10)

    # 并发控制
    acquired = await ctx.acquire_lock("resource-1", agent_id="worker-001")
    if acquired:
        try:
            # 执行独占操作
            pass
        finally:
            await ctx.release_lock("resource-1", agent_id="worker-001")
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SharedContextEntry:
    """共享上下文中的单条数据"""

    key: str
    value: Any
    set_by: str  # 写入的 agent_id
    timestamp: datetime
    version: int = 1  # 版本号，用于冲突检测


@dataclass
class MessageBoardPost:
    """消息板上的一条消息"""

    post_id: str
    agent_id: str  # 发布者
    content: str  # 消息内容
    timestamp: datetime
    tags: list[str] = field(default_factory=list)  # 标签（如 "finding", "decision", "question"）
    replies: list[MessageBoardPost] = field(default_factory=list)


class SharedContext:
    """多 Agent 共享的上下文空间

    提供:
    - 共享键值存储（带版本控制和冲突检测）
    - 消息板（所有参与者可见的消息流）
    - 并发控制锁
    """

    def __init__(self, context_id: str | None = None, creator_agent_id: str = ""):
        self.context_id: str = context_id or str(uuid.uuid4())
        self.creator_agent_id: str = creator_agent_id
        self.created_at: datetime = datetime.now()
        self._participants: set[str] = set()
        self._shared_memory: dict[str, SharedContextEntry] = {}
        self._message_board: list[MessageBoardPost] = []
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_owners: dict[str, str] = {}  # lock_name -> agent_id

    # === 参与者管理 ===

    def add_participant(self, agent_id: str) -> None:
        """添加参与者"""
        self._participants.add(agent_id)

    def remove_participant(self, agent_id: str) -> None:
        """移除参与者"""
        self._participants.discard(agent_id)

    @property
    def participants(self) -> list[str]:
        """返回所有参与者列表"""
        return list(self._participants)

    # === 共享键值存储 ===

    async def set(self, key: str, value: Any, agent_id: str) -> SharedContextEntry:
        """设置共享数据（自动递增版本号）"""
        existing = self._shared_memory.get(key)
        new_version = 1 if existing is None else existing.version + 1

        entry = SharedContextEntry(
            key=key,
            value=value,
            set_by=agent_id,
            timestamp=datetime.now(),
            version=new_version,
        )
        self._shared_memory[key] = entry
        return entry

    async def get(self, key: str) -> Any:
        """获取共享数据的值"""
        entry = self._shared_memory.get(key)
        return entry.value if entry else None

    async def get_entry(self, key: str) -> SharedContextEntry | None:
        """获取完整的数据条目（包含版本信息）"""
        return self._shared_memory.get(key)

    async def compare_and_set(
        self, key: str, expected_version: int, value: Any, agent_id: str
    ) -> bool:
        """乐观锁：仅当版本匹配时才设置（用于冲突检测）"""
        existing = self._shared_memory.get(key)
        current_version = existing.version if existing else 0

        if current_version != expected_version:
            return False

        entry = SharedContextEntry(
            key=key,
            value=value,
            set_by=agent_id,
            timestamp=datetime.now(),
            version=current_version + 1,
        )
        self._shared_memory[key] = entry
        return True

    async def delete(self, key: str, agent_id: str) -> bool:
        """删除共享数据"""
        if key in self._shared_memory:
            del self._shared_memory[key]
            return True
        return False

    async def list_keys(self) -> list[str]:
        """列出所有键"""
        return list(self._shared_memory.keys())

    # === 消息板 ===

    async def post_message(
        self, agent_id: str, content: str, tags: list[str] | None = None
    ) -> MessageBoardPost:
        """发布消息到消息板"""
        post = MessageBoardPost(
            post_id=str(uuid.uuid4()),
            agent_id=agent_id,
            content=content,
            timestamp=datetime.now(),
            tags=tags or [],
        )
        self._message_board.append(post)
        return post

    async def reply_to_post(
        self, post_id: str, agent_id: str, content: str
    ) -> MessageBoardPost | None:
        """回复某条消息"""
        # 查找父消息
        parent = None
        for post in self._message_board:
            if post.post_id == post_id:
                parent = post
                break
            # 在回复中查找
            for reply in post.replies:
                if reply.post_id == post_id:
                    parent = reply
                    break
            if parent:
                break

        if parent is None:
            return None

        reply = MessageBoardPost(
            post_id=str(uuid.uuid4()),
            agent_id=agent_id,
            content=content,
            timestamp=datetime.now(),
        )
        parent.replies.append(reply)
        return reply

    async def get_messages(self, limit: int = 50, tag: str | None = None) -> list[MessageBoardPost]:
        """获取消息板消息（可按标签过滤）"""
        messages = self._message_board

        if tag:
            messages = [m for m in messages if tag in m.tags]

        # 返回最新的消息
        return messages[-limit:] if len(messages) > limit else list(messages)

    # === 并发控制 ===

    async def acquire_lock(self, lock_name: str, agent_id: str, timeout: float = 30.0) -> bool:
        """获取命名锁"""
        # 获取或创建锁
        if lock_name not in self._locks:
            self._locks[lock_name] = asyncio.Lock()

        lock = self._locks[lock_name]

        # 检查是否已被其他 agent 持有
        current_owner = self._lock_owners.get(lock_name)
        if current_owner and current_owner != agent_id:
            return False

        # 尝试获取锁
        try:
            await asyncio.wait_for(lock.acquire(), timeout=timeout)
            self._lock_owners[lock_name] = agent_id
            return True
        except TimeoutError:
            return False

    async def release_lock(self, lock_name: str, agent_id: str) -> bool:
        """释放命名锁（只有锁持有者才能释放）"""
        current_owner = self._lock_owners.get(lock_name)

        if current_owner != agent_id:
            return False

        lock = self._locks.get(lock_name)
        if lock and lock.locked():
            lock.release()
            del self._lock_owners[lock_name]
            return True

        return False

    # === 统计 ===

    def get_summary(self) -> dict[str, Any]:
        """获取共享上下文摘要"""
        return {
            "context_id": self.context_id,
            "creator_agent_id": self.creator_agent_id,
            "created_at": self.created_at.isoformat(),
            "participants": list(self._participants),
            "memory_keys": list(self._shared_memory.keys()),
            "message_count": len(self._message_board),
            "active_locks": list(self._lock_owners.keys()),
        }
