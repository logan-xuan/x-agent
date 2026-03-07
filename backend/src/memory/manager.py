"""MemoryManager — 记忆系统统一入口.

整合三大能力：
1. 写入 (Write): 历史总结、压缩前归档、直接记录
2. 搜索 (Search): 混合检索、向量同步
3. 会话 (Session): 数据库持久层查询

所有外部模块通过 MemoryManager 访问记忆系统，不再直接调用底层组件。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .models import MemoryContentType, MemoryEntry
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .md_sync import MarkdownSync
    from .hybrid_search import HybridSearch, SearchResult
    from .vector_store import VectorStore
    from .embedder import ONNXEmbedder, MockEmbedder
    from .importance_detector import ImportanceDetector
    from ..conversation.session import SessionManager
    from ..services.llm.router import LLMRouter
    from ..models.message import Message

logger = get_logger(__name__)

# LLM prompt for summarizing recent conversation history
HISTORY_SUMMARY_PROMPT = """你是一个对话摘要专家。请对以下对话历史进行精炼总结，提取关键信息。

## 对话历史
{conversation}

## 要求
1. 提取用户的关键偏好、决策、计划
2. 保留重要的上下文信息（如用户身份、项目背景）
3. 忽略日常闲聊和重复内容
4. 总结控制在 200 字以内
5. 使用简洁的要点格式

## 输出格式
直接输出总结内容，不要有额外的标记或说明。"""

# LLM prompt for extracting important info before compression
ARCHIVE_EXTRACTION_PROMPT = """你是一个信息提取专家。从以下即将被压缩的对话中，提取需要长期保留的重要信息。

## 对话内容
{conversation}

## 已有的长期记忆（不要重复提取）
{existing_memories}

## 提取标准
只提取以下类型的信息：
1. 用户的明确偏好或习惯
2. 重要的决策和结论
3. 关键的技术方案或架构决定
4. 用户身份相关信息
5. 需要长期记住的约定

**重要：如果某条信息已经在"已有的长期记忆"中存在（即使措辞略有不同），不要重复提取。只提取真正新的信息。**

## 输出格式（JSON）
{{
  "has_important_info": true/false,
  "entries": [
    {{
      "content": "提取的关键内容（简洁，不超过50字）",
      "category": "偏好|决策|技术|身份|约定"
    }}
  ]
}}

