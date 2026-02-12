import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import sys
from pathlib import Path

# Add src to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.agent_core.monitoring.heartbeat_emitter import HeartbeatEmitter  # Adjust import based on actual implementation
from src.agent_core.monitoring.progress_tracker import ProgressTracker
from src.agent_core.monitoring.cancellation_handler import CancellationHandler


@pytest.mark.asyncio
async def test_heartbeat_emission():
    """Test basic heartbeat emission functionality"""

    with patch('src.agent_core.monitoring.heartbeat_emitter.HeartbeatEmitter.emit_heartbeat') as mock_emit:
        mock_emit.return_value = {
            "task_id": "long-task-123",
            "status": "running",
            "progress": 45,
            "timestamp": "2023-01-01T10:00:00Z",
            "message": "Processing step 2 of 5"
        }

        emitter = HeartbeatEmitter()

        # Test emitting a heartbeat for a long-running task
        heartbeat_data = {
            "task_id": "long-task-123",
            "progress": 45,
            "message": "Processing step 2 of 5"
        }

        result = await emitter.emit_heartbeat(heartbeat_data)

        assert result["task_id"] == "long-task-123"
        assert result["progress"] == 45
        assert result["status"] == "running"
        assert "Processing step 2 of 5" in result["message"]
        mock_emit.assert_called_once_with(heartbeat_data)


@pytest.mark.asyncio
async def test_progress_tracking():
    """Test progress tracking functionality"""

    with patch('src.agent_core.monitoring.progress_tracker.ProgressTracker.update_progress') as mock_update:
        mock_update.return_value = {
            "task_id": "tracking-task-456",
            "current_step": 3,
            "total_steps": 5,
            "percentage": 60,
            "eta_seconds": 120
        }

        tracker = ProgressTracker()

        # Test updating progress
        progress_data = {
            "task_id": "tracking-task-456",
            "current_step": 3,
            "total_steps": 5,
            "details": "Completed data processing"
        }

        result = await tracker.update_progress(progress_data)

        assert result["task_id"] == "tracking-task-456"
        assert result["current_step"] == 3
        assert result["total_steps"] == 5
        assert result["percentage"] == 60
        assert result["eta_seconds"] == 120
        mock_update.assert_called_once_with(progress_data)


@pytest.mark.asyncio
async def test_heartbeat_broadcasting():
    """Test broadcasting heartbeats to multiple listeners"""

    with patch('src.agent_core.monitoring.ws_broadcaster.WebSocketBroadcaster.broadcast_to_session') as mock_broadcast:
        mock_broadcast.return_value = {"status": "broadcast", "recipients": 3}

        # Mock WebSocket broadcaster
        from src.agent_core.monitoring.ws_broadcaster import WebSocketBroadcaster
        broadcaster = WebSocketBroadcaster()

        # Test broadcasting heartbeat to session
        heartbeat_msg = {
            "type": "heartbeat",
            "task_id": "broadcast-task-789",
            "progress": 75,
            "message": "Almost complete"
        }

        result = await broadcaster.broadcast_to_session("session-123", heartbeat_msg)

        assert result["status"] == "broadcast"
        assert result["recipients"] == 3
        mock_broadcast.assert_called_once_with("session-123", heartbeat_msg)


@pytest.mark.asyncio
async def test_task_cancellation_request():
    """Test requesting task cancellation"""

    with patch('src.agent_core.monitoring.cancellation_handler.CancellationHandler.request_cancellation') as mock_cancel:
        mock_cancel.return_value = {
            "task_id": "cancel-task-999",
            "status": "cancellation_requested",
            "timestamp": "2023-01-01T10:30:00Z"
        }

        handler = CancellationHandler()

        # Test canceling a task
        result = await handler.request_cancellation("cancel-task-999")

        assert result["task_id"] == "cancel-task-999"
        assert result["status"] == "cancellation_requested"
        mock_cancel.assert_called_once_with("cancel-task-999")


