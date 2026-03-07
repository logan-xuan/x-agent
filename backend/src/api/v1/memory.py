"""Memory system API endpoints.

This module provides REST API endpoints for:
- Identity management (SPIRIT.md, OWNER.md)
- Memory entries
- Search functionality
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...utils.logger import get_logger
from ...memory.models import (
    DailyLog,
    IdentityInitRequest,
    IdentityInitResponse,
    IdentityStatus,
    MemoryContentType,
    MemoryEntry,
    OwnerProfile,
    SpiritConfig,
    ToolDefinition,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ============ Identity Endpoints ============

@router.get("/identity/status", response_model=IdentityStatus)
async def get_identity_status() -> IdentityStatus:
    """Get identity initialization status.
    
    Returns whether SPIRIT.md and OWNER.md exist.
    """
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    status = md_sync.check_identity_status()
    
    logger.info(
        "Identity status checked",
        extra={"status": status}
    )
    
    return IdentityStatus(
        initialized=status["initialized"],
        has_spirit=status["has_spirit"],
        has_owner=status["has_owner"],
    )


@router.post("/identity/init", response_model=IdentityInitResponse)
async def initialize_identity(request: IdentityInitRequest) -> IdentityInitResponse:
    """Initialize identity with user-provided information.
    
    Creates SPIRIT.md and OWNER.md with initial values.
    """
    from ...memory.md_sync import get_md_sync
    from ...memory.spirit_loader import SpiritLoader
    
    logger.info(
        "Initializing identity",
        extra={"owner_name": request.owner_name}
    )
    
    try:
        md_sync = get_md_sync()
        loader = SpiritLoader()
        
        # Create owner profile
        owner = OwnerProfile(
            name=request.owner_name,
            occupation=request.owner_occupation or "",
            interests=request.owner_interests,
        )
        md_sync.save_owner(owner)
        
        # Create spirit config
        spirit = SpiritConfig(
            role=request.ai_role or "我是一个专注型 AI 助手，服务于个人知识管理。",
            personality=request.ai_personality or "温和、理性、主动但不过度打扰",
            values=["尊重隐私", "不编造信息", "帮助用户变得更好"],
            behavior_rules=[
                "在每次响应前，先回顾当前上下文和长期记忆",
                "对重要计划进行提醒",
                "拒绝不合理请求",
            ],
        )
        md_sync.save_spirit(spirit)
        
        logger.info(
            "Identity initialized successfully",
            extra={"owner_name": owner.name}
        )
        
        return IdentityInitResponse(
            success=True,
            spirit=spirit,
            owner=owner,
        )
        
    except Exception as e:
        logger.error(
            "Failed to initialize identity",
            extra={"error": str(e)}
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/identity/spirit", response_model=SpiritConfig)
async def get_spirit() -> SpiritConfig:
    """Get AI personality configuration."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    spirit = md_sync.load_spirit()
    
    if spirit is None:
        raise HTTPException(status_code=404, detail="SPIRIT.md not found")
    
    logger.info("Spirit config retrieved")
    return spirit


@router.put("/identity/spirit", response_model=SpiritConfig)
async def update_spirit(config: SpiritConfig) -> SpiritConfig:
    """Update AI personality configuration."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    
    if not md_sync.save_spirit(config):
        raise HTTPException(status_code=500, detail="Failed to save SPIRIT.md")
    
    logger.info(
        "Spirit config updated",
        extra={"role": config.role[:50] if config.role else ""}
    )
    return config


@router.get("/identity/owner", response_model=OwnerProfile)
async def get_owner() -> OwnerProfile:
    """Get user profile."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    owner = md_sync.load_owner()
    
    if owner is None:
        raise HTTPException(status_code=404, detail="OWNER.md not found")
    
    logger.info("Owner profile retrieved", extra={"name": owner.name})
    return owner


