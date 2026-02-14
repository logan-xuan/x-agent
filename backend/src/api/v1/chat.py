"""Chat API endpoints."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...core.agent import Agent

router = APIRouter(prefix="/chat", tags=["chat"])

# Global agent instance
_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create agent instance."""
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    session_id: str


class ChatResponse(BaseModel):
    """Chat response model."""
    type: str
    role: str
    content: str
    session_id: str
    model: str | None = None


class CreateSessionRequest(BaseModel):
    """Create session request."""
    title: str | None = None


class CreateSessionResponse(BaseModel):
    """Create session response."""
    id: str
    title: str | None
    created_at: str | None
    updated_at: str | None
    message_count: int


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest) -> CreateSessionResponse:
    """Create a new chat session."""
    agent = get_agent()
    session = await agent.create_session(request.title)
    return CreateSessionResponse(**session)


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a chat message (non-streaming)."""
    agent = get_agent()
    response = await agent.chat(
        session_id=request.session_id,
        user_message=request.message,
        stream=False
    )
    
    if response.get("type") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=response.get("error", "Unknown error")
        )
    
    return ChatResponse(**response)


@router.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str) -> list[dict]:
    """Get session message history."""
    agent = get_agent()
    return await agent.get_session_history(session_id)
