"""记忆存储接口定义.

MemoryPort 定义了 agent_core 与记忆系统交互的接口。
"""

from __future__ import annotations

from typing import Protocol, Any


class MemoryPort(Protocol):
    """记忆存储接口.
    
    agent_core 通过此接口存储和检索记忆，不关心具体实现。
    实现者需要将具体的记忆系统（如向量数据库、Markdown 文件等）适配到此接口。
    
    Example:
        class VectorStoreAdapter:
            def __init__(self, vector_store, embedder):
                self.vector_store = vector_store
                self.embedder = embedder
            
            async def store(self, content: str, metadata: dict) -> str:
                embedding = self.embedder.embed(content)
                entry_id = self.vector_store.insert(embedding, content, metadata)
                return entry_id
            
            async def search(self, query: str, limit: int = 10) -> list[dict]:
                embedding = self.embedder.embed(query)
                results = self.vector_store.search(embedding, limit=limit)
                return results
    """
    
    async def store(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """存储记忆.
        
        Args:
            content: 记忆内容
            metadata: 元数据（可选），如：
                - source: 来源（tool_call, conversation, etc.）
                - tool_name: 工具名称
                - is_error: 是否为错误
                - tags: 标签列表
        
        Returns:
            str: 记忆 ID
        
        Raises:
            Exception: 存储失败时抛出异常
        """
        ...
    
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
            filters: 过滤条件（可选），如：
                - source: 来源过滤
                - tool_name: 工具名称过滤
                - min_score: 最低相似度
        
        Returns:
            list[dict]: 检索结果列表，每项包含：
                - id: 记忆 ID
                - content: 记忆内容
                - score: 相似度分数
                - metadata: 元数据
        """
        ...
    
    async def delete(self, entry_id: str) -> bool:
        """删除记忆.
        
        Args:
            entry_id: 记忆 ID
        
        Returns:
            bool: 是否删除成功
        """
        ...
