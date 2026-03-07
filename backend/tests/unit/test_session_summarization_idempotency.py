"""测试 SessionManager 会话总结的幂等保护。

验证同一个会话不会被重复总结，防止 MEMORY.md 出现重复条目。
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.conversation.session import SessionManager
from src.models.session import Session


def _make_session(session_id: str, message_count: int = 5) -> Session:
    """创建一个模拟的 Session 对象。"""
    session = MagicMock(spec=Session)
    session.id = session_id
    session.message_count = message_count
    session.title = f"Test Session {session_id}"
    session.created_at = datetime.utcnow()
    session.updated_at = datetime.utcnow()
    return session


class TestSummarizationIdempotency:
    """验证 _trigger_history_summarization 的幂等保护。"""

    def setup_method(self):
        """每个测试前清空类级别的去重集合。"""
        SessionManager._summarized_session_ids.clear()

    def test_same_session_only_summarized_once(self):
        """同一个 session_id 只应触发一次总结任务。"""
        manager = SessionManager(storage=MagicMock())

        previous_sessions = [
            _make_session("prev-session-001", message_count=10),
            _make_session("prev-session-002", message_count=3),
        ]

        created_tasks = []
        original_create_task = asyncio.create_task

        with patch("asyncio.create_task") as mock_create_task:
            mock_create_task.side_effect = lambda coro, **kwargs: created_tasks.append(kwargs.get("name")) or MagicMock()

            # 第一次调用：应该创建任务
            manager._trigger_history_summarization(previous_sessions, "new-session-001")
            assert len(created_tasks) == 1

            # 第二次调用（模拟重复触发）：应该被跳过
            manager._trigger_history_summarization(previous_sessions, "new-session-002")
            assert len(created_tasks) == 1  # 仍然是 1，没有新增

    def test_different_sessions_both_summarized(self):
        """不同的 session_id 应该各自触发一次总结。"""
        manager = SessionManager(storage=MagicMock())

        created_tasks = []

        with patch("asyncio.create_task") as mock_create_task:
            mock_create_task.side_effect = lambda coro, **kwargs: created_tasks.append(kwargs.get("name")) or MagicMock()

            # 第一个会话的 previous
            sessions_batch_1 = [
                _make_session("prev-session-A", message_count=5),
            ]
            manager._trigger_history_summarization(sessions_batch_1, "new-001")
            assert len(created_tasks) == 1

            # 第二个会话的 previous（不同的 target）
            sessions_batch_2 = [
                _make_session("prev-session-B", message_count=8),
            ]
            manager._trigger_history_summarization(sessions_batch_2, "new-002")
            assert len(created_tasks) == 2

    def test_no_previous_session_with_messages(self):
        """没有有消息的历史会话时，不应触发总结。"""
        manager = SessionManager(storage=MagicMock())

        previous_sessions = [
            _make_session("empty-session", message_count=0),
        ]

        with patch("asyncio.create_task") as mock_create_task:
            manager._trigger_history_summarization(previous_sessions, "new-session")
            mock_create_task.assert_not_called()

    def test_idempotency_shared_across_instances(self):
        """去重集合是类级别的，跨实例共享。"""
        manager_a = SessionManager(storage=MagicMock())
        manager_b = SessionManager(storage=MagicMock())

        previous_sessions = [
            _make_session("shared-prev", message_count=5),
        ]

        created_tasks = []

        with patch("asyncio.create_task") as mock_create_task:
            mock_create_task.side_effect = lambda coro, **kwargs: created_tasks.append(1) or MagicMock()

            # 实例 A 触发
            manager_a._trigger_history_summarization(previous_sessions, "new-a")
            assert len(created_tasks) == 1

            # 实例 B 对同一个 session 触发：应该被跳过
            manager_b._trigger_history_summarization(previous_sessions, "new-b")
            assert len(created_tasks) == 1
