"""会话 DAO 层测试的公共 fixture。

提供基于内存 SQLite 的 StorageService，每个测试函数独立建表，
确保测试之间完全隔离。
"""

import pytest

from src.services.storage import StorageService
from src.conversation.dao.dao import UserDAO


@pytest.fixture
async def storage():
    """创建基于内存 SQLite 的 StorageService，测试结束后自动关闭。"""
    service = StorageService(database_url="sqlite+aiosqlite:///:memory:")
    await service.initialize()
    yield service
    await service.close()


@pytest.fixture
def user_dao(storage: StorageService) -> UserDAO:
    return UserDAO(storage)


@pytest.fixture
def agent_dao(storage: StorageService) -> AgentDAO:
    return AgentDAO(storage)


@pytest.fixture
def channel_dao(storage: StorageService) -> ChannelDAO:
    return ChannelDAO(storage)


@pytest.fixture
def session_dao(storage: StorageService) -> ChatSessionDAO:
    return ChatSessionDAO(storage)


@pytest.fixture
async def default_user(user_dao: UserDAO):
    """创建一个默认用户，供其他 fixture 使用。"""
    return await user_dao.create(name="测试用户", user_id="test-user")


@pytest.fixture
async def default_agent(agent_dao: AgentDAO, default_user):
    """创建一个默认 Agent，依赖 default_user。"""
    return await agent_dao.create(
        agent_name="测试Agent",
        user_id=default_user.user_id,
        agent_type="main",
        agent_persona="测试人设",
        agent_id="test-agent",
    )


@pytest.fixture
async def default_channel(channel_dao: ChannelDAO, default_user, default_agent):
    """创建一个默认 Channel，依赖 default_user 和 default_agent。"""
    return await channel_dao.create(
        channel_type="web_chat",
        user_id=default_user.user_id,
        agent_id=default_agent.agent_id,
        channel_protocol="websocket",
        channel_id="test-channel",
    )
