import asyncio
import logging
from typing import Dict, Any, Callable
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import traceback
from .cron_scheduler import ScheduledTask, TaskStatus


class ExecutionEngine:
    """Handles the actual execution of scheduled tasks"""

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._logger = logging.getLogger(__name__)

    async def execute_task(self, task: ScheduledTask) -> bool:
        """
        Execute a scheduled task asynchronously

        Args:
            task: The task to execute

        Returns:
            True if successful, False otherwise
        """
        try:
            self._logger.info(f"Starting execution of task {task.id}: {task.name}")

            # Update task status to running
            task.status = TaskStatus.RUNNING
            task.last_run_at = datetime.now()

            # Here we would dynamically import and call the task function
            # based on the task_type and parameters
            success = await self._run_task_function(task)

            # Update task status based on result
            if success:
                task.last_run_status = TaskStatus.COMPLETED
                task.retry_count = 0  # Reset retry count on success
                self._logger.info(f"Successfully completed task {task.id}")
            else:
                task.last_run_status = TaskStatus.FAILED
                task.retry_count += 1
                self._logger.warning(f"Task {task.id} execution failed")

            return success

        except Exception as e:
            self._logger.error(f"Error executing task {task.id}: {str(e)}\n{traceback.format_exc()}")
            task.last_run_status = TaskStatus.FAILED
            task.retry_count += 1
            return False

    async def _run_task_function(self, task: ScheduledTask) -> bool:
        """Run the actual task function based on task type"""
        try:
            # Map task types to actual function implementations
            task_functions: Dict[str, Callable] = {
                "health_check": self._execute_health_check,
                "data_cleanup": self._execute_data_cleanup,
                "report_generation": self._execute_report_generation,
                "backup": self._execute_backup,
                "notification": self._execute_notification,
                # Add more task types as needed
            }

            if task.task_type not in task_functions:
                self._logger.error(f"Unknown task type: {task.task_type}")
                return False

            # Get the task function
            task_func = task_functions[task.task_type]

            # Parse parameters if they exist
            params = {}
            if task.task_params:
                import json
                try:
                    params = json.loads(task.task_params)
                except json.JSONDecodeError:
                    self._logger.error(f"Invalid JSON in task parameters for task {task.id}")
                    return False

            # Execute the task in a thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, task_func, params)

            return result

        except Exception as e:
            self._logger.error(f"Error in task function execution: {str(e)}")
            return False

    def _execute_health_check(self, params: Dict[str, Any]) -> bool:
        """Execute a health check task"""
        try:
            # Implement health check logic
            self._logger.info("Executing health check task")
            # Add actual health check implementation
            return True
        except Exception as e:
            self._logger.error(f"Health check failed: {str(e)}")
            return False

    def _execute_data_cleanup(self, params: Dict[str, Any]) -> bool:
        """Execute a data cleanup task"""
        try:
            # Implement data cleanup logic
            self._logger.info("Executing data cleanup task")
            # Add actual cleanup implementation
            days_to_keep = params.get("days_to_keep", 30)
            tables_to_clean = params.get("tables", [])

            # Add cleanup implementation here
            self._logger.info(f"Cleaning up data older than {days_to_keep} days from tables: {tables_to_clean}")

            return True
        except Exception as e:
            self._logger.error(f"Data cleanup failed: {str(e)}")
            return False

    def _execute_report_generation(self, params: Dict[str, Any]) -> bool:
        """Execute a report generation task"""
        try:
            # Implement report generation logic
            self._logger.info("Executing report generation task")
            report_type = params.get("report_type", "daily_summary")
            recipients = params.get("recipients", [])

            # Add report generation implementation here
            self._logger.info(f"Generating {report_type} report for recipients: {recipients}")

            return True
        except Exception as e:
            self._logger.error(f"Report generation failed: {str(e)}")
            return False

    def _execute_backup(self, params: Dict[str, Any]) -> bool:
        """Execute a backup task"""
        try:
            # Implement backup logic
            self._logger.info("Executing backup task")
            backup_location = params.get("location", "/tmp/backups")
            databases = params.get("databases", ["main"])

            # Add backup implementation here
            self._logger.info(f"Backing up databases {databases} to {backup_location}")

            return True
        except Exception as e:
            self._logger.error(f"Backup failed: {str(e)}")
            return False

    def _execute_notification(self, params: Dict[str, Any]) -> bool:
        """Execute a notification task"""
        try:
            # Implement notification logic
            self._logger.info("Executing notification task")
            message = params.get("message", "Default notification message")
            recipients = params.get("recipients", [])
            notification_type = params.get("type", "email")

            # Add notification implementation here
            self._logger.info(f"Sending {notification_type} notification to {len(recipients)} recipients")

            return True
        except Exception as e:
            self._logger.error(f"Notification failed: {str(e)}")
            return False

    def shutdown(self):
        """Clean shutdown of the execution engine"""
        self.executor.shutdown(wait=True)
        self._logger.info("Execution engine shut down")