"""Cron API router.

Architecture constraint: This module MUST only depend on SchedulerManager (manager.py),
never directly on CronScheduler (scheduler.py). See backend/src/cron/README.md.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from ...utils.logger import get_logger
from ..config import JobConfig
from ..manager import get_scheduler_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/cron", tags=["Cron"])
TASK_RUN_ARGS_BODY = Body(default_factory=dict)


class ScheduleResponse(BaseModel):
    """Response for schedule operations."""

    success: bool
    message: str
    data: dict | None = None
    trace_id: str


class ErrorResponse(BaseModel):
    """Error response."""

    success: bool = False
    error: dict | None = None
    trace_id: str


def generate_trace_id() -> str:
    """Generate a unique trace ID for request tracking."""
    return str(uuid.uuid4())


# === Schedule Management Endpoints ===


@router.get("/list_schedules")
async def list_schedules() -> list[dict]:
    """List all scheduled jobs."""
    manager = get_scheduler_manager()
    return await manager.get_all_schedules()


@router.get("/schedules")
async def get_schedules() -> list[dict]:
    """List all scheduled jobs (RESTful endpoint)."""
    manager = get_scheduler_manager()
    return await manager.get_all_schedules()


@router.get("/schedule/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Get a specific schedule."""
    trace_id = generate_trace_id()
    logger.info("Getting schedule", extra={"trace_id": trace_id, "schedule_id": schedule_id})

    manager = get_scheduler_manager()
    try:
        schedule = await manager.get_schedule_by_id(schedule_id)
        if schedule:
            return {
                "success": True,
                "data": schedule,
                "trace_id": trace_id,
            }
        raise HTTPException(
            status_code=404, detail={"trace_id": trace_id, "error": "Schedule not found"}
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get schedule", extra={"trace_id": trace_id, "error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail={"trace_id": trace_id, "error": str(exc)},
        ) from exc


@router.get("/schedules/{schedule_id}")
async def get_schedule_by_id(schedule_id: str):
    """Get a specific schedule by ID (RESTful endpoint)."""
    manager = get_scheduler_manager()
    try:
        schedule = await manager.get_schedule_by_id(schedule_id)
        if schedule:
            return schedule
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get schedule", extra={"schedule_id": schedule_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


# === Job Management Endpoints ===


@router.get("/jobs")
async def list_jobs() -> list[dict]:
    """List all running/completed jobs."""
    manager = get_scheduler_manager()
    return await manager.get_jobs()


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a specific job by ID."""
    manager = get_scheduler_manager()
    try:
        jobs = await manager.get_jobs()
        for job in jobs:
            if job.get("id") == job_id:
                return job
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get job", extra={"job_id": job_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/tasks")
async def list_tasks() -> list[dict]:
    """List all available tasks."""
    manager = get_scheduler_manager()
    try:
        return await manager.get_tasks()
    except Exception as e:
        logger.error("Failed to list tasks", extra={"error": str(e)})
        return []


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str, args: dict[str, Any] = TASK_RUN_ARGS_BODY) -> dict:
    """Run a task immediately."""
    manager = get_scheduler_manager()
    logger.info("run_task_now called", extra={"task_id": task_id, "args": args})
    try:
        result = await manager.run_task_now(task_id, args=args)
        logger.info("run_task_now completed", extra={"task_id": task_id, "result": str(result)})
        return result
    except Exception as exc:
        logger.error(
            "run_task_now failed",
            extra={"task_id": task_id, "error": str(exc), "error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    """Delete a task definition."""
    manager = get_scheduler_manager()
    try:
        return await manager.remove_task(task_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get a specific task by ID."""
    manager = get_scheduler_manager()
    try:
        task = await manager.get_task_by_id(task_id)
        if task:
            return task
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get task", extra={"task_id": task_id, "error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# === Scheduler Status Endpoints ===


@router.get("/status")
async def get_scheduler_status() -> dict:
    """Get scheduler status."""
    manager = get_scheduler_manager()
    return await manager.get_status()
