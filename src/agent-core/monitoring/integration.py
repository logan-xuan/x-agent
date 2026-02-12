"""
Heartbeat integration for long-running tasks in the x-agent2 AI assistant system.

This module provides integration between the heartbeat system and long-running tasks,
enabling automatic heartbeat emission during task execution.
"""

import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, Callable, Awaitable, Union
from datetime import datetime
import logging
import functools
from contextlib import contextmanager

from src.agent_core.monitoring.heartbeat_emitter import (
    AdvancedHeartbeatEmitter,
    heartbeat_manager,
    HeartbeatStatus,
    HeartbeatLevel,
    HeartbeatMessage
)
from src.agent_core.monitoring.progress_tracker import (
    task_progress_tracker,
    TaskProgressStatus
)
from src.agent_core.monitoring.cancellation_handler import (
    cancellation_manager,
    CancellationReason,
    CancellableTask
)


class HeartbeatTaskIntegration:
    """Integrates heartbeat functionality with long-running tasks."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def create_heartbeat_wrapper(
        self,
        func: Callable,
        task_id: str,
        task_description: str,
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ) -> Callable:
        """
        Creates a wrapper function that emits heartbeats during execution.

        Args:
            func: The function to wrap
            task_id: Unique identifier for the task
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds
            progress_tracking: Whether to enable progress tracking

        Returns:
            Wrapped function with heartbeat integration
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create heartbeat emitter
            emitter = AdvancedHeartbeatEmitter(task_id)

            # Register with heartbeat manager
            heartbeat_manager.register_emitter(emitter)

            # Register with cancellation manager
            cancellation_manager.register_task(
                task_id=task_id,
                name=task_description
            )

            # Register with progress tracker if enabled
            if progress_tracking and total_steps:
                task_progress_tracker.start_task(
                    task_id=task_id,
                    task_name=task_description,
                    total_steps=total_steps
                )

            try:
                # Start task
                emitter.start_task_with_tracking(
                    task_description=task_description,
                    total_steps=total_steps or 0
                )

                # Set heartbeat interval
                emitter.set_heartbeat_interval(heartbeat_interval)

                # Execute the original function
                result = func(*args, **kwargs)

                # Complete task
                emitter.complete_task()

                # Update progress tracker if enabled
                if progress_tracking:
                    task_progress_tracker.complete_task(task_id)

                return result
            except Exception as e:
                # Fail task
                emitter.fail_task(str(e))

                # Update progress tracker if enabled
                if progress_tracking:
                    task_progress_tracker.fail_task(task_id, str(e))

                raise
            finally:
                # Clean up registrations
                heartbeat_manager.unregister_emitter(task_id)
                cancellation_manager.deregister_task(task_id)

        return wrapper

    def create_async_heartbeat_wrapper(
        self,
        func: Callable,
        task_id: str,
        task_description: str,
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ) -> Callable:
        """
        Creates an async wrapper function that emits heartbeats during execution.

        Args:
            func: The async function to wrap
            task_id: Unique identifier for the task
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds
            progress_tracking: Whether to enable progress tracking

        Returns:
            Wrapped async function with heartbeat integration
        """
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create heartbeat emitter
            emitter = AdvancedHeartbeatEmitter(task_id)

            # Register with heartbeat manager
            heartbeat_manager.register_emitter(emitter)

            # Register with cancellation manager
            cancellation_manager.register_task(
                task_id=task_id,
                name=task_description
            )

            # Register with progress tracker if enabled
            if progress_tracking and total_steps:
                task_progress_tracker.start_task(
                    task_id=task_id,
                    task_name=task_description,
                    total_steps=total_steps
                )

            try:
                # Start task
                emitter.start_task_with_tracking(
                    task_description=task_description,
                    total_steps=total_steps or 0
                )

                # Set heartbeat interval
                emitter.set_heartbeat_interval(heartbeat_interval)

                # Execute the original function
                result = await func(*args, **kwargs)

                # Complete task
                emitter.complete_task()

                # Update progress tracker if enabled
                if progress_tracking:
                    task_progress_tracker.complete_task(task_id)

                return result
            except asyncio.CancelledError:
                # Handle cancellation
                emitter.cancel_task("Task was cancelled")

                # Update progress tracker if enabled
                if progress_tracking:
                    task_progress_tracker.cancel_task(task_id)

                # Update cancellation manager
                cancellation_manager.request_cancellation(task_id, CancellationReason.USER_REQUESTED)

                raise
            except Exception as e:
                # Fail task
                emitter.fail_task(str(e))

                # Update progress tracker if enabled
                if progress_tracking:
                    task_progress_tracker.fail_task(task_id, str(e))

                raise
            finally:
                # Clean up registrations
                heartbeat_manager.unregister_emitter(task_id)
                cancellation_manager.deregister_task(task_id)

        return async_wrapper

    def create_progress_reporting_wrapper(
        self,
        func: Callable,
        task_id: str,
        task_description: str,
        total_steps: int,
        heartbeat_interval: float = 5.0
    ) -> Callable:
        """
        Creates a wrapper that reports progress during execution.

        Args:
            func: The function to wrap
            task_id: Unique identifier for the task
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds

        Returns:
            Wrapped function with progress reporting
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create heartbeat emitter with progress tracking
            emitter = AdvancedHeartbeatEmitter(task_id)
            heartbeat_manager.register_emitter(emitter)

            # Register with cancellation manager
            cancellation_manager.register_task(
                task_id=task_id,
                name=task_description
            )

            # Register with progress tracker
            task_progress_tracker.start_task(
                task_id=task_id,
                task_name=task_description,
                total_steps=total_steps
            )

            try:
                # Start task
                emitter.start_task_with_tracking(
                    task_description=task_description,
                    total_steps=total_steps
                )

                # Set heartbeat interval
                emitter.set_heartbeat_interval(heartbeat_interval)

                # Call the function with a progress callback
                def progress_callback(current_step: int, message: str = ""):
                    # Update heartbeat
                    emitter.update_progress_with_tracking(
                        steps_completed=1,
                        message=message
                    )

                    # Update progress tracker
                    task_progress_tracker.update_progress(
                        task_id=task_id,
                        increment_steps=1,
                        message=message
                    )

                    # Check for cancellation
                    if cancellation_manager.is_task_cancelled(task_id):
                        raise asyncio.CancelledError("Task was cancelled")

                # Add progress callback to function arguments
                kwargs['progress_callback'] = progress_callback

                result = func(*args, **kwargs)

                # Complete task
                emitter.complete_task()

                # Update progress tracker
                task_progress_tracker.complete_task(task_id)

                return result
            except asyncio.CancelledError:
                # Handle cancellation
                emitter.cancel_task("Task was cancelled")

                # Update progress tracker
                task_progress_tracker.cancel_task(task_id)

                # Update cancellation manager
                cancellation_manager.request_cancellation(task_id, CancellationReason.USER_REQUESTED)

                raise
            except Exception as e:
                # Fail task
                emitter.fail_task(str(e))

                # Update progress tracker
                task_progress_tracker.fail_task(task_id, str(e))

                raise
            finally:
                # Clean up registrations
                heartbeat_manager.unregister_emitter(task_id)
                cancellation_manager.deregister_task(task_id)

        return wrapper

    def create_async_progress_reporting_wrapper(
        self,
        func: Callable,
        task_id: str,
        task_description: str,
        total_steps: int,
        heartbeat_interval: float = 5.0
    ) -> Callable:
        """
        Creates an async wrapper that reports progress during execution.

        Args:
            func: The async function to wrap
            task_id: Unique identifier for the task
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds

        Returns:
            Wrapped async function with progress reporting
        """
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Create heartbeat emitter with progress tracking
            emitter = AdvancedHeartbeatEmitter(task_id)
            heartbeat_manager.register_emitter(emitter)

            # Register with cancellation manager
            cancellation_manager.register_task(
                task_id=task_id,
                name=task_description
            )

            # Register with progress tracker
            task_progress_tracker.start_task(
                task_id=task_id,
                task_name=task_description,
                total_steps=total_steps
            )

            try:
                # Start task
                emitter.start_task_with_tracking(
                    task_description=task_description,
                    total_steps=total_steps
                )

                # Set heartbeat interval
                emitter.set_heartbeat_interval(heartbeat_interval)

                # Call the function with a progress callback
                async def progress_callback(current_step: int, message: str = ""):
                    # Update heartbeat
                    emitter.update_progress_with_tracking(
                        steps_completed=1,
                        message=message
                    )

                    # Update progress tracker
                    task_progress_tracker.update_progress(
                        task_id=task_id,
                        increment_steps=1,
                        message=message
                    )

                    # Check for cancellation
                    if cancellation_manager.is_task_cancelled(task_id):
                        raise asyncio.CancelledError("Task was cancelled")

                # Add progress callback to function arguments
                kwargs['async_progress_callback'] = progress_callback

                result = await func(*args, **kwargs)

                # Complete task
                emitter.complete_task()

                # Update progress tracker
                task_progress_tracker.complete_task(task_id)

                return result
            except asyncio.CancelledError:
                # Handle cancellation
                emitter.cancel_task("Task was cancelled")

                # Update progress tracker
                task_progress_tracker.cancel_task(task_id)

                # Update cancellation manager
                cancellation_manager.request_cancellation(task_id, CancellationReason.USER_REQUESTED)

                raise
            except Exception as e:
                # Fail task
                emitter.fail_task(str(e))

                # Update progress tracker
                task_progress_tracker.fail_task(task_id, str(e))

                raise
            finally:
                # Clean up registrations
                heartbeat_manager.unregister_emitter(task_id)
                cancellation_manager.deregister_task(task_id)

        return async_wrapper

    def run_with_heartbeat(
        self,
        func: Callable,
        task_id: Optional[str] = None,
        task_description: str = "Long-running task",
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ) -> Any:
        """
        Run a function with heartbeat integration.

        Args:
            func: Function to run
            task_id: Unique identifier for the task (generated if not provided)
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds
            progress_tracking: Whether to enable progress tracking

        Returns:
            Result of the function
        """
        task_id = task_id or f"task_{datetime.utcnow().timestamp()}"

        # Determine if the function is async
        if asyncio.iscoroutinefunction(func):
            wrapper = self.create_async_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )
            return asyncio.run(wrapper())
        else:
            wrapper = self.create_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )
            return wrapper()

    async def run_with_heartbeat_async(
        self,
        func: Callable,
        task_id: Optional[str] = None,
        task_description: str = "Long-running task",
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ) -> Any:
        """
        Run a function with heartbeat integration asynchronously.

        Args:
            func: Function to run
            task_id: Unique identifier for the task (generated if not provided)
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds
            progress_tracking: Whether to enable progress tracking

        Returns:
            Result of the function
        """
        task_id = task_id or f"task_{datetime.utcnow().timestamp()}"

        # Determine if the function is async
        if asyncio.iscoroutinefunction(func):
            wrapper = self.create_async_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )
            return await wrapper()
        else:
            # For synchronous functions in async context, run in thread pool
            loop = asyncio.get_event_loop()
            wrapper = self.create_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )
            return await loop.run_in_executor(None, wrapper)


class HeartbeatContextManager:
    """Context manager for tasks with heartbeat integration."""

    def __init__(
        self,
        task_id: str,
        task_description: str,
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ):
        self.task_id = task_id
        self.task_description = task_description
        self.total_steps = total_steps
        self.heartbeat_interval = heartbeat_interval
        self.progress_tracking = progress_tracking

        self.emitter = None
        self.logger = logging.getLogger(__name__)

    async def __aenter__(self):
        """Async enter method for context manager."""
        # Create heartbeat emitter
        self.emitter = AdvancedHeartbeatEmitter(self.task_id)

        # Register with heartbeat manager
        heartbeat_manager.register_emitter(self.emitter)

        # Register with cancellation manager
        cancellation_manager.register_task(
            task_id=self.task_id,
            name=self.task_description
        )

        # Register with progress tracker if enabled
        if self.progress_tracking and self.total_steps:
            task_progress_tracker.start_task(
                task_id=self.task_id,
                task_name=self.task_description,
                total_steps=self.total_steps
            )

        # Start task
        self.emitter.start_task_with_tracking(
            task_description=self.task_description,
            total_steps=self.total_steps or 0
        )

        # Set heartbeat interval
        self.emitter.set_heartbeat_interval(self.heartbeat_interval)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager."""
        if self.emitter:
            try:
                if exc_type is asyncio.CancelledError:
                    # Handle cancellation
                    self.emitter.cancel_task("Task was cancelled")

                    # Update progress tracker if enabled
                    if self.progress_tracking:
                        task_progress_tracker.cancel_task(self.task_id)

                    # Update cancellation manager
                    cancellation_manager.request_cancellation(self.task_id, CancellationReason.USER_REQUESTED)
                elif exc_type:
                    # Handle exceptions
                    self.emitter.fail_task(f"{exc_type.__name__}: {exc_val}")

                    # Update progress tracker if enabled
                    if self.progress_tracking:
                        task_progress_tracker.fail_task(self.task_id, f"{exc_type.__name__}: {exc_val}")
                else:
                    # Complete task normally
                    self.emitter.complete_task()

                    # Update progress tracker if enabled
                    if self.progress_tracking:
                        task_progress_tracker.complete_task(self.task_id)

            finally:
                # Clean up registrations
                heartbeat_manager.unregister_emitter(self.task_id)
                cancellation_manager.deregister_task(self.task_id)

    def update_progress(self, steps_completed: int = 1, message: str = ""):
        """Update progress during task execution."""
        if self.emitter:
            # Update heartbeat
            self.emitter.update_progress_with_tracking(
                steps_completed=steps_completed,
                message=message
            )

            # Update progress tracker if enabled
            if self.progress_tracking:
                task_progress_tracker.update_progress(
                    task_id=self.task_id,
                    increment_steps=steps_completed,
                    message=message
                )

    def check_for_cancellation(self):
        """Check if the task has been cancelled."""
        if cancellation_manager.is_task_cancelled(self.task_id):
            raise asyncio.CancelledError("Task was cancelled")

    def get_current_status(self):
        """Get the current status of the task."""
        if self.emitter:
            return {
                "task_id": self.task_id,
                "description": self.task_description,
                "is_cancelled": cancellation_manager.is_task_cancelled(self.task_id),
                "progress": self.emitter.progress_tracker.get_current_metrics() if self.progress_tracking else None,
                "last_heartbeat": self.emitter.last_heartbeat_time
            }


