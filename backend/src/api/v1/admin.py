"""管理后台 API。

提供 User、Agent、Channel、ChatSession 的查看和管理功能，
通过简单密码认证保护。
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

from ...services.storage import get_storage_service
from ...conversation.dao.dao import AgentDAO, ChannelDAO, ChatSessionDAO, UserDAO
from ...conversation.dao.models import SessionStatus
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
    """更新 Agent 信息。"""
    storage = get_storage_service()
    agent_dao = AgentDAO(storage)

    current_agent = await agent_dao.get_by_id(agent_id)
    if current_agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    if request.agent_name is not None:
        result = await agent_dao.update_name(agent_id, request.agent_name)
        if result is not None:
            current_agent = result
    if request.agent_persona is not None:
        result = await agent_dao.update_persona(agent_id, request.agent_persona)
        if result is not None:
            current_agent = result

    return AgentResponse(
        agent_id=current_agent.agent_id,
        agent_name=current_agent.agent_name,
        agent_type=current_agent.agent_type,
        agent_persona=current_agent.agent_persona,
        user_id=current_agent.user_id,
        workspace=current_agent.workspace,
        feature=current_agent.feature,
        create_time=None,  # 配置驱动下无创建时间
    )


@router.delete("/admin/agents/{agent_id}")
async def delete_agent(
    agent_id: str, _: None = Depends(verify_admin)
) -> dict:
    """删除 Agent（级联删除关联数据）。"""
    storage = get_storage_service()
    agent_dao = AgentDAO(storage)
    deleted = await agent_dao.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"success": True, "message": f"Agent {agent_id} 已删除"}


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
    """删除 Channel（级联删除关联会话）。"""
    storage = get_storage_service()
    channel_dao = ChannelDAO(storage)
    deleted = await channel_dao.delete(channel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel 不存在")
    return {"success": True, "message": f"Channel {channel_id} 已删除"}


# ---------------------------------------------------------------------------
# ChatSession 管理
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    session_id: str
    session_name: str
    user_id: str
    agent_id: str
    channel_id: str
    status: str
    create_time: Optional[str] = None
    updated_at: Optional[str] = None


class UpdateSessionStatusRequest(BaseModel):
    status: str = Field(..., description="新状态：active / closed / archived")


@router.get("/admin/sessions", response_model=list[SessionResponse])
async def list_sessions(_: None = Depends(verify_admin)) -> list[SessionResponse]:
    """列出所有 ChatSession。"""
    storage = get_storage_service()
    session_dao = ChatSessionDAO(storage)
    user_dao = UserDAO(storage)
    users = await user_dao.list_all()
    all_sessions = []
    for user in users:
        sessions = await session_dao.list_by_user(user.user_id)
        all_sessions.extend(sessions)
    return [
        SessionResponse(
            session_id=s.session_id,
            session_name=s.session_name,
            user_id=s.user_id,
            agent_id=s.agent_id,
            channel_id=s.channel_id,
            status=s.status,
            create_time=s.create_time.isoformat() if s.create_time else None,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )
        for s in all_sessions
    ]


@router.put("/admin/sessions/{session_id}/status", response_model=SessionResponse)
async def update_session_status(
    session_id: str,
    request: UpdateSessionStatusRequest,
    _: None = Depends(verify_admin),
) -> SessionResponse:
    """更新会话状态。"""
    try:
        new_status = SessionStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效状态：{request.status}，可选值：active / closed / archived",
        )

    storage = get_storage_service()
    session_dao = ChatSessionDAO(storage)
    session = await session_dao.update_status(session_id, new_status)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return SessionResponse(
        session_id=session.session_id,
        session_name=session.session_name,
        user_id=session.user_id,
        agent_id=session.agent_id,
        channel_id=session.channel_id,
        status=session.status,
        create_time=session.create_time.isoformat() if session.create_time else None,
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
    )


@router.delete("/admin/sessions/{session_id}")
async def delete_session(
    session_id: str, _: None = Depends(verify_admin)
) -> dict:
    """删除会话。"""
    storage = get_storage_service()
    session_dao = ChatSessionDAO(storage)
    deleted = await session_dao.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": f"会话 {session_id} 已删除"}
