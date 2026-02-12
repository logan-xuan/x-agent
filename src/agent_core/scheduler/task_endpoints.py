from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from ..config.config_service import get_config
from .cron_scheduler import CronScheduler


router = APIRouter()
scheduler = CronScheduler()


class TaskRequest(BaseModel):
    name: str
    schedule: str  # cron expression
    task_function_ref: str  # reference to task function
    params: Dict[str, Any] = {}


class TaskResponse(BaseModel):
    task_id: str
    name: str
    schedule: str
    status: str
    created_at: datetime


@router.post("/tasks", response_model=dict)
async def create_scheduled_task(request: TaskRequest):
    """Create a new scheduled task."""
    try:
        # In a real implementation, we would resolve the task_function_ref
        # to an actual function, but for this example we'll simulate
        def dummy_task(**params):
            print(f"Executing task {request.name} with params {params}")
            return "Task completed"

        task_id = scheduler.add_task(
            name=request.name,
            schedule=request.schedule,
            task_function=dummy_task,
            params=request.params
        )

        return {
            "task_id": task_id,
            "message": "Task scheduled successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tasks", response_model=List[Dict])
async def list_scheduled_tasks():
    """List all scheduled tasks."""
    tasks = scheduler.get_all_tasks()
    return [
        {
            "id": task.id,
            "name": task.name,
            "schedule": task.schedule,
            "status": task.last_run_status.value if hasattr(task.last_run_status, 'value') else task.last_run_status,
            "created_at": task.created_at,
            "last_run": task.last_run,
            "next_run": task.next_run,
            "retry_count": task.retry_count
        }
        for task in tasks
    ]


@router.get("/tasks/{task_id}", response_model=Dict)
async def get_task(task_id: str):
    """Get a specific task by ID."""
    task = scheduler.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "id": task.id,
        "name": task.name,
        "schedule": task.schedule,
        "status": task.last_run_status.value if hasattr(task.last_run_status, 'value') else task.last_run_status,
        "created_at": task.created_at,
        "last_run": task.last_run,
        "next_run": task.next_run,
        "retry_count": task.retry_count
    }


@router.delete("/tasks/{task_id}", response_model=dict)
async def delete_scheduled_task(task_id: str):
    """Delete a scheduled task."""
    success = scheduler.remove_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"message": "Task deleted successfully"}


@router.put("/tasks/{task_id}/pause", response_model=dict)
async def pause_task(task_id: str):
    """Pause a scheduled task."""
    task = scheduler.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    success = scheduler.pause_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to pause task")

    return {"message": "Task paused successfully"}


@router.put("/tasks/{task_id}/resume", response_model=dict)
async def resume_task(task_id: str):
    """Resume a paused task."""
    task = scheduler.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    success = scheduler.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to resume task")

    return {"message": "Task resumed successfully"}


@router.post("/scheduler/start", response_model=dict)
async def start_scheduler():
    """Start the scheduler."""
    await scheduler.start()
    return {"message": "Scheduler started successfully"}


@router.post("/scheduler/stop", response_model=dict)
async def stop_scheduler():
    """Stop the scheduler."""
    await scheduler.stop()
    return {"message": "Scheduler stopped successfully"}