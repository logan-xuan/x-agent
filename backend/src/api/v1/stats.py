"""Statistics API endpoints."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from ...services.stat_service import get_stat_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/aggregated")
async def get_aggregated_stats(
    provider_name: str | None = Query(None, description="Filter by provider name"),
    model_id: str | None = Query(None, description="Filter by model ID"),
    hours: int | None = Query(None, description="Query last N hours"),
    days: int | None = Query(None, description="Query last N days"),
) -> dict:
    """Get aggregated LLM request statistics.
    
    Args:
        provider_name: Filter by provider name
        model_id: Filter by model ID
        hours: Query last N hours
        days: Query last N days
        
    Returns:
        Aggregated statistics
    """
    stat_service = get_stat_service()
    
    start_time = None
    if hours:
        start_time = datetime.now() - timedelta(hours=hours)
    elif days:
        start_time = datetime.now() - timedelta(days=days)
    
    return await stat_service.get_aggregated_stats(
        provider_name=provider_name,
        model_id=model_id,
        start_time=start_time,
    )


@router.get("/by-provider")
async def get_stats_by_provider(
    hours: int | None = Query(None, description="Query last N hours"),
    days: int | None = Query(None, description="Query last N days"),
) -> list[dict]:
    """Get statistics grouped by provider.
    
    Args:
        hours: Query last N hours
        days: Query last N days
        
    Returns:
        List of provider statistics
    """
    stat_service = get_stat_service()
    
    start_time = None
    if hours:
        start_time = datetime.now() - timedelta(hours=hours)
    elif days:
        start_time = datetime.now() - timedelta(days=days)
    
    return await stat_service.get_stats_by_provider(start_time=start_time)


@router.get("/recent-errors")
async def get_recent_errors(
    provider_name: str | None = Query(None, description="Filter by provider name"),
    limit: int = Query(10, description="Maximum number of records"),
) -> list[dict]:
    """Get recent error records.
    
    Args:
        provider_name: Filter by provider name
        limit: Maximum number of records to return
        
    Returns:
        List of error records
    """
    stat_service = get_stat_service()
    return await stat_service.get_recent_errors(
        provider_name=provider_name,
        limit=limit,
    )


@router.get("/daily")
async def get_daily_stats(
    days: int = Query(7, description="Number of days to include"),
    provider_name: str | None = Query(None, description="Filter by provider name"),
) -> list[dict]:
    """Get daily statistics.
    
    Args:
        days: Number of days to include
        provider_name: Filter by provider name
        
    Returns:
        List of daily statistics
    """
    stat_service = get_stat_service()
    return await stat_service.get_daily_stats(
        days=days,
        provider_name=provider_name,
    )
