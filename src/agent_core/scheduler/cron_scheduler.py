import asyncio
import datetime
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
from enum import Enum
import uuid


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledTask:
    """Represents a scheduled task"""
    id: str
    name: str
    schedule: str  # Cron-like schedule expression
    task_function: Callable
    params: dict
    created_at: datetime.datetime
    last_run: Optional[datetime.datetime] = None
    next_run: Optional[datetime.datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    max_retries: int = 3
    retry_count: int = 0


class CronScheduler:
    """Cron job scheduler service"""

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._scheduler_task = None

    async def start(self):
        """Start the scheduler"""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

    async def stop(self):
        """Stop the scheduler"""
        if not self._running:
            return

        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    async def _run_scheduler(self):
        """Main scheduler loop"""
        while self._running:
            now = datetime.datetime.now()

            for task_id, task in self._tasks.items():
                if (task.status == TaskStatus.PENDING and
                    task.next_run and
                    now >= task.next_run):

                    # Execute the task
                    await self._execute_task(task)

            # Sleep for a bit before checking again
            await asyncio.sleep(30)  # Check every 30 seconds

    async def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task"""
        try:
            # Update task status
            task.status = TaskStatus.RUNNING
            task.last_run = datetime.datetime.now()

            # Execute the task function
            result = await task.task_function(**task.params)

            # Update task status on success
            task.status = TaskStatus.COMPLETED
            task.retry_count = 0  # Reset retry count on success

            # Schedule next run
            task.next_run = self._calculate_next_run(task.schedule)

        except Exception as e:
            # Handle execution failure
            task.retry_count += 1
            if task.retry_count >= task.max_retries:
                task.status = TaskStatus.FAILED
            else:
                # Retry after a delay
                task.next_run = datetime.datetime.now() + datetime.timedelta(minutes=2**task.retry_count)

    def _calculate_next_run(self, schedule: str) -> datetime.datetime:
        """Calculate the next run time based on the schedule expression"""
        # This is a simplified version - a real implementation would parse cron expressions
        # For now, we'll just return a time based on a simple interval

        # Parse simple intervals like "@hourly", "@daily", "@weekly" or "* * * * *" format
        now = datetime.datetime.now()

        if schedule == "@hourly":
            return now + datetime.timedelta(hours=1)
        elif schedule == "@daily":
            tomorrow = now.date() + datetime.timedelta(days=1)
            return datetime.datetime.combine(tomorrow, datetime.time.min)
        elif schedule == "@weekly":
            next_week = now.date() + datetime.timedelta(weeks=1)
            return datetime.datetime.combine(next_week, datetime.time.min)
        else:
            # For more complex cron expressions, we'd implement proper parsing
            # For now, default to hourly
            return now + datetime.timedelta(hours=1)

    def add_task(self, name: str, schedule: str, task_function: Callable, params: dict = None, max_retries: int = 3) -> str:
        """Add a new scheduled task"""
        task_id = str(uuid.uuid4())

        if params is None:
            params = {}

        task = ScheduledTask(
            id=task_id,
            name=name,
            schedule=schedule,
            task_function=task_function,
            params=params,
            created_at=datetime.datetime.now(),
            next_run=self._calculate_next_run(schedule),
            max_retries=max_retries
        )

        self._tasks[task_id] = task
        return task_id

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a specific task by ID"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[ScheduledTask]:
        """Get all tasks"""
        return list(self._tasks.values())

    def pause_task(self, task_id: str) -> bool:
        """Pause a running task"""
        task = self._tasks.get(task_id)
        if task and task.status != TaskStatus.CANCELLED:
            # Store the original schedule to restore later
            task.original_schedule = task.schedule
            task.schedule = None  # Remove schedule to prevent execution
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task"""
        task = self._tasks.get(task_id)
        if task and hasattr(task, 'original_schedule'):
            task.schedule = task.original_schedule
            delattr(task, 'original_schedule')
            return True
        return False