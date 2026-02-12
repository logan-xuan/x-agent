"""
Cancellation API endpoints for the x-agent2 AI assistant system.

This module provides API endpoints for cancelling long-running tasks
through the task cancellation system.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from src.agent_core.monitoring.cancellation_handler import (
    cancellation_manager,
    request_task_cancellation,
    get_task_cancellation_status,
    CancellationReason
)
from src.agent_core.api_utils.response_handler import (
    APIResponse,
    APIExceptionHandler,
    create_success_response,
    create_error_response
)
from src.agent_core.security.tool_security import authenticate_user


router = APIRouter(prefix="/cancellation", tags=["cancellation"])


@router.post("/cancel-task")
async def cancel_task(
    task_id: str = Query(..., description="ID of the task to cancel"),
    reason: str = Query("user_requested", description="Reason for cancellation"),
    message: Optional[str] = Query(None, description="Optional cancellation message")
):
    """
    Cancel a long-running task.

    Args:
        task_id: ID of the task to cancel
        reason: Reason for cancellation
        message: Optional cancellation message

    Returns:
        JSON response with cancellation confirmation
    """
    try:
        # Validate cancellation reason
        try:
            cancellation_reason = CancellationReason(reason)
        except ValueError:
            return create_error_response(
                message=f"Invalid cancellation reason: {reason}",
                status_code=400,
                details={
                    "valid_reasons": [r.value for r in CancellationReason],
                    "provided_reason": reason
                }
            )

        # Request cancellation of the task
        result = request_task_cancellation(task_id, cancellation_reason)

        if result["success"]:
            return create_success_response(
                data={
                    "task_id": task_id,
                    "status": result["status"],
                    "reason": result["reason"],
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": message or f"Task {task_id} cancellation requested"
                },
                message=f"Task {task_id} cancellation requested successfully"
            )
        else:
            return create_error_response(
                message=result["error"],
                status_code=404,
                details={"task_id": task_id}
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to cancel task"
        )


@router.post("/cancel-tasks-batch")
async def cancel_tasks_batch(
    task_ids: str = Query(..., description="Comma-separated list of task IDs to cancel"),
    reason: str = Query("user_requested", description="Reason for cancellation"),
    message: Optional[str] = Query(None, description="Optional cancellation message")
):
    """
    Cancel multiple long-running tasks.

    Args:
        task_ids: Comma-separated list of task IDs to cancel
        reason: Reason for cancellation
        message: Optional cancellation message

    Returns:
        JSON response with batch cancellation results
    """
    try:
        # Parse the list of task IDs
        task_id_list = [tid.strip() for tid in task_ids.split(",") if tid.strip()]

        if not task_id_list:
            return create_error_response(
                message="No valid task IDs provided",
                status_code=400
            )

        # Validate cancellation reason
        try:
            cancellation_reason = CancellationReason(reason)
        except ValueError:
            return create_error_response(
                message=f"Invalid cancellation reason: {reason}",
                status_code=400,
                details={
                    "valid_reasons": [r.value for r in CancellationReason],
                    "provided_reason": reason
                }
            )

        # Cancel each task and collect results
        results = {
            "cancelled": [],
            "failed": [],
            "not_found": [],
            "already_cancelled": []
        }

        for task_id in task_id_list:
            result = request_task_cancellation(task_id, cancellation_reason)

            if result["success"]:
                results["cancelled"].append({
                    "task_id": task_id,
                    "status": result["status"],
                    "reason": result["reason"]
                })
            elif "not found" in result.get("error", "").lower():
                results["not_found"].append({
                    "task_id": task_id,
                    "error": result["error"]
                })
            elif "already completed" in result.get("error", "").lower():
                results["already_cancelled"].append({
                    "task_id": task_id,
                    "status": result["status"]
                })
            else:
                results["failed"].append({
                    "task_id": task_id,
                    "error": result["error"]
                })

        return create_success_response(
            data={
                "total_requested": len(task_id_list),
                "cancelled": len(results["cancelled"]),
                "failed": len(results["failed"]),
                "not_found": len(results["not_found"]),
                "already_cancelled": len(results["already_cancelled"]),
                "results": results,
                "timestamp": datetime.utcnow().isoformat()
            },
            message=f"Batch cancellation completed: {len(results['cancelled'])} cancelled, {len(results['failed'])} failed"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to cancel tasks in batch"
        )


@router.get("/cancellation-status/{task_id}")
async def get_cancellation_status(task_id: str):
    """
    Get the cancellation status of a specific task.

    Args:
        task_id: ID of the task to check cancellation status for

    Returns:
        JSON response with cancellation status information
    """
    try:
        status = get_task_cancellation_status(task_id)

        if status is None:
            return create_error_response(
                message=f"Task {task_id} not found or not registered for cancellation",
                status_code=404
            )

        return create_success_response(
            data=status,
            message=f"Cancellation status for task {task_id}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to get cancellation status"
        )


@router.get("/all-cancellation-statuses")
async def get_all_cancellation_statuses():
    """
    Get the cancellation status of all registered tasks.

    Returns:
        JSON response with all cancellation statuses
    """
    try:
        statuses = cancellation_manager.get_all_task_statuses()

        return create_success_response(
            data={
                "statuses": statuses,
                "total_tasks": len(statuses),
                "timestamp": datetime.utcnow().isoformat()
            },
            message="Cancellation statuses for all tasks retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to get all cancellation statuses"
        )


@router.post("/cancel-all-tasks")
async def cancel_all_tasks(
    reason: str = Query("system_shutdown", description="Reason for cancellation"),
    message: Optional[str] = Query(None, description="Optional cancellation message")
):
    """
    Cancel all registered tasks.

    Args:
        reason: Reason for cancellation
        message: Optional cancellation message

    Returns:
        JSON response with cancellation results
    """
    try:
        # Validate cancellation reason
        try:
            cancellation_reason = CancellationReason(reason)
        except ValueError:
            return create_error_response(
                message=f"Invalid cancellation reason: {reason}",
                status_code=400,
                details={
                    "valid_reasons": [r.value for r in CancellationReason],
                    "provided_reason": reason
                }
            )

        # Cancel all tasks
        results = cancellation_manager.cancel_all_tasks(cancellation_reason)

        return create_success_response(
            data={
                **results,
                "timestamp": datetime.utcnow().isoformat(),
                "reason": cancellation_reason.value
            },
            message=f"All tasks cancellation completed: {results['cancelled']} cancelled, {results['failed']} failed"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to cancel all tasks"
        )


@router.get("/task-cancellable/{task_id}")
async def is_task_cancellable_endpoint(task_id: str):
    """
    Check if a task is registered for cancellation.

    Args:
        task_id: ID of the task to check

    Returns:
        JSON response indicating if the task is cancellable
    """
    try:
        is_cancellable = cancellation_manager.is_task_cancellable(task_id)

        return create_success_response(
            data={
                "task_id": task_id,
                "is_cancellable": is_cancellable,
                "timestamp": datetime.utcnow().isoformat()
            },
            message=f"Task {task_id} cancellability: {'Yes' if is_cancellable else 'No'}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to check task cancellability"
        )


@router.get("/task-cancelled/{task_id}")
async def is_task_cancelled_endpoint(task_id: str):
    """
    Check if a task has been cancelled.

    Args:
        task_id: ID of the task to check

    Returns:
        JSON response indicating if the task has been cancelled
    """
    try:
        is_cancelled = cancellation_manager.is_task_cancelled(task_id)

        return create_success_response(
            data={
                "task_id": task_id,
                "is_cancelled": is_cancelled,
                "timestamp": datetime.utcnow().isoformat()
            },
            message=f"Task {task_id} cancellation status: {'Cancelled' if is_cancelled else 'Not Cancelled'}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to check task cancellation status"
        )


@router.get("/task-running/{task_id}")
async def is_task_running_endpoint(task_id: str):
    """
    Check if a task is currently running (not cancelled or completed).

    Args:
        task_id: ID of the task to check

    Returns:
        JSON response indicating if the task is running
    """
    try:
        is_running = cancellation_manager.is_task_running(task_id)

        return create_success_response(
            data={
                "task_id": task_id,
                "is_running": is_running,
                "timestamp": datetime.utcnow().isoformat()
            },
            message=f"Task {task_id} running status: {'Running' if is_running else 'Not Running'}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to check task running status"
        )


@router.post("/register-task-for-cancellation")
async def register_task_endpoint(
    task_id: str = Query(..., description="Unique identifier for the task"),
    task_name: str = Query(..., description="Name of the task"),
    description: Optional[str] = Query(None, description="Description of the task")
):
    """
    Register a task for cancellation tracking.

    Args:
        task_id: Unique identifier for the task
        task_name: Name of the task
        description: Optional description of the task

    Returns:
        JSON response with registration confirmation
    """
    try:
        success = cancellation_manager.register_task(
            task_id=task_id,
            name=task_name,
            context={"description": description} if description else {}
        )

        if success:
            return create_success_response(
                data={
                    "task_id": task_id,
                    "task_name": task_name,
                    "description": description,
                    "registered": True,
                    "timestamp": datetime.utcnow().isoformat()
                },
                message=f"Task {task_id} registered for cancellation successfully"
            )
        else:
            return create_error_response(
                message=f"Task {task_id} already registered for cancellation",
                status_code=409  # Conflict
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to register task for cancellation"
        )


@router.delete("/deregister-task/{task_id}")
async def deregister_task_endpoint(task_id: str):
    """
    Deregister a task from cancellation tracking.

    Args:
        task_id: ID of the task to deregister

    Returns:
        JSON response with deregistration confirmation
    """
    try:
        success = cancellation_manager.deregister_task(task_id)

        if success:
            return create_success_response(
                data={
                    "task_id": task_id,
                    "deregistered": True,
                    "timestamp": datetime.utcnow().isoformat()
                },
                message=f"Task {task_id} deregistered from cancellation successfully"
            )
        else:
            return create_error_response(
                message=f"Task {task_id} not found in cancellation registry",
                status_code=404
            )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to deregister task from cancellation"
        )


@router.get("/health")
async def cancellation_health():
    """
    Health check endpoint for the cancellation system.

    Returns:
        JSON response with system health status
    """
    try:
        # Get all task statuses to determine system health
        statuses = cancellation_manager.get_all_task_statuses()

        cancellable_tasks = len(statuses)
        cancelled_tasks = sum(1 for status in statuses.values() if status.get("is_cancelled", False))
        running_tasks = sum(1 for status in statuses.values() if status.get("is_running", False))

        return create_success_response(
            data={
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "total_cancellable_tasks": cancellable_tasks,
                "cancelled_tasks": cancelled_tasks,
                "running_tasks": running_tasks,
                "pending_tasks": cancellable_tasks - cancelled_tasks - running_tasks
            },
            message="Cancellation system is healthy"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Cancellation system health check failed"
        )


@router.post("/cancel-with-timeout/{task_id}")
async def cancel_task_if_timeout(
    task_id: str,
    timeout_seconds: float = Query(5.0, gt=0, description="Timeout in seconds"),
    reason: str = Query("timeout", description="Reason for cancellation")
):
    """
    Cancel a task if it doesn't complete within the specified timeout.

    Args:
        task_id: ID of the task to potentially cancel
        timeout_seconds: Timeout in seconds
        reason: Reason for cancellation

    Returns:
        JSON response with timeout cancellation request
    """
    try:
        # Validate cancellation reason
        try:
            cancellation_reason = CancellationReason(reason)
        except ValueError:
            return create_error_response(
                message=f"Invalid cancellation reason: {reason}",
                status_code=400,
                details={
                    "valid_reasons": [r.value for r in CancellationReason],
                    "provided_reason": reason
                }
            )

        # In a real implementation, we would schedule a delayed cancellation
        # Here we'll just return a placeholder response
        # A real implementation would use asyncio.call_later or similar

        import asyncio
        async def delayed_cancellation():
            await asyncio.sleep(timeout_seconds)

            # Check if the task is still running before cancelling
            if cancellation_manager.is_task_running(task_id):
                request_task_cancellation(task_id, cancellation_reason)

        # Start the delayed cancellation in the background
        asyncio.create_task(delayed_cancellation())

        return create_success_response(
            data={
                "task_id": task_id,
                "timeout_seconds": timeout_seconds,
                "scheduled_reason": cancellation_reason.value,
                "timestamp": datetime.utcnow().isoformat()
            },
            message=f"Task {task_id} will be cancelled if it doesn't complete within {timeout_seconds} seconds"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to schedule timeout cancellation"
        )


# Register the router in the main app
def register_cancellation_routes(app):
    """
    Register cancellation routes with the main application.

    Args:
        app: The FastAPI application instance
    """
    app.include_router(router)