@router.put("/identity/owner", response_model=OwnerProfile)
async def update_owner(profile: OwnerProfile) -> OwnerProfile:
    """Update user profile."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    
    if not md_sync.save_owner(profile):
        raise HTTPException(status_code=500, detail="Failed to save OWNER.md")
    
    logger.info("Owner profile updated", extra={"name": profile.name})
    return profile




# ============ Memory Endpoints ============

# ============ Search Endpoints ============

from pydantic import BaseModel, Field
from typing import Any


class SearchRequestModel(BaseModel):
    """Search request model."""
    query: str = Field(..., description="Search query string")
    limit: int | None = Field(default=None, ge=1, le=100, description="Maximum number of results (default from config)")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    content_type: str | None = Field(default=None, description="Filter by content type")
    min_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Minimum relevance score (default from config)")
    
    def get_limit(self) -> int:
        """Get limit, using config default if not specified."""
        if self.limit is not None:
            return self.limit
        try:
            from ...config import get_config
            return get_config().search.limit
        except Exception:
            return 10
    
    def get_min_score(self) -> float:
        """Get min_score, using config default if not specified."""
        if self.min_score is not None:
            return self.min_score
        try:
            from ...config import get_config
            return get_config().search.min_score
        except Exception:
            return 0.0


class SearchResultItem(BaseModel):
    """Single search result item."""
    entry: MemoryEntry
    score: float = Field(description="Combined relevance score (0-1)")
    vector_score: float = Field(default=0.0, description="Vector similarity score")
    text_score: float = Field(default=0.0, description="Text similarity score")


class SearchResponse(BaseModel):
    """Search response with results and metadata."""
    items: list[SearchResultItem]
    query: str
    total: int


@router.post("/search", response_model=SearchResponse)
async def search_memory(request: SearchRequestModel) -> SearchResponse:
    """Search memory using hybrid search (vector + text).
    
    Uses configurable vector + text similarity scoring (default: 0.7 + 0.3).
    Delegates to MemoryManager for unified search access.
    
    Args:
        request: Search request with query and options
        
    Returns:
        Search results sorted by combined relevance score
    """
    from ...memory.manager import get_memory_manager
    
    limit = request.get_limit()
    
    logger.info(
        "Memory API | search",
        extra={
            "scene": "api_search",
            "query": request.query[:80] if request.query else "",
            "limit": limit,
            "offset": request.offset,
            "content_type": request.content_type,
            "min_score": request.get_min_score(),
        }
    )
    
    if not request.query or not request.query.strip():
        return SearchResponse(items=[], query=request.query or "", total=0)
    
    memory_manager = get_memory_manager()

    content_type_enum = None
    if request.content_type:
        try:
            content_type_enum = MemoryContentType(request.content_type)
        except ValueError:
            pass

    results = memory_manager.search(
        query=request.query,
        limit=limit,
        offset=request.offset,
        content_type=content_type_enum,
        min_score=request.get_min_score(),
    )
    
    items = [
        SearchResultItem(
            entry=r.entry,
            score=r.score,
            vector_score=r.vector_score,
            text_score=r.text_score,
        )
        for r in results
    ]
    
    logger.info(
        "Memory API | search completed",
        extra={
            "scene": "api_search",
            "query": request.query[:80],
            "results_count": len(items),
            "top_score": round(items[0].score, 3) if items else None,
        }
    )
    
    return SearchResponse(
        items=items,
        query=request.query,
        total=len(items),
    )


@router.get("/search/similar/{entry_id}", response_model=SearchResponse)
async def find_similar(entry_id: str, limit: int = 5) -> SearchResponse:
    """Find entries similar to a specific entry.
    
    Uses the entry's content as the search query via MemoryManager.
    
    Args:
        entry_id: Entry ID to find similar entries for
        limit: Maximum number of results
        
    Returns:
        Similar entries sorted by relevance score
    """
    from ...memory.md_sync import get_md_sync
    from ...memory.manager import get_memory_manager
    
    logger.info(
        "Memory API | find_similar",
        extra={
            "scene": "api_find_similar",
            "entry_id": entry_id,
            "limit": limit,
        }
    )
    
    md_sync = get_md_sync()
    target_entry = md_sync.get_entry_by_id(entry_id)
    if target_entry is None:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    
    memory_manager = get_memory_manager()
    results = memory_manager.search(
        query=target_entry.content[:200],
        limit=limit,
    )
    
    items = [
        SearchResultItem(
            entry=r.entry,
            score=r.score,
            vector_score=r.vector_score,
            text_score=r.text_score,
        )
        for r in results
        if r.entry.id != entry_id
    ]
    
    logger.info(
        "Memory API | find_similar completed",
        extra={
            "scene": "api_find_similar",
            "entry_id": entry_id,
            "results_count": len(items),
            "top_score": round(items[0].score, 3) if items else None,
        }
    )
    
    return SearchResponse(
        items=items,
        query=target_entry.content[:100],
        total=len(items),
    )


