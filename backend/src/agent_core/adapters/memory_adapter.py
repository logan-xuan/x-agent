"""XAgentMemoryAdapter - 适配 X-Agent 记忆系统到 MemoryPort.

通过构造函数注入 MemoryManager 实例（依赖倒置），
保持 agent_core 的独立性，不直接 import 外部模块。

存储: memory_manager.record_entry()
搜索: memory_manager.search()
删除: memory_manager.delete_entry()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class XAgentMemoryAdapter:
    """MemoryPort 适配器，通过注入的 MemoryManager 访问记忆系统.

    adapter 不直接 import 任何外部模块，所有依赖通过构造函数注入。

    Example:
        from src.memory.manager import get_memory_manager

        manager = get_memory_manager()
        adapter = XAgentMemoryAdapter(manager)
        config = AgentCoreConfig(memory=adapter)
    """

    def __init__(self, memory_manager: Any) -> None:
        """初始化适配器.

        Args:
            memory_manager: MemoryManager 实例（鸭子类型，需提供
                record_entry / search / delete_entry 方法）
        """
        self._memory_manager = memory_manager

    async def store(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """存储记忆.

        Args:
            content: 记忆内容
            metadata: 元数据

        Returns:
            固定返回 "ok"
        """
        meta = metadata or {}
        content_type = meta.pop("content_type", "conversation")

        logger.info(
            "MemoryAdapter store",
            extra={
                "scene": "adapter_store",
                "content_type": content_type,
                "content_preview": content[:80],
                "session_id": meta.get("session_id", ""),
            },
        )

        self._memory_manager.record_entry(
            content=content,
            content_type=content_type,
            metadata=meta,
        )
        return "ok"

    async def search(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """检索相关记忆.

        Args:
            query: 查询文本
            limit: 返回结果数量上限
            filters: 过滤条件

        Returns:
            检索结果列表
        """
        content_type = None
        if filters and "content_type" in filters:
            content_type = filters["content_type"]

        logger.info(
            "MemoryAdapter search",
            extra={
                "scene": "adapter_search",
                "query": query[:80],
                "limit": limit,
                "content_type": content_type,
            },
        )

        results = self._memory_manager.search(
            query=query,
            limit=limit,
            content_type=content_type,
        )

        result_list = [
            {
                "id": r.entry.id if hasattr(r, "entry") else "",
                "content": r.entry.content if hasattr(r, "entry") else "",
                "score": r.score if hasattr(r, "score") else 0.0,
                "metadata": r.entry.metadata
                if hasattr(r, "entry") and hasattr(r.entry, "metadata")
                else {},
            }
            for r in results
        ]

        logger.info(
            "MemoryAdapter search completed",
            extra={
                "scene": "adapter_search",
                "query": query[:80],
                "results_count": len(result_list),
            },
        )
        return result_list

    async def delete(self, entry_id: str) -> bool:
        """删除记忆.

        Args:
            entry_id: 记忆 ID

        Returns:
            是否删除成功
        """
        if hasattr(self._memory_manager, "delete_entry"):
            return self._memory_manager.delete_entry(entry_id)
        return False
