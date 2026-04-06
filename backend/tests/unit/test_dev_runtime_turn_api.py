"""Unit tests for the runtime turn developer API endpoint."""

import asyncio
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
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["mode"] == "debug"
    assert metadata["runtime_timeout_ms"] == 30000


def test_dev_runtime_turn_endpoint_accepts_custom_runtime_timeout():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="abort",
                finish_reason="max_wall_time",
                output_text=None,
                metadata={"timeout_ms": 1500},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "runtime_timeout_ms": 1500,
                "metadata": {"mode": "debug"},
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_timeout_ms"] == 1500


def test_dev_runtime_turn_endpoint_accepts_runtime_max_tokens():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "runtime_max_tokens": 48,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_max_tokens"] == 48


def test_dev_runtime_turn_endpoint_accepts_runtime_temperature():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "runtime_temperature": 0.2,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_temperature"] == 0.2


def test_dev_runtime_turn_endpoint_accepts_force_non_streaming():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "runtime_force_non_streaming": True,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_force_non_streaming"] is True


def test_dev_runtime_turn_endpoint_accepts_timeout_fallback_mode():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="max_wall_time",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "timeout_fallback_mode": "final",
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_timeout_fallback_mode"] == "final"


def test_dev_runtime_turn_endpoint_defaults_fast_mode_timeout_fallback_to_final():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="max_wall_time",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "disable_tools": True,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_timeout_fallback_mode"] == "final"


def test_dev_runtime_turn_top_level_flags_override_conflicting_metadata():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "runtime_timeout_ms": 1500,
                "disable_tools": True,
                "disable_skills": True,
                "metadata": {
                    "runtime_timeout_ms": 0,
                    "runtime_disable_tools": False,
                    "runtime_disable_skills": False,
                    "runtime_skip_history_load": False,
                    "persist_user_message": True,
                },
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_timeout_ms"] == 1500
    assert metadata["runtime_disable_tools"] is True
    assert metadata["runtime_disable_skills"] is True
    assert metadata["runtime_skip_history_load"] is True
    assert metadata["persist_user_message"] is False


def test_dev_runtime_turn_endpoint_can_disable_tools():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "disable_tools": True,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_disable_tools"] is True
    assert metadata["runtime_disable_skills"] is True
    assert metadata["runtime_skip_history_load"] is True
    assert metadata["persist_user_message"] is False


def test_dev_runtime_turn_endpoint_can_disable_skills():
    client = TestClient(app)

    with patch("src.api.v1.dev.GatewayDispatcher") as mock_dispatcher_cls:
        dispatcher = mock_dispatcher_cls.return_value
        dispatcher.execute_runtime_turn = AsyncMock(
            return_value=TurnResult(
                kind="final",
                finish_reason="done_definition_satisfied",
                output_text="runtime-ok",
                metadata={},
            )
        )

        response = client.post(
            "/api/v1/dev/runtime-turn",
            json={
                "content": "hello runtime",
                "session_id": "dev-session",
                "channel_type": "web_chat",
                "channel_protocol": "rest_api",
                "disable_skills": True,
            },
        )

    assert response.status_code == 200
    metadata = dispatcher.execute_runtime_turn.await_args.kwargs["metadata"]
    assert metadata["runtime_disable_skills"] is True


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


def test_dev_llm_stream_probe_endpoint_reports_timings():
    client = TestClient(app)

    class FakeRouter:
        async def chat(self, messages, stream=False, max_tokens=None, temperature=None):
            assert stream is True
            assert max_tokens == 32
            assert temperature is None
            assert messages[-1]["content"] == "probe"

            async def _stream():
                yield type("Chunk", (), {"content": "hello", "is_finished": False})()
                yield type("Chunk", (), {"content": " world", "is_finished": True})()

            return _stream()

    with patch("src.api.v1.dev._get_shared_llm_router", return_value=FakeRouter()):
        response = client.post(
            "/api/v1/dev/llm-stream-probe",
            json={
                "content": "probe",
                "max_tokens": 32,
                "timeout_ms": 1000,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["timed_out"] is False
    assert data["chunk_count"] == 2
    assert data["content_preview"] == "hello world"
    assert data["first_chunk_ms"] is not None
    assert data["done_ms"] is not None
    assert data["samples"] and len(data["samples"]) == 1


def test_dev_llm_stream_probe_endpoint_handles_timeout():
    client = TestClient(app)

    class FakeRouter:
        async def chat(self, messages, stream=False, max_tokens=None, temperature=None):
            _ = messages
            _ = stream
            _ = max_tokens
            _ = temperature

            async def _stream():
                await asyncio.sleep(0.05)
                yield type("Chunk", (), {"content": "late", "is_finished": False})()

            return _stream()

    with patch("src.api.v1.dev._get_shared_llm_router", return_value=FakeRouter()):
        response = client.post(
            "/api/v1/dev/llm-stream-probe",
            json={
                "content": "probe",
                "timeout_ms": 1,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["timed_out"] is True
    assert data["first_chunk_ms"] is None
    assert data["chunk_count"] == 0


def test_dev_llm_stream_probe_endpoint_supports_multiple_attempts():
    client = TestClient(app)

    class FakeRouter:
        async def chat(self, messages, stream=False, max_tokens=None, temperature=None):
            _ = messages
            _ = stream
            _ = max_tokens
            _ = temperature

            async def _stream():
                yield type("Chunk", (), {"content": "ok", "is_finished": True})()

            return _stream()

    with patch("src.api.v1.dev._get_shared_llm_router", return_value=FakeRouter()):
        response = client.post(
            "/api/v1/dev/llm-stream-probe",
            json={
                "content": "probe",
                "attempts": 2,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["attempts"] == 2
    assert len(data["samples"]) == 2


def test_dev_llm_stream_probe_endpoint_reports_override_errors():
    client = TestClient(app)

    with patch("src.api.v1.dev._probe_with_base_url_override", side_effect=RuntimeError("boom")):
        response = client.post(
            "/api/v1/dev/llm-stream-probe",
            json={
                "content": "probe",
                "base_url_override": "https://example.com/v1",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] == "RuntimeError: boom"
    assert data["samples"][0]["error"] == "RuntimeError: boom"
