"""Context API endpoints for agent guidance system.

This module provides REST API endpoints for:
- Loading context with session awareness
- Reloading AGENTS.md on user queries
- Getting loaded file information
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...utils.logger import get_logger
from ...memory.models import SessionType, ContextBundle

logger = get_logger(__name__)

router = APIRouter(prefix="/context", tags=["context"])


# ============ Request/Response Models ============

class ContextLoadRequest(BaseModel):
    """Request for loading context."""
    session_id: str = Field(description="会话唯一标识")
    session_type: str = Field(default="main", description="会话类型: main 或 shared")
    workspace_path: Optional[str] = Field(default=None, description="workspace 目录路径")


class FileLoadResultResponse(BaseModel):
    """File load result in response."""
    file_path: str
    success: bool
    content_length: int = 0
    error: Optional[str] = None
    from_cache: bool = False
    is_default: bool = False


class ContextLoadResponse(BaseModel):
    """Response for context loading."""
    success: bool
    session_id: str
    session_type: str
    loaded_files: list[FileLoadResultResponse] = []
    context_version: Optional[str] = None
    load_time_ms: int = 0
    errors: list[str] = []


class ContextReloadRequest(BaseModel):
    """Request for reloading AGENTS.md."""
    session_id: str = Field(description="会话标识")
    force_reload: bool = Field(default=False, description="强制重新加载")


class ContextReloadResponse(BaseModel):
    """Response for AGENTS.md reload."""
    success: bool
    reloaded: bool = Field(description="是否实际执行了重载")
    previous_version: Optional[str] = None
    current_version: Optional[str] = None
    reload_time_ms: float = 0


class ContextFileInfo(BaseModel):
    """Information about a loaded context file."""
    name: str
    path: str
    loaded: bool
    from_cache: bool = False
    is_default: bool = False
    last_modified: Optional[str] = None
    size_bytes: int = 0


class ContextFilesResponse(BaseModel):
    """Response for context files list."""
    session_id: str
    files: list[ContextFileInfo]


# ============ Endpoints ============

@router.post("/load", response_model=ContextLoadResponse)
async def load_context(request: ContextLoadRequest) -> ContextLoadResponse:
    """Load agent context based on session type.
    
    Loads all context files including:
    - AGENTS.md (main guidance)
    - SPIRIT.md (AI identity)
    - OWNER.md (user profile)
    - TOOLS.md (tool definitions)
    - MEMORY.md (only in main sessions)
    - Daily memory files (today + yesterday)
    """
    from ...core.context_loader import get_context_loader
    
    logger.info(
        "Loading context",
        extra={
            "session_id": request.session_id,
            "session_type": request.session_type
        }
    )
    
    try:
        # Parse session type
        try:
            session_type = SessionType(request.session_type.lower())
        except ValueError:
            session_type = SessionType.MAIN
        
        # Get context loader
        workspace_path = request.workspace_path or "workspace"
        loader = get_context_loader(workspace_path)
        
        # Load context
        context = loader.load_context(
            session_id=request.session_id,
            session_type=session_type
        )
        
        # Build response
        loaded_files = [
            FileLoadResultResponse(
                file_path=f,
                success=True,
                content_length=0,  # Would need more tracking
                from_cache=False,
                is_default=False
            )
            for f in context.loaded_files
        ]
        
        return ContextLoadResponse(
            success=True,
            session_id=request.session_id,
            session_type=request.session_type,
            loaded_files=loaded_files,
            context_version=f"v1-{context.loaded_at.isoformat()}",
            load_time_ms=context.load_time_ms
        )
        
    except Exception as e:
        logger.error(
            "Failed to load context",
            extra={
                "session_id": request.session_id,
                "error": str(e)
            }
        )
        return ContextLoadResponse(
            success=False,
            session_id=request.session_id,
            session_type=request.session_type,
            errors=[str(e)]
        )


@router.post("/reload", response_model=ContextReloadResponse)
async def reload_context(request: ContextReloadRequest) -> ContextReloadResponse:
    """Reload AGENTS.md if it has changed.
    
    Called on each user query to ensure fresh guidance.
    Performance target: <1000ms (SC-004)
    """
    from ...core.context_loader import get_context_loader
    
    logger.info(
        "Reloading AGENTS.md",
        extra={
            "session_id": request.session_id,
            "force_reload": request.force_reload
        }
    )
    
    try:
        loader = get_context_loader()
        
        if request.force_reload:
            content, reloaded = loader.load_agents_content(force_reload=True)
            reload_info = loader.get_context_reload_info(request.session_id)
        else:
            content, reloaded, reload_time_ms = loader.reload_agents_if_changed()
            reload_info = {
                "reloaded": reloaded,
                "reload_time_ms": reload_time_ms
            }
        
        return ContextReloadResponse(
            success=True,
            reloaded=reloaded,
            reload_time_ms=reload_info.get("reload_time_ms", 0)
        )
        
    except Exception as e:
        logger.error(
            "Failed to reload AGENTS.md",
            extra={
                "session_id": request.session_id,
                "error": str(e)
            }
        )
        return ContextReloadResponse(
            success=False,
            reloaded=False
        )


@router.get("/files", response_model=ContextFilesResponse)
async def list_context_files(session_id: str) -> ContextFilesResponse:
    """List all context files and their loading status.
    
    Returns information about which files have been loaded
    and whether they came from cache or were created with defaults.
    """
    from ...core.context_loader import get_context_loader
    
    logger.info(
        "Listing context files",
        extra={"session_id": session_id}
    )
    
    try:
        loader = get_context_loader()
        files_info = loader.get_loaded_files_info(session_id)
        
        files = [
            ContextFileInfo(
                name=f["name"],
                path=f["path"],
                loaded=f.get("loaded", False),
                from_cache=f.get("from_cache", False),
                is_default=f.get("is_default", False),
                last_modified=f.get("last_modified"),
                size_bytes=f.get("size_bytes", 0)
            )
            for f in files_info
        ]
        
        return ContextFilesResponse(
            session_id=session_id,
            files=files
        )
        
    except Exception as e:
        logger.error(
            "Failed to list context files",
            extra={
                "session_id": session_id,
                "error": str(e)
            }
        )
        raise HTTPException(status_code=500, detail=str(e))
