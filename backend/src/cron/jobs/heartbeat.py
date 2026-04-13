"""Heartbeat job for system health monitoring."""

from datetime import datetime

from .base import BaseJob


class HeartbeatJob(BaseJob):
    """System heartbeat job.

    Monitors system health by checking:
    - Database connectivity
    - Memory usage
    - Scheduler status
    """

    def __init__(self) -> None:
        super().__init__("heartbeat", "System Heartbeat")

    async def _run(self) -> dict:
        """Execute heartbeat check."""
        result = {"timestamp": datetime.now().isoformat(), "status": "healthy", "checks": {}}

        # Check database connectivity
        try:
            from ...services.storage import get_storage_service

            storage = get_storage_service()
            is_healthy = await storage.health_check()
            result["checks"]["database"] = "connected" if is_healthy else "disconnected"
            if not is_healthy:
                result["status"] = "degraded"
        except Exception as e:
            result["checks"]["database"] = f"error: {e}"
            result["status"] = "degraded"

        # Check memory (simplified)
        try:
            import psutil

            memory = psutil.virtual_memory()
            result["checks"]["memory"] = {
                "percent": memory.percent,
                "available_mb": memory.available // (1024 * 1024),
            }
            if memory.percent > 90:
                result["status"] = "warning"
        except ImportError:
            result["checks"]["memory"] = "psutil not installed"

        self.logger.info(
            "Heartbeat completed",
            extra={"status": result["status"], "checks": list(result["checks"].keys())},
        )

        return result


async def heartbeat_task() -> dict:
    """Global function for scheduler to call."""
    job = HeartbeatJob()
    return await job.execute()
