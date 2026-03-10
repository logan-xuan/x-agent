
"""首次启动自动注册默认实体。

Agent 和 Channel 已全部改为配置驱动（从 x-agent.yaml 加载），
此模块仅负责确保默认 User 在数据库中存在。

默认实体使用固定的 well-known ID，确保幂等性（多次调用不会重复创建）。
"""

from __future__ import annotations

from ...services.storage import get_storage_service
from ...utils.logger import get_logger
from .dao import UserDAO

logger = get_logger(__name__)

# 固定的默认实体 ID，确保幂等
# 与 x-agent.yaml 中的 multi_agent.channels[*].default_user 保持一致
DEFAULT_USER_ID = "admin"
DEFAULT_AGENT_ID = "main-agent"
DEFAULT_CHANNEL_ID = "web_channel"  # web chat 交互默认 channel
CLI_CHANNEL_ID = "cli_channel"  # CLI 交互默认 channel

async def ensure_default_entities(workspace_path: str | None = None) -> None:
    """确保默认 User 存在。

    Agent 和 Channel 已全部从配置加载，无需在此创建或同步。
    仅在首次启动时创建默认用户。

    Args:
        workspace_path: workspace 目录的绝对路径（保留参数兼容性，不再使用）。
    """
    storage = get_storage_service()
    user_dao = UserDAO(storage)

    existing_user = await user_dao.get_by_id(DEFAULT_USER_ID)
    if existing_user is not None:
        logger.info("默认用户已存在，跳过初始化", extra={"user_id": DEFAULT_USER_ID})
        return

    await user_dao.create(name="用户", user_id=DEFAULT_USER_ID)

    logger.info(
        "默认实体初始化完成",
        extra={"user_id": DEFAULT_USER_ID},
    )