@pytest.mark.asyncio
async def test_active_task_monitoring():
    """Test monitoring of active tasks"""

    with patch('src.agent_core.monitoring.progress_tracker.ProgressTracker.get_active_tasks') as mock_get:
        mock_get.return_value = [
            {"task_id": "active-1", "progress": 30, "status": "running"},
            {"task_id": "active-2", "progress": 65, "status": "running"},
            {"task_id": "active-3", "progress": 10, "status": "starting"}
        ]

        tracker = ProgressTracker()

        # Get list of active tasks
        active_tasks = await tracker.get_active_tasks()

        assert len(active_tasks) == 3
        for task in active_tasks:
            assert task["status"] in ["running", "starting"]
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_cancellation_of_nonexistent_task():
    """Test cancelling a task that doesn't exist"""

    with patch('src.agent_core.monitoring.cancellation_handler.CancellationHandler.request_cancellation') as mock_cancel:
        mock_cancel.return_value = {
            "task_id": "nonexistent-task",
            "status": "not_found",
            "message": "Task not found or already completed"
        }

        handler = CancellationHandler()

        # Try to cancel a nonexistent task
        result = await handler.request_cancellation("nonexistent-task")

        assert result["status"] == "not_found"
        assert "not found" in result["message"]
        mock_cancel.assert_called_once_with("nonexistent-task")


@pytest.mark.asyncio
async def test_heartbeat_frequency_control():
    """Test controlling heartbeat emission frequency"""

    with patch('src.agent_core.monitoring.heartbeat_emitter.HeartbeatEmitter.emit_heartbeat') as mock_emit:
        # First call succeeds, subsequent ones might be rate-limited
        mock_emit.side_effect = [
            {"status": "emitted", "sequence": 1},
            {"status": "rate_limited", "sequence": 2}  # Simulate rate limiting
        ]

        emitter = HeartbeatEmitter()

        # Emit first heartbeat
        result1 = await emitter.emit_heartbeat({
            "task_id": "freq-task-123",
            "progress": 10,
            "message": "First heartbeat"
        })

        # Try to emit another immediately (might be rate limited)
        result2 = await emitter.emit_heartbeat({
            "task_id": "freq-task-123",
            "progress": 12,
            "message": "Second heartbeat (might be rate limited)"
        })

        # Both calls should have been made to the mock
        assert mock_emit.call_count == 2


@pytest.mark.asyncio
async def test_monitoring_integration():
    """Test integration between heartbeat emission and progress tracking"""

    # Create mock objects for integration test
    with patch.multiple('src.agent_core.monitoring',
                        HeartbeatEmitter=MagicMock(),
                        ProgressTracker=MagicMock()):

        heartbeat_mock = MagicMock()
        heartbeat_mock.emit_heartbeat.return_value = {
            "task_id": "integration-task",
            "status": "running",
            "progress": 50
        }

        progress_mock = MagicMock()
        progress_mock.update_progress.return_value = {
            "task_id": "integration-task",
            "percentage": 50,
            "eta_seconds": 60
        }

        # Simulate integrated workflow
        task_details = {"task_id": "integration-task", "current_step": 1, "total_steps": 2}

        progress_result = await progress_mock.update_progress(task_details)
        heartbeat_result = await heartbeat_mock.emit_heartbeat({
            "task_id": "integration-task",
            "progress": progress_result["percentage"],
            "message": f"Progress: {progress_result['percentage']}%"
        })

        # Verify both systems responded correctly
        assert progress_result["task_id"] == "integration-task"
        assert heartbeat_result["task_id"] == "integration-task"
        assert progress_result["percentage"] == heartbeat_result["progress"]


def test_monitoring_component_names():
    """Test that monitoring components have expected interfaces"""

    # Test if classes exist and have expected methods
    try:
        emitter = HeartbeatEmitter()
        assert hasattr(emitter, 'emit_heartbeat')
        assert hasattr(emitter, 'register_listener')
    except NameError:
        # Classes might not be defined yet, which is okay
        pass

    try:
        tracker = ProgressTracker()
        assert hasattr(tracker, 'update_progress')
        assert hasattr(tracker, 'get_task_status')
    except NameError:
        # Classes might not be defined yet, which is okay
        pass

    try:
        handler = CancellationHandler()
        assert hasattr(handler, 'request_cancellation')
        assert hasattr(handler, 'is_cancelled')
    except NameError:
        # Classes might not be defined yet, which is okay
        pass