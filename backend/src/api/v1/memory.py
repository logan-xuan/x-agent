"""Memory system API endpoints.

This module provides REST API endpoints for:
- Identity management (SPIRIT.md, OWNER.md)
- Context loading
- Memory entries
- Search functionality
"""

from fastapi import APIRouter, HTTPException

from ...utils.logger import get_logger
from ...memory.models import (
    ContextBundle,
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


# ============ Context Endpoints ============

@router.post("/context/load", response_model=ContextBundle)
async def load_context() -> ContextBundle:
    """Load all context for AI response.
    
    Returns bundled context including spirit, owner, tools, and recent logs.
    """
    from ...memory.context_builder import ContextBuilder
    
    logger.info("Loading context")
    
    builder = ContextBuilder()
    context = builder.build_context()
    
    logger.info(
        "Context loaded",
        extra={
            "has_spirit": context.spirit is not None,
            "has_owner": context.owner is not None,
            "tools_count": len(context.tools),
        }
    )
    
    return context


@router.post("/context/reload", response_model=ContextBundle)
async def reload_context() -> ContextBundle:
    """Force reload all context from files.
    
    Clears cache and reloads all identity and memory files.
    """
    from ...memory.context_builder import ContextBuilder
    
    logger.info("Forcing context reload")
    
    builder = ContextBuilder()
    builder.clear_cache()
    context = builder.build_context()
    
    logger.info("Context reloaded")
    return context


# ============ Memory Endpoints ============

@router.get("/entries", response_model=list[MemoryEntry])
async def list_memory_entries(
    content_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[MemoryEntry]:
    """List memory entries with optional filtering.
    
    Args:
        content_type: Filter by content type
        limit: Maximum number of entries
        offset: Pagination offset
    """
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    entries = md_sync.list_all_entries(
        limit=limit,
        offset=offset,
        content_type=content_type,
    )
    
    logger.info(
        "Listing memory entries",
        extra={
            "content_type": content_type,
            "limit": limit,
            "offset": offset,
            "count": len(entries),
        }
    )
    return entries


@router.post("/entries", response_model=MemoryEntry)
async def create_memory_entry(entry: MemoryEntry) -> MemoryEntry:
    """Create a new memory entry."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    
    if not md_sync.append_memory_entry(entry):
        raise HTTPException(status_code=500, detail="Failed to save memory entry")
    
    logger.info(
        "Memory entry created",
        extra={"entry_id": entry.id, "content_type": entry.content_type}
    )
    
    return entry


@router.get("/entries/{entry_id}", response_model=MemoryEntry)
async def get_memory_entry(entry_id: str) -> MemoryEntry:
    """Get a specific memory entry."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    entry = md_sync.get_entry_by_id(entry_id)
    
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    logger.info("Memory entry retrieved", extra={"entry_id": entry_id})
    return entry


@router.delete("/entries/{entry_id}")
async def delete_memory_entry(entry_id: str) -> dict[str, str]:
    """Delete a memory entry."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    
    if not md_sync.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail="Entry not found or delete failed")
    
    logger.info("Memory entry deleted", extra={"entry_id": entry_id})
    return {"status": "deleted", "entry_id": entry_id}


@router.get("/daily/{date}", response_model=DailyLog)
async def get_daily_log(date: str) -> DailyLog:
    """Get daily log for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
    """
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    log = md_sync.load_daily_log(date)
    
    if log is None:
        raise HTTPException(status_code=404, detail=f"No log found for {date}")
    
    logger.info("Daily log retrieved", extra={"date": date})
    return log


@router.get("/dates")
async def list_available_dates() -> list[str]:
    """List all dates that have daily logs."""
    from ...memory.md_sync import get_md_sync
    
    md_sync = get_md_sync()
    dates = md_sync.list_available_dates()
    
    logger.info("Available dates listed", extra={"count": len(dates)})
    return dates


@router.post("/analyze")
async def analyze_importance(request: dict) -> dict:
    """Analyze content for importance.
    
    Args:
        request: JSON body with 'content' field
        
    Returns:
        Analysis result with importance indicators
    """
    from ...memory.importance_detector import get_importance_detector
    
    content = request.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="Content is required")
    
    detector = get_importance_detector()
    result = detector.extract_important_info(content)
    
    logger.info(
        "Content analyzed for importance",
        extra={
            "is_important": result["is_important"],
            "content_type": result["content_type"],
        }
    )
    
    return result


# ============ Search Endpoints ============

from pydantic import BaseModel, Field
from typing import Any


class SearchRequestModel(BaseModel):
    """Search request model."""
    query: str = Field(..., description="Search query string")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results")
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    content_type: str | None = Field(default=None, description="Filter by content type")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum relevance score")


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
    
    Uses 0.7 vector + 0.3 text similarity scoring as per research decision.
    
    Args:
        request: Search request with query and options
        
    Returns:
        Search results sorted by combined relevance score
    """
    from ...memory.hybrid_search import get_hybrid_search
    from ...memory.md_sync import get_md_sync
    from ...memory.vector_store import get_vector_store
    from ...services.embedder import get_embedder
    
    logger.info(
        "Searching memory",
        extra={
            "query": request.query[:50] if request.query else "",
            "limit": request.limit,
            "content_type": request.content_type,
        }
    )
    
    if not request.query or not request.query.strip():
        return SearchResponse(items=[], query=request.query or "", total=0)
    
    # Get all entries from md_sync
    md_sync = get_md_sync()
    entries = md_sync.list_all_entries(limit=1000)  # Get all for searching
    
    if not entries:
        return SearchResponse(items=[], query=request.query, total=0)
    
    # Initialize hybrid search with dependencies
    try:
        vector_store = get_vector_store()
        embedder = get_embedder()
        hybrid_search = get_hybrid_search(vector_store=vector_store, embedder=embedder)
    except Exception as e:
        logger.warning(
            "Hybrid search initialization failed, using text-only search",
            extra={"error": str(e)}
        )
        # Fall back to text-only search
        from ...memory.hybrid_search import HybridSearch
        hybrid_search = HybridSearch()
    
    # Convert content_type string to enum if provided
    content_type_enum = None
    if request.content_type:
        try:
            content_type_enum = MemoryContentType(request.content_type)
        except ValueError:
            pass  # Invalid content type, ignore filter
    
    # Perform search
    results = hybrid_search.search(
        query=request.query,
        entries=entries,
        limit=request.limit,
        offset=request.offset,
        content_type=content_type_enum,
        min_score=request.min_score,
    )
    
    # Convert to response format
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
        "Search completed",
        extra={
            "query": request.query[:50],
            "results_count": len(items),
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
    
    Uses the entry's content as the search query for similarity matching.
    
    Args:
        entry_id: Entry ID to find similar entries for
        limit: Maximum number of results
        
    Returns:
        Similar entries sorted by relevance score
    """
    from ...memory.hybrid_search import get_hybrid_search
    from ...memory.md_sync import get_md_sync
    from ...memory.vector_store import get_vector_store
    from ...services.embedder import get_embedder
    
    logger.info(
        "Finding similar entries",
        extra={"entry_id": entry_id, "limit": limit}
    )
    
    # Get all entries
    md_sync = get_md_sync()
    entries = md_sync.list_all_entries(limit=1000)
    
    # Find target entry
    target_entry = md_sync.get_entry_by_id(entry_id)
    if target_entry is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
    
    # Initialize hybrid search
    try:
        vector_store = get_vector_store()
        embedder = get_embedder()
        hybrid_search = get_hybrid_search(vector_store=vector_store, embedder=embedder)
    except Exception:
        from ...memory.hybrid_search import HybridSearch
        hybrid_search = HybridSearch()
    
    # Find similar entries
    results = hybrid_search.find_similar(
        entry_id=entry_id,
        entries=entries,
        limit=limit,
    )
    
    # Convert to response format
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
        "Similar entries found",
        extra={
            "entry_id": entry_id,
            "results_count": len(items),
        }
    )
    
    return SearchResponse(
        items=items,
        query=target_entry.content[:100],
        total=len(items),
    )
