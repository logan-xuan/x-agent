"""
Heartbeat emitter for the x-agent2 AI assistant system.

This module provides functionality for emitting heartbeat signals during
long-running tasks to indicate progress and activity.
"""

import asyncio
import json
from typing import Dict, Any, Optional, Callable, Union
from datetime import datetime
from enum import Enum
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
import time


class HeartbeatStatus(Enum):
    """Status values for heartbeat messages."""
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HeartbeatLevel(Enum):
    """Levels of heartbeat messages."""
    INFO = "info"
    PROGRESS = "progress"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HeartbeatMessage:
    """Structure for heartbeat messages."""
    id: str
    timestamp: datetime
    task_id: str
    status: HeartbeatStatus
    progress: float  # 0.0 to 100.0
    message: str
    level: HeartbeatLevel
    details: Optional[Dict[str, Any]]
    worker_id: Optional[str]
    metadata: Optional[Dict[str, Any]]


class HeartbeatEmitter:
    """Emits heartbeat messages for long-running tasks."""

    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self._callbacks: list[Callable[[HeartbeatMessage], None]] = []
        self.last_heartbeat_time = None
        self.heartbeat_interval = 5.0  # seconds

    def add_callback(self, callback: Callable[[HeartbeatMessage], None]):
        """
        Add a callback to be called when a heartbeat is emitted.

        Args:
            callback: Function to call when heartbeat is emitted
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[HeartbeatMessage], None]):
        """
        Remove a callback.

        Args:
            callback: Function to remove from callbacks
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit_heartbeat(
        self,
        progress: float = 0.0,
        message: str = "",
        status: HeartbeatStatus = HeartbeatStatus.RUNNING,
        level: HeartbeatLevel = HeartbeatLevel.INFO,
        details: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Emit a heartbeat message.

        Args:
            progress: Progress percentage (0.0 to 100.0)
            message: Message to include with heartbeat
            status: Status of the task
            level: Level of the heartbeat
            details: Additional details
            worker_id: ID of the worker emitting the heartbeat
            metadata: Additional metadata

        Returns:
            HeartbeatMessage that was emitted
        """
        heartbeat = HeartbeatMessage(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            task_id=self.task_id,
            status=status,
            progress=min(100.0, max(0.0, progress)),  # Clamp between 0 and 100
            message=message,
            level=level,
            details=details or {},
            worker_id=worker_id,
            metadata=metadata or {}
        )

        # Call all registered callbacks
        for callback in self._callbacks:
            try:
                callback(heartbeat)
            except Exception as e:
                self.logger.error(f"Error in heartbeat callback: {e}")

        # Log the heartbeat
        self.logger.info(f"Heartbeat: {self.task_id} - {status.value} - {progress}% - {message}")

        # Update last heartbeat time
        self.last_heartbeat_time = time.time()

        return heartbeat

    async def emit_heartbeat_async(
        self,
        progress: float = 0.0,
        message: str = "",
        status: HeartbeatStatus = HeartbeatStatus.RUNNING,
        level: HeartbeatLevel = HeartbeatLevel.INFO,
        details: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Asynchronously emit a heartbeat message.

        Args:
            progress: Progress percentage (0.0 to 100.0)
            message: Message to include with heartbeat
            status: Status of the task
            level: Level of the heartbeat
            details: Additional details
            worker_id: ID of the worker emitting the heartbeat
            metadata: Additional metadata

        Returns:
            HeartbeatMessage that was emitted
        """
        return self.emit_heartbeat(progress, message, status, level, details, worker_id, metadata)

    def start_task(
        self,
        task_description: str,
        total_steps: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Start a new task and emit a heartbeat.

        Args:
            task_description: Description of the task
            total_steps: Total number of steps (for progress calculation)
            metadata: Additional metadata

        Returns:
            HeartbeatMessage for the task start
        """
        self.is_running = True
        meta = metadata or {}
        if total_steps:
            meta['total_steps'] = total_steps

        return self.emit_heartbeat(
            progress=0.0,
            message=f"Starting: {task_description}",
            status=HeartbeatStatus.RUNNING,
            level=HeartbeatLevel.INFO,
            metadata=meta
        )

    def update_progress(
        self,
        current_step: int,
        total_steps: int,
        message: str = "",
        details: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Update progress and emit a heartbeat.

        Args:
            current_step: Current step number
            total_steps: Total number of steps
            message: Message to include with heartbeat
            details: Additional details

        Returns:
            HeartbeatMessage with progress update
        """
        if total_steps <= 0:
            progress = 0.0
        else:
            progress = min(100.0, (current_step / total_steps) * 100.0)

        return self.emit_heartbeat(
            progress=progress,
            message=message or f"Step {current_step} of {total_steps}",
            status=HeartbeatStatus.RUNNING,
            level=HeartbeatLevel.PROGRESS,
            details=details
        )

    def pause_task(self, message: str = "") -> HeartbeatMessage:
        """
        Pause the current task and emit a heartbeat.

        Args:
            message: Message to include with heartbeat

        Returns:
            HeartbeatMessage for the pause
        """
        self.is_running = False
        return self.emit_heartbeat(
            message=message or "Task paused",
            status=HeartbeatStatus.PAUSED,
            level=HeartbeatLevel.INFO
        )

    def resume_task(self, message: str = "") -> HeartbeatMessage:
        """
        Resume the current task and emit a heartbeat.

        Args:
            message: Message to include with heartbeat

        Returns:
            HeartbeatMessage for the resume
        """
        self.is_running = True
        return self.emit_heartbeat(
            message=message or "Task resumed",
            status=HeartbeatStatus.RUNNING,
            level=HeartbeatLevel.INFO
        )

    def complete_task(self, message: str = "", details: Optional[Dict[str, Any]] = None) -> HeartbeatMessage:
        """
        Complete the current task and emit a heartbeat.

        Args:
            message: Message to include with heartbeat
            details: Additional details

        Returns:
            HeartbeatMessage for the completion
        """
        self.is_running = False
        return self.emit_heartbeat(
            progress=100.0,
            message=message or "Task completed successfully",
            status=HeartbeatStatus.COMPLETED,
            level=HeartbeatLevel.INFO,
            details=details
        )

    def fail_task(self, error_message: str, details: Optional[Dict[str, Any]] = None) -> HeartbeatMessage:
        """
        Fail the current task and emit a heartbeat.

        Args:
            error_message: Error message
            details: Additional details

        Returns:
            HeartbeatMessage for the failure
        """
        self.is_running = False
        return self.emit_heartbeat(
            message=error_message,
            status=HeartbeatStatus.FAILED,
            level=HeartbeatLevel.ERROR,
            details=details
        )

    def cancel_task(self, message: str = "") -> HeartbeatMessage:
        """
        Cancel the current task and emit a heartbeat.

        Args:
            message: Message to include with heartbeat

        Returns:
            HeartbeatMessage for the cancellation
        """
        self.is_running = False
        return self.emit_heartbeat(
            message=message or "Task cancelled",
            status=HeartbeatStatus.CANCELLED,
            level=HeartbeatLevel.INFO
        )

    def set_heartbeat_interval(self, interval: float):
        """
        Set the minimum interval between heartbeats.

        Args:
            interval: Minimum interval in seconds
        """
        self.heartbeat_interval = interval


class HeartbeatManager:
    """Manages multiple heartbeat emitters and coordinates heartbeat activities."""

    def __init__(self):
        self.emitters: Dict[str, HeartbeatEmitter] = {}
        self.global_callbacks: list[Callable[[HeartbeatMessage], None]] = []
        self.logger = logging.getLogger(__name__)

    def register_emitter(self, emitter: HeartbeatEmitter) -> str:
        """
        Register a new heartbeat emitter.

        Args:
            emitter: HeartbeatEmitter to register

        Returns:
            Task ID of the registered emitter
        """
        self.emitters[emitter.task_id] = emitter

        # Add global callbacks to the new emitter
        for callback in self.global_callbacks:
            emitter.add_callback(callback)

        return emitter.task_id

    def unregister_emitter(self, task_id: str) -> bool:
        """
        Unregister a heartbeat emitter.

        Args:
            task_id: Task ID of the emitter to unregister

        Returns:
            True if successfully unregistered, False otherwise
        """
        if task_id in self.emitters:
            del self.emitters[task_id]
            return True
        return False

    def get_emitter(self, task_id: str) -> Optional[HeartbeatEmitter]:
        """
        Get a registered heartbeat emitter.

        Args:
            task_id: Task ID of the emitter to retrieve

        Returns:
            HeartbeatEmitter if found, None otherwise
        """
        return self.emitters.get(task_id)

    def add_global_callback(self, callback: Callable[[HeartbeatMessage], None]):
        """
        Add a global callback that receives all heartbeats.

        Args:
            callback: Function to call when any heartbeat is emitted
        """
        self.global_callbacks.append(callback)

        # Add this callback to all existing emitters
        for emitter in self.emitters.values():
            emitter.add_callback(callback)

    def remove_global_callback(self, callback: Callable[[HeartbeatMessage], None]):
        """
        Remove a global callback.

        Args:
            callback: Function to remove from global callbacks
        """
        if callback in self.global_callbacks:
            self.global_callbacks.remove(callback)

            # Remove this callback from all existing emitters
            for emitter in self.emitters.values():
                emitter.remove_callback(callback)

    def emit_to_all(
        self,
        message: str,
        status: HeartbeatStatus = HeartbeatStatus.RUNNING,
        level: HeartbeatLevel = HeartbeatLevel.INFO
    ):
        """
        Emit a message to all registered emitters.

        Args:
            message: Message to emit
            status: Status to set
            level: Level to set
        """
        for emitter in self.emitters.values():
            emitter.emit_heartbeat(
                message=message,
                status=status,
                level=level
            )

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a specific task.

        Args:
            task_id: Task ID to get status for

        Returns:
            Dictionary with task status information, or None if task not found
        """
        emitter = self.get_emitter(task_id)
        if not emitter:
            return None

        # In a real implementation, we'd track more detailed status
        # For now, return basic info
        return {
            "task_id": task_id,
            "is_running": emitter.is_running,
            "last_heartbeat": emitter.last_heartbeat_time
        }

    def get_all_task_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the status of all registered tasks.

        Returns:
            Dictionary mapping task IDs to their status information
        """
        statuses = {}
        for task_id in self.emitters.keys():
            status = self.get_task_status(task_id)
            if status:
                statuses[task_id] = status
        return statuses

    def cancel_all_tasks(self) -> Dict[str, Any]:
        """
        Cancel all registered tasks.

        Returns:
            Dictionary with cancellation results
        """
        results = {
            "cancelled": [],
            "failed": [],
            "already_completed": []
        }

        for task_id, emitter in self.emitters.items():
            try:
                # Check if task is still running
                if emitter.is_running:
                    emitter.cancel_task()
                    results["cancelled"].append(task_id)
                else:
                    results["already_completed"].append(task_id)
            except Exception as e:
                self.logger.error(f"Error cancelling task {task_id}: {e}")
                results["failed"].append({"task_id": task_id, "error": str(e)})

        return results


class TaskProgressTracker:
    """Tracks progress of tasks with detailed metrics."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.steps_completed = 0
        self.total_steps = 0
        self.start_time = None
        self.last_update_time = None
        self.estimated_completion_time = None
        self.speed_metrics = []  # Track speed over time
        self.history = []  # Keep history of progress updates
        self.logger = logging.getLogger(__name__)

    def start(self, total_steps: int):
        """
        Start tracking progress for a task.

        Args:
            total_steps: Total number of steps in the task
        """
        self.total_steps = total_steps
        self.start_time = time.time()
        self.last_update_time = self.start_time

    def update(self, steps: int = 1, message: str = "") -> Dict[str, Any]:
        """
        Update progress by the specified number of steps.

        Args:
            steps: Number of steps completed
            message: Optional message

        Returns:
            Dictionary with current progress metrics
        """
        self.steps_completed += steps
        current_time = time.time()

        # Calculate metrics
        elapsed_time = current_time - self.start_time if self.start_time else 0
        current_speed = self._calculate_current_speed(steps, current_time - self.last_update_time)

        # Estimate completion time
        remaining_steps = self.total_steps - self.steps_completed
        if current_speed > 0:
            estimated_remaining_time = remaining_steps / current_speed
            self.estimated_completion_time = current_time + estimated_remaining_time
        else:
            self.estimated_completion_time = None

        # Calculate progress percentage
        progress = 0.0
        if self.total_steps > 0:
            progress = min(100.0, (self.steps_completed / self.total_steps) * 100.0)

        # Store history
        history_entry = {
            "timestamp": current_time,
            "steps_completed": self.steps_completed,
            "progress": progress,
            "message": message,
            "elapsed_time": elapsed_time,
            "speed": current_speed,
            "estimated_remaining_time": estimated_remaining_time if current_speed > 0 else None
        }
        self.history.append(history_entry)

        # Keep only last 100 history entries
        if len(self.history) > 100:
            self.history = self.history[-100:]

        # Update last update time
        self.last_update_time = current_time

        return {
            "task_id": self.task_id,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "progress_percentage": progress,
            "elapsed_time": elapsed_time,
            "estimated_remaining_time": estimated_remaining_time if current_speed > 0 else None,
            "estimated_completion_time": self.estimated_completion_time.isoformat() if self.estimated_completion_time else None,
            "current_speed_steps_per_second": current_speed,
            "message": message
        }

    def _calculate_current_speed(self, steps_completed: int, time_elapsed: float) -> float:
        """
        Calculate the current speed of task execution.

        Args:
            steps_completed: Number of steps completed in this update
            time_elapsed: Time elapsed for these steps

        Returns:
            Speed in steps per second
        """
        if time_elapsed <= 0:
            return 0.0

        # Add to speed metrics
        current_speed = steps_completed / time_elapsed
        self.speed_metrics.append(current_speed)

        # Keep only last 10 speed measurements
        if len(self.speed_metrics) > 10:
            self.speed_metrics = self.speed_metrics[-10:]

        # Return average of recent speeds
        if self.speed_metrics:
            return sum(self.speed_metrics) / len(self.speed_metrics)
        else:
            return current_speed

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        Get current progress metrics.

        Returns:
            Dictionary with current metrics
        """
        if not self.start_time:
            return {"error": "Task not started"}

        current_time = time.time()
        elapsed_time = current_time - self.start_time

        progress = 0.0
        if self.total_steps > 0:
            progress = min(100.0, (self.steps_completed / self.total_steps) * 100.0)

        # Calculate average speed
        avg_speed = 0.0
        if elapsed_time > 0:
            avg_speed = self.steps_completed / elapsed_time if self.steps_completed > 0 else 0.0

        # Calculate ETA based on average speed
        remaining_steps = self.total_steps - self.steps_completed
        eta = None
        if avg_speed > 0:
            eta = remaining_steps / avg_speed

        return {
            "task_id": self.task_id,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "progress_percentage": progress,
            "elapsed_time": elapsed_time,
            "estimated_remaining_time": eta,
            "average_speed_steps_per_second": avg_speed,
            "current_speed_steps_per_second": self.speed_metrics[-1] if self.speed_metrics else 0.0,
            "last_update_time": self.last_update_time
        }

    def is_complete(self) -> bool:
        """Check if the task is complete."""
        return self.steps_completed >= self.total_steps if self.total_steps > 0 else False

    def reset(self):
        """Reset the tracker."""
        self.steps_completed = 0
        self.total_steps = 0
        self.start_time = None
        self.last_update_time = None
        self.estimated_completion_time = None
        self.speed_metrics = []
        self.history = []


class AdvancedHeartbeatEmitter(HeartbeatEmitter):
    """Enhanced heartbeat emitter with advanced tracking capabilities."""

    def __init__(self, task_id: Optional[str] = None):
        super().__init__(task_id)
        self.progress_tracker = TaskProgressTracker(self.task_id)
        self.steps_tracking_enabled = True

    def start_task_with_tracking(
        self,
        task_description: str,
        total_steps: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Start a new task with progress tracking enabled.

        Args:
            task_description: Description of the task
            total_steps: Total number of steps in the task
            metadata: Additional metadata

        Returns:
            HeartbeatMessage for the task start
        """
        # Initialize progress tracker
        self.progress_tracker.start(total_steps)

        return self.start_task(
            task_description,
            total_steps=total_steps,
            metadata=metadata
        )

    def update_progress_with_tracking(
        self,
        steps_completed: int = 1,
        message: str = "",
        details: Optional[Dict[str, Any]] = None
    ) -> HeartbeatMessage:
        """
        Update progress using the built-in tracker.

        Args:
            steps_completed: Number of steps completed
            message: Message to include
            details: Additional details

        Returns:
            HeartbeatMessage with progress update
        """
        if not self.steps_tracking_enabled:
            # Fall back to regular progress update
            return super().update_progress(
                self.progress_tracker.steps_completed + steps_completed,
                self.progress_tracker.total_steps,
                message,
                details
            )

        # Update tracker and get metrics
        metrics = self.progress_tracker.update(steps_completed, message)

        return self.emit_heartbeat(
            progress=metrics["progress_percentage"],
            message=message or f"Completed {self.progress_tracker.steps_completed}/{self.progress_tracker.total_steps} steps",
            status=HeartbeatStatus.RUNNING,
            level=HeartbeatLevel.PROGRESS,
            details={
                "steps_completed": metrics["steps_completed"],
                "total_steps": metrics["total_steps"],
                "elapsed_time": metrics["elapsed_time"],
                "estimated_remaining_time": metrics["estimated_remaining_time"],
                "speed": metrics["current_speed_steps_per_second"],
                **(details or {})
            }
        )

    def get_task_metrics(self) -> Dict[str, Any]:
        """
        Get current task metrics.

        Returns:
            Dictionary with task metrics
        """
        return self.progress_tracker.get_current_metrics()


# Global heartbeat manager instance
heartbeat_manager = HeartbeatManager()


# Convenience functions
def create_heartbeat_emitter(task_id: Optional[str] = None) -> HeartbeatEmitter:
    """Create a new heartbeat emitter."""
    emitter = HeartbeatEmitter(task_id)
    heartbeat_manager.register_emitter(emitter)
    return emitter


def create_advanced_heartbeat_emitter(task_id: Optional[str] = None) -> AdvancedHeartbeatEmitter:
    """Create a new advanced heartbeat emitter with progress tracking."""
    emitter = AdvancedHeartbeatEmitter(task_id)
    heartbeat_manager.register_emitter(emitter)
    return emitter


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a specific task."""
    return heartbeat_manager.get_task_status(task_id)


def get_all_task_statuses() -> Dict[str, Dict[str, Any]]:
    """Get the status of all registered tasks."""
    return heartbeat_manager.get_all_task_statuses()


def add_global_heartbeat_callback(callback: Callable[[HeartbeatMessage], None]):
    """Add a global callback for all heartbeats."""
    heartbeat_manager.add_global_callback(callback)


def remove_global_heartbeat_callback(callback: Callable[[HeartbeatMessage], None]):
    """Remove a global callback."""
    heartbeat_manager.remove_global_callback(callback)