注意：如果没有需要长期保留的信息，或所有重要信息都已在已有记忆中，返回 {{"has_important_info": false, "entries": []}}
只输出JSON，不要有其他内容。"""


class MemoryManager:
    """记忆系统统一入口.

    整合写入、搜索、会话三大能力，对外提供简洁 API。
    所有外部模块通过此类访问记忆系统。

    Example:
        manager = MemoryManager(
            workspace_path="workspace",
            llm_router=llm_router,
            session_manager=session_manager,
        )
        await manager.sync_to_vectors()
        results = manager.search("用户偏好")
    """

    def __init__(
        self,
        workspace_path: str,
        llm_router: "LLMRouter",
        session_manager: "SessionManager",
    ) -> None:
        """初始化 MemoryManager.

        Args:
            workspace_path: workspace 目录路径
            llm_router: LLM 路由器（用于总结、分析）
            session_manager: 会话管理器（用于数据库查询）
        """
        self._workspace_path = Path(workspace_path)
        self._llm_router = llm_router
        self._session_manager = session_manager

        # 延迟初始化的内部组件
        self._md_sync: MarkdownSync | None = None
        self._hybrid_search: HybridSearch | None = None
        self._vector_store: VectorStore | None = None
        self._embedder: Any | None = None
        self._importance_detector: ImportanceDetector | None = None

        logger.info(
            "MemoryManager initialized",
            extra={"workspace_path": str(workspace_path)},
        )

    # ================================================================
    # 内部组件懒加载
    # ================================================================

    def _get_md_sync(self) -> "MarkdownSync":
        """获取 MarkdownSync 实例（懒加载）."""
        if self._md_sync is None:
            from .md_sync import get_md_sync
            self._md_sync = get_md_sync(str(self._workspace_path))
        return self._md_sync

    def _get_vector_store(self) -> "VectorStore":
        """获取 VectorStore 实例（懒加载）."""
        if self._vector_store is None:
            from .vector_store import get_vector_store
            self._vector_store = get_vector_store()
        return self._vector_store

    def _get_embedder(self) -> Any:
        """获取 Embedder 实例（懒加载）."""
        if self._embedder is None:
            from .embedder import get_embedder
            self._embedder = get_embedder()
        return self._embedder

    def _get_hybrid_search(self) -> "HybridSearch":
        """获取 HybridSearch 实例（懒加载）."""
        if self._hybrid_search is None:
            from .hybrid_search import get_hybrid_search
            self._hybrid_search = get_hybrid_search(
                vector_store=self._get_vector_store(),
                embedder=self._get_embedder(),
            )
        return self._hybrid_search

    def _get_importance_detector(self) -> "ImportanceDetector":
        """获取 ImportanceDetector 实例（懒加载）."""
        if self._importance_detector is None:
            from .importance_detector import ImportanceDetector
            self._importance_detector = ImportanceDetector()
        return self._importance_detector

    # ================================================================
    # 写入能力 (Write)
    # ================================================================

    async def summarize_recent_history(
        self,
        session_id: str,
        rounds: int = 15,
    ) -> str | None:
        """对历史会话最近 N 轮进行 LLM 总结，写入 MEMORY.md.

        在新会话创建时调用，将上一个会话的关键信息提炼为长期记忆。

        Args:
            session_id: 要总结的会话 ID
            rounds: 总结最近多少轮对话（1轮 = 1条user + 1条assistant）

        Returns:
            总结内容，如果无需总结则返回 None
        """
        message_limit = rounds * 2
        messages = await self._session_manager.get_latest_messages(
            session_id, limit=message_limit,
        )

        if not messages:
            logger.debug(
                "No messages to summarize",
                extra={"session_id": session_id},
            )
            return None

        # 只从 user/assistant 的实际对话中总结，跳过 system 消息
        # 避免从 system prompt 中的压缩 summary 里重复提取旧信息
        actual_messages = [
            msg for msg in messages
            if msg.role in ("user", "assistant")
        ]

        if not actual_messages:
            return None

        # 构建对话文本
        conversation_lines = []
        for msg in actual_messages:
            role_label = "用户" if msg.role == "user" else "助手"
            content_preview = (msg.content or "")[:500]
            conversation_lines.append(f"{role_label}: {content_preview}")

        conversation_text = "\n".join(conversation_lines)

        # 如果对话太短，不值得总结
        if len(conversation_text) < 100:
            logger.debug(
                "Conversation too short to summarize",
                extra={"session_id": session_id, "length": len(conversation_text)},
            )
            return None

        try:
            prompt = HISTORY_SUMMARY_PROMPT.format(conversation=conversation_text)
            response = await self._llm_router.chat(  # type: ignore[union-attr]
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            summary = response.content or ""  # type: ignore[union-attr]

            if not summary:
                return None

            # 写入 MEMORY.md
            self._append_to_memory_md(
                content=summary,
                category="会话总结",
                source=f"session:{session_id}",
            )

            # 同时写入日志 Markdown + 向量同步
            self._record_to_daily_log_and_vectors(
                content=summary,
                content_type=MemoryContentType.SUMMARY,
                metadata={"session_id": session_id, "rounds": rounds},
            )

            logger.info(
                "Memory write | session_summary",
                extra={
                    "scene": "session_summary",
                    "content_type": MemoryContentType.SUMMARY.value,
                    "session_id": session_id,
                    "rounds": rounds,
                    "summary_length": len(summary),
                    "content_preview": summary[:80],
                },
            )
            return summary

        except Exception as exc:
            logger.error(
                "Failed to summarize session history",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return None

    async def archive_before_compression(
        self,
        messages: list[dict[str, str]],
        session_id: str,
    ) -> list[dict[str, str]]:
        """压缩前提取重要信息归档到记忆.

        在上下文压缩触发前调用，从即将被压缩的消息中提取需要长期保留的信息。

        Args:
            messages: 即将被压缩的消息列表 [{"role": "...", "content": "..."}]
            session_id: 会话 ID

        Returns:
            提取出的重要信息条目列表
        """
        if not messages:
            return []

        # 只从 user/assistant 的实际对话中提取，跳过 system 消息和压缩 summary
        # 避免从 summary 中循环提取已有的旧偏好信息
        actual_messages = [
            msg for msg in messages
            if msg.get("role") in ("user", "assistant")
        ]

        if not actual_messages:
            return []

        # 构建对话文本
        conversation_lines = []
        for msg in actual_messages:
            role_label = "用户" if msg.get("role") == "user" else "助手"
            content_preview = (msg.get("content") or "")[:500]
            conversation_lines.append(f"{role_label}: {content_preview}")

        conversation_text = "\n".join(conversation_lines)

        # 先用规则检测快速过滤
        detector = self._get_importance_detector()
        has_potential = any(
            detector.is_important(msg.get("content", ""))
            for msg in actual_messages
            if msg.get("role") == "user"
        )

        if not has_potential and len(conversation_text) < 200:
            logger.debug(
                "No important content detected before compression",
                extra={"session_id": session_id},
            )
            return []

        try:
            # 读取已有记忆，注入 prompt 避免 LLM 重复提取
            existing_memories = self._get_existing_memory_entries()
            prompt = ARCHIVE_EXTRACTION_PROMPT.format(
                conversation=conversation_text,
                existing_memories=existing_memories,
            )
            response = await self._llm_router.chat(  # type: ignore[union-attr]
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            response_text = response.content or ""  # type: ignore[union-attr]
            extraction = self._parse_json_response(response_text)

            if not extraction.get("has_important_info"):
                return []

            archived_entries = []
            for item in extraction.get("entries", []):
                content = item.get("content", "")
                category = item.get("category", "其他")

                if not content:
                    continue

                # 写入 MEMORY.md
                self._append_to_memory_md(
                    content=content,
                    category=category,
                    source=f"compression-archive:{session_id}",
                )

                # 写入日志 + 向量
                self._record_to_daily_log_and_vectors(
                    content=content,
                    content_type=MemoryContentType.DECISION,
                    metadata={
                        "session_id": session_id,
                        "source": "compression_archive",
                        "category": category,
                    },
                )

                archived_entries.append({"content": content, "category": category})

            logger.info(
                "Memory write | compression_archive",
                extra={
                    "scene": "compression_archive",
                    "content_type": MemoryContentType.DECISION.value,
                    "session_id": session_id,
                    "archived_count": len(archived_entries),
                    "categories": [e.get("category", "") for e in archived_entries],
                },
            )
            return archived_entries

        except Exception as exc:
            logger.error(
                "Failed to archive before compression",
                extra={"session_id": session_id, "error": str(exc)},
            )
            return []

    def record_entry(
        self,
        content: str,
        content_type: str | MemoryContentType = MemoryContentType.MANUAL,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """直接写入一条记忆（Markdown + 向量同步）.

        供 agent 工具调用或手动记录使用。

        Args:
            content: 记忆内容
            content_type: 内容类型
            metadata: 扩展元数据

        Returns:
            是否写入成功
        """
        if isinstance(content_type, str):
            try:
                content_type = MemoryContentType(content_type)
            except ValueError:
                content_type = MemoryContentType.MANUAL

        meta = metadata or {}
        session_id = meta.get("session_id", "")

        logger.info(
            "Memory write | record_entry",
            extra={
                "scene": "record_entry",
                "content_type": content_type.value,
                "session_id": session_id,
                "content_preview": content[:80],
                "metadata_keys": list(meta.keys()),
            },
        )

        # 写入 MEMORY.md
        category = self._content_type_to_category(content_type)
        self._append_to_memory_md(
            content=content,
            category=category,
            source="manual",
        )

        # 写入日志 + 向量
        success = self._record_to_daily_log_and_vectors(
            content=content,
            content_type=content_type,
            metadata=meta,
        )

        logger.info(
            "Memory write completed | record_entry",
            extra={
                "scene": "record_entry",
                "content_type": content_type.value,
                "success": success,
            },
        )
        return success

    # ================================================================
    # 搜索能力 (Search)
    # ================================================================

    def search(
        self,
        query: str,
        limit: int = 10,
        offset: int = 0,
        content_type: MemoryContentType | None = None,
        min_score: float | None = None,
    ) -> list["SearchResult"]:
        """混合搜索记忆（文本 + 向量）.

        Args:
            query: 搜索查询
            limit: 返回结果数量上限
            offset: 分页偏移量
            content_type: 按内容类型过滤
            min_score: 最低相关度阈值（0-1），None 时从配置读取默认值

        Returns:
            搜索结果列表，按相关度排序
        """
        # min_score 未指定时从配置读取默认值
        if min_score is None:
            from ..config.manager import get_config
            min_score = get_config().search.min_score

        md_sync = self._get_md_sync()
        entries = md_sync.list_all_entries(limit=1000)

        if not entries:
            return []

        hybrid_search = self._get_hybrid_search()

        search_kwargs: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "min_score": min_score,
        }
        if content_type:
            search_kwargs["content_type"] = content_type

        results = hybrid_search.search(query, entries, **search_kwargs)

        logger.info(
            "Memory query | search",
            extra={
                "scene": "hybrid_search",
                "query": query[:80],
                "limit": limit,
                "offset": offset,
                "content_type": content_type.value if content_type else None,
                "min_score": min_score,
                "candidates_count": len(entries),
                "results_count": len(results),
                "top_score": round(results[0].score, 3) if results else None,
            },
        )
        return results

    def get_related_memories(self, query: str, limit: int = 5) -> list[str]:
        """获取与查询相关的记忆内容（简化版 search）.

        返回纯文本列表，适合直接拼入 LLM 上下文。

        Args:
            query: 搜索查询
            limit: 返回数量

        Returns:
            相关记忆内容列表
        """
        results = self.search(query, limit=limit)
        contents = [
            result.entry.content
            for result in results
            if hasattr(result, "entry") and result.entry.content
        ]

        logger.info(
            "Memory query | get_related_memories",
            extra={
                "scene": "get_related_memories",
                "query": query[:80],
                "limit": limit,
                "returned_count": len(contents),
            },
        )
        return contents

    def sync_to_vectors(self, file_path: str | None = None) -> int:
        """Markdown → 向量库同步.

        Args:
            file_path: 指定文件路径（增量同步），None 则全量同步

        Returns:
            同步的条目数量
        """
        md_sync = self._get_md_sync()
        vector_store = self._get_vector_store()
        embedder = self._get_embedder()

        if file_path:
            success = md_sync.sync_on_file_change(file_path, vector_store, embedder)
            synced = 1 if success else 0
        else:
            synced = md_sync.sync_all_entries_to_vector_store(vector_store, embedder)

        logger.info(
            "Vector sync completed",
            extra={
                "mode": "incremental" if file_path else "full",
                "synced_count": synced,
            },
        )
        return synced

    def delete_entry(self, entry_id: str) -> bool:
        """删除一条记忆（向量库 + Markdown）.

        Args:
            entry_id: 记忆条目 ID

        Returns:
            是否删除成功
        """
        try:
            vector_store = self._get_vector_store()
            deleted = vector_store.delete(entry_id)

            logger.info(
                "Memory entry deleted",
                extra={"entry_id": entry_id, "success": deleted},
            )
            return deleted
        except Exception as exc:
            logger.warning(
                "Failed to delete memory entry",
                extra={"entry_id": entry_id, "error": str(exc)},
            )
            return False

    # ================================================================
    # 会话能力 (Session)
    # ================================================================

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list["Message"]:
        """获取会话历史消息.

        Args:
            session_id: 会话 ID
            limit: 最大消息数

        Returns:
            消息列表（按时间正序）
        """
        return await self._session_manager.get_messages(session_id, limit=limit)

    async def get_session_history_as_agent_messages(
        self,
        session_id: str,
        limit: int = 200,
    ) -> list[Any]:
        """获取会话历史并转换为 AgentMessage 格式.

        用于 WebSocket 连接时将历史消息加载到 Agent 内存。

        Args:
            session_id: 会话 ID
            limit: 最大消息数

        Returns:
            AgentMessage 列表（UserMessage / AssistantMessage）
        """
        from ..agent_core.types import UserMessage, AssistantMessage, TextContent

        db_messages = await self._session_manager.get_messages(session_id, limit=limit)

        if not db_messages:
            return []

        agent_messages = []
        for msg in db_messages:
            text_content = TextContent(text=msg.content or "")
            if msg.role == "user":
                agent_messages.append(UserMessage(content=[text_content]))
            elif msg.role == "assistant":
                agent_messages.append(AssistantMessage(content=[text_content]))

        logger.info(
            "Session history loaded as AgentMessages",
            extra={
                "session_id": session_id,
                "loaded_count": len(agent_messages),
            },
        )
        return agent_messages

    async def get_recent_sessions(self, limit: int = 10) -> list[Any]:
        """获取最近的会话列表.

        Args:
            limit: 返回数量

        Returns:
            会话列表（按更新时间倒序）
        """
        return await self._session_manager.list_sessions(limit=limit)

    # ================================================================
    # 内部工具方法
    # ================================================================

    # ----------------------------------------------------------------
    # 已有记忆读取（供 LLM prompt 注入）
    # ----------------------------------------------------------------

    def _get_existing_memory_entries(self, max_entries: int = 30) -> str:
        """读取 MEMORY.md 中已有的记忆条目，用于注入 LLM prompt 避免重复提取.

        Args:
            max_entries: 最多返回的条目数（取最近的）

        Returns:
            格式化的已有记忆文本，如果没有则返回"（暂无）"
        """
        memory_md_path = self._workspace_path / "MEMORY.md"
        if not memory_md_path.exists():
            return "（暂无）"

        try:
            existing_text = memory_md_path.read_text(encoding="utf-8")
            entries = re.findall(
                r"- \*\*\[.*?\]\*\* \[.*?\] (.+)", existing_text,
            )
            if not entries:
                return "（暂无）"

            # 取最近的 max_entries 条
            recent_entries = entries[-max_entries:]
            return "\n".join(f"- {entry}" for entry in recent_entries)
        except Exception:
            return "（暂无）"

    # ----------------------------------------------------------------
    # 去重工具
    # ----------------------------------------------------------------

    _DEDUP_SIMILARITY_THRESHOLD = 0.85

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """计算两段文本的相似度 (0-1)."""
        return SequenceMatcher(None, text_a, text_b).ratio()

    def _is_duplicate_in_memory_md(self, content: str) -> bool:
        """检查 MEMORY.md 中是否已存在高度相似的条目."""
        memory_md_path = self._workspace_path / "MEMORY.md"
        if not memory_md_path.exists():
            return False

        try:
            existing_text = memory_md_path.read_text(encoding="utf-8")
            # 提取已有条目内容：匹配 "- **[...]** [...] 实际内容"
            existing_entries = re.findall(
                r"- \*\*\[.*?\]\*\* \[.*?\] (.+)", existing_text,
            )
            for existing_content in existing_entries:
                if self._text_similarity(content, existing_content) >= self._DEDUP_SIMILARITY_THRESHOLD:
                    return True
        except Exception:
            pass
        return False

    def _is_duplicate_in_daily_log(self, content: str, date_str: str) -> bool:
        """检查当天日志中是否已存在高度相似的条目."""
        log_path = self._workspace_path / "memory" / f"{date_str}.md"
        if not log_path.exists():
            return False

        try:
            existing_text = log_path.read_text(encoding="utf-8")
            # 提取已有条目内容：匹配 "### HH:MM:SS - type\n内容"
            existing_entries = re.findall(
                r"###\s*\d{2}:\d{2}(?::\d{2})?\s*-\s*\w+\s*\n(.+?)(?=###|$)",
                existing_text,
                re.DOTALL,
            )
            for existing_content in existing_entries:
                existing_stripped = existing_content.strip()
                if self._text_similarity(content, existing_stripped) >= self._DEDUP_SIMILARITY_THRESHOLD:
                    return True
        except Exception:
            pass
        return False

    # ----------------------------------------------------------------

    def _append_to_memory_md(
        self,
        content: str,
        category: str,
        source: str,
    ) -> None:
        """追加内容到 MEMORY.md 长期记忆文件."""
        memory_md_path = self._workspace_path / "MEMORY.md"

        try:
            # 确保文件存在
            if not memory_md_path.exists():
                self._workspace_path.mkdir(parents=True, exist_ok=True)
                template = (
                    "# 长期记忆\n\n"
                    "此文件存储经过提炼的持久化记忆摘要，跨日期的重要信息。\n\n"
                    "---\n\n"
                    "## 记忆条目\n\n"
                )
                memory_md_path.write_text(template, encoding="utf-8")

            # 去重：检查是否已存在高度相似的条目
            if self._is_duplicate_in_memory_md(content):
                logger.debug(
                    "Skipped duplicate entry in MEMORY.md",
                    extra={"category": category, "content_preview": content[:50]},
                )
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry_text = f"\n- **[{timestamp}]** [{category}] {content}\n"

            with open(memory_md_path, "a", encoding="utf-8") as file_handle:
                file_handle.write(entry_text)

            logger.debug(
                "Appended to MEMORY.md",
                extra={"category": category, "content_preview": content[:50]},
            )

        except Exception as exc:
            logger.error(
                "Failed to append to MEMORY.md",
                extra={"error": str(exc)},
            )

    def _record_to_daily_log_and_vectors(
        self,
        content: str,
        content_type: MemoryContentType,
        metadata: dict[str, Any],
    ) -> bool:
        """写入日志 Markdown 并同步到向量库."""
        # 去重：检查当天日志中是否已存在高度相似的条目
        date_str = datetime.now().strftime("%Y-%m-%d")
        if self._is_duplicate_in_daily_log(content, date_str):
            logger.debug(
                "Skipped duplicate entry in daily log",
                extra={
                    "content_type": content_type.value,
                    "content_preview": content[:80],
                },
            )
            return True

        md_sync = self._get_md_sync()

        entry = MemoryEntry(
            content=content,
            content_type=content_type,
            metadata=metadata,
        )

        logger.info(
            "Memory persist | daily_log + vector",
            extra={
                "scene": "daily_log_and_vectors",
                "entry_id": entry.id,
                "content_type": content_type.value,
                "content_preview": content[:80],
                "session_id": metadata.get("session_id", ""),
            },
        )

        # 写入日志 Markdown
        success = md_sync.append_memory_entry(entry)

        if success:
            # 同步到向量库
            try:
                vector_store = self._get_vector_store()
                embedder = self._get_embedder()
                md_sync.sync_entry_to_vector_store(entry, vector_store, embedder)
            except Exception as exc:
                logger.warning(
                    "Vector sync failed for entry (non-fatal)",
                    extra={
                        "entry_id": entry.id,
                        "content_type": content_type.value,
                        "error": str(exc),
                    },
                )
        else:
            logger.warning(
                "Failed to persist entry to daily log",
                extra={
                    "entry_id": entry.id,
                    "content_type": content_type.value,
                },
            )

        return success

    @staticmethod
    def _content_type_to_category(content_type: MemoryContentType) -> str:
        """将 MemoryContentType 映射为 MEMORY.md 中的分类标签."""
        mapping = {
            MemoryContentType.DECISION: "决策",
            MemoryContentType.MANUAL: "记录",
            MemoryContentType.SUMMARY: "总结",
            MemoryContentType.CONVERSATION: "对话",
            MemoryContentType.EXPERIENCE: "经验",
        }
        return mapping.get(content_type, "其他")

    @staticmethod
    def _parse_json_response(response_text: str) -> dict[str, Any]:
        """从 LLM 响应中解析 JSON."""
        text = response_text.strip()

        # 去除 markdown 代码块包裹
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            return json.loads(text.strip())
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Failed to parse JSON from LLM response",
                extra={"response_preview": response_text[:100]},
            )
            return {}


# ================================================================
# 全局单例
# ================================================================

_memory_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """获取全局 MemoryManager 实例.

    必须先调用 init_memory_manager() 初始化。

    Returns:
        MemoryManager 实例

    Raises:
        RuntimeError: 如果未初始化
    """
    if _memory_manager is None:
        raise RuntimeError(
            "MemoryManager not initialized. Call init_memory_manager() first."
        )
    return _memory_manager


def init_memory_manager(
    workspace_path: str,
    llm_router: "LLMRouter",
    session_manager: "SessionManager",
) -> MemoryManager:
    """初始化全局 MemoryManager 实例.

    Args:
        workspace_path: workspace 目录路径
        llm_router: LLM 路由器
        session_manager: 会话管理器

    Returns:
        初始化后的 MemoryManager 实例
    """
    global _memory_manager
    _memory_manager = MemoryManager(
        workspace_path=workspace_path,
        llm_router=llm_router,
        session_manager=session_manager,
    )
    return _memory_manager
