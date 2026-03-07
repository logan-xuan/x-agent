"""首次启动自动注册默认实体 & 文件变更同步。

提供两类功能：
1. ensure_default_entities() — 应用启动时确保默认 User/Agent/Channel 存在
2. _sync_*_to_db() — 文件监听回调，当 OWNER.md / IDENTITY.md / SPIRIT.md
   被修改时，同步更新 DB 中的 User 和 Agent

默认实体使用固定的 well-known ID，确保幂等性（多次调用不会重复创建）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...services.storage import get_storage_service
from ...utils.logger import get_logger
from .dao import AgentDAO, UserDAO, ChannelDAO

logger = get_logger(__name__)

# 固定的默认实体 ID，确保幂等
DEFAULT_USER_ID = "default-user"
DEFAULT_AGENT_ID = "default-agent"
DEFAULT_CHANNEL_ID = "default-channel"


async def ensure_default_entities(workspace_path: str | None = None) -> None:
    """确保默认的 User、Agent、Channel 存在。

    首次启动时自动创建，后续启动同步 SPIRIT.md 人设。

    Args:
        workspace_path: workspace 目录的绝对路径。
            如果未提供，则尝试从配置中获取。
    """
    storage = get_storage_service()
    user_dao = UserDAO(storage)
    agent_dao = AgentDAO(storage)
    channel_dao = ChannelDAO(storage)

    # 解析 workspace 路径
    resolved_workspace = _resolve_workspace_path(workspace_path)

    # 从 SPIRIT.md 读取人设（完整内容）
    initial_persona = _read_spirit_content(resolved_workspace)

    # 检查默认用户是否存在
    existing_user = await user_dao.get_by_id(DEFAULT_USER_ID)
    if existing_user is not None:
        # 已存在 → 仅同步 SPIRIT.md 人设到 Agent（确保每次启动都同步最新状态）
        if initial_persona:
            await agent_dao.update_persona(DEFAULT_AGENT_ID, initial_persona)
            logger.info(
                "启动同步：SPIRIT.md → Agent 人设已更新",
                extra={"persona_length": len(initial_persona)},
            )
        return

    # 创建默认用户
    await user_dao.create(name="用户", user_id=DEFAULT_USER_ID)

    # 创建默认 Agent
    await agent_dao.create(
        agent_name="X-Agent",
        user_id=DEFAULT_USER_ID,
        agent_type="main",
        agent_persona=initial_persona,
        agent_id=DEFAULT_AGENT_ID,
    )

    # 创建默认 Channel（WEB_CHAT + WEBSOCKET）
    await channel_dao.create(
        channel_type="web_chat",
        user_id=DEFAULT_USER_ID,
        agent_id=DEFAULT_AGENT_ID,
        channel_protocol="websocket",
        channel_id=DEFAULT_CHANNEL_ID,
    )

    logger.info(
        "默认实体初始化完成",
        extra={
            "user_id": DEFAULT_USER_ID,
            "agent_id": DEFAULT_AGENT_ID,
            "channel_id": DEFAULT_CHANNEL_ID,
            "persona_length": len(initial_persona),
        },
    )


def _resolve_workspace_path(workspace_path: str | None) -> Path:
    """解析 workspace 目录的绝对路径。

    优先使用传入的路径，否则从配置中读取并解析。
    """
    if workspace_path is not None:
        return Path(workspace_path)

    try:
        from ...config.manager import ConfigManager
        config = ConfigManager().config
        raw_path = config.workspace.path
        expanded = Path(raw_path).expanduser()
        if expanded.is_absolute():
            return expanded.resolve()
        backend_src_dir = Path(__file__).parent.parent.parent
        return (backend_src_dir / raw_path).resolve()
    except Exception:
        return Path(__file__).parent.parent.parent.parent / "workspace"


def _read_spirit_content(workspace: Path) -> str:
    """直接读取 SPIRIT.md 的完整文本内容作为人设。

    不依赖 MarkdownSync 的结构化解析，因为用户可能自由编辑格式。
    """
    spirit_path = workspace / "SPIRIT.md"
    logger.debug(
        "尝试读取 SPIRIT.md",
        extra={"path": str(spirit_path), "exists": spirit_path.exists()},
    )
    if not spirit_path.exists():
        return ""
    try:
        return spirit_path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("读取 SPIRIT.md 失败", extra={"error": str(exc)})
        return ""


# ---------------------------------------------------------------------------
# 文件变更 → DB 同步回调
# ---------------------------------------------------------------------------
# file_watcher 的回调在 watchdog 线程中执行（非 async），
# 所以需要通过 asyncio.run_coroutine_threadsafe 桥接到事件循环。

def _sync_owner_to_db(workspace_path: str) -> None:
    """OWNER.md 变更时，同步更新 DB 中的 User.name。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("无法获取事件循环，跳过 OWNER.md 同步")
        return

    asyncio.run_coroutine_threadsafe(_async_sync_owner(workspace_path), loop)


async def _async_sync_owner(workspace_path: str) -> None:
    """异步执行：解析 OWNER.md 并更新 User.name。"""
    try:
        from ...memory.md_sync import MarkdownSync
        md_sync = MarkdownSync(workspace_path)
        owner = md_sync.load_owner()
        if owner is None or not owner.name:
            return

        storage = get_storage_service()
        user_dao = UserDAO(storage)
        await user_dao.update_name(DEFAULT_USER_ID, owner.name)
        logger.info("OWNER.md → User 同步完成", extra={"name": owner.name})
    except Exception as exc:
        logger.warning("OWNER.md → User 同步失败", extra={"error": str(exc)})


def _sync_identity_to_db(workspace_path: str) -> None:
    """IDENTITY.md 变更时，同步更新 DB 中的 Agent.agent_name。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("无法获取事件循环，跳过 IDENTITY.md 同步")
        return

    asyncio.run_coroutine_threadsafe(_async_sync_identity(workspace_path), loop)


async def _async_sync_identity(workspace_path: str) -> None:
    """异步执行：解析 IDENTITY.md 并更新 Agent.agent_name。

    IDENTITY.md 由 Agent 自由写入，格式示例::

        # 虾铁蛋的身份认知
        **姓名**: 虾铁蛋 🦐

    从中提取 **姓名** 字段作为 agent_name。
    """
    import re

    try:
        identity_path = Path(workspace_path) / "IDENTITY.md"
        if not identity_path.exists():
            return

        content = identity_path.read_text(encoding="utf-8")

        # 提取 **姓名**: xxx 格式的名字
        name_match = re.search(r"\*\*姓名\*\*\s*[:：]\s*(.+)", content)
        if not name_match:
            return

        # 去除 emoji 和多余空白，保留核心名字
        raw_name = name_match.group(1).strip()
        # 移除尾部 emoji（保留中文/英文/数字部分）
        clean_name = re.sub(r"\s*[\U00010000-\U0010ffff]+\s*$", "", raw_name).strip()
        if not clean_name:
            clean_name = raw_name

        storage = get_storage_service()
        agent_dao = AgentDAO(storage)
        await agent_dao.update_name(DEFAULT_AGENT_ID, clean_name)
        logger.info("IDENTITY.md → Agent 同步完成", extra={"agent_name": clean_name})
    except Exception as exc:
        logger.warning("IDENTITY.md → Agent 同步失败", extra={"error": str(exc)})


def _sync_spirit_to_db(workspace_path: str) -> None:
    """SPIRIT.md 变更时，同步更新 DB 中的 Agent.agent_persona。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("无法获取事件循环，跳过 SPIRIT.md 同步")
        return

    asyncio.run_coroutine_threadsafe(_async_sync_spirit(workspace_path), loop)


async def _async_sync_spirit(workspace_path: str) -> None:
    """异步执行：读取 SPIRIT.md 完整内容并更新 Agent.agent_persona。

    直接使用文件全文作为人设，不依赖结构化解析，
    因为用户可能自由编辑 SPIRIT.md 的格式。
    """
    try:
        spirit_path = Path(workspace_path) / "SPIRIT.md"
        if not spirit_path.exists():
            return

        content = spirit_path.read_text(encoding="utf-8").strip()
        if not content:
            return

        storage = get_storage_service()
        agent_dao = AgentDAO(storage)
        await agent_dao.update_persona(DEFAULT_AGENT_ID, content)
        logger.info(
            "SPIRIT.md → Agent 同步完成",
            extra={"persona_length": len(content)},
        )
    except Exception as exc:
        logger.warning("SPIRIT.md → Agent 同步失败", extra={"error": str(exc)})
