from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
import logging

from src.db.models.scheduled_task import ScheduledTask, TaskStatus
from src.agent_core.scheduler.cron_scheduler import CronScheduler
from src.agent_core.scheduler.execution_engine import ExecutionEngine

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])

# Initialize scheduler and execution engine
scheduler = CronScheduler()
engine = ExecutionEngine()
logger = logging.getLogger(__name__)


@router.on_event("startup")
async def startup_event():
    await scheduler.start()


@router.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()
    engine.shutdown()


@router.post("/", response_model=dict)
async def create_scheduled_task(
    name: str,
    description: str,
    cron_expression: str,
    task_type: str,
    task_params: Optional[dict] = None,
    enabled: bool = True
):
    """Create a new scheduled task"""
    try:
        task_id = scheduler.add_task(
            name=name,
            schedule=cron_expression,
            task_function=lambda **kwargs: True,  # Placeholder, actual function will be mapped in execution
            params=task_params or {},
            max_retries=3
        )

        # Create the database record
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            scheduled_task = ScheduledTask(
                id=task_id,
                name=name,
                description=description,
                cron_expression=cron_expression,
                task_type=task_type,
                task_params=str(task_params) if task_params else None,
                enabled=enabled
            )
            db.add(scheduled_task)
            db.commit()
            db.refresh(scheduled_task)

            logger.info(f"Created scheduled task {task_id}: {name}")
            return {"id": task_id, "status": "created", "message": "Task created successfully"}

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error creating scheduled task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.get("/{task_id}", response_model=dict)
async def get_scheduled_task(task_id: str):
    """Get a specific scheduled task by ID"""
    try:
        task = scheduler.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Get database record for additional details
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not db_task:
                raise HTTPException(status_code=404, detail="Task record not found in database")

            return {
                "id": task.id,
                "name": task.name,
                "schedule": task.schedule,
                "status": task.status.value,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "database_record": {
                    "description": db_task.description,
                    "task_type": db_task.task_type,
                    "enabled": db_task.enabled,
                    "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
                    "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
                    "last_run_at": db_task.last_run_at.isoformat() if db_task.last_run_at else None,
                    "last_run_status": db_task.last_run_status.value if db_task.last_run_status else None,
                    "next_run_at": db_task.next_run_at.isoformat() if db_task.next_run_at else None
                }
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting scheduled task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get task: {str(e)}")


@router.get("/", response_model=List[dict])
async def list_scheduled_tasks():
    """List all scheduled tasks"""
    try:
        tasks = scheduler.get_all_tasks()

        # Get database records for additional details
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            # Get all task IDs from scheduler
            task_ids = [task.id for task in tasks]
            db_tasks = db.query(ScheduledTask).filter(ScheduledTask.id.in_(task_ids)).all()
            db_task_map = {t.id: t for t in db_tasks}

            result = []
            for task in tasks:
                db_task = db_task_map.get(task.id)
                result.append({
                    "id": task.id,
                    "name": task.name,
                    "schedule": task.schedule,
                    "status": task.status.value,
                    "next_run": task.next_run.isoformat() if task.next_run else None,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "enabled": db_task.enabled if db_task else None,
                    "task_type": db_task.task_type if db_task else None
                })

            return result

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error listing scheduled tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@router.put("/{task_id}/enable", response_model=dict)
async def enable_scheduled_task(task_id: str):
    """Enable a scheduled task"""
    try:
        task = scheduler.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update in database
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not db_task:
                raise HTTPException(status_code=404, detail="Task record not found in database")

            db_task.enabled = True
            db_task.updated_at = datetime.utcnow()
            db.commit()

            # For now, just log that the task is enabled - the scheduler itself handles scheduling
            logger.info(f"Enabled scheduled task {task_id}")
            return {"id": task_id, "status": "enabled", "message": "Task enabled successfully"}

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling scheduled task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to enable task: {str(e)}")


@router.put("/{task_id}/disable", response_model=dict)
async def disable_scheduled_task(task_id: str):
    """Disable a scheduled task"""
    try:
        task = scheduler.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Update in database
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not db_task:
                raise HTTPException(status_code=404, detail="Task record not found in database")

            db_task.enabled = False
            db_task.updated_at = datetime.utcnow()
            db.commit()

            logger.info(f"Disabled scheduled task {task_id}")
            return {"id": task_id, "status": "disabled", "message": "Task disabled successfully"}

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling scheduled task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to disable task: {str(e)}")


@router.delete("/{task_id}", response_model=dict)
async def delete_scheduled_task(task_id: str):
    """Delete a scheduled task"""
    try:
        # First check if task exists
        task = scheduler.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # Remove from scheduler
        success = scheduler.remove_task(task_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove task from scheduler")

        # Remove from database
        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not db_task:
                raise HTTPException(status_code=404, detail="Task record not found in database")

            db.delete(db_task)
            db.commit()

            logger.info(f"Deleted scheduled task {task_id}")
            return {"id": task_id, "status": "deleted", "message": "Task deleted successfully"}

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting scheduled task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")


@router.post("/{task_id}/trigger", response_model=dict)
async def trigger_scheduled_task_now(task_id: str):
    """Manually trigger a scheduled task immediately"""
    try:
        task = scheduler.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        from src.db.database import SessionLocal
        db = SessionLocal()
        try:
            db_task = db.query(ScheduledTask).filter(ScheduledTask.id == task_id).first()
            if not db_task:
                raise HTTPException(status_code=404, detail="Task record not found in database")

            if not db_task.enabled:
                raise HTTPException(status_code=400, detail="Task is disabled and cannot be triggered")

            # Execute the task now
            success = await engine.execute_task(task)

            return {
                "id": task_id,
                "status": "executed",
                "success": success,
                "message": f"Task {'executed successfully' if success else 'failed to execute'}"
            }

        finally:
            db.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering scheduled task {task_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger task: {str(e)}")