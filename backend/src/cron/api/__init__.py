"""Cron scheduler API endpoints.

Architecture constraint: This module MUST only depend on SchedulerManager (manager.py),
never directly on CronScheduler (scheduler.py). See backend/src/cron/README.md.
"""

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..config import JobConfig
from ..manager import get_scheduler_manager

router = APIRouter(prefix="/cron", tags=["Cron"])
TASK_RUN_ARGS_BODY = Body(default_factory=dict)


@router.get("/schedules")
async def list_schedules() -> list[dict]:
    """List all scheduled jobs."""
    manager = get_scheduler_manager()
    return await manager.get_all_schedules()


@router.get("/jobs")
async def list_jobs() -> list[dict]:
    """List all running/completed jobs."""
    manager = get_scheduler_manager()
    return await manager.get_jobs()


@router.post("/schedules")
async def create_schedule(config: JobConfig) -> dict:
    """Create a new schedule."""
    manager = get_scheduler_manager()
    try:
        schedule_id = await manager.create_schedule(config)
        return {"id": schedule_id, "status": "created"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict:
    """Remove a schedule."""
    manager = get_scheduler_manager()
    try:
        await manager.delete_task(schedule_id)
        return {"id": schedule_id, "status": "removed"}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule(schedule_id: str) -> dict:
    """Pause a schedule."""
    manager = get_scheduler_manager()
    try:
        await manager.pause_task(schedule_id)
        return {"id": schedule_id, "status": "paused"}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/schedules/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: str, resume_from: str = Body(default="now", embed=True)
) -> dict:
    """Resume a paused schedule."""
    manager = get_scheduler_manager()
    try:
        await manager.resume_task(schedule_id, resume_from=resume_from)
        return {"id": schedule_id, "status": "resumed"}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str, args: dict[str, Any] = TASK_RUN_ARGS_BODY) -> dict:
    """Run a task immediately."""
    manager = get_scheduler_manager()
    try:
        return await manager.run_task_now(task_id, args=args)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
async def get_scheduler_status() -> dict:
    """Get scheduler status."""
    manager = get_scheduler_manager()
    return await manager.get_status()
