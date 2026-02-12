"""
Heartbeat API endpoints for the x-agent2 AI assistant system.

This module provides API endpoints for monitoring long-running tasks
through heartbeat signals and progress tracking.
"""

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
import json

from src.agent_core.monitoring.heartbeat_emitter import (
    heartbeat_manager,
    create_heartbeat_emitter,
    get_task_status,
    get_all_task_statuses,
    HeartbeatStatus,
    HeartbeatLevel,
    HeartbeatMessage
)
from src.agent_core.api_utils.response_handler import (
    APIResponse,
    APIExceptionHandler,
    create_success_response,
    create_error_response
)
from src.agent_core.security.tool_security import authenticate_user


router = APIRouter(prefix="/heartbeat", tags=["heartbeat"])


@router.post("/start-task")
async def start_task(
    task_id: str = Query(..., description="Unique identifier for the task"),
    task_description: str = Query(..., description="Description of the task"),
    total_steps: Optional[int] = Query(None, description="Total number of steps in the task"),
    metadata: Optional[str] = Query(None, description="Additional metadata as JSON string")
):
    """
    Start monitoring a long-running task.

    Args:
        task_id: Unique identifier for the task
        task_description: Description of what the task does
        total_steps: Total number of steps (optional)
        metadata: Additional metadata as JSON string (optional)

    Returns:
        JSON response with task start confirmation
    """
    try:
        # Parse metadata if provided
        parsed_metadata = None
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                return create_error_response(
                    message="Invalid JSON in metadata parameter",
                    status_code=400
                )

        # Create a new heartbeat emitter for the task
        emitter = create_heartbeat_emitter(task_id)

        # Start the task with the emitter
        heartbeat_msg = emitter.start_task(
            task_description=task_description,
            total_steps=total_steps,
            metadata=parsed_metadata
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": "started",
                "timestamp": datetime.utcnow().isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} started successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to start task monitoring"
        )


@router.post("/update-progress")
async def update_task_progress(
    task_id: str = Query(..., description="ID of the task to update"),
    current_step: int = Query(..., ge=0, description="Current step number"),
    total_steps: int = Query(..., gt=0, description="Total number of steps"),
    message: Optional[str] = Query(None, description="Optional progress message"),
    details: Optional[str] = Query(None, description="Additional details as JSON string")
):
    """
    Update progress for a long-running task.

    Args:
        task_id: ID of the task to update
        current_step: Current step number
        total_steps: Total number of steps
        message: Optional progress message
        details: Additional details as JSON string

    Returns:
        JSON response with progress update confirmation
    """
    try:
        # Parse details if provided
        parsed_details = None
        if details:
            try:
                parsed_details = json.loads(details)
            except json.JSONDecodeError:
                return create_error_response(
                    message="Invalid JSON in details parameter",
                    status_code=400
                )

        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Update progress
        heartbeat_msg = emitter.update_progress(
            current_step=current_step,
            total_steps=total_steps,
            message=message or f"Step {current_step} of {total_steps}",
            details=parsed_details
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "progress": heartbeat_msg.progress,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Progress updated for task {task_id}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to update task progress"
        )


@router.post("/complete-task")
async def complete_task(
    task_id: str = Query(..., description="ID of the task to complete"),
    message: Optional[str] = Query(None, description="Optional completion message"),
    details: Optional[str] = Query(None, description="Completion details as JSON string")
):
    """
    Mark a long-running task as completed.

    Args:
        task_id: ID of the task to complete
        message: Optional completion message
        details: Completion details as JSON string

    Returns:
        JSON response with completion confirmation
    """
    try:
        # Parse details if provided
        parsed_details = None
        if details:
            try:
                parsed_details = json.loads(details)
            except json.JSONDecodeError:
                return create_error_response(
                    message="Invalid JSON in details parameter",
                    status_code=400
                )

        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Complete the task
        heartbeat_msg = emitter.complete_task(
            message=message or f"Task {task_id} completed successfully",
            details=parsed_details
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} completed successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to complete task"
        )


