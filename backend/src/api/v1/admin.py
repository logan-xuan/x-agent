"""管理后台 API。

提供 User、Agent、Channel、Session 的查看和管理功能，
通过简单密码认证保护。
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from ...services.storage import get_storage_service
from ...conversation.dao.dao import UserDAO
from ...utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# 默认管理密码
ADMIN_PASSWORD = "88888"

# 简单的 token（密码验证通过后前端携带此 token）
ADMIN_TOKEN = "x-agent-admin-token-88888"


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str = ""


def verify_admin(x_admin_token: str = Header(..., alias="X-Admin-Token")) -> None:
    """验证管理员 token，所有管理接口都需要此依赖。"""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="未授权访问")


@router.post("/admin/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest) -> LoginResponse:
    """管理员登录。

    验证密码，返回 token 供后续请求使用。
    """
    if request.password == ADMIN_PASSWORD:
        logger.info("管理员登录成功")
        return LoginResponse(success=True, token=ADMIN_TOKEN, message="登录成功")
    logger.warning("管理员登录失败：密码错误")
    return LoginResponse(success=False, message="密码错误")


# ---------------------------------------------------------------------------
# User 管理
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    user_id: str
    name: str
    create_time: Optional[str] = None


class UpdateUserRequest(BaseModel):
    name: str


@router.get("/admin/users", response_model=list[UserResponse])
async def list_users(_: None = Depends(verify_admin)) -> list[UserResponse]:
    """列出所有用户。"""
    storage = get_storage_service()
    user_dao = UserDAO(storage)
    users = await user_dao.list_all()
    return [
        UserResponse(
            user_id=user.user_id,
            name=user.name,
            create_time=user.create_time.isoformat() if user.create_time else None,
        )
        for user in users
    ]


@router.put("/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    _: None = Depends(verify_admin),
) -> UserResponse:
    """更新用户信息。"""
    storage = get_storage_service()
    user_dao = UserDAO(storage)
    user = await user_dao.update_name(user_id, request.name)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserResponse(
        user_id=user.user_id,
        name=user.name,
        create_time=user.create_time.isoformat() if user.create_time else None,
    )


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str, _: None = Depends(verify_admin)
) -> dict:
    """删除用户（级联删除关联数据）。"""
    storage = get_storage_service()
    user_dao = UserDAO(storage)
    deleted = await user_dao.delete(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "message": f"用户 {user_id} 已删除"}


# ---------------------------------------------------------------------------
# Agent 管理
# ---------------------------------------------------------------------------

class AgentResponse(BaseModel):
    agent_id: str
    agent_name: str
    agent_type: str
    agent_persona: str
    user_id: str
    workspace: str = ""
    feature: str = ""
    create_time: Optional[str] = None  # 配置驱动下无创建时间


class UpdateAgentRequest(BaseModel):
    agent_name: Optional[str] = None
    agent_persona: Optional[str] = None


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents_public() -> list[AgentResponse]:
    """列出所有 Agent（公开接口，无需认证）。"""
    from ...conversation.dao.models import Agent

    all_agents = Agent.list_all()
    return [
        AgentResponse(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            agent_type=agent.agent_type,
            agent_persona=agent.agent_persona,
            user_id=agent.user_id,
            workspace=agent.workspace,
            feature=agent.feature,
            create_time=None,
        )
        for agent in all_agents
    ]


@router.get("/admin/agents", response_model=list[AgentResponse])
async def list_agents(_: None = Depends(verify_admin)) -> list[AgentResponse]:
    """列出所有 Agent（配置驱动，直接从配置加载）。"""
    from ...conversation.dao.models import Agent

    all_agents = Agent.list_all()
    return [
        AgentResponse(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            agent_type=agent.agent_type,
            agent_persona=agent.agent_persona,
            user_id=agent.user_id,
            workspace=agent.workspace,
            feature=agent.feature,
            create_time=None,
        )
        for agent in all_agents
    ]


@router.put("/admin/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    _: None = Depends(verify_admin),
) -> AgentResponse:
    """更新 Agent 信息（配置驱动，仅返回当前配置，不支持持久化修改）。"""
    from ...conversation.dao.models import Agent

    current_agent = Agent.from_config(agent_id)
    if current_agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    return AgentResponse(
        agent_id=current_agent.agent_id,
        agent_name=current_agent.agent_name,
        agent_type=current_agent.agent_type,
        agent_persona=current_agent.agent_persona,
        user_id=current_agent.user_id,
        workspace=current_agent.workspace,
        feature=current_agent.feature,
        create_time=None,
    )

@router.delete("/admin/agents/{agent_id}")
async def delete_agent(
    agent_id: str, _: None = Depends(verify_admin)
) -> dict:
    """删除 Agent（配置驱动，不支持删除）。"""
    from ...conversation.dao.models import Agent

    agent = Agent.from_config(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    raise HTTPException(status_code=400, detail="Agent 由配置文件管理，不支持通过 API 删除")


# ---------------------------------------------------------------------------
# Channel 管理
# ---------------------------------------------------------------------------

class ChannelResponse(BaseModel):
    channel_id: str
    channel_type: str
    channel_protocol: str
    user_id: str
    agent_id: str
    create_time: Optional[str] = None


@router.get("/admin/channels", response_model=list[ChannelResponse])
async def list_channels(_: None = Depends(verify_admin)) -> list[ChannelResponse]:
    """列出所有 Channel（配置驱动，直接从配置加载）。"""
    from ...conversation.dao.models import Channel

    all_channels = Channel.list_all()
    return [
        ChannelResponse(
            channel_id=ch.channel_id,
            channel_type=ch.channel_type,
            channel_protocol=ch.channel_protocol,
            user_id=ch.user_id,
            agent_id=ch.agent_id,
            create_time=None,
        )
        for ch in all_channels
    ]


@router.delete("/admin/channels/{channel_id}")
async def delete_channel(
    channel_id: str, _: None = Depends(verify_admin)
) -> dict:
    """删除 Channel（配置驱动，不支持删除）。"""
    from ...conversation.dao.models import Channel

    channel = Channel.from_config(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel 不存在")
    raise HTTPException(status_code=400, detail="Channel 由配置文件管理，不支持通过 API 删除")


# ---------------------------------------------------------------------------
# Session 管理（使用 SessionManager，基于 sessions 表）
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    session_id: str
    session_name: str
    user_id: str = ""
    agent_id: str = ""
    channel_id: str = ""
    status: str
    create_time: Optional[str] = None
    updated_at: Optional[str] = None

class UpdateSessionStatusRequest(BaseModel):
    status: str = Field(..., description="新状态：active / closed")

def _session_to_response(s) -> SessionResponse:
    """将 Session ORM 对象转为 SessionResponse。"""
    return SessionResponse(
        session_id=s.id,
        session_name=s.title or "未命名",
        agent_id=s.agent_id or "",
        status=s.status,
        create_time=s.created_at.isoformat() if s.created_at else None,
        updated_at=s.updated_at.isoformat() if s.updated_at else None,
    )

@router.get("/admin/sessions", response_model=list[SessionResponse])
async def list_sessions(_: None = Depends(verify_admin)) -> list[SessionResponse]:
    """列出所有 Session（基于 sessions 表）。"""
    from ...conversation.session import SessionManager
    session_manager = SessionManager()
    sessions = await session_manager.list_sessions(limit=200)
    return [
        SessionResponse(
            session_id=s.id,
            session_name=s.title or "未命名",
            agent_id=s.agent_id or "",
            status=s.status,
            create_time=s.created_at.isoformat() if s.created_at else None,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s in sessions
    ]

@router.put("/admin/sessions/{session_id}/status", response_model=SessionResponse)
async def update_session_status(
    session_id: str,
    request: UpdateSessionStatusRequest,
    _: None = Depends(verify_admin),
) -> SessionResponse:
    """更新会话状态。"""
    from ...models.session import SessionStatus as WebSessionStatus
    try:
        new_status = WebSessionStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效状态：{request.status}，可选值：active / closed",
        )

    from ...conversation.session import SessionManager
    from sqlalchemy import select
    from ...models.session import Session

    session_manager = SessionManager()
    async with session_manager._storage.session() as db_session:
        session = await db_session.get(Session, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        session.status = new_status.value
        from datetime import datetime
        session.updated_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(session)
    return _session_to_response(session)

@router.delete("/admin/sessions/{session_id}")
async def delete_session(
    session_id: str, _: None = Depends(verify_admin),
) -> dict:
    """删除会话。"""
    from ...conversation.session import SessionManager
    session_manager = SessionManager()
    deleted = await session_manager.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": f"会话 {session_id} 已删除"}