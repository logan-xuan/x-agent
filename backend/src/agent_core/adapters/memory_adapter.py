"""XAgentMemoryAdapter - 适配 X-Agent 记忆系统到 MemoryPort.

将 X-Agent 的 MarkdownSync + HybridSearch 包装为
agent_core 的 MemoryPort Protocol。

存储: MarkdownSync.append_memory_entry() + sync_entry_to_vector_store()
搜索: HybridSearch.search()
删除: VectorStore.delete()
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


class XAgentMemoryAdapter:
    """MemoryPort 适配器，包装 X-Agent 的记忆系统.
    
    Example:
        from src.memory.md_sync import get_md_sync
        from src.memory.hybrid_search import get_hybrid_search
        
        md_sync = get_md_sync()
        search = get_hybrid_search()
        
        adapter = XAgentMemoryAdapter(md_sync, search)
        config = AgentCoreConfig(memory=adapter)
    """
    
    def __init__(
        self,
        md_sync: Any,
        hybrid_search: Any,
        vector_store: Any | None = None,
        embedder: Any | None = None,
    ) -> None:
        """初始化适配器.
        
        Args:
            md_sync: X-Agent MarkdownSync 实例
            hybrid_search: X-Agent HybridSearch 实例
            vector_store: VectorStore 实例 (可选, 用于向量同步和删除)
            embedder: Embedder 实例 (可选, 用于向量同步)
        """
        self._md_sync = md_sync
        self._search = hybrid_search
        self._vector_store = vector_store
        self._embedder = embedder
    
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
            记忆 ID
        """
        meta = metadata or {}
        entry_id = str(uuid.uuid4())
        
        # 构建 MemoryEntry (使用动态属性避免直接导入 X-Agent 类型)
        entry = _create_memory_entry(
            entry_id=entry_id,
            content=content,
            metadata=meta,
        )
        
        # 写入 Markdown 文件
        self._md_sync.append_memory_entry(entry)
        
        # 同步到向量存储
        if self._vector_store and self._embedder:
            self._md_sync.sync_entry_to_vector_store(
                entry, self._vector_store, self._embedder
            )
        
        return entry_id
    
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
        # 获取所有条目
        entries = self._md_sync.list_all_entries(limit=1000)
        
        # 构建搜索参数
        search_kwargs: dict[str, Any] = {
            "limit": limit,
        }
        
        if filters:
            if "content_type" in filters:
                search_kwargs["content_type"] = filters["content_type"]
            if "min_score" in filters:
                search_kwargs["min_score"] = filters["min_score"]
        
        # 执行搜索
        results = self._search.search(query, entries, **search_kwargs)
        
        # 转换为标准格式
        return [
            {
                "id": r.entry.id if hasattr(r, 'entry') else "",
                "content": r.entry.content if hasattr(r, 'entry') else "",
                "score": r.score if hasattr(r, 'score') else 0.0,
                "metadata": r.entry.metadata if hasattr(r, 'entry') and hasattr(r.entry, 'metadata') else {},
            }
            for r in results
        ]
    
    async def delete(self, entry_id: str) -> bool:
        """删除记忆.
        
        Args:
            entry_id: 记忆 ID
        
        Returns:
            是否删除成功
        """
        if self._vector_store:
            return self._vector_store.delete(entry_id)
        return False


def _create_memory_entry(
    entry_id: str,
    content: str,
    metadata: dict[str, Any],
) -> Any:
    """创建 MemoryEntry 对象.
    
    使用简单的命名空间对象避免直接导入 X-Agent 类型。
    如果 X-Agent MemoryEntry 可用，应使用真实类型。
    """
    try:
        from src.memory.models import MemoryEntry, MemoryContentType
        return MemoryEntry(
            id=entry_id,
            content=content,
            content_type=MemoryContentType.CONVERSATION,
            source_file="",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            metadata=metadata,
        )
    except ImportError:
        # 回退: 创建简单对象
        class SimpleEntry:
            pass
        entry = SimpleEntry()
        entry.id = entry_id
        entry.content = content
        entry.content_type = "daily_log"
        entry.source_file = ""
        entry.created_at = datetime.now()
        entry.updated_at = datetime.now()
        entry.metadata = metadata
        return entry
