"""Unit tests for the runtime turn developer API endpoint."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.runtime.types import TurnResult


def test_dev_runtime_turn_endpoint_returns_runtime_result():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={"turn_index": 0},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "metadata": {"mode": "debug"},
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "dev-session"
    assert data["kind"] == "final"
    assert data["finish_reason"] == "done_definition_satisfied"
    assert data["output_text"] == "runtime-ok"
    assert data["metadata"]["turn_index"] == 0


def test_dev_runtime_turn_endpoint_rejects_invalid_channel_type():
    client = TestClient(app)

    response = client.post(
        "/api/v1/dev/runtime-turn",
        json={
            "content": "hello runtime",
            "session_id": "dev-session",
            "channel_type": "invalid-channel",
            "channel_protocol": "rest_api",
        },
    )

    assert response.status_code == 400
    assert "Unsupported channel_type" in response.json()["detail"]
