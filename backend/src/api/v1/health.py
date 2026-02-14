"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_check() -> dict[str, str]:
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Readiness probe for orchestration."""
    return {"status": "ready"}
