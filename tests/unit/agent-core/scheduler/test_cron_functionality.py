import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.agent_core.scheduler.cron_scheduler import CronScheduler, ScheduledTask, TaskStatus
from src.agent_core.scheduler.execution_engine import ExecutionEngine


@pytest.mark.asyncio
async def test_cron_scheduler_initialization():
    """Test initializing the cron scheduler"""

    scheduler = CronScheduler()

    # Initially should have no tasks
    assert len(scheduler.get_all_tasks()) == 0
    assert not scheduler._running


@pytest.mark.asyncio
async def test_add_and_remove_task():
    """Test adding and removing tasks from scheduler"""

    scheduler = CronScheduler()

    # Define a simple async task function
    async def sample_task(param1="default"):
        return f"Task executed with param: {param1}"

    # Add a task
    task_id = scheduler.add_task(
        name="Sample Task",
        schedule="@hourly",
        task_function=sample_task,
        params={"param1": "test_value"}
    )

    # Verify task was added
    assert task_id is not None
    assert len(scheduler.get_all_tasks()) == 1

    task = scheduler.get_task(task_id)
    assert task is not None
    assert task.name == "Sample Task"
    assert task.schedule == "@hourly"

    # Remove the task
    removed = scheduler.remove_task(task_id)
    assert removed is True
    assert len(scheduler.get_all_tasks()) == 0

    # Try to remove non-existent task
    removed_again = scheduler.remove_task(task_id)
    assert removed_again is False


@pytest.mark.asyncio
async def test_task_execution():
    """Test executing a scheduled task"""

    async def simple_task(return_value="success"):
        return return_value

    # Create a scheduled task
    task = ScheduledTask(
        id="test-task-123",
        name="Test Task",
        schedule="@daily",
        task_function=simple_task,
        params={"return_value": "execution successful"},
        created_at=datetime.now()
    )

    # Create execution engine
    engine = ExecutionEngine()

    # Execute the task
    success = await engine.execute_task(task)

    # Verify execution was successful
    assert success is True
    assert task.last_run_status == TaskStatus.COMPLETED
    assert task.retry_count == 0

    engine.shutdown()


@pytest.mark.asyncio
async def test_execution_engine_error_handling():
    """Test error handling in execution engine"""

    async def failing_task():
        raise Exception("Simulated task failure")

    # Create a scheduled task that will fail
    task = ScheduledTask(
        id="failing-task-123",
        name="Failing Task",
        schedule="@daily",
        task_function=failing_task,
        params={},
        created_at=datetime.now()
    )

    # Create execution engine
    engine = ExecutionEngine()

    # Execute the task (should fail)
    success = await engine.execute_task(task)

    # Verify error was handled correctly
    assert success is False
    assert task.last_run_status == TaskStatus.FAILED
    assert task.retry_count == 1  # Should increment retry count

    engine.shutdown()


@pytest.mark.asyncio
async def test_calculate_next_run():
    """Test calculating next run times for different schedules"""

    scheduler = CronScheduler()

    # Test @hourly schedule
    next_hourly = scheduler._calculate_next_run("@hourly")
    expected_hourly = datetime.now() + timedelta(hours=1)
    assert abs((next_hourly - expected_hourly).total_seconds()) < 60  # Within 1 minute tolerance

    # Test @daily schedule
    next_daily = scheduler._calculate_next_run("@daily")
    now = datetime.now()
    expected_daily = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    assert abs((next_daily - expected_daily).total_seconds()) < 60  # Within 1 minute tolerance

    # Test @weekly schedule
    next_weekly = scheduler._calculate_next_run("@weekly")
    expected_weekly = datetime.now() + timedelta(weeks=1)
    assert abs((next_weekly - expected_weekly).total_seconds()) < 60  # Within 1 minute tolerance


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    """Test starting and stopping the scheduler"""

    scheduler = CronScheduler()

    # Start the scheduler
    await scheduler.start()
    assert scheduler._running is True

    # Give it a moment to start
    await asyncio.sleep(0.1)

    # Stop the scheduler
    await scheduler.stop()
    assert scheduler._running is False


@pytest.mark.asyncio
async def test_pause_resume_task():
    """Test pausing and resuming a scheduled task"""

    scheduler = CronScheduler()

    # Add a task
    async def sample_task():
        return "executed"

    task_id = scheduler.add_task(
        name="Pausable Task",
        schedule="@hourly",
        task_function=sample_task,
        params={}
    )

    # Verify task exists
    task = scheduler.get_task(task_id)
    assert task is not None

    # Pause the task
    paused = scheduler.pause_task(task_id)
    assert paused is True

    # Resume the task
    resumed = scheduler.resume_task(task_id)
    assert resumed is True


@pytest.mark.asyncio
async def test_scheduler_with_multiple_tasks():
    """Test scheduler with multiple concurrent tasks"""

    scheduler = CronScheduler()

    # Define sample tasks
    async def task1():
        return "task1_result"

    async def task2():
        return "task2_result"

    async def task3():
        return "task3_result"

    # Add multiple tasks
    task_ids = []
    task_ids.append(scheduler.add_task("Task 1", "@hourly", task1, {}))
    task_ids.append(scheduler.add_task("Task 2", "@daily", task2, {}))
    task_ids.append(scheduler.add_task("Task 3", "@weekly", task3, {}))

    # Verify all tasks were added
    all_tasks = scheduler.get_all_tasks()
    assert len(all_tasks) == 3

    # Verify each task exists individually
    for task_id in task_ids:
        task = scheduler.get_task(task_id)
        assert task is not None
        assert task.name.startswith("Task ")

    # Clean up
    for task_id in task_ids:
        scheduler.remove_task(task_id)

    # Verify all tasks were removed
    assert len(scheduler.get_all_tasks()) == 0


@pytest.mark.asyncio
async def test_task_retry_mechanism():
    """Test the task retry mechanism"""

    execution_count = 0

    async def flaky_task():
        nonlocal execution_count
        execution_count += 1

        if execution_count < 3:
            raise Exception("Simulated intermittent failure")
        return "finally successful"

    task = ScheduledTask(
        id="flaky-task-123",
        name="Flaky Task",
        schedule="@daily",
        task_function=flaky_task,
        params={},
        created_at=datetime.now(),
        max_retries=5
    )

    # Execute the task with retries
    engine = ExecutionEngine()

    # First execution should fail and increment retry count
    success = await engine.execute_task(task)
    assert success is False
    assert task.retry_count == 1

    # Second execution should also fail
    success = await engine.execute_task(task)
    assert success is False
    assert task.retry_count == 2

    # Third execution should succeed (since the flaky_task succeeds after 3 attempts)
    success = await engine.execute_task(task)
    assert success is True
    assert task.last_run_status == TaskStatus.COMPLETED
    assert task.retry_count == 0  # Should reset after success

    engine.shutdown()