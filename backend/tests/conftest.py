"""Global test fixtures for backend test isolation."""

import pytest
from sqlalchemy import delete

from src.agent_core.api.dev_routes import get_logger as get_agent_logger
from src.conversation.context import clear_current_context
from src.models.runtime import RuntimeRecord
from src.runtime import reset_runtime_services
from src.services.storage import get_storage_service


@pytest.fixture(autouse=True)
async def _reset_runtime_state():
    """Reset shared runtime singletons and persisted runtime records between tests."""
    reset_runtime_services()
    clear_current_context()
    get_agent_logger().clear()

    storage = get_storage_service()
    await storage.initialize()
    async with storage.session() as db:
        await db.execute(delete(RuntimeRecord))

    yield

    reset_runtime_services()
    clear_current_context()
    get_agent_logger().clear()
    async with storage.session() as db:
        await db.execute(delete(RuntimeRecord))
