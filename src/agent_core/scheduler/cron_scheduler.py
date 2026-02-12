import asyncio
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from croniter import croniter
import logging
from concurrent.futures import ThreadPoolExecutor


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class ScheduledTask:
    id: str
    name: str
    schedule: str  # cron expression
    task_function: Callable
    params: Dict[str, Any]
    created_at: datetime
    last_run: Optional[datetime] = None
    last_run_status: TaskStatus = TaskStatus.PENDING
    next_run: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    paused: bool = False


class ExecutionEngine:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self._shutdown = False

    async def execute_task(self, task: ScheduledTask) -> bool:
        """Execute a scheduled task and update its status."""
        try:
            if self._shutdown:
                return False

            task.last_run = datetime.now()
            task.last_run_status = TaskStatus.RUNNING

            # Execute the task function with provided parameters
            if asyncio.iscoroutinefunction(task.task_function):
                result = await task.task_function(**task.params)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    lambda: task.task_function(**task.params)
                )

            task.last_run_status = TaskStatus.COMPLETED
            task.retry_count = 0  # Reset retry count on success
            logging.info(f"Task {task.id} ({task.name}) executed successfully")
            return True

        except Exception as e:
            task.last_run_status = TaskStatus.FAILED
            task.retry_count += 1
            logging.error(f"Task {task.id} ({task.name}) failed: {str(e)}")

            # Check if we should retry
            if task.retry_count < task.max_retries:
                logging.info(f"Task {task.id} will retry ({task.retry_count}/{task.max_retries})")
                return False
            else:
                logging.error(f"Task {task.id} exceeded max retries ({task.max_retries})")
                return False

    def shutdown(self):
        """Shut down the execution engine."""
        self._shutdown = True
        if self.executor:
            self.executor.shutdown(wait=True)


class CronScheduler:
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.execution_engine = ExecutionEngine()

    def add_task(self, name: str, schedule: str, task_function: Callable, params: Dict[str, Any]) -> str:
        """Add a new scheduled task."""
        import uuid
        task_id = str(uuid.uuid4())

        # Validate cron expression
        try:
            croniter(schedule, datetime.now())
        except ValueError:
            raise ValueError(f"Invalid cron expression: {schedule}")

        task = ScheduledTask(
            id=task_id,
            name=name,
            schedule=schedule,
            task_function=task_function,
            params=params,
            created_at=datetime.now(),
            next_run=self._calculate_next_run(schedule)
        )

        self.tasks[task_id] = task
        return task_id

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a specific task by ID."""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[ScheduledTask]:
        """Get all tasks."""
        return list(self.tasks.values())

    def pause_task(self, task_id: str) -> bool:
        """Pause a scheduled task."""
        if task_id in self.tasks:
            self.tasks[task_id].paused = True
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        if task_id in self.tasks:
            self.tasks[task_id].paused = False
            return True
        return False

    def _calculate_next_run(self, schedule: str) -> datetime:
        """Calculate the next run time based on the cron schedule."""
        now = datetime.now()

        # Handle special predefined schedules
        if schedule == '@hourly':
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        elif schedule == '@daily':
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif schedule == '@weekly':
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7  # If today is Monday, go to next Monday
            next_monday = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
            return next_monday
        else:
            # Use croniter for standard cron expressions
            return croniter(schedule, now).get_next(datetime)

    async def _run_scheduler(self):
        """Main scheduler loop that runs in a separate thread."""
        while not self._stop_event.is_set():
            try:
                await self._check_and_execute_tasks()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logging.error(f"Scheduler error: {str(e)}")

    async def _check_and_execute_tasks(self):
        """Check for tasks that need to be executed and run them."""
        now = datetime.now()

        for task in self.tasks.values():
            if (task.paused or
                task.next_run is None or
                task.next_run > now or
                task.last_run_status == TaskStatus.RUNNING):
                continue

            # Schedule next run before executing
            task.next_run = self._calculate_next_run(task.schedule)

            # Execute the task
            await self.execution_engine.execute_task(task)

    async def start(self):
        """Start the scheduler."""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()

        # Start the scheduler loop in a separate thread
        loop = asyncio.get_event_loop()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._run_scheduler()), daemon=True)
        self._thread.start()

    async def stop(self):
        """Stop the scheduler."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=5)  # Wait up to 5 seconds for graceful shutdown

        self.execution_engine.shutdown()