@router.post("/fail-task")
async def fail_task(
    task_id: str = Query(..., description="ID of the task to mark as failed"),
    error_message: str = Query(..., description="Error message"),
    details: Optional[str] = Query(None, description="Failure details as JSON string")
):
    """
    Mark a long-running task as failed.

    Args:
        task_id: ID of the task to mark as failed
        error_message: Error message explaining the failure
        details: Failure details as JSON string

    Returns:
        JSON response with failure confirmation
    """
    try:
        # Parse details if provided
        parsed_details = None
        if details:
            try:
                parsed_details = json.loads(details)
            except json.JSONDecodeError:
                return create_error_response(
                    message="Invalid JSON in details parameter",
                    status_code=400
                )

        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Mark task as failed
        heartbeat_msg = emitter.fail_task(
            error_message=error_message,
            details=parsed_details
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "error_message": error_message,
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} marked as failed: {error_message}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to mark task as failed"
        )


@router.post("/cancel-task")
async def cancel_task(
    task_id: str = Query(..., description="ID of the task to cancel"),
    message: Optional[str] = Query(None, description="Optional cancellation message")
):
    """
    Cancel a long-running task.

    Args:
        task_id: ID of the task to cancel
        message: Optional cancellation message

    Returns:
        JSON response with cancellation confirmation
    """
    try:
        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Cancel the task
        heartbeat_msg = emitter.cancel_task(
            message=message or f"Task {task_id} cancelled"
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} cancelled successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to cancel task"
        )


@router.get("/task-status/{task_id}")
async def get_single_task_status(task_id: str):
    """
    Get the status of a specific long-running task.

    Args:
        task_id: ID of the task to check status for

    Returns:
        JSON response with task status information
    """
    try:
        status = get_task_status(task_id)

        if not status:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        return create_success_response(
            data=status,
            message=f"Status for task {task_id}"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to get task status"
        )


@router.get("/all-task-statuses")
async def get_all_tasks_status():
    """
    Get the status of all long-running tasks.

    Returns:
        JSON response with all task statuses
    """
    try:
        statuses = get_all_task_statuses()

        return create_success_response(
            data={
                "statuses": statuses,
                "total_tasks": len(statuses)
            },
            message="Statuses for all tasks retrieved successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to get all task statuses"
        )


@router.get("/recent-heartbeats/{task_id}")
async def get_recent_heartbeats(
    task_id: str,
    limit: int = Query(50, ge=1, le=1000, description="Number of recent heartbeats to return")
):
    """
    Get recent heartbeat messages for a specific task.

    Args:
        task_id: ID of the task to get heartbeats for
        limit: Maximum number of heartbeats to return

    Returns:
        JSON response with recent heartbeat messages
    """
    try:
        # This would require extending the emitter to store recent heartbeats
        # For now, we'll return a placeholder implementation
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # In a real implementation, this would return stored heartbeat history
        # Since our current implementation doesn't store history, we'll return a mock response
        return create_success_response(
            data={
                "task_id": task_id,
                "heartbeats": [],
                "limit": limit,
                "total_available": 0
            },
            message=f"Recent heartbeats for task {task_id} (history not implemented in current version)"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to get recent heartbeats"
        )


@router.websocket("/ws/monitor/{task_id}")
async def websocket_monitor(websocket: WebSocket, task_id: str):
    """
    WebSocket endpoint for real-time task monitoring.

    Args:
        websocket: WebSocket connection
        task_id: ID of the task to monitor
    """
    await websocket.accept()

    # Check if task exists
    emitter = heartbeat_manager.get_emitter(task_id)
    if not emitter:
        await websocket.close(code=1003, reason=f"Task {task_id} not found")
        return

    # Add a callback to send heartbeat updates via WebSocket
    def send_heartbeat(heartbeat: HeartbeatMessage):
        try:
            message_data = {
                "id": heartbeat.id,
                "task_id": heartbeat.task_id,
                "timestamp": heartbeat.timestamp.isoformat(),
                "status": heartbeat.status.value,
                "progress": heartbeat.progress,
                "message": heartbeat.message,
                "level": heartbeat.level.value,
                "details": heartbeat.details,
                "worker_id": heartbeat.worker_id
            }
            websocket.send_text(json.dumps(message_data))
        except:
            # If sending fails, the connection may be closed
            pass

    # Add the WebSocket callback to the emitter
    emitter.add_callback(send_heartbeat)

    try:
        # Keep the connection alive
        while True:
            # Receive messages from the client (could be used for controlling the task)
            try:
                data = await websocket.receive_text()

                # Parse the received command
                try:
                    command = json.loads(data)
                    cmd_type = command.get("type")

                    if cmd_type == "pause":
                        # Pause the task if the client sends a pause command
                        emitter.pause_task("Paused by user request")
                    elif cmd_type == "resume":
                        # Resume the task if the client sends a resume command
                        emitter.resume_task("Resumed by user request")
                    elif cmd_type == "cancel":
                        # Cancel the task if the client sends a cancel command
                        emitter.cancel_task("Cancelled by user request")
                    else:
                        # Unknown command
                        await websocket.send_text(json.dumps({
                            "error": f"Unknown command: {cmd_type}",
                            "type": "error"
                        }))

                except json.JSONDecodeError:
                    # If the data isn't valid JSON, send an error
                    await websocket.send_text(json.dumps({
                        "error": "Invalid JSON command",
                        "type": "error"
                    }))
            except:
                # If receiving fails, break the loop (client disconnected)
                break
    except WebSocketDisconnect:
        # Handle disconnection
        pass
    finally:
        # Remove the callback when the connection closes
        emitter.remove_callback(send_heartbeat)


@router.get("/health")
async def heartbeat_health():
    """
    Health check endpoint for the heartbeat system.

    Returns:
        JSON response with system health status
    """
    try:
        # Get all task statuses to determine system health
        statuses = get_all_task_statuses()

        active_tasks = sum(1 for status in statuses.values() if status.get("is_running", False))
        total_tasks = len(statuses)

        return create_success_response(
            data={
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
                "total_tasks_monitored": total_tasks,
                "active_tasks": active_tasks,
                "inactive_tasks": total_tasks - active_tasks
            },
            message="Heartbeat system is healthy"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Heartbeat system health check failed"
        )


@router.post("/pause-task/{task_id}")
async def pause_task(task_id: str, message: Optional[str] = Query(None)):
    """
    Pause a long-running task.

    Args:
        task_id: ID of the task to pause
        message: Optional pause message

    Returns:
        JSON response with pause confirmation
    """
    try:
        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Pause the task
        heartbeat_msg = emitter.pause_task(
            message=message or f"Task {task_id} paused"
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} paused successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to pause task"
        )


@router.post("/resume-task/{task_id}")
async def resume_task(task_id: str, message: Optional[str] = Query(None)):
    """
    Resume a paused long-running task.

    Args:
        task_id: ID of the task to resume
        message: Optional resume message

    Returns:
        JSON response with resume confirmation
    """
    try:
        # Get the emitter for this task
        emitter = heartbeat_manager.get_emitter(task_id)
        if not emitter:
            return create_error_response(
                message=f"Task {task_id} not found or not started",
                status_code=404
            )

        # Resume the task
        heartbeat_msg = emitter.resume_task(
            message=message or f"Task {task_id} resumed"
        )

        return create_success_response(
            data={
                "task_id": task_id,
                "status": heartbeat_msg.status.value,
                "timestamp": heartbeat_msg.timestamp.isoformat(),
                "heartbeat_id": heartbeat_msg.id
            },
            message=f"Task {task_id} resumed successfully"
        )

    except Exception as e:
        return APIExceptionHandler.handle_general_error(
            e,
            message="Failed to resume task"
        )


# Register the router in the main app
def register_heartbeat_routes(app):
    """
    Register heartbeat routes with the main application.

    Args:
        app: The FastAPI application instance
    """
    app.include_router(router)