class BackgroundHeartbeatService:
    """Service for managing background heartbeat emission."""

    def __init__(self):
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)

    async def start_background_task(
        self,
        func: Callable,
        task_id: str,
        task_description: str,
        total_steps: Optional[int] = None,
        heartbeat_interval: float = 5.0,
        progress_tracking: bool = True
    ) -> asyncio.Task:
        """
        Start a task in the background with heartbeat integration.

        Args:
            func: Function to run in the background
            task_id: Unique identifier for the task
            task_description: Description of the task
            total_steps: Total number of steps in the task
            heartbeat_interval: Interval between heartbeats in seconds
            progress_tracking: Whether to enable progress tracking

        Returns:
            asyncio.Task instance
        """
        # Create integration instance
        integration = HeartbeatTaskIntegration()

        # Determine if the function is async
        if asyncio.iscoroutinefunction(func):
            wrapper = integration.create_async_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )
        else:
            wrapper = integration.create_heartbeat_wrapper(
                func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
            )

        # Create and start the task
        task = asyncio.create_task(wrapper())

        # Track the task
        self.active_tasks[task_id] = {
            "task": task,
            "description": task_description,
            "start_time": datetime.utcnow()
        }

        return task

    def cancel_background_task(self, task_id: str) -> bool:
        """
        Cancel a background task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if task was cancelled, False otherwise
        """
        if task_id not in self.active_tasks:
            return False

        task_info = self.active_tasks[task_id]
        task = task_info["task"]

        if not task.done():
            task.cancel()
            # Update cancellation manager
            cancellation_manager.request_cancellation(task_id, CancellationReason.USER_REQUESTED)
            return True

        return False

    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all active background tasks."""
        active_info = {}
        for task_id, task_info in self.active_tasks.items():
            task = task_info["task"]
            active_info[task_id] = {
                "description": task_info["description"],
                "start_time": task_info["start_time"],
                "done": task.done(),
                "cancelled": task.cancelled(),
                "status": "done" if task.done() else "running"
            }
        return active_info


# Global integration instance
heartbeat_integration = HeartbeatTaskIntegration()
background_service = BackgroundHeartbeatService()


# Convenience functions
def run_with_heartbeat(
    func: Callable,
    task_id: Optional[str] = None,
    task_description: str = "Long-running task",
    total_steps: Optional[int] = None,
    heartbeat_interval: float = 5.0,
    progress_tracking: bool = True
) -> Any:
    """Run a function with heartbeat integration."""
    return heartbeat_integration.run_with_heartbeat(
        func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
    )


async def run_with_heartbeat_async(
    func: Callable,
    task_id: Optional[str] = None,
    task_description: str = "Long-running task",
    total_steps: Optional[int] = None,
    heartbeat_interval: float = 5.0,
    progress_tracking: bool = True
) -> Any:
    """Run a function with heartbeat integration asynchronously."""
    return await heartbeat_integration.run_with_heartbeat_async(
        func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
    )


def create_heartbeat_wrapper(
    func: Callable,
    task_id: str,
    task_description: str,
    total_steps: Optional[int] = None,
    heartbeat_interval: float = 5.0,
    progress_tracking: bool = True
) -> Callable:
    """Create a wrapper function with heartbeat integration."""
    if asyncio.iscoroutinefunction(func):
        return heartbeat_integration.create_async_heartbeat_wrapper(
            func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
        )
    else:
        return heartbeat_integration.create_heartbeat_wrapper(
            func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
        )


@contextmanager
def heartbeat_context(
    task_id: str,
    task_description: str,
    total_steps: Optional[int] = None,
    heartbeat_interval: float = 5.0,
    progress_tracking: bool = True
):
    """
    Context manager for tasks with heartbeat integration.

    Note: This is the synchronous version that creates an async context.
    For true async usage, use the HeartbeatContextManager directly.
    """
    import threading

    # Create the async context manager
    async_context = HeartbeatContextManager(
        task_id, task_description, total_steps, heartbeat_interval, progress_tracking
    )

    # Create an event loop if needed
    def run_async_context():
        async def run():
            return await async_context.__aenter__()

        # Run the async enter
        return asyncio.run(run())

    # For now, we'll return the async context manager directly
    # In a real implementation, we'd handle the sync/async context properly
    raise NotImplementedError(
        "Synchronous context manager for async operations is not implemented. "
        "Use HeartbeatContextManager directly in async code."
    )


async def start_background_task(
    func: Callable,
    task_id: str,
    task_description: str,
    total_steps: Optional[int] = None,
    heartbeat_interval: float = 5.0,
    progress_tracking: bool = True
) -> asyncio.Task:
    """Start a task in the background with heartbeat integration."""
    return await background_service.start_background_task(
        func, task_id, task_description, total_steps, heartbeat_interval, progress_tracking
    )


def cancel_background_task(task_id: str) -> bool:
    """Cancel a background task."""
    return background_service.cancel_background_task(task_id)


def get_active_background_tasks() -> Dict[str, Dict[str, Any]]:
    """Get information about all active background tasks."""
    return background_service.get_active_tasks()