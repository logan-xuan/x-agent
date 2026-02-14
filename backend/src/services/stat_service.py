"""LLM request statistics service."""

import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stat import LLMRequestStat
from ..services.storage import StorageService
from ..utils.logger import get_logger

logger = get_logger(__name__)


class StatService:
    """Service for managing LLM request statistics.
    
    Provides:
    - Record individual request stats
    - Query aggregated statistics
    - Multi-dimensional analysis (by provider, model, time range)
    """
    
    def __init__(self, storage: StorageService | None = None) -> None:
        """Initialize stat service.
        
        Args:
            storage: Storage service instance
        """
        self._storage = storage or StorageService()
    
    async def record_request(
        self,
        provider_name: str,
        model_id: str,
        success: bool,
        session_id: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
        error_message: str | None = None,
        request_type: str = "chat",
    ) -> LLMRequestStat:
        """Record a single LLM request statistic.
        
        Args:
            provider_name: Name of the provider (e.g., "primary", "backup1")
            model_id: Model identifier (e.g., "qwen3-coder-flash")
            success: Whether the request succeeded
            session_id: Optional session ID for correlation
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens generated
            latency_ms: Request latency in milliseconds
            error_message: Error message if request failed
            request_type: Type of request (chat, embedding, etc.)
            
        Returns:
            Created stat record
        """
        stat = LLMRequestStat(
            id=str(uuid.uuid4()),
            provider_name=provider_name,
            model_id=model_id,
            session_id=session_id,
            request_type=request_type,
            success=1 if success else 0,
            error_message=error_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            created_at=datetime.now(),
        )
        
        async with self._storage.session() as db_session:
            db_session.add(stat)
            await db_session.commit()
            await db_session.refresh(stat)
        
        logger.debug(f"Recorded stat: {provider_name}/{model_id} success={success}")
        return stat
    
    async def get_aggregated_stats(
        self,
        provider_name: str | None = None,
        model_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, Any]:
        """Get aggregated statistics with optional filters.
        
        Args:
            provider_name: Filter by provider name
            model_id: Filter by model ID
            start_time: Filter from this time
            end_time: Filter to this time
            
        Returns:
            Aggregated statistics dict
        """
        async with self._storage.session() as db_session:
            # Build base query
            base_query = select(LLMRequestStat)
            
            if provider_name:
                base_query = base_query.where(LLMRequestStat.provider_name == provider_name)
            if model_id:
                base_query = base_query.where(LLMRequestStat.model_id == model_id)
            if start_time:
                base_query = base_query.where(LLMRequestStat.created_at >= start_time)
            if end_time:
                base_query = base_query.where(LLMRequestStat.created_at <= end_time)
            
            # Get aggregated stats
            agg_query = select(
                func.count(LLMRequestStat.id).label("total_requests"),
                func.sum(LLMRequestStat.success).label("successful_requests"),
                func.sum(LLMRequestStat.prompt_tokens).label("total_prompt_tokens"),
                func.sum(LLMRequestStat.completion_tokens).label("total_completion_tokens"),
                func.sum(LLMRequestStat.total_tokens).label("total_tokens"),
                func.avg(LLMRequestStat.latency_ms).label("avg_latency_ms"),
                func.max(LLMRequestStat.latency_ms).label("max_latency_ms"),
                func.min(LLMRequestStat.latency_ms).label("min_latency_ms"),
            ).select_from(LLMRequestStat)
            
            if provider_name:
                agg_query = agg_query.where(LLMRequestStat.provider_name == provider_name)
            if model_id:
                agg_query = agg_query.where(LLMRequestStat.model_id == model_id)
            if start_time:
                agg_query = agg_query.where(LLMRequestStat.created_at >= start_time)
            if end_time:
                agg_query = agg_query.where(LLMRequestStat.created_at <= end_time)
            
            result = await db_session.execute(agg_query)
            row = result.one()
            
            total = row.total_requests or 0
            successful = row.successful_requests or 0
            failed = total - successful
            
            return {
                "total_requests": total,
                "successful_requests": successful,
                "failed_requests": failed,
                "success_rate": round(successful / total * 100, 2) if total > 0 else 0.0,
                "total_prompt_tokens": row.total_prompt_tokens or 0,
                "total_completion_tokens": row.total_completion_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "avg_latency_ms": round(row.avg_latency_ms or 0, 2),
                "max_latency_ms": row.max_latency_ms or 0,
                "min_latency_ms": row.min_latency_ms or 0,
            }
    
    async def get_stats_by_provider(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get statistics grouped by provider.
        
        Args:
            start_time: Filter from this time
            end_time: Filter to this time
            
        Returns:
            List of provider statistics
        """
        async with self._storage.session() as db_session:
            query = select(
                LLMRequestStat.provider_name,
                LLMRequestStat.model_id,
                func.count(LLMRequestStat.id).label("total_requests"),
                func.sum(LLMRequestStat.success).label("successful_requests"),
                func.avg(LLMRequestStat.latency_ms).label("avg_latency_ms"),
            ).group_by(
                LLMRequestStat.provider_name,
                LLMRequestStat.model_id,
            )
            
            if start_time:
                query = query.where(LLMRequestStat.created_at >= start_time)
            if end_time:
                query = query.where(LLMRequestStat.created_at <= end_time)
            
            result = await db_session.execute(query)
            rows = result.all()
            
            stats = []
            for row in rows:
                total = row.total_requests or 0
                successful = row.successful_requests or 0
                stats.append({
                    "provider_name": row.provider_name,
                    "model_id": row.model_id,
                    "total_requests": total,
                    "successful_requests": successful,
                    "failed_requests": total - successful,
                    "success_rate": round(successful / total * 100, 2) if total > 0 else 0.0,
                    "avg_latency_ms": round(row.avg_latency_ms or 0, 2),
                })
            
            return stats
    
    async def get_recent_errors(
        self,
        provider_name: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent error records.
        
        Args:
            provider_name: Filter by provider name
            limit: Maximum number of records to return
            
        Returns:
            List of error records
        """
        async with self._storage.session() as db_session:
            query = select(LLMRequestStat).where(
                LLMRequestStat.success == 0
            ).order_by(LLMRequestStat.created_at.desc()).limit(limit)
            
            if provider_name:
                query = query.where(LLMRequestStat.provider_name == provider_name)
            
            result = await db_session.execute(query)
            records = result.scalars().all()
            
            return [r.to_dict() for r in records]
    
    async def get_daily_stats(
        self,
        days: int = 7,
        provider_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get daily statistics for the past N days.
        
        Args:
            days: Number of days to include
            provider_name: Filter by provider name
            
        Returns:
            List of daily statistics
        """
        start_time = datetime.now() - timedelta(days=days)
        
        async with self._storage.session() as db_session:
            # SQLite date function
            query = select(
                func.date(LLMRequestStat.created_at).label("date"),
                func.count(LLMRequestStat.id).label("total_requests"),
                func.sum(LLMRequestStat.success).label("successful_requests"),
                func.sum(LLMRequestStat.total_tokens).label("total_tokens"),
            ).where(
                LLMRequestStat.created_at >= start_time
            ).group_by(
                func.date(LLMRequestStat.created_at)
            ).order_by(
                func.date(LLMRequestStat.created_at).desc()
            )
            
            if provider_name:
                query = query.where(LLMRequestStat.provider_name == provider_name)
            
            result = await db_session.execute(query)
            rows = result.all()
            
            stats = []
            for row in rows:
                total = row.total_requests or 0
                successful = row.successful_requests or 0
                stats.append({
                    "date": row.date,
                    "total_requests": total,
                    "successful_requests": successful,
                    "failed_requests": total - successful,
                    "success_rate": round(successful / total * 100, 2) if total > 0 else 0.0,
                    "total_tokens": row.total_tokens or 0,
                })
            
            return stats


# Context manager for timing requests
class RequestTimer:
    """Context manager for measuring request latency."""
    
    def __init__(self) -> None:
        self.start_time: float = 0
        self.latency_ms: int = 0
    
    def __enter__(self) -> "RequestTimer":
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args: Any) -> None:
        self.latency_ms = int((time.time() - self.start_time) * 1000)


# Global stat service instance
_stat_service: StatService | None = None


def get_stat_service() -> StatService:
    """Get or create global stat service instance."""
    global _stat_service
    if _stat_service is None:
        _stat_service = StatService()
    return _stat_service
