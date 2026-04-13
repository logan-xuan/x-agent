"""SchedulerManager - Unified interface for cron task management.

This module provides a high-level interface for managing scheduled tasks,
with automatic agent_id and user_id tracking. It serves as the single source
of truth for both API and tool layers.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..conversation.identity import get_current_identity
from ..utils.logger import get_logger
from .config import JobConfig
from .exceptions import JobNotFoundError, SchedulerError
from .scheduler import CronScheduler, get_scheduler

logger = get_logger(__name__)


def _get_workspace_config() -> tuple[Path, str]:
    """获取 workspace 配置。

    Returns:
        tuple: (workspace_path, jobs_dir)
    """
    try:
        from ..config.manager import ConfigManager

        config = ConfigManager().config
        workspace_path = Path(config.workspace.path).expanduser().resolve()
        jobs_dir = getattr(config.workspace, "jobs_dir", "jobs")
        return workspace_path, jobs_dir
    except Exception as exc:
        logger.warning(
            "Failed to load workspace config, using defaults",
            extra={"error": str(exc)},
        )
        return Path("~/.x-agent/workspace").expanduser().resolve(), "jobs"


def resolve_func_path(func_path: str) -> str:
    """解析任务函数路径，支持 workspace: 前缀。

    支持的格式：
    1. 模块路径: 'cron.jobs.heartbeat:heartbeat_task'
    2. 绝对路径: '/Users/xxx/jobs/my_task.py:run_task'
    3. 相对路径: './jobs/my_task.py:run_task' (相对于当前工作目录)
    4. Workspace 路径: 'workspace:jobs/my_task.py:run_task' (相对于配置的 workspace 目录)
    5. 裸文件名: 'my_task.py:run_task' (自动在 workspace/jobs 下查找)

    Args:
        func_path: 原始函数路径

    Returns:
        解析后的函数路径（绝对路径或模块路径）
    """
    # 解析路径和函数名
    try:
        path_part, func_name = func_path.rsplit(":", 1)
    except ValueError as exc:
        raise SchedulerError(
            f"Invalid func_path format: {func_path}. Expected 'path:function_name'"
        ) from exc

    # 检查是否是 workspace: 前缀
    if path_part.startswith("workspace:"):
        # 获取 workspace 配置
        workspace_path, jobs_dir = _get_workspace_config()

        # 提取相对路径部分
        relative_path = path_part[len("workspace:") :]

        # 直接使用相对路径，不强制添加 jobs_dir
        # 这样可以支持 workspace:scripts/, workspace:jobs/, workspace:custom/ 等任意子目录
        resolved_path = workspace_path / relative_path
        return f"{resolved_path}:{func_name}"

    # 检查是否是 .py 结尾但不是绝对路径或相对路径（裸文件名）
    if path_part.endswith(".py") and not path_part.startswith(("/", "./", "../")):
        # 自动在 workspace/jobs_dir 下查找
        workspace_path, jobs_dir = _get_workspace_config()
        resolved_path = workspace_path / jobs_dir / path_part
        return f"{resolved_path}:{func_name}"

    # 其他情况直接返回原路径
    return func_path


class SchedulerManager:
    """Unified manager for cron task operations.

    This class provides a high-level interface for managing scheduled tasks,
    with automatic agent_id and user_id tracking. It wraps the CronScheduler
    and provides consistent behavior for both API and tool layers.

    Key features:
    - Automatic agent_id and user_id injection
    - Unified error handling
    - Consistent response format
    - Task lifecycle management
    """

    def __init__(self) -> None:
        """Initialize the scheduler manager."""
        self._scheduler: CronScheduler | None = None

    def _get_scheduler(self) -> CronScheduler:
        """Get the scheduler instance."""
        if self._scheduler is None:
            self._scheduler = get_scheduler()
        return self._scheduler

    def _get_current_identity(self) -> tuple[str | None, str | None]:
        """Get current agent_id and user_id.

        Returns:
            Tuple of (agent_id, user_id)
        """
        identity = get_current_identity()
        if identity:
            return identity.agent_id, identity.user_id
        return None, None

    def _inject_identity(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        """Inject agent_id and user_id into metadata.

        Args:
            metadata: Original metadata dict

        Returns:
            Metadata dict with agent_id and user_id added
        """
        agent_id, user_id = self._get_current_identity()

        if metadata is None:
            metadata = {}

        # Only add if not already present
        if agent_id and "agent_id" not in metadata:
            metadata["agent_id"] = agent_id
        if user_id and "user_id" not in metadata:
            metadata["user_id"] = user_id

        return metadata

    async def create_task(
        self,
        name: str,
        func_path: str,
        trigger_type: str,
        trigger_args: dict[str, Any],
        description: str = "",
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new scheduled task.

        Args:
            name: Task name
            func_path: Function path, supports multiple formats:
                - Module path: 'cron.jobs.heartbeat:heartbeat_task'
                - Absolute path: '/Users/xxx/jobs/my_task.py:run_task'
                - Workspace path: 'workspace:my_task.py:run_task' (auto-resolved)
                - Bare filename: 'my_task.py:run_task' (auto-resolved in workspace/jobs)
            trigger_type: Trigger type (cron/interval/date/calendar)
            trigger_args: Trigger-specific arguments
            description: Task description
            enabled: Whether to enable the task
            metadata: Custom metadata (agent_id/user_id will be auto-injected)
            task_id: Optional custom task ID. If not provided, auto-generated.

        Returns:
            Dict with task_id and creation status

        Raises:
            SchedulerError: If task creation fails
        """
        try:
            # Get current identity
            agent_id, user_id = self._get_current_identity()

            # Use provided task_id or generate one
            if not task_id:
                task_id = f"task_{uuid4().hex[:16]}"

            # Inject identity into metadata
            metadata = self._inject_identity(metadata)

            # Add task metadata
            metadata["task_name"] = name
            metadata["task_description"] = description
            metadata["created_at"] = datetime.now(UTC).isoformat()

            # Resolve func_path (support workspace: prefix and bare filenames)
            resolved_func_path = resolve_func_path(func_path)
            if resolved_func_path != func_path:
                logger.info(
                    "Func path resolved",
                    extra={"original": func_path, "resolved": resolved_func_path},
                )

            # Create job config
            # Validate trigger_type
            valid_trigger_types = ["cron", "interval", "date", "calendar"]
            if trigger_type not in valid_trigger_types:
                raise SchedulerError(
                    f"Invalid trigger type: {trigger_type}. Must be one of: {', '.join(valid_trigger_types)}"
                )

            job_config = JobConfig(
                id=task_id,
                func=resolved_func_path,
                trigger_type=trigger_type,  # type: ignore[assignment]
                trigger_args=trigger_args,
                enabled=enabled,
                metadata=metadata,
            )

            # Add to scheduler
            scheduler = self._get_scheduler()
            schedule_id = await scheduler.add_schedule(job_config)

            logger.info(
                "Task created successfully",
                extra={
                    "task_id": task_id,
                    "schedule_id": schedule_id,
                    "name": name,
                    "agent_id": agent_id,
                    "user_id": user_id,
                },
            )

            return {
                "id": task_id,
                "task_id": task_id,  # Alias for tool layer compatibility
                "name": name,
                "trigger_type": trigger_type,
                "enabled": enabled,
                "agent_id": agent_id,
                "user_id": user_id,
                "status": "created",
            }

        except Exception as e:
            logger.error("Failed to create task", extra={"name": name, "error": str(e)})
            raise SchedulerError(f"Failed to create task: {e}") from e

    async def query_tasks(
        self,
        task_id: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        enabled_only: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Query scheduled tasks.

        Args:
            task_id: Specific task ID to query
            agent_id: Filter by agent_id
            user_id: Filter by user_id
            enabled_only: Only return enabled tasks
            limit: Maximum number of results

        Returns:
            Dict with task list and metadata
        """
        try:
            scheduler = self._get_scheduler()

            # If task_id is provided, get single task
            if task_id:
                schedules = await scheduler.get_schedules()
                for schedule in schedules:
                    if schedule.get("id") == task_id:
                        return {
                            "task": schedule,
                            "total": 1,
                        }
                raise JobNotFoundError(f"Task not found: {task_id}")

            # Get all schedules
            schedules = await scheduler.get_schedules()

            # Filter tasks
            filtered = []
            for schedule in schedules:
                metadata = schedule.get("metadata", {})

                # Filter by agent_id
                if agent_id and metadata.get("agent_id") != agent_id:
                    continue

                # Filter by user_id
                if user_id and metadata.get("user_id") != user_id:
                    continue

                # Filter by enabled status
                if enabled_only and schedule.get("paused", True):
                    continue

                filtered.append(schedule)

            # Apply limit
            filtered = filtered[:limit]

            return {
                "tasks": filtered,
                "total": len(filtered),
            }

        except JobNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to query tasks", extra={"error": str(e)})
            raise SchedulerError(f"Failed to query tasks: {e}") from e

    async def pause_task(self, task_id: str) -> dict[str, Any]:
        """Pause a scheduled task.

        Args:
            task_id: Task ID to pause

        Returns:
            Dict with pause status
        """
        try:
            scheduler = self._get_scheduler()
            await scheduler.pause_schedule(task_id)

            logger.info("Task paused", extra={"task_id": task_id})

            return {
                "task_id": task_id,
                "status": "paused",
            }

        except Exception as e:
            logger.error("Failed to pause task", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to pause task: {e}") from e

    async def resume_task(
        self,
        task_id: str,
        resume_from: str = "now",
    ) -> dict[str, Any]:
        """Resume a paused task.

        Args:
            task_id: Task ID to resume
            resume_from: When to resume (now or datetime)

        Returns:
            Dict with resume status
        """
        try:
            scheduler = self._get_scheduler()
            await scheduler.resume_schedule(task_id, resume_from=resume_from)

            logger.info("Task resumed", extra={"task_id": task_id})

            return {
                "task_id": task_id,
                "status": "resumed",
            }

        except Exception as e:
            logger.error("Failed to resume task", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to resume task: {e}") from e

    async def delete_task(self, task_id: str) -> dict[str, Any]:
        """Delete a scheduled task.

        Args:
            task_id: Task ID to delete

        Returns:
            Dict with delete status
        """
        try:
            scheduler = self._get_scheduler()
            await scheduler.remove_schedule(task_id)

            logger.info("Task deleted", extra={"task_id": task_id})

            return {
                "task_id": task_id,
                "status": "deleted",
            }

        except Exception as e:
            logger.error("Failed to delete task", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to delete task: {e}") from e

    async def get_all_schedules(self) -> list[dict]:
        """Get all schedules (raw list from scheduler).

        Returns:
            List of schedule dicts
        """
        try:
            scheduler = self._get_scheduler()
            return await scheduler.get_schedules()
        except Exception as e:
            logger.error("Failed to get schedules", extra={"error": str(e)})
            raise SchedulerError(f"Failed to get schedules: {e}") from e

    async def get_schedule_by_id(self, schedule_id: str) -> dict[str, Any] | None:
        """Get a specific schedule by ID.

        Args:
            schedule_id: Schedule ID to look up

        Returns:
            Schedule dict if found, None otherwise
        """
        try:
            schedules = await self.get_all_schedules()
            for schedule in schedules:
                if schedule.get("id") == schedule_id:
                    return schedule
            return None
        except Exception as e:
            logger.error(
                "Failed to get schedule", extra={"schedule_id": schedule_id, "error": str(e)}
            )
            raise SchedulerError(f"Failed to get schedule: {e}") from e

    async def create_schedule(self, config: JobConfig) -> str:
        """Create a schedule from a JobConfig (low-level API for router).

        Args:
            config: JobConfig instance

        Returns:
            Schedule ID
        """
        try:
            scheduler = self._get_scheduler()
            schedule_id = await scheduler.add_schedule(config)
            logger.info("Schedule created", extra={"schedule_id": schedule_id})
            return schedule_id
        except Exception as e:
            logger.error("Failed to create schedule", extra={"error": str(e)})
            raise SchedulerError(f"Failed to create schedule: {e}") from e

    async def get_jobs(self) -> list[dict]:
        """Get job execution history.

        Returns:
            List of job execution records
        """
        try:
            scheduler = self._get_scheduler()
            return await scheduler.get_jobs()
        except Exception as e:
            logger.error("Failed to get jobs", extra={"error": str(e)})
            raise SchedulerError(f"Failed to get jobs: {e}") from e

    async def get_tasks(self) -> list[dict]:
        """Get all registered tasks from the data store.

        Returns:
            List of task dicts
        """
        try:
            scheduler = self._get_scheduler()
            if hasattr(scheduler, "get_tasks"):
                return await scheduler.get_tasks()
            return []
        except Exception as e:
            logger.error("Failed to get tasks", extra={"error": str(e)})
            raise SchedulerError(f"Failed to get tasks: {e}") from e

    async def get_task_by_id(self, task_id: str) -> dict[str, Any] | None:
        """Get a specific task by ID.

        Args:
            task_id: Task ID to look up

        Returns:
            Task dict if found, None otherwise
        """
        try:
            tasks = await self.get_tasks()
            for task in tasks:
                if task.get("id") == task_id:
                    return task
            return None
        except Exception as e:
            logger.error("Failed to get task", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to get task: {e}") from e

    async def remove_task(self, task_id: str) -> dict[str, Any]:
        """Remove a task definition.

        Args:
            task_id: Task ID to remove

        Returns:
            Dict with removal status
        """
        try:
            scheduler = self._get_scheduler()
            await scheduler.remove_task(task_id)
            logger.info("Task removed", extra={"task_id": task_id})
            return {"task_id": task_id, "status": "deleted"}
        except Exception as e:
            logger.error("Failed to remove task", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to remove task: {e}") from e

    async def run_task_now(
        self,
        task_id: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a task immediately (alias for execute_now with consistent return).

        Args:
            task_id: Task ID to execute
            args: Arguments to pass to the task function

        Returns:
            Dict with task_id and result
        """
        try:
            scheduler = self._get_scheduler()
            result = await scheduler.run_job_now(task_id, **(args or {}))
            logger.info("Task run immediately", extra={"task_id": task_id})
            return {"task_id": task_id, "result": result}
        except Exception as e:
            logger.error("Failed to run task now", extra={"task_id": task_id, "error": str(e)})
            raise SchedulerError(f"Failed to run task: {e}") from e

    async def get_status(self) -> dict[str, Any]:
        """Get scheduler status information.

        Returns:
            Dict with scheduler status details
        """
        try:
            scheduler = self._get_scheduler()

            schedules = await scheduler.get_schedules()
            tasks = await scheduler.get_tasks() if hasattr(scheduler, "get_tasks") else []

            # Determine data store type
            data_store_type = "memory"
            if scheduler._data_store:
                store_class_name = type(scheduler._data_store).__name__
                if "SQLAlchemy" in store_class_name:
                    data_store_type = "sqlite"

            # Get timezone from config
            scheduler_timezone = "UTC"
            if scheduler._config:
                scheduler_timezone = getattr(scheduler._config, "timezone", "UTC")

            return {
                "running": scheduler.is_running,
                "has_scheduler": scheduler.scheduler is not None,
                "timezone": scheduler_timezone,
                "data_store": data_store_type,
                "schedule_count": len(schedules),
                "job_count": len(tasks),
            }
        except Exception as e:
            logger.error("Failed to get scheduler status", extra={"error": str(e)})
            raise SchedulerError(f"Failed to get scheduler status: {e}") from e


# Global instance
_manager_instance: SchedulerManager | None = None


def get_scheduler_manager() -> SchedulerManager:
    """Get the global scheduler manager instance.

    Returns:
        SchedulerManager instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SchedulerManager()
    return _manager_instance
    return _manager_instance
