"""APScheduler 4.0 core scheduler wrapper for X-Agent."""

import asyncio
import importlib
import importlib.util
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from apscheduler import AsyncScheduler
from apscheduler.datastores.memory import MemoryDataStore
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.calendarinterval import CalendarIntervalTrigger
from apscheduler._events import JobAcquired, JobReleased
from apscheduler._enums import JobOutcome, CoalescePolicy, ConflictPolicy

from ..utils.logger import get_logger
from ..conversation.identity import get_identity_manager
from .config import CronConfig, JobConfig
from .exceptions import SchedulerError, JobNotFoundError, InvalidTriggerError
from .retry import RetryPolicy, RetryState, JobStatus, JobExecutionRecord
from .execution_mode import ExecutionMode, ExecutionModeConfig

logger = get_logger(__name__)


class CronScheduler:
    """APScheduler 4.0 wrapper for X-Agent.
    
    Features:
    - Async-first design using AsyncScheduler
    - Support for both memory and SQLAlchemy data stores
    - Lifecycle management (startup/shutdown)
    - Dynamic job management (add/remove/pause/resume)
    """
    
    _instance: "CronScheduler | None" = None
    
    def __new__(cls) -> "CronScheduler":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
            
        self._scheduler: AsyncScheduler | None = None
        self._config: CronConfig | None = None
        self._initialized = True
        self._running = False
        self._data_store = None
        # Unified job execution history (both scheduled and manual triggers)
        # Keyed by job_id for easy lookup during JobReleased event
        # Using OrderedDict for LRU cache implementation
        self._job_history: OrderedDict[str, dict] = OrderedDict()
        # Max history entries to prevent unbounded memory growth
        self._max_history = 1000  # 增加默认限制到 1000
        # Track task_ids currently being run manually to avoid duplicate records
        self._manual_running_tasks: set[str] = set()
        # Registry mapping task_id -> original func_path for recovery after restart
        self._func_path_registry: dict[str, str] = {}
        # Retry state tracking: job_id -> RetryState
        self._retry_states: dict[str, RetryState] = {}
        # Health tracking
        self._failed_job_count: int = 0
        self._recent_failures: list[datetime] = []  # 最近失败时间戳列表
        self._max_recent_failures: int = 100  # 保留的最近失败记录数
        # Execution mode cache
        self._execution_mode_configs: dict[str, ExecutionModeConfig] = {}
    
    async def initialize(self, config: CronConfig | None = None) -> None:
        """Initialize the scheduler configuration."""
        # Load configuration
        if config is None:
            from ..config.manager import get_config as get_app_config
            app_config = get_app_config()
            cron_config = getattr(app_config, 'cron', None)
            if cron_config:
                # Handle both dict and Pydantic model
                if hasattr(cron_config, 'model_dump'):
                    config = CronConfig(**cron_config.model_dump())
                else:
                    config = CronConfig(**cron_config)
            else:
                config = CronConfig()
        
        self._config = config
        
        if not config.enabled:
            logger.info("Scheduler is disabled")
            return
        
        # Create data store
        if config.job_store_url:
            self._data_store = SQLAlchemyDataStore(
                engine_or_url=config.job_store_url
            )
            logger.info(f"Using SQLAlchemy data store: {config.job_store_url}")
        else:
            self._data_store = MemoryDataStore()
            logger.info("Using memory data store")
    
    async def start(self) -> None:
        """Start the scheduler in background."""
        if not self._config or not self._config.enabled:
            return
        
        if self._running:
            return
        
        if not self._data_store:
            raise SchedulerError("Scheduler not initialized")
        
        try:
            # Create scheduler
            self._scheduler = AsyncScheduler(data_store=self._data_store)
            
            # Initialize scheduler using async context manager (required for APScheduler 4.0)
            await self._scheduler.__aenter__()
            
            # Subscribe to job events to track execution history
            self._scheduler.subscribe(self._on_job_acquired, JobAcquired)
            self._scheduler.subscribe(self._on_job_released, JobReleased)

            # Recover persisted tasks BEFORE starting the scheduler
            # This prevents crashes from orphaned jobs referencing deleted tasks
            await self._recover_persisted_tasks()
            
            # Clean up stale jobs left over from previous runs to prevent
            # burst-execution of all missed fire times on restart
            await self._cleanup_stale_jobs()
            
            # Start in background
            await self._scheduler.start_in_background()
            self._running = True
            await self._register_predefined_jobs()
            logger.info("Scheduler started in background")
        except Exception as e:
            raise SchedulerError(f"Failed to start scheduler: {e}") from e
    
    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._scheduler or not self._running:
            return
        
        try:
            await self._scheduler.stop()
            # Exit context manager
            await self._scheduler.__aexit__(None, None, None)
            self._running = False
            self._scheduler = None
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error("Error stopping scheduler", extra={"error": str(e)})
    
    def _on_job_acquired(self, event: JobAcquired) -> None:
        """Record job start when scheduler acquires a job for execution."""
        job_id = event.job_id.hex
        
        # Use IdentityManager to generate trace_id
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create()
        trace_id = identity.trace_id
        
        logger.info(
            "Job execution started",
            extra={
                "job_id": job_id,
                "task_id": event.task_id,
                "schedule_id": event.schedule_id,
                "trigger": "scheduled",
                "trace_id": trace_id,
                "state": "running",
            }
        )
        
        # Skip if this task is currently being run manually (run_job_now already recorded it)
        if event.task_id in self._manual_running_tasks:
            return
        
        # Update existing record if present (LRU: move to end)
        if job_id in self._job_history:
            self._job_history.move_to_end(job_id)
            return
            
        # Create new record
        self._job_history[job_id] = {
            "id": job_id,
            "task_id": event.task_id,
            "schedule_id": event.schedule_id,
            "trigger": "scheduled",
            "state": "running",
            "trace_id": trace_id,
            "created_at": event.scheduled_start.isoformat() if event.scheduled_start else datetime.now(timezone.utc).isoformat(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "result": None,
            "exception": None,
        }
        # Evict oldest entries if over limit (LRU: remove from beginning)
        while len(self._job_history) > self._max_history:
            oldest_key = next(iter(self._job_history))
            del self._job_history[oldest_key]

    def _on_job_released(self, event: JobReleased) -> None:
        """Update job record when scheduler finishes a job."""
        job_id = event.job_id.hex
        record = self._job_history.get(job_id)
        
        # Get trace_id from record or generate new one using IdentityManager
        trace_id = record.get("trace_id") if record else get_identity_manager().create().trace_id
        
        logger.info(
            "Job execution finished",
            extra={
                "job_id": job_id,
                "task_id": event.task_id,
                "schedule_id": event.schedule_id,
                "outcome": str(event.outcome),
                "trace_id": trace_id,
            }
        )
        
        # Skip if this task is currently being run manually (run_job_now handles its own record)
        if event.task_id in self._manual_running_tasks:
            return
        if record is None:
            # Job not tracked yet (edge case), create a minimal record
            record = {
                "id": job_id,
                "task_id": event.task_id,
                "schedule_id": event.schedule_id,
                "trigger": "scheduled",
                "state": "unknown",
                "trace_id": trace_id,
                "created_at": event.scheduled_start.isoformat() if event.scheduled_start else None,
                "started_at": event.started_at.isoformat() if event.started_at else None,
                "ended_at": None,
                "result": None,
                "exception": None,
            }
            self._job_history[job_id] = record

        record["ended_at"] = datetime.now(timezone.utc).isoformat()
        if event.started_at:
            record["started_at"] = event.started_at.isoformat()

        if event.outcome == JobOutcome.success:
            record["state"] = "completed"
            # Clear retry state on success
            if job_id in self._retry_states:
                del self._retry_states[job_id]
        elif event.outcome == JobOutcome.error:
            record["state"] = "failed"
            record["exception"] = event.exception_message
            
            # Track failure for health monitoring
            self._track_failure()
            
            # Check if retry is needed (schedule async task from sync callback)
            asyncio.create_task(
                self._handle_job_failure(job_id, event.task_id, event.exception_message)
            )
            
            logger.error(
                "Job execution failed",
                extra={
                    "job_id": job_id,
                    "task_id": event.task_id,
                    "trace_id": trace_id,
                    "error": event.exception_message,
                }
            )
        elif event.outcome == JobOutcome.missed_start_deadline:
            record["state"] = "missed"
        elif event.outcome == JobOutcome.cancelled:
            record["state"] = "cancelled"
        else:
            record["state"] = str(event.outcome)

    async def _recover_persisted_tasks(self) -> None:
        """Recover persisted tasks from the data store after restart.
        
        Recovery strategy (precise, metadata-first):
        1. Read all schedules from the data store and build a task_id -> func_path
           mapping from each schedule's metadata (persisted via add_schedule).
        2. For each task with a dynamic module name (user_job_*), look up the
           func_path from the metadata mapping.
        3. Verify the script file still exists on disk:
           - File exists → re-import and register the callable (recover).
           - File missing → remove the task, its schedules, and orphaned jobs.
        4. If no metadata is available (legacy data), fall back to scanning
           workspace/jobs directory for a matching function name.
        """
        if not self._scheduler:
            return
        
        try:
            # Step 1: Build task_id -> func_path mapping from schedule metadata
            task_func_path_from_metadata: dict[str, str] = {}
            try:
                schedules = await self._scheduler.data_store.get_schedules()
                for schedule in schedules:
                    schedule_task_id = getattr(schedule, 'task_id', None)
                    metadata = getattr(schedule, 'metadata', {}) or {}
                    func_path = metadata.get("func_path")
                    if schedule_task_id and func_path:
                        task_func_path_from_metadata[schedule_task_id] = func_path
                        logger.debug(
                            "Found func_path in schedule metadata",
                            extra={
                                "schedule_id": getattr(schedule, 'id', ''),
                                "task_id": schedule_task_id,
                                "func_path": func_path,
                            }
                        )
            except Exception as e:
                logger.warning("Failed to read schedules for metadata recovery", extra={"error": str(e)})
            
            # Step 2: Iterate over all tasks and recover or cleanup
            tasks = await self._scheduler.data_store.get_tasks()
            
            for task in tasks:
                task_id = task.id
                func_ref = getattr(task, 'func', None)
                
                if not func_ref or task_id in self._func_path_registry:
                    continue
                
                # Parse func reference
                try:
                    module_part, func_name = func_ref.rsplit(":", 1)
                except ValueError:
                    continue
                
                if module_part.startswith("user_job_"):
                    # Dynamic module - try metadata-based recovery first
                    recovered = False
                    
                    # Strategy A: Use func_path from schedule metadata (precise)
                    metadata_func_path = task_func_path_from_metadata.get(task_id)
                    if metadata_func_path:
                        try:
                            # Extract file path from func_path (format: "/path/to/file.py:func_name")
                            file_part = metadata_func_path.rsplit(":", 1)[0]
                            script_file = Path(file_part)
                            
                            if script_file.exists() and script_file.is_file():
                                func = self._import_function(metadata_func_path)
                                self._func_path_registry[task_id] = metadata_func_path
                                self._scheduler._task_callables[task_id] = func
                                logger.info(
                                    "Recovered task from schedule metadata",
                                    extra={"task_id": task_id, "func_path": metadata_func_path}
                                )
                                recovered = True
                            else:
                                logger.warning(
                                    "Script file from metadata no longer exists",
                                    extra={"task_id": task_id, "func_path": metadata_func_path}
                                )
                        except Exception as e:
                            logger.warning(
                                "Failed to recover task from metadata func_path",
                                extra={"task_id": task_id, "func_path": metadata_func_path, "error": str(e)}
                            )
                    
                    # Strategy B: Fallback - scan workspace/jobs directory (legacy data without metadata)
                    if not recovered and not metadata_func_path:
                        try:
                            from .manager import _get_workspace_config
                            workspace_path, jobs_dir = _get_workspace_config()
                            jobs_path = workspace_path / jobs_dir
                            
                            if jobs_path.exists():
                                for py_file in jobs_path.glob("*.py"):
                                    try:
                                        spec = importlib.util.spec_from_file_location(
                                            f"recovery_check_{py_file.stem}", py_file
                                        )
                                        if spec and spec.loader:
                                            test_module = importlib.util.module_from_spec(spec)
                                            spec.loader.exec_module(test_module)
                                            if hasattr(test_module, func_name):
                                                resolved_path = f"{py_file}:{func_name}"
                                                self._func_path_registry[task_id] = resolved_path
                                                self._scheduler._task_callables[task_id] = getattr(test_module, func_name)
                                                logger.info(
                                                    "Recovered task via workspace scan (legacy fallback)",
                                                    extra={"task_id": task_id, "func_path": resolved_path}
                                                )
                                                recovered = True
                                                break
                                    except Exception as e:
                                        logger.debug(
                                            "Skipping file during recovery scan",
                                            extra={"file": str(py_file), "error": str(e)}
                                        )
                        except Exception as e:
                            logger.warning("Error during workspace scan fallback", extra={"error": str(e)})
                    
                    if not recovered:
                        logger.warning(
                            "Removing unrecoverable task and its schedules/jobs",
                            extra={"task_id": task_id, "func_ref": func_ref}
                        )
                        await self._cleanup_broken_task(task_id)
                else:
                    # Standard module path - try to import and register
                    try:
                        func = self._import_function(func_ref)
                        self._func_path_registry[task_id] = func_ref
                        self._scheduler._task_callables[task_id] = func
                    except Exception as e:
                        logger.warning(
                            "Failed to recover standard task, removing",
                            extra={"task_id": task_id, "func_ref": func_ref, "error": str(e)}
                        )
                        await self._cleanup_broken_task(task_id)
                    
        except Exception as e:
            logger.error("Failed to recover persisted tasks", extra={"error": str(e)})
    
    async def _cleanup_broken_task(self, task_id: str) -> None:
        """Remove a broken task and all its associated schedules and jobs from the data store."""
        if not self._scheduler:
            return
        
        data_store = self._scheduler.data_store
        try:
            # Remove associated schedules
            schedules = await data_store.get_schedules()
            for s in schedules:
                if getattr(s, 'task_id', '') == task_id:
                    schedule_id = getattr(s, 'id', '')
                    await data_store.remove_schedules({schedule_id})
                    logger.info("Removed orphaned schedule", extra={"schedule_id": schedule_id})
            
            # Remove orphaned jobs from the database directly
            # APScheduler's data_store doesn't expose a bulk job removal by task_id,
            # so we use direct SQL for cleanup
            if self._config and self._config.job_store_url:
                try:
                    import aiosqlite
                    db_path = self._config.job_store_url.replace("sqlite:///", "")
                    async with aiosqlite.connect(db_path) as db:
                        # Delete job_results first (references jobs), then jobs
                        await db.execute(
                            "DELETE FROM job_results WHERE job_id IN (SELECT id FROM jobs WHERE task_id = ?)",
                            (task_id,)
                        )
                        cursor = await db.execute(
                            "DELETE FROM jobs WHERE task_id = ?", (task_id,)
                        )
                        deleted_jobs = cursor.rowcount
                        await db.commit()
                        if deleted_jobs:
                            logger.info(
                                "Removed orphaned jobs from database",
                                extra={"task_id": task_id, "deleted_count": deleted_jobs}
                            )
                except Exception as db_err:
                    logger.warning("Failed to cleanup jobs via SQL", extra={"error": str(db_err)})
            
            # Remove the broken task itself
            await data_store.remove_task(task_id)
            logger.info("Removed unrecoverable task", extra={"task_id": task_id})
        except Exception as cleanup_err:
            logger.error(
                "Failed to cleanup broken task",
                extra={"task_id": task_id, "error": str(cleanup_err)}
            )

    async def _cleanup_stale_jobs(self) -> None:
        """Remove all pending jobs from the data store on startup.
        
        When the service restarts, APScheduler may have accumulated many pending
        jobs for missed fire times (especially if misfire_grace_time was not set).
        These stale jobs would all execute in rapid succession, causing burst
        behavior instead of following the configured schedule cadence.
        
        By clearing all pending jobs before starting the scheduler worker loop,
        we ensure that only newly generated jobs (from the next fire time onward)
        are executed.
        """
        if not self._config or not self._config.job_store_url:
            return
        
        try:
            import aiosqlite
            db_path = self._config.job_store_url.replace("sqlite:///", "")
            async with aiosqlite.connect(db_path) as db:
                # Count pending jobs before cleanup
                cursor = await db.execute("SELECT COUNT(*) FROM jobs")
                row = await cursor.fetchone()
                pending_count = row[0] if row else 0
                
                if pending_count == 0:
                    return
                
                # Delete all job_results first (foreign key references), then jobs
                await db.execute("DELETE FROM job_results WHERE job_id IN (SELECT id FROM jobs)")
                await db.execute("DELETE FROM jobs")
                await db.commit()
                
                logger.info(
                    "Cleaned up stale jobs on startup to prevent burst execution",
                    extra={"deleted_count": pending_count}
                )
        except Exception as e:
            logger.warning(
                "Failed to cleanup stale jobs on startup",
                extra={"error": str(e)}
            )

    async def _register_predefined_jobs(self) -> None:
        """Register jobs from configuration."""
        if not self._config:
            return
        
        for job_config in self._config.jobs:
            if not job_config.enabled:
                continue
            try:
                await self.add_schedule(job_config)
                logger.info("Registered predefined job", extra={"job_id": job_config.id})
            except Exception as e:
                logger.error("Failed to register job", extra={"job_id": job_config.id, "error": str(e)})
    
    def _create_trigger(self, trigger_type: str, args: dict) -> Any:
        """Create trigger instance."""
        if trigger_type == "date":
            # Handle parameter compatibility: support both 'run_date' and 'run_time'
            # APScheduler 4.0 uses 'run_time', but some tools may use 'run_date'
            trigger_args = args.copy()
            if "run_date" in trigger_args and "run_time" not in trigger_args:
                trigger_args["run_time"] = trigger_args.pop("run_date")
                logger.debug(
                    "Converted run_date to run_time for DateTrigger",
                    extra={"original_args": args, "converted_args": trigger_args}
                )
            return DateTrigger(**trigger_args)
        elif trigger_type == "interval":
            return IntervalTrigger(**args)
        elif trigger_type == "cron":
            return CronTrigger(**args)
        elif trigger_type == "calendar":
            return CalendarIntervalTrigger(**args)
        else:
            raise InvalidTriggerError(f"Unsupported trigger type: {trigger_type}")
    
    def _import_function(self, func_path: str) -> Callable:
        """Import function - supports both module path and absolute file path.
        
        支持两种格式：
        1. 模块路径：'cron.jobs.heartbeat:heartbeat_task'
        2. 绝对路径：'/Users/xxx/workspace/jobs/my_task.py:run_task'
           或相对路径：'./jobs/my_task.py:run_task'（相对于当前工作目录）
        
        Args:
            func_path: 函数路径，格式为 'module_or_file:function_name'
            
        Returns:
            可调用的函数对象
            
        Raises:
            SchedulerError: 导入失败时抛出
        """
        try:
            module_or_path, func_name = func_path.rsplit(":", 1)
        except ValueError:
            raise SchedulerError(
                f"Invalid func_path format: {func_path}. "
                f"Expected 'module_or_file:function_name'"
            )
        
        # 检查是否是文件路径（绝对路径或相对路径）
        path_candidate = Path(module_or_path)
        
        # 判断是否为文件路径：
        # 1. 绝对路径（以 / 开头）
        # 2. 相对路径（以 ./ 或 ../ 开头）
        # 3. 以 .py 结尾的路径
        is_file_path = (
            module_or_path.startswith("/") or 
            module_or_path.startswith("./") or 
            module_or_path.startswith("../") or
            module_or_path.endswith(".py")
        )
        
        if is_file_path:
            # 文件路径方式加载
            if not path_candidate.is_absolute():
                # 相对路径转为绝对路径
                path_candidate = Path.cwd() / path_candidate
            
            if not path_candidate.exists():
                raise SchedulerError(
                    f"Job script file not found: {path_candidate}"
                )
            
            if not path_candidate.is_file():
                raise SchedulerError(
                    f"Job script path is not a file: {path_candidate}"
                )
            
            # 使用 importlib.util 从文件动态加载模块
            # 生成唯一的模块名以避免冲突
            module_name = f"user_job_{uuid.uuid4().hex[:8]}"
            
            spec = importlib.util.spec_from_file_location(module_name, path_candidate)
            if spec is None or spec.loader is None:
                raise SchedulerError(
                    f"Failed to create module spec from file: {path_candidate}"
                )
            
            module = importlib.util.module_from_spec(spec)
            
            # 执行模块代码
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                raise SchedulerError(
                    f"Failed to execute module {path_candidate}: {e}"
                ) from e
            
            logger.info(
                "Job module loaded from file",
                extra={
                    "file_path": str(path_candidate),
                    "module_name": module_name,
                    "func_name": func_name,
                }
            )
        else:
            # 原有的模块路径方式
            try:
                module = importlib.import_module(module_or_path)
            except ImportError as e:
                raise SchedulerError(
                    f"Failed to import module '{module_or_path}': {e}"
                ) from e
        
        # 获取目标函数
        if not hasattr(module, func_name):
            available_funcs = [
                name for name in dir(module) 
                if callable(getattr(module, name)) and not name.startswith("_")
            ]
            raise SchedulerError(
                f"Function '{func_name}' not found in module. "
                f"Available functions: {available_funcs}"
            )
        
        return getattr(module, func_name)
    
    async def add_schedule(self, config: JobConfig) -> str:
        """Add a schedule to the scheduler."""
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        
        # Resolve func_path if it contains workspace: prefix or bare filename
        from .manager import resolve_func_path
        resolved_func = resolve_func_path(config.func)
        if resolved_func != config.func:
            logger.info(
                "Func path resolved",
                extra={"original": config.func, "resolved": resolved_func}
            )
        
        func = self._import_function(resolved_func)
        trigger = self._create_trigger(config.trigger_type, config.trigger_args)
        
        # APScheduler 4.0 add_schedule with a function object will auto-create a task
        # with a dynamic module name (e.g. user_job_xxx:func_name).
        # We register the func path mapping BEFORE adding the schedule so that
        # _resolve_task_function can find it immediately.
        
        # Predict the task_id that APScheduler will generate
        # APScheduler uses the callable's qualified name as task_id
        func_module = getattr(func, '__module__', '')
        func_qualname = getattr(func, '__qualname__', getattr(func, '__name__', ''))
        predicted_task_id = f"{func_module}:{func_qualname}"
        
        # Pre-register the func path mapping
        self._func_path_registry[predicted_task_id] = resolved_func
        logger.info(
            "Pre-registered func path for task",
            extra={"predicted_task_id": predicted_task_id, "func_path": resolved_func}
        )
        
        # Merge config metadata with func_path for persistence
        # config.metadata may contain task_name, agent_id, user_id, etc. from manager layer
        schedule_metadata = dict(config.metadata) if config.metadata else {}
        schedule_metadata["func_path"] = resolved_func
        schedule_metadata["conflict_policy"] = config.conflict_policy
        schedule_metadata["coalesce"] = config.coalesce
        
        # Convert misfire_grace_time from seconds to timedelta
        misfire_grace = timedelta(seconds=config.misfire_grace_time)
        
        # Map config string values to APScheduler enum values
        coalesce_map = {
            "earliest": CoalescePolicy.earliest,
            "latest": CoalescePolicy.latest,
            "all": CoalescePolicy.all,
        }
        coalesce_policy = coalesce_map.get(config.coalesce, CoalescePolicy.latest)
        
        conflict_map = {
            "replace": ConflictPolicy.replace,
            "do_nothing": ConflictPolicy.do_nothing,
            "exception": ConflictPolicy.exception,
        }
        conflict_policy = conflict_map.get(config.conflict_policy, ConflictPolicy.replace)
        
        schedule_id = await self._scheduler.add_schedule(
            func_or_task_id=func,
            trigger=trigger,
            id=config.id,
            coalesce=coalesce_policy,
            misfire_grace_time=misfire_grace,
            conflict_policy=conflict_policy,
            metadata=schedule_metadata,
        )
        
        return config.id

    async def remove_schedule(self, schedule_id: str) -> None:
        """Remove a schedule."""
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        
        try:
            # Remove the schedule from the scheduler
            await self._scheduler.remove_schedule(schedule_id)
            
            # Verify removal by checking if the schedule still exists
            try:
                schedules = await self._scheduler.get_schedules()
                still_exists = False
                for schedule in schedules:
                    if str(getattr(schedule, 'id', '')) == schedule_id:
                        still_exists = True
                        break
                
                if still_exists:
                    logger.error(
                        "Schedule still exists after removal - this indicates a bug",
                        extra={"schedule_id": schedule_id}
                    )
                    # Try to remove again as a fallback
                    await self._scheduler.remove_schedule(schedule_id)
            except Exception as check_error:
                logger.warning(
                    "Failed to verify schedule removal",
                    extra={"schedule_id": schedule_id, "error": str(check_error)}
                )
            
            logger.info("Schedule removed", extra={"schedule_id": schedule_id})
        except Exception as e:
            raise JobNotFoundError(f"Schedule {schedule_id} not found") from e
    
    async def get_schedules(self) -> list[dict]:
        """Get all schedules."""
        if not self._scheduler:
            return []
        
        try:
            schedules = await self._scheduler.get_schedules()
            result = []
            for s in schedules:
                # Safely extract trigger info
                trigger_type = "unknown"
                trigger_args = {}
                trigger = getattr(s, 'trigger', None)
                if trigger:
                    trigger_type = trigger.__class__.__name__.replace("Trigger", "").lower()
                    # IntervalTrigger: stores weeks/days/hours/minutes/seconds/microseconds as individual attrs
                    if trigger_type == "interval":
                        for field in ("weeks", "days", "hours", "minutes", "seconds", "microseconds"):
                            value = getattr(trigger, field, 0)
                            if value and value > 0:
                                trigger_args[field] = value
                    # DateTrigger: has 'run_time' attribute (APScheduler 4.0)
                    elif hasattr(trigger, 'run_time'):
                        run_time = getattr(trigger, 'run_time', None)
                        trigger_args = {'run_time': run_time.isoformat() if run_time else None}
                    # CronTrigger: has 'fields' attribute
                    elif hasattr(trigger, 'fields'):
                        for field in trigger.fields:
                            if hasattr(field, 'name'):
                                trigger_args[field.name] = str(getattr(field, 'values', ''))
                
                # Safely extract other attributes
                coalesce_attr = getattr(s, 'coalesce', None)
                metadata = getattr(s, 'metadata', {}) or {}
                
                # coalesce: prefer APScheduler's persisted value, fallback to metadata
                if coalesce_attr is not None and hasattr(coalesce_attr, 'name'):
                    coalesce_value = coalesce_attr.name.lower()  # type: ignore[union-attr]
                else:
                    coalesce_value = metadata.get("coalesce", "latest")
                
                # conflict_policy: APScheduler does NOT persist this on the schedule object,
                # so we always read it from metadata where we stored it during add_schedule
                conflict_policy_value = metadata.get("conflict_policy", "replace")
                
                next_fire_time = getattr(s, 'next_fire_time', None)
                last_fire_time = getattr(s, 'last_fire_time', None)
                result.append({
                    "id": str(getattr(s, 'id', 'unknown')),
                    "task_id": getattr(s, 'task_id', 'unknown'),
                    "trigger": {
                        "type": trigger_type,
                        "args": trigger_args,
                    },
                    "next_fire_time": next_fire_time.isoformat() if next_fire_time is not None else None,
                    "last_fire_time": last_fire_time.isoformat() if last_fire_time is not None else None,
                    "coalesce": coalesce_value,
                    "conflict_policy": conflict_policy_value,
                    "paused": getattr(s, 'paused', False),
                    "enabled": not getattr(s, 'paused', False),
                    "func_path": metadata.get("func_path", None),
                    "task_name": metadata.get("task_name", None),
                    "task_description": metadata.get("task_description", None),
                    "metadata": metadata,
                })
            return result
        except Exception as e:
            logger.error("Failed to get schedules", extra={"error": str(e)})
            return []
    
    async def pause_schedule(self, schedule_id: str) -> None:
        """Pause a schedule."""
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        
        try:
            await self._scheduler.pause_schedule(schedule_id)
            logger.info("Schedule paused", extra={"schedule_id": schedule_id})
        except Exception as e:
            raise JobNotFoundError(f"Schedule {schedule_id} not found") from e
    
    async def resume_schedule(self, schedule_id: str, resume_from: str | datetime = "now") -> None:
        """Resume a paused schedule."""
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")

        try:
            # APScheduler 4.0 accepts datetime or the literal "now"
            resolved_resume_from: datetime | None = None if resume_from == "now" else (
                resume_from if isinstance(resume_from, datetime) else None
            )
            await self._scheduler.unpause_schedule(schedule_id, resume_from=resolved_resume_from)
            logger.info("Schedule resumed", extra={"schedule_id": schedule_id})
        except Exception as e:
            raise JobNotFoundError(f"Schedule {schedule_id} not found") from e
    
    async def run_job_now(self, task_id: str, **kwargs) -> Any:
        """Run a job immediately and save execution record.
        
        APScheduler 4.0's run_job() executes directly without writing to the data store,
        so we maintain a unified job history for observability.
        """
        logger.info("[DEBUG] run_job_now entry", extra={"task_id": task_id, "kwargs": kwargs})
        
        if not self._scheduler:
            logger.error("[DEBUG] Scheduler not initialized")
            raise SchedulerError("Scheduler not initialized")

        job_id = str(uuid.uuid4())
        
        # Use IdentityManager to generate trace_id
        identity_mgr = get_identity_manager()
        identity = identity_mgr.create()
        trace_id = identity.trace_id
        
        created_at = datetime.now(timezone.utc)
        
        logger.info(
            "Manual job execution started",
            extra={
                "job_id": job_id,
                "task_id": task_id,
                "trigger": "manual",
                "trace_id": trace_id,
                "state": "running",
            }
        )
        
        record: dict = {
            "id": job_id,
            "task_id": task_id,
            "schedule_id": None,
            "trigger": "manual",
            "trace_id": trace_id,
            "state": "running",
            "created_at": created_at.isoformat(),
            "started_at": created_at.isoformat(),
            "ended_at": None,
            "result": None,
            "exception": None,
        }
        self._job_history[job_id] = record
        self._job_history.move_to_end(job_id)
        # LRU eviction: remove oldest entries if over limit
        while len(self._job_history) > self._max_history:
            oldest_key = next(iter(self._job_history))
            del self._job_history[oldest_key]

        # Mark this task as manually running to prevent event callbacks from creating duplicates
        self._manual_running_tasks.add(task_id)
        try:
            # Resolve the task function directly instead of relying on scheduler.run_job()
            # which can hang if the scheduler has crashed
            func = await self._resolve_task_function(task_id)
            logger.info(
                "Resolved task function for direct execution",
                extra={"task_id": task_id, "func": str(func)}
            )
            
            # Execute the function directly
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            
            record["state"] = "completed"
            record["result"] = result
            record["ended_at"] = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Manual job execution completed",
                extra={
                    "job_id": job_id,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "result": str(result),
                }
            )
            return result
        except Exception as e:
            record["state"] = "failed"
            record["exception"] = str(e)
            record["ended_at"] = datetime.now(timezone.utc).isoformat()
            logger.error(
                "Manual job execution failed",
                extra={
                    "job_id": job_id,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            raise SchedulerError(f"Failed to run task {task_id}: {e}") from e
        finally:
            self._manual_running_tasks.discard(task_id)
    
    async def _resolve_task_function(self, task_id: str) -> Callable:
        """Resolve a task_id to its callable function.
        
        Resolution order:
        1. Check in-memory func_path_registry (set during add_schedule)
        2. Look up task in data store and try to import its func reference
        3. Try importing task_id directly as a func reference
        """
        # 1. Check our in-memory registry first (most reliable for file-based tasks)
        if task_id in self._func_path_registry:
            func_path = self._func_path_registry[task_id]
            logger.info(
                "Resolving task from func_path_registry",
                extra={"task_id": task_id, "func_path": func_path}
            )
            return self._import_function(func_path)
        
        # 2. Try to find the task in the data store
        if self._scheduler:
            try:
                tasks = await self._scheduler.data_store.get_tasks()
                for task in tasks:
                    if task.id == task_id:
                        func_ref = getattr(task, 'func', None)
                        if func_ref:
                            return self._import_function(func_ref)
            except Exception as e:
                logger.warning(
                    "Failed to resolve task from data store",
                    extra={"task_id": task_id, "error": str(e)}
                )
        
        # 3. If task_id itself looks like a func reference, try importing directly
        if ":" in task_id:
            try:
                return self._import_function(task_id)
            except Exception as e:
                logger.warning(
                    "Failed to import task_id as func reference",
                    extra={"task_id": task_id, "error": str(e)}
                )
        
        raise SchedulerError(f"Cannot resolve task function for task_id: {task_id}")

    async def get_database_job_results(self) -> list[dict]:
        """Get job execution results from SQLite database via aiosqlite."""
        if not self._config or not self._config.job_store_url:
            logger.warning("No job_store_url configured, cannot read job results from database")
            return []

        try:
            import aiosqlite

            # Extract SQLite file path from URL like "sqlite:///data/cron_jobs.db"
            db_url = self._config.job_store_url
            db_path = db_url.replace("sqlite:///", "")
            logger.info(f"Querying job results from database: {db_path}")

            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # First, get all available schedules
                cursor = await db.execute("SELECT id, task_id FROM schedules")
                schedule_rows = await cursor.fetchall()
                schedule_map = {row["task_id"]: row["id"] for row in schedule_rows}
                
                # If there's only one schedule, use its task_id as default
                default_task_id = None
                default_schedule_id = None
                if len(schedule_map) == 1:
                    default_task_id = list(schedule_map.keys())[0]
                    default_schedule_id = list(schedule_map.values())[0]
                    logger.info(f"Using default task_id: {default_task_id}, schedule_id: {default_schedule_id}")
                
                # Get job results
                cursor = await db.execute("""
                    SELECT
                        jr.job_id,
                        jr.outcome,
                        jr.started_at,
                        jr.finished_at,
                        jr.exception,
                        j.task_id,
                        j.schedule_id
                    FROM job_results jr
                    LEFT JOIN jobs j ON jr.job_id = j.id
                    ORDER BY jr.finished_at DESC
                    LIMIT 100
                """)
                rows = await cursor.fetchall()
                rows_list = list(rows)
                logger.info(f"Found {len(rows_list)} job results in database")

                db_records = []
                for row in rows_list:
                    # Normalize state values to match in-memory records
                    outcome = row["outcome"] or "unknown"
                    state = outcome
                    if outcome == "success":
                        state = "completed"
                    
                    # Try to get task_id from jobs table first, then use default if available
                    task_id = row["task_id"] if row["task_id"] else None
                    if not task_id and default_task_id:
                        task_id = default_task_id
                    
                    # Get schedule_id from jobs table or from schedule_map using task_id
                    schedule_id = row["schedule_id"] if row["schedule_id"] else None
                    if not schedule_id and task_id and task_id in schedule_map:
                        schedule_id = schedule_map[task_id]
                    
                    db_records.append({
                        "id": str(row["job_id"]),
                        "task_id": task_id if task_id else "unknown",
                        "schedule_id": schedule_id,
                        "trigger": "scheduled",
                        "state": state,
                        "created_at": row["started_at"],
                        "started_at": row["started_at"],
                        "ended_at": row["finished_at"],
                        "result": "success" if outcome == "success" else None,
                        "exception": row["exception"] if row["exception"] else None,
                    })
                return db_records
        except ImportError:
            logger.warning("aiosqlite not installed, cannot read job results from database")
            return []
        except Exception as e:
            logger.error("Failed to get job results from database", extra={"error": str(e)})
            return []

    async def get_jobs(self) -> list[dict]:
        """Get job execution history (both scheduled and manual triggers).
        
        Returns records captured via JobAcquired/JobReleased event subscriptions
        plus manually triggered jobs from run_job_now(), merged with database records.
        Each record has a 'trigger' field indicating 'manual' or 'scheduled'.
        
        Ensures manual records are always included, prioritizing them over scheduled records.
        """
        # Get in-memory records (manual triggers and recently scheduled ones)
        in_memory_records = list(self._job_history.values())
        logger.info(f"get_jobs: Found {len(in_memory_records)} in-memory records")
        
        # Get database records (historical scheduled triggers)
        db_records = await self.get_database_job_results()
        logger.info(f"get_jobs: Found {len(db_records)} database records")
        
        # Separate manual and scheduled records
        manual_records = [r for r in in_memory_records if r.get("trigger") == "manual"]
        scheduled_records = [r for r in in_memory_records if r.get("trigger") != "manual"]
        
        logger.info(f"get_jobs: {len(manual_records)} manual, {len(scheduled_records)} scheduled in-memory")
        
        # Merge scheduled records with database records
        # Prefer in-memory scheduled records over database ones
        scheduled_record_ids = {r["id"] for r in scheduled_records}
        for db_record in db_records:
            if db_record["id"] not in scheduled_record_ids:
                scheduled_records.append(db_record)
        
        # Sort scheduled records by created_at descending
        scheduled_records.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        # Sort manual records by created_at descending
        manual_records.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        # Limit to 50 total records, ensuring at least 10 manual records are included
        # If there are fewer than 10 manual records, include all of them
        manual_limit = max(10, len(manual_records))
        scheduled_limit = 50 - min(manual_limit, len(manual_records))
        
        final_manual_records = manual_records[:manual_limit]
        final_scheduled_records = scheduled_records[:scheduled_limit]
        
        # Combine manual and scheduled records, with manual records first
        result = final_manual_records + final_scheduled_records
        
        # Sort final result by created_at descending for display
        result.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        
        logger.info(f"get_jobs: Returning {len(result)} records ({len(final_manual_records)} manual, {len(final_scheduled_records)} scheduled)")
        return result

    async def get_tasks(self) -> list[dict]:
        """Get all registered tasks from the data store."""
        if not self._scheduler:
            return []
        try:
            tasks = await self._scheduler.data_store.get_tasks()
            result = []
            for task in tasks:
                misfire_grace_time = getattr(task, 'misfire_grace_time', None)
                result.append({
                    "id": task.id,
                    "func": getattr(task, 'func', None),
                    "job_executor": getattr(task, 'job_executor', None),
                    "max_running_jobs": getattr(task, 'max_running_jobs', None),
                    "misfire_grace_time": misfire_grace_time.total_seconds() if misfire_grace_time and hasattr(misfire_grace_time, 'total_seconds') else misfire_grace_time,
                    "running_jobs": getattr(task, 'running_jobs', 0),
                })
            return result
        except Exception as e:
            logger.error("Failed to get tasks", extra={"error": str(e)})
            return []

    async def remove_task(self, task_id: str) -> None:
        """Remove a task definition from the data store."""
        if not self._scheduler:
            raise SchedulerError("Scheduler not initialized")
        try:
            await self._scheduler.data_store.remove_task(task_id)
            logger.info("Task removed", extra={"task_id": task_id})
        except Exception as e:
            raise JobNotFoundError(f"Task {task_id} not found") from e

    # === Health Monitoring ===
    
    def _track_failure(self) -> None:
        """Track a job failure for health monitoring."""
        self._failed_job_count += 1
        now = datetime.now(timezone.utc)
        self._recent_failures.append(now)
        
        # Trim old failures to prevent unbounded growth
        cutoff = now - timedelta(hours=24)
        self._recent_failures = [f for f in self._recent_failures if f > cutoff]
        
        # Keep only max_recent_failures
        if len(self._recent_failures) > self._max_recent_failures:
            self._recent_failures = self._recent_failures[-self._max_recent_failures:]
    
    def get_health_status(self) -> dict[str, Any]:
        """Get scheduler health status.
        
        Returns:
            Dict with health metrics:
            - status: "healthy", "degraded", or "unhealthy"
            - running: Whether scheduler is running
            - pending_jobs: Number of pending jobs
            - recent_failures: Count of failures in last hour
            - total_failures: Total failure count since startup
            - history_size: Current job history cache size
            - retry_states: Number of jobs being retried
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        recent_failures_count = sum(1 for f in self._recent_failures if f > one_hour_ago)
        
        # Determine health status
        status = "healthy"
        if not self._running:
            status = "unhealthy"
        elif recent_failures_count > 10:
            status = "unhealthy"
        elif recent_failures_count > 5:
            status = "degraded"
        
        # Count pending jobs
        pending_jobs = len(self._job_history)
        
        return {
            "status": status,
            "running": self._running,
            "pending_jobs": pending_jobs,
            "recent_failures_1h": recent_failures_count,
            "total_failures": self._failed_job_count,
            "history_size": len(self._job_history),
            "retry_states": len(self._retry_states),
            "max_history_limit": self._max_history,
        }
    
    # === Retry Logic ===
    
    async def _handle_job_failure(self, job_id: str, task_id: str, error_message: str | None) -> None:
        """Handle a job failure and schedule retry if needed.
        
        Args:
            job_id: The job ID that failed
            task_id: The task ID
            error_message: Error message from the failure
        """
        # Get or create retry state
        retry_state = self._retry_states.get(job_id)
        if retry_state is None:
            # Try to get retry policy from schedule metadata
            policy = await self._get_retry_policy_for_task(task_id)
            retry_state = RetryState(
                job_id=job_id,
                task_id=task_id,
                policy=policy,
            )
            self._retry_states[job_id] = retry_state
        
        # Increment attempt
        attempt = retry_state.increment_attempt()
        retry_state.last_error = error_message
        
        # Check if we should retry
        # For now, we retry on any exception (can be refined with exception type checking)
        if attempt <= retry_state.policy.max_retries:
            next_retry_time = retry_state.calculate_next_retry()
            delay = retry_state.policy.get_delay(attempt)
            
            logger.info(
                "Scheduling job retry",
                extra={
                    "job_id": job_id,
                    "task_id": task_id,
                    "attempt": attempt,
                    "max_retries": retry_state.policy.max_retries,
                    "delay_seconds": delay,
                    "next_retry_at": next_retry_time.isoformat(),
                }
            )
            
            # Schedule retry using asyncio
            asyncio.create_task(self._schedule_retry(job_id, task_id, delay))
        else:
            # Max retries exceeded - mark as dead letter
            logger.error(
                "Job exceeded max retries, marking as dead letter",
                extra={
                    "job_id": job_id,
                    "task_id": task_id,
                    "attempts": attempt,
                    "max_retries": retry_state.policy.max_retries,
                }
            )
            # Update job history to dead_letter status
            if job_id in self._job_history:
                self._job_history[job_id]["state"] = JobStatus.DEAD_LETTER.value
            
            # Clean up retry state
            del self._retry_states[job_id]
    
    async def _schedule_retry(self, job_id: str, task_id: str, delay: float) -> None:
        """Schedule a job retry after delay.
        
        Args:
            job_id: Original job ID
            task_id: Task ID to retry
            delay: Delay in seconds before retry
        """
        try:
            await asyncio.sleep(delay)
            
            if not self._running or not self._scheduler:
                logger.warning(
                    "Cannot retry job - scheduler not running",
                    extra={"job_id": job_id, "task_id": task_id}
                )
                return
            
            # Update status to retrying
            if job_id in self._job_history:
                self._job_history[job_id]["state"] = JobStatus.RETRYING.value
            
            # Execute the retry
            logger.info(
                "Executing job retry",
                extra={"job_id": job_id, "task_id": task_id, "delay": delay}
            )
            
            # Use run_job_now for retry (this creates a new execution)
            await self.run_job_now(task_id)
            
        except Exception as e:
            logger.error(
                "Failed to execute job retry",
                extra={"job_id": job_id, "task_id": task_id, "error": str(e)}
            )
    
    async def _get_retry_policy_for_task(self, task_id: str) -> RetryPolicy:
        """Get retry policy for a task from schedule metadata.
        
        Args:
            task_id: The task ID
            
        Returns:
            RetryPolicy instance (default if not configured)
        """
        if not self._scheduler:
            return RetryPolicy()  # Return default
        
        try:
            schedules = await self._scheduler.get_schedules()
            for schedule in schedules:
                if schedule.get("task_id") == task_id:
                    metadata = schedule.get("metadata", {})
                    retry_policy_data = metadata.get("retry_policy")
                    if retry_policy_data:
                        # Parse retry policy from metadata
                        return RetryPolicy(**retry_policy_data)
                    break
        except Exception as e:
            logger.debug(
                "Failed to get retry policy for task",
                extra={"task_id": task_id, "error": str(e)}
            )
        
        return RetryPolicy()  # Return default policy
    
    # === Execution Mode Support ===
    
    def set_execution_mode(self, task_id: str, mode: ExecutionMode | str) -> None:
        """Set execution mode for a task.
        
        Args:
            task_id: The task ID
            mode: Execution mode (enum or string)
        """
        config = ExecutionModeConfig.from_mode(mode)
        self._execution_mode_configs[task_id] = config
        logger.info(
            "Set execution mode for task",
            extra={"task_id": task_id, "mode": config.mode.value}
        )
    
    def get_execution_mode(self, task_id: str) -> ExecutionModeConfig:
        """Get execution mode config for a task.
        
        Args:
            task_id: The task ID
            
        Returns:
            ExecutionModeConfig instance (default if not set)
        """
        return self._execution_mode_configs.get(task_id, ExecutionModeConfig())
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def scheduler(self) -> AsyncScheduler | None:
        return self._scheduler


def get_scheduler() -> CronScheduler:
    """Get the singleton scheduler instance."""
    return CronScheduler()