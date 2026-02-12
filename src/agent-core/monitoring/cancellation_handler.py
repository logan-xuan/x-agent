"""
Task cancellation mechanism for the x-agent2 AI assistant system.

This module provides functionality for safely cancelling long-running tasks
that are managed by the system.
"""

import asyncio
import threading
import time
from typing import Dict, Optional, Any, Callable, Set
from datetime import datetime
from enum import Enum
import logging
import signal
import weakref


class CancellationReason(Enum):
    """Reasons for task cancellation."""
    USER_REQUESTED = "user_requested"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT_EXCEEDED = "resource_limit_exceeded"
    SYSTEM_SHUTDOWN = "system_shutdown"
    DEPENDENCY_FAILED = "dependency_failed"
    MANUAL_INTERRUPT = "manual_interrupt"


class CancellationStatus(Enum):
    """Status of cancellation operations."""
    PENDING = "pending"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    ALREADY_COMPLETED = "already_completed"


class TaskCancellationInfo:
    """Information about a cancellable task."""
    def __init__(
        self,
        task_id: str,
        name: str,
        start_time: datetime,
        cancellable_func: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.task_id = task_id
        self.name = name
        self.start_time = start_time
        self.cancellable_func = cancellable_func
        self.context = context or {}
        self.status = CancellationStatus.PENDING
        self.reason: Optional[CancellationReason] = None
        self.cancel_requested_time: Optional[datetime] = None
        self.completed_time: Optional[datetime] = None
        self.cancellation_result: Optional[Any] = None


class TaskCancellationManager:
    """Manages cancellation of long-running tasks."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._tasks: Dict[str, TaskCancellationInfo] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._futures: Dict[str, asyncio.Future] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._coroutines: Dict[str, asyncio.Task] = {}
        self._cancellation_callbacks: Dict[str, list] = {}

    def register_task(
        self,
        task_id: str,
        name: str,
        cancellable_func: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Register a task that can be cancelled.

        Args:
            task_id: Unique identifier for the task
            name: Name of the task
            cancellable_func: Function that can be used to cancel the task
            context: Additional context for the task

        Returns:
            True if registration was successful, False otherwise
        """
        if task_id in self._tasks:
            self.logger.warning(f"Task {task_id} already registered for cancellation")
            return False

        task_info = TaskCancellationInfo(
            task_id=task_id,
            name=name,
            start_time=datetime.utcnow(),
            cancellable_func=cancellable_func,
            context=context
        )

        self._tasks[task_id] = task_info
        self._locks[task_id] = threading.Lock()
        self._cancellation_callbacks[task_id] = []

        self.logger.info(f"Registered cancellable task: {task_id} ({name})")
        return True

    def deregister_task(self, task_id: str) -> bool:
        """
        Deregister a task that was previously registered.

        Args:
            task_id: ID of the task to deregister

        Returns:
            True if deregistration was successful, False otherwise
        """
        if task_id not in self._tasks:
            return False

        # Clean up related objects
        if task_id in self._locks:
            del self._locks[task_id]
        if task_id in self._cancellation_callbacks:
            del self._cancellation_callbacks[task_id]

        # Cancel any pending futures
        if task_id in self._futures:
            future = self._futures[task_id]
            if not future.done():
                future.cancel()

        # Interrupt any running threads
        if task_id in self._threads:
            thread = self._threads[task_id]
            if thread.is_alive():
                # Note: Thread.interrupt() doesn't exist in Python, we'll need to handle this differently
                # In practice, we rely on cooperative cancellation mechanisms
                pass

        # Cancel any running coroutines
        if task_id in self._coroutines:
            coro = self._coroutines[task_id]
            if not coro.done():
                coro.cancel()

        del self._tasks[task_id]

        self.logger.info(f"Deregistered cancellable task: {task_id}")
        return True

    def request_cancellation(
        self,
        task_id: str,
        reason: CancellationReason = CancellationReason.USER_REQUESTED,
        notify_callbacks: bool = True
    ) -> Dict[str, Any]:
        """
        Request cancellation of a registered task.

        Args:
            task_id: ID of the task to cancel
            reason: Reason for cancellation
            notify_callbacks: Whether to notify cancellation callbacks

        Returns:
            Dictionary with cancellation request result
        """
        if task_id not in self._tasks:
            return {
                "success": False,
                "error": f"Task {task_id} not found in cancellation registry",
                "task_id": task_id
            }

        task_info = self._tasks[task_id]

        with self._locks[task_id]:
            # Check if task is already completed
            if task_info.status in [CancellationStatus.CANCELLED, CancellationStatus.ALREADY_COMPLETED]:
                return {
                    "success": False,
                    "error": f"Task {task_id} is already completed",
                    "status": task_info.status.value,
                    "task_id": task_id
                }

            # Update task info
            task_info.status = CancellationStatus.CANCELLING
            task_info.reason = reason
            task_info.cancel_requested_time = datetime.utcnow()

            # Trigger cancellation
            cancellation_result = self._trigger_cancellation(task_id)

            # Update result
            task_info.cancellation_result = cancellation_result

            # Notify callbacks if requested
            if notify_callbacks:
                self._notify_cancellation_callbacks(task_id, reason)

        # Update status after attempting cancellation
        with self._locks[task_id]:
            if cancellation_result and cancellation_result.get("success", False):
                task_info.status = CancellationStatus.CANCELLED
                task_info.completed_time = datetime.utcnow()
            else:
                task_info.status = CancellationStatus.FAILED

        self.logger.info(f"Requested cancellation for task {task_id}: {reason.value}")

        return {
            "success": True,
            "task_id": task_id,
            "status": task_info.status.value,
            "reason": reason.value,
            "cancellation_result": cancellation_result
        }

    async def request_cancellation_async(
        self,
        task_id: str,
        reason: CancellationReason = CancellationReason.USER_REQUESTED,
        notify_callbacks: bool = True
    ) -> Dict[str, Any]:
        """
        Asynchronously request cancellation of a registered task.

        Args:
            task_id: ID of the task to cancel
            reason: Reason for cancellation
            notify_callbacks: Whether to notify cancellation callbacks

        Returns:
            Dictionary with cancellation request result
        """
        # Use asyncio event loop to run the synchronous method
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.request_cancellation,
            task_id,
            reason,
            notify_callbacks
        )

    def _trigger_cancellation(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Internal method to trigger the actual cancellation of a task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            Result of cancellation attempt
        """
        task_info = self._tasks[task_id]

        # If the task has a specific cancellation function, use it
        if task_info.cancellable_func:
            try:
                result = task_info.cancellable_func()
                return {"success": True, "result": result}
            except Exception as e:
                self.logger.error(f"Error in cancellation function for task {task_id}: {e}")
                return {"success": False, "error": str(e)}

        # If it's a future, try to cancel it
        if task_id in self._futures:
            future = self._futures[task_id]
            if not future.done():
                future.cancel()
                return {"success": True, "type": "future_cancelled"}

        # If it's a coroutine, try to cancel it
        if task_id in self._coroutines:
            coro = self._coroutines[task_id]
            if not coro.done():
                coro.cancel()
                return {"success": True, "type": "coroutine_cancelled"}

        # If it's a thread, we rely on cooperative cancellation mechanisms
        # In Python, threads cannot be forcibly stopped, so we just mark it for cancellation
        if task_id in self._threads:
            thread = self._threads[task_id]
            if thread.is_alive():
                # Add a flag in the context to signal cancellation
                task_info.context["_cancelled"] = True
                return {"success": True, "type": "thread_signaled"}

        # If we don't have specific cancellation mechanism, mark as cancelled
        return {"success": True, "type": "marked_cancelled"}

    def _notify_cancellation_callbacks(self, task_id: str, reason: CancellationReason):
        """
        Notify all registered callbacks about task cancellation.

        Args:
            task_id: ID of the task that was cancelled
            reason: Reason for cancellation
        """
        if task_id not in self._cancellation_callbacks:
            return

        for callback in self._cancellation_callbacks[task_id]:
            try:
                callback(task_id, reason)
            except Exception as e:
                self.logger.error(f"Error in cancellation callback for task {task_id}: {e}")

    def add_cancellation_callback(self, task_id: str, callback: Callable[[str, CancellationReason], None]):
        """
        Add a callback to be called when a task is cancelled.

        Args:
            task_id: ID of the task
            callback: Callback function to add
        """
        if task_id not in self._cancellation_callbacks:
            self._cancellation_callbacks[task_id] = []

        if callback not in self._cancellation_callbacks[task_id]:
            self._cancellation_callbacks[task_id].append(callback)

    def remove_cancellation_callback(self, task_id: str, callback: Callable[[str, CancellationReason], None]):
        """
        Remove a cancellation callback.

        Args:
            task_id: ID of the task
            callback: Callback function to remove
        """
        if task_id in self._cancellation_callbacks:
            if callback in self._cancellation_callbacks[task_id]:
                self._cancellation_callbacks[task_id].remove(callback)

    def is_task_cancellable(self, task_id: str) -> bool:
        """
        Check if a task is registered for cancellation.

        Args:
            task_id: ID of the task to check

        Returns:
            True if task is cancellable, False otherwise
        """
        return task_id in self._tasks

    def is_task_cancelled(self, task_id: str) -> bool:
        """
        Check if a task has been cancelled.

        Args:
            task_id: ID of the task to check

        Returns:
            True if task is cancelled, False otherwise
        """
        if task_id not in self._tasks:
            return False

        return self._tasks[task_id].status == CancellationStatus.CANCELLED

    def is_task_running(self, task_id: str) -> bool:
        """
        Check if a task is currently running (not cancelled or completed).

        Args:
            task_id: ID of the task to check

        Returns:
            True if task is running, False otherwise
        """
        if task_id not in self._tasks:
            return False

        status = self._tasks[task_id].status
        return status not in [CancellationStatus.CANCELLED, CancellationStatus.ALREADY_COMPLETED]

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the cancellation status of a task.

        Args:
            task_id: ID of the task to check

        Returns:
            Dictionary with task status information, or None if task not found
        """
        if task_id not in self._tasks:
            return None

        task_info = self._tasks[task_id]
        return {
            "task_id": task_info.task_id,
            "name": task_info.name,
            "status": task_info.status.value,
            "start_time": task_info.start_time.isoformat(),
            "reason": task_info.reason.value if task_info.reason else None,
            "cancel_requested_time": task_info.cancel_requested_time.isoformat() if task_info.cancel_requested_time else None,
            "completed_time": task_info.completed_time.isoformat() if task_info.completed_time else None,
            "is_cancellable": self.is_task_cancellable(task_id),
            "is_cancelled": self.is_task_cancelled(task_id),
            "is_running": self.is_task_running(task_id)
        }

    def get_all_task_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get the cancellation status of all registered tasks.

        Returns:
            Dictionary mapping task IDs to their status information
        """
        statuses = {}
        for task_id in self._tasks:
            status = self.get_task_status(task_id)
            if status:
                statuses[task_id] = status
        return statuses

    def cancel_all_tasks(self, reason: CancellationReason = CancellationReason.SYSTEM_SHUTDOWN) -> Dict[str, Any]:
        """
        Cancel all registered tasks.

        Args:
            reason: Reason for cancellation of all tasks

        Returns:
            Dictionary with cancellation results
        """
        results = {
            "cancelled": [],
            "failed": [],
            "already_completed": [],
            "not_found": []
        }

        for task_id in list(self._tasks.keys()):  # Copy the list as we might modify it during iteration
            result = self.request_cancellation(task_id, reason)

            if result["success"]:
                results["cancelled"].append(task_id)
            elif "already completed" in result.get("error", "").lower():
                results["already_completed"].append(task_id)
            elif "not found" in result.get("error", "").lower():
                results["not_found"].append(task_id)
            else:
                results["failed"].append({
                    "task_id": task_id,
                    "error": result.get("error")
                })

        return {
            "total_attempts": len(self._tasks),
            "cancelled": len(results["cancelled"]),
            "failed": len(results["failed"]),
            "already_completed": len(results["already_completed"]),
            "not_found": len(results["not_found"]),
            "details": results
        }

    def register_future(self, task_id: str, future: asyncio.Future):
        """
        Register an asyncio Future for cancellation tracking.

        Args:
            task_id: ID to associate with the future
            future: The asyncio Future to register
        """
        self._futures[task_id] = future

    def register_coroutine(self, task_id: str, coro: asyncio.Task):
        """
        Register an asyncio Task for cancellation tracking.

        Args:
            task_id: ID to associate with the coroutine
            coro: The asyncio Task to register
        """
        self._coroutines[task_id] = coro

    def register_thread(self, task_id: str, thread: threading.Thread):
        """
        Register a thread for cancellation tracking.

        Args:
            task_id: ID to associate with the thread
            thread: The thread to register
        """
        self._threads[task_id] = thread


class CancellableTask:
    """Wrapper for a cancellable task."""

    def __init__(self, cancellation_manager: TaskCancellationManager, task_id: str, name: str):
        self.cancellation_manager = cancellation_manager
        self.task_id = task_id
        self.name = name
        self.cancelled = False
        self.context = {"_cancelled": False}

        # Register with the cancellation manager
        self.cancellation_manager.register_task(
            task_id=task_id,
            name=name,
            cancellable_func=self._attempt_cancel,
            context=self.context
        )

    def _attempt_cancel(self) -> Dict[str, Any]:
        """Attempt to cancel this specific task."""
        self.cancelled = True
        self.context["_cancelled"] = True
        return {"success": True, "cancelled": True}

    def is_cancelled(self) -> bool:
        """Check if this task has been cancelled."""
        return self.cancelled or self.context.get("_cancelled", False)

    def check_for_cancellation(self):
        """Raise an exception if the task has been cancelled."""
        if self.is_cancelled():
            raise asyncio.CancelledError(f"Task {self.task_id} was cancelled")


class CancellationContext:
    """Context manager for cancellable operations."""

    def __init__(self, cancellation_manager: TaskCancellationManager, task_id: str, name: str):
        self.cancellation_manager = cancellation_manager
        self.task_id = task_id
        self.name = name
        self.token = None

    async def __aenter__(self):
        """Async enter method for context manager."""
        self.token = self.cancellation_manager.register_task(self.task_id, self.name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager."""
        if self.token:
            self.cancellation_manager.deregister_task(self.task_id)

    def check_for_cancellation(self):
        """Check if the current operation has been cancelled."""
        if self.cancellation_manager.is_task_cancelled(self.task_id):
            raise asyncio.CancelledError(f"Operation {self.task_id} was cancelled")

    def is_cancelled(self) -> bool:
        """Check if this context has been cancelled."""
        return self.cancellation_manager.is_task_cancelled(self.task_id)


class CooperativeCancellationMixin:
    """Mixin class to add cooperative cancellation to other classes."""

    def __init__(self):
        self._cancelled = False
        self._cancel_reason = None

    def cancel(self, reason: CancellationReason = CancellationReason.USER_REQUESTED):
        """Cancel this operation."""
        self._cancelled = True
        self._cancel_reason = reason

    def is_cancelled(self) -> bool:
        """Check if this operation has been cancelled."""
        return self._cancelled

    def check_for_cancellation(self):
        """Raise an exception if this operation has been cancelled."""
        if self.is_cancelled():
            reason = self._cancel_reason or CancellationReason.USER_REQUESTED
            raise asyncio.CancelledError(f"Operation cancelled: {reason.value}")

    def get_cancel_reason(self) -> Optional[CancellationReason]:
        """Get the reason for cancellation."""
        return self._cancel_reason


# Global cancellation manager instance
cancellation_manager = TaskCancellationManager()


# Convenience functions
def register_task_for_cancellation(
    task_id: str,
    name: str,
    cancellable_func: Optional[Callable] = None,
    context: Optional[Dict[str, Any]] = None
) -> bool:
    """Register a task that can be cancelled."""
    return cancellation_manager.register_task(task_id, name, cancellable_func, context)


def request_task_cancellation(
    task_id: str,
    reason: CancellationReason = CancellationReason.USER_REQUESTED
) -> Dict[str, Any]:
    """Request cancellation of a registered task."""
    return cancellation_manager.request_cancellation(task_id, reason)


async def request_task_cancellation_async(
    task_id: str,
    reason: CancellationReason = CancellationReason.USER_REQUESTED
) -> Dict[str, Any]:
    """Asynchronously request cancellation of a registered task."""
    return await cancellation_manager.request_cancellation_async(task_id, reason)


def is_task_cancellable(task_id: str) -> bool:
    """Check if a task is registered for cancellation."""
    return cancellation_manager.is_task_cancellable(task_id)


def is_task_cancelled(task_id: str) -> bool:
    """Check if a task has been cancelled."""
    return cancellation_manager.is_task_cancelled(task_id)


def get_task_cancellation_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the cancellation status of a task."""
    return cancellation_manager.get_task_status(task_id)


def add_cancellation_callback(task_id: str, callback: Callable[[str, CancellationReason], None]):
    """Add a callback to be called when a task is cancelled."""
    cancellation_manager.add_cancellation_callback(task_id, callback)


def remove_cancellation_callback(task_id: str, callback: Callable[[str, CancellationReason], None]):
    """Remove a cancellation callback."""
    cancellation_manager.remove_cancellation_callback(task_id, callback)