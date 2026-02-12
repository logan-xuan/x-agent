import asyncio
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor
import logging
from ..monitoring.logging_service import LoggingService


class ExecutionEngine:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.logging_service = LoggingService()
        self._shutdown = False

    async def execute_task(self, task: 'ScheduledTask') -> bool:
        """Execute a scheduled task and update its status."""
        try:
            if self._shutdown:
                return False

            task.last_run = datetime.now()
            task.last_run_status = 'RUNNING'

            # Log task execution
            self.logging_service.log_task_execution(
                task.id,
                task.name,
                "Starting execution"
            )

            # Execute the task function with provided parameters
            if asyncio.iscoroutinefunction(task.task_function):
                result = await task.task_function(**task.params)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    lambda: task.task_function(**task.params)
                )

            task.last_run_status = 'COMPLETED'
            task.retry_count = 0  # Reset retry count on success

            # Log successful completion
            self.logging_service.log_task_execution(
                task.id,
                task.name,
                f"Completed successfully: {result}"
            )

            return True

        except Exception as e:
            task.last_run_status = 'FAILED'
            task.retry_count += 1

            # Log failure
            self.logging_service.log_task_execution(
                task.id,
                task.name,
                f"Failed with error: {str(e)}"
            )

            # Check if we should retry
            if task.retry_count < task.max_retries:
                # Log retry attempt
                self.logging_service.log_task_execution(
                    task.id,
                    task.name,
                    f"Retry attempt {task.retry_count}/{task.max_retries}"
                )
                return False
            else:
                # Log max retries exceeded
                self.logging_service.log_task_execution(
                    task.id,
                    task.name,
                    f"Exceeded max retries ({task.max_retries})"
                )
                return False

    def shutdown(self):
        """Shut down the execution engine."""
        self._shutdown = True
        if self.executor:
            self.executor.shutdown(wait=True)