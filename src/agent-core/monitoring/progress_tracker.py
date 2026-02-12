"""
Task progress tracking for the x-agent2 AI assistant system.

This module provides functionality for tracking and monitoring the progress
of long-running tasks.
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
import time


class TaskProgressStatus(Enum):
    """Status values for task progress."""
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for tasks."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaskProgress:
    """Structure for task progress information."""
    id: str
    task_id: str
    status: TaskProgressStatus
    progress_percent: float  # 0.0 to 100.0
    current_step: int
    total_steps: int
    current_stage: str
    total_stages: int
    message: str
    start_time: datetime
    estimated_completion_time: Optional[datetime]
    actual_completion_time: Optional[datetime]
    elapsed_time: Optional[timedelta]
    remaining_time: Optional[timedelta]
    metadata: Dict[str, Any]


class TaskProgressTracker:
    """Tracks progress of tasks with detailed metrics."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._tasks: Dict[str, TaskProgress] = {}
        self._stage_names: Dict[str, List[str]] = {}  # task_id -> list of stage names
        self._current_stage_indices: Dict[str, int] = {}  # task_id -> current stage index

    def start_task(
        self,
        task_id: str,
        task_name: str,
        total_steps: int,
        stages: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Start tracking progress for a new task.

        Args:
            task_id: Unique identifier for the task
            task_name: Name of the task
            total_steps: Total number of steps in the task
            stages: Optional list of stages for the task
            priority: Priority level of the task
            metadata: Additional metadata for the task

        Returns:
            True if successful, False otherwise
        """
        if task_id in self._tasks:
            self.logger.warning(f"Task {task_id} already exists in progress tracker")
            return False

        stages_list = stages or [task_name]  # Default to single stage if not provided
        self._stage_names[task_id] = stages_list
        self._current_stage_indices[task_id] = 0

        progress = TaskProgress(
            id=str(uuid.uuid4()),
            task_id=task_id,
            status=TaskProgressStatus.QUEUED,
            progress_percent=0.0,
            current_step=0,
            total_steps=total_steps,
            current_stage=stages_list[0],
            total_stages=len(stages_list),
            message="Task queued",
            start_time=datetime.utcnow(),
            estimated_completion_time=None,
            actual_completion_time=None,
            elapsed_time=None,
            remaining_time=None,
            metadata=metadata or {}
        )

        self._tasks[task_id] = progress
        self.logger.info(f"Started tracking task {task_id}: {task_name}")

        # Update status to running immediately
        return self.update_status(task_id, TaskProgressStatus.RUNNING, "Task started")

    def update_progress(
        self,
        task_id: str,
        current_step: Optional[int] = None,
        message: Optional[str] = None,
        increment_steps: int = 0
    ) -> bool:
        """
        Update progress for a task.

        Args:
            task_id: ID of the task to update
            current_step: Current step number (absolute)
            message: Optional message
            increment_steps: Number of steps to increment by (relative)

        Returns:
            True if successful, False otherwise
        """
        if task_id not in self._tasks:
            return False

        task_progress = self._tasks[task_id]

        # Update step count
        if current_step is not None:
            task_progress.current_step = max(0, current_step)
        elif increment_steps != 0:
            task_progress.current_step = max(0, task_progress.current_step + increment_steps)

        # Calculate progress percentage
        if task_progress.total_steps > 0:
            task_progress.progress_percent = min(100.0, (task_progress.current_step / task_progress.total_steps) * 100.0)
        else:
            task_progress.progress_percent = 0.0

        # Update message if provided
        if message:
            task_progress.message = message

        # Update timing information
        self._update_timing_info(task_id)

        return True

    def advance_to_next_stage(
        self,
        task_id: str,
        message: Optional[str] = None
    ) -> bool:
        """
        Advance a task to the next stage.

        Args:
            task_id: ID of the task to advance
            message: Optional message

        Returns:
            True if successful, False otherwise
        """
        if task_id not in self._tasks or task_id not in self._stage_names:
            return False

        current_stage_idx = self._current_stage_indices[task_id]
        total_stages = len(self._stage_names[task_id])

        # Check if there's a next stage
        if current_stage_idx >= total_stages - 1:
            self.logger.warning(f"Task {task_id} has already reached the final stage")
            return False

        # Move to next stage
        self._current_stage_indices[task_id] = current_stage_idx + 1
        next_stage = self._stage_names[task_id][current_stage_idx + 1]

        task_progress = self._tasks[task_id]
        task_progress.current_stage = next_stage

        if message:
            task_progress.message = message
        else:
            task_progress.message = f"Advanced to stage: {next_stage}"

        # Reset step count for the new stage if this is a stage-based progression
        # For now, we'll just update the timing info
        self._update_timing_info(task_id)

        return True

    def update_status(
        self,
        task_id: str,
        status: TaskProgressStatus,
        message: Optional[str] = None
    ) -> bool:
        """
        Update the status of a task.

        Args:
            task_id: ID of the task to update
            status: New status for the task
            message: Optional message

        Returns:
            True if successful, False otherwise
        """
        if task_id not in self._tasks:
            return False

        task_progress = self._tasks[task_id]
        old_status = task_progress.status
        task_progress.status = status

        # Update message if provided
        if message:
            task_progress.message = message

        # Update completion time if the task is completed
        if status in [TaskProgressStatus.COMPLETED, TaskProgressStatus.FAILED, TaskProgressStatus.CANCELLED]:
            task_progress.actual_completion_time = datetime.utcnow()

        # Update timing info
        self._update_timing_info(task_id)

        self.logger.info(f"Task {task_id} status changed from {old_status.value} to {status.value}")

        return True

    def complete_task(self, task_id: str, message: Optional[str] = None) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: ID of the task to complete
            message: Optional completion message

        Returns:
            True if successful, False otherwise
        """
        success = self.update_status(task_id, TaskProgressStatus.COMPLETED, message)
        if success:
            self._update_timing_info(task_id)
        return success

    def fail_task(self, task_id: str, error_message: str) -> bool:
        """
        Mark a task as failed.

        Args:
            task_id: ID of the task to fail
            error_message: Error message

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(task_id, TaskProgressStatus.FAILED, error_message)

    def cancel_task(self, task_id: str, message: Optional[str] = None) -> bool:
        """
        Mark a task as cancelled.

        Args:
            task_id: ID of the task to cancel
            message: Optional cancellation message

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(task_id, TaskProgressStatus.CANCELLED, message)

    def pause_task(self, task_id: str, message: Optional[str] = None) -> bool:
        """
        Mark a task as paused.

        Args:
            task_id: ID of the task to pause
            message: Optional pause message

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(task_id, TaskProgressStatus.PAUSED, message)

    def resume_task(self, task_id: str, message: Optional[str] = None) -> bool:
        """
        Resume a paused task.

        Args:
            task_id: ID of the task to resume
            message: Optional resume message

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(task_id, TaskProgressStatus.RUNNING, message)

    def get_task_progress(self, task_id: str) -> Optional[TaskProgress]:
        """
        Get the progress information for a task.

        Args:
            task_id: ID of the task to get progress for

        Returns:
            TaskProgress object if found, None otherwise
        """
        if task_id not in self._tasks:
            return None

        # Update timing info before returning to ensure accuracy
        self._update_timing_info(task_id)
        return self._tasks[task_id]

    def get_task_progress_dict(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the progress information for a task as a dictionary.

        Args:
            task_id: ID of the task to get progress for

        Returns:
            Dictionary with task progress information if found, None otherwise
        """
        progress = self.get_task_progress(task_id)
        if not progress:
            return None

        return {
            "id": progress.id,
            "task_id": progress.task_id,
            "status": progress.status.value,
            "progress_percent": progress.progress_percent,
            "current_step": progress.current_step,
            "total_steps": progress.total_steps,
            "current_stage": progress.current_stage,
            "total_stages": progress.total_stages,
            "message": progress.message,
            "start_time": progress.start_time.isoformat(),
            "estimated_completion_time": progress.estimated_completion_time.isoformat() if progress.estimated_completion_time else None,
            "actual_completion_time": progress.actual_completion_time.isoformat() if progress.actual_completion_time else None,
            "elapsed_time_seconds": progress.elapsed_time.total_seconds() if progress.elapsed_time else None,
            "remaining_time_seconds": progress.remaining_time.total_seconds() if progress.remaining_time else None,
            "metadata": progress.metadata
        }

    def get_all_task_progress(self) -> Dict[str, Dict[str, Any]]:
        """
        Get progress information for all tracked tasks.

        Returns:
            Dictionary mapping task IDs to their progress information
        """
        all_progress = {}
        for task_id in self._tasks:
            progress_dict = self.get_task_progress_dict(task_id)
            if progress_dict:
                all_progress[task_id] = progress_dict
        return all_progress

    def is_task_complete(self, task_id: str) -> bool:
        """
        Check if a task is complete.

        Args:
            task_id: ID of the task to check

        Returns:
            True if complete, False otherwise
        """
        progress = self.get_task_progress(task_id)
        if not progress:
            return False
        return progress.status == TaskProgressStatus.COMPLETED

    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is currently running.

        Args:
            task_id: ID of the task to check

        Returns:
            True if running, False otherwise
        """
        progress = self.get_task_progress(task_id)
        if not progress:
            return False
        return progress.status == TaskProgressStatus.RUNNING

    def get_tasks_by_status(self, status: TaskProgressStatus) -> List[str]:
        """
        Get all tasks with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of task IDs with the specified status
        """
        task_ids = []
        for task_id, progress in self._tasks.items():
            if progress.status == status:
                task_ids.append(task_id)
        return task_ids

    def get_tasks_by_priority(self, priority: TaskPriority) -> List[str]:
        """
        Get all tasks with a specific priority (from metadata).

        Args:
            priority: Priority to filter by

        Returns:
            List of task IDs with the specified priority
        """
        task_ids = []
        for task_id, progress in self._tasks.items():
            if progress.metadata.get("priority") == priority.value:
                task_ids.append(task_id)
        return task_ids

    def _update_timing_info(self, task_id: str):
        """
        Update timing information for a task.

        Args:
            task_id: ID of the task to update timing for
        """
        if task_id not in self._tasks:
            return

        task_progress = self._tasks[task_id]
        current_time = datetime.utcnow()

        # Calculate elapsed time
        task_progress.elapsed_time = current_time - task_progress.start_time

        # Calculate estimated completion time and remaining time
        if task_progress.status == TaskProgressStatus.RUNNING and task_progress.total_steps > 0 and task_progress.current_step > 0:
            # Calculate average time per step
            steps_completed = task_progress.current_step
            if steps_completed > 0:
                time_per_step = task_progress.elapsed_time.total_seconds() / steps_completed
                remaining_steps = task_progress.total_steps - steps_completed
                estimated_remaining_seconds = time_per_step * remaining_steps
                task_progress.remaining_time = timedelta(seconds=estimated_remaining_seconds)
                task_progress.estimated_completion_time = current_time + timedelta(seconds=estimated_remaining_seconds)

    def get_completion_percentage(self, task_id: str) -> float:
        """
        Get the completion percentage for a task.

        Args:
            task_id: ID of the task to get percentage for

        Returns:
            Completion percentage as a float (0.0 to 100.0)
        """
        progress = self.get_task_progress(task_id)
        if not progress:
            return 0.0
        return progress.progress_percent

    def get_eta(self, task_id: str) -> Optional[datetime]:
        """
        Get the estimated time of arrival/finish for a task.

        Args:
            task_id: ID of the task to get ETA for

        Returns:
            Estimated completion time if available, None otherwise
        """
        progress = self.get_task_progress(task_id)
        if not progress:
            return None
        return progress.estimated_completion_time

    def remove_task(self, task_id: str) -> bool:
        """
        Remove a task from tracking (after completion, failure, or cancellation).

        Args:
            task_id: ID of the task to remove

        Returns:
            True if successful, False otherwise
        """
        if task_id not in self._tasks:
            return False

        # Clean up related data structures
        del self._tasks[task_id]
        if task_id in self._stage_names:
            del self._stage_names[task_id]
        if task_id in self._current_stage_indices:
            del self._current_stage_indices[task_id]

        self.logger.info(f"Removed task {task_id} from progress tracker")
        return True

    def get_average_completion_time(self, task_type: Optional[str] = None) -> Optional[float]:
        """
        Get the average completion time for completed tasks.

        Args:
            task_type: Optional task type to filter by

        Returns:
            Average completion time in seconds, or None if no completed tasks
        """
        completed_tasks = self.get_tasks_by_status(TaskProgressStatus.COMPLETED)
        if not completed_tasks:
            return None

        total_time = 0
        count = 0

        for task_id in completed_tasks:
            progress = self._tasks[task_id]
            if task_type and progress.metadata.get("type") != task_type:
                continue

            if progress.elapsed_time:
                total_time += progress.elapsed_time.total_seconds()
                count += 1

        return total_time / count if count > 0 else None

    def get_throughput_rate(self, task_type: Optional[str] = None) -> float:
        """
        Get the average throughput rate (tasks per hour) for completed tasks.

        Args:
            task_type: Optional task type to filter by

        Returns:
            Throughput rate as tasks per hour
        """
        completed_tasks = self.get_tasks_by_status(TaskProgressStatus.COMPLETED)
        if not completed_tasks:
            return 0.0

        # Count tasks of specific type if specified
        if task_type:
            count = 0
            for task_id in completed_tasks:
                if self._tasks[task_id].metadata.get("type") == task_type:
                    count += 1
        else:
            count = len(completed_tasks)

        # Calculate time span from earliest start to latest completion
        start_times = []
        completion_times = []
        for task_id in completed_tasks:
            if task_type and self._tasks[task_id].metadata.get("type") != task_type:
                continue
            start_times.append(self._tasks[task_id].start_time)
            if self._tasks[task_id].actual_completion_time:
                completion_times.append(self._tasks[task_id].actual_completion_time)

        if not start_times or not completion_times:
            return 0.0

        time_span = max(completion_times) - min(start_times)
        hours_span = time_span.total_seconds() / 3600  # seconds in an hour

        return count / hours_span if hours_span > 0 else 0.0


class AdvancedTaskProgressTracker(TaskProgressTracker):
    """Extended task progress tracker with additional features."""

    def __init__(self):
        super().__init__()
        self._historical_data: List[TaskProgress] = []
        self._performance_metrics: Dict[str, Dict[str, Any]] = {}

    def complete_task(self, task_id: str, message: Optional[str] = None) -> bool:
        """
        Mark a task as completed and store historical data.
        """
        success = super().complete_task(task_id, message)

        if success and task_id in self._tasks:
            # Store completed task in historical data
            task_progress = self._tasks[task_id]
            self._historical_data.append(task_progress)

            # Update performance metrics
            self._update_performance_metrics(task_progress)

        return success

    def _update_performance_metrics(self, task_progress: TaskProgress):
        """
        Update performance metrics based on completed task.

        Args:
            task_progress: The completed task's progress information
        """
        task_type = task_progress.metadata.get("type", "general")

        if task_type not in self._performance_metrics:
            self._performance_metrics[task_type] = {
                "completed_count": 0,
                "total_duration": 0,
                "total_steps": 0,
                "avg_completion_time": 0,
                "avg_steps_per_second": 0
            }

        metrics = self._performance_metrics[task_type]
        metrics["completed_count"] += 1

        if task_progress.elapsed_time:
            duration = task_progress.elapsed_time.total_seconds()
            metrics["total_duration"] += duration
            metrics["avg_completion_time"] = metrics["total_duration"] / metrics["completed_count"]

        if task_progress.total_steps > 0:
            metrics["total_steps"] += task_progress.total_steps
            if task_progress.elapsed_time and task_progress.elapsed_time.total_seconds() > 0:
                steps_per_sec = task_progress.total_steps / task_progress.elapsed_time.total_seconds()
                # For averaging steps per second, we'd need to store all individual values
                # For now, just keep track of total for average calculation
                pass

    def get_performance_report(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a performance report for tasks.

        Args:
            task_type: Optional task type to filter by

        Returns:
            Dictionary with performance metrics
        """
        if task_type:
            if task_type in self._performance_metrics:
                return {task_type: self._performance_metrics[task_type]}
            else:
                return {task_type: {}}
        else:
            return self._performance_metrics.copy()

    def get_historical_tasks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get historical task data.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of historical task progress data
        """
        recent_tasks = self._historical_data[-limit:] if len(self._historical_data) > limit else self._historical_data
        return [self._progress_to_dict(task) for task in recent_tasks]

    def _progress_to_dict(self, progress: TaskProgress) -> Dict[str, Any]:
        """
        Convert TaskProgress object to dictionary.

        Args:
            progress: TaskProgress object to convert

        Returns:
            Dictionary representation of the TaskProgress
        """
        return {
            "id": progress.id,
            "task_id": progress.task_id,
            "status": progress.status.value,
            "progress_percent": progress.progress_percent,
            "current_step": progress.current_step,
            "total_steps": progress.total_steps,
            "current_stage": progress.current_stage,
            "total_stages": progress.total_stages,
            "message": progress.message,
            "start_time": progress.start_time.isoformat(),
            "estimated_completion_time": progress.estimated_completion_time.isoformat() if progress.estimated_completion_time else None,
            "actual_completion_time": progress.actual_completion_time.isoformat() if progress.actual_completion_time else None,
            "elapsed_time_seconds": progress.elapsed_time.total_seconds() if progress.elapsed_time else None,
            "remaining_time_seconds": progress.remaining_time.total_seconds() if progress.remaining_time else None,
            "metadata": progress.metadata
        }

    def export_progress_data(self, filepath: str, format: str = "json") -> bool:
        """
        Export progress tracking data to a file.

        Args:
            filepath: Path to export the data to
            format: Format to export in ("json" or "csv")

        Returns:
            True if successful, False otherwise
        """
        try:
            if format.lower() == "json":
                data = {
                    "export_timestamp": datetime.utcnow().isoformat(),
                    "tasks": self.get_all_task_progress(),
                    "historical_tasks": self.get_historical_tasks(),
                    "performance_metrics": self.get_performance_report()
                }

                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=str)

            elif format.lower() == "csv":
                import csv

                # Create CSV with current tasks
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = [
                        'task_id', 'status', 'progress_percent', 'current_step',
                        'total_steps', 'current_stage', 'message', 'start_time'
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                    writer.writeheader()
                    for task_id, task_data in self.get_all_task_progress().items():
                        writer.writerow({
                            'task_id': task_data['task_id'],
                            'status': task_data['status'],
                            'progress_percent': task_data['progress_percent'],
                            'current_step': task_data['current_step'],
                            'total_steps': task_data['total_steps'],
                            'current_stage': task_data['current_stage'],
                            'message': task_data['message'],
                            'start_time': task_data['start_time']
                        })
            else:
                self.logger.error(f"Unsupported export format: {format}")
                return False

            self.logger.info(f"Exported progress data to {filepath}")
            return True

        except Exception as e:
            self.logger.error(f"Error exporting progress data: {e}")
            return False


# Global task progress tracker instance
task_progress_tracker = AdvancedTaskProgressTracker()


# Convenience functions
def start_task_tracking(
    task_id: str,
    task_name: str,
    total_steps: int,
    stages: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Start tracking progress for a new task."""
    return task_progress_tracker.start_task(task_id, task_name, total_steps, stages, metadata=metadata)


def update_task_progress(
    task_id: str,
    current_step: Optional[int] = None,
    message: Optional[str] = None,
    increment_steps: int = 0
) -> bool:
    """Update progress for a task."""
    return task_progress_tracker.update_progress(task_id, current_step, message, increment_steps)


def advance_task_to_next_stage(task_id: str, message: Optional[str] = None) -> bool:
    """Advance a task to the next stage."""
    return task_progress_tracker.advance_to_next_stage(task_id, message)


def update_task_status(task_id: str, status: TaskProgressStatus, message: Optional[str] = None) -> bool:
    """Update the status of a task."""
    return task_progress_tracker.update_status(task_id, status, message)


def complete_task(task_id: str, message: Optional[str] = None) -> bool:
    """Mark a task as completed."""
    return task_progress_tracker.complete_task(task_id, message)


def fail_task(task_id: str, error_message: str) -> bool:
    """Mark a task as failed."""
    return task_progress_tracker.fail_task(task_id, error_message)


def cancel_task(task_id: str, message: Optional[str] = None) -> bool:
    """Mark a task as cancelled."""
    return task_progress_tracker.cancel_task(task_id, message)


def get_task_progress(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the progress information for a task."""
    return task_progress_tracker.get_task_progress_dict(task_id)


def get_all_task_progress() -> Dict[str, Dict[str, Any]]:
    """Get progress information for all tracked tasks."""
    return task_progress_tracker.get_all_task_progress()


def is_task_complete(task_id: str) -> bool:
    """Check if a task is complete."""
    return task_progress_tracker.is_task_complete(task_id)


def is_task_running(task_id: str) -> bool:
    """Check if a task is currently running."""
    return task_progress_tracker.is_task_running(task_id)


def get_tasks_by_status(status: TaskProgressStatus) -> List[str]:
    """Get all tasks with a specific status."""
    return task_progress_tracker.get_tasks_by_status(status)


def get_completion_percentage(task_id: str) -> float:
    """Get the completion percentage for a task."""
    return task_progress_tracker.get_completion_percentage(task_id)


def get_eta(task_id: str) -> Optional[datetime]:
    """Get the estimated time of arrival/finish for a task."""
    return task_progress_tracker.get_eta(task_id)


def remove_task(task_id: str) -> bool:
    """Remove a task from tracking."""
    return task_progress_tracker.remove_task(task_id)