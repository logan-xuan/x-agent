"""Unit tests for LLMRouter provider health probe behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytest

from src.agent_core.adapters.llm_adapter import XAgentLLMAdapter
from src.services.llm.circuit_breaker import CircuitState, circuit_breaker_manager
from src.services.llm.provider import LLMResponse, StreamingLLMResponse
from src.services.llm.router import LLMRouter


@dataclass
class FakeProvider:
    """Minimal provider stub for router behavior tests."""

    name: str = "fake-primary"
    model_id: str = "fake-model"
    health_result: bool = True
    chat_content: str = "ok"

    def __post_init__(self) -> None:
        self.health_calls = 0
        self.chat_calls = 0

    async def health_check(self) -> bool:
        self.health_calls += 1
        return self.health_result

    async def chat(self, messages, stream=False, **kwargs):
        self.chat_calls += 1
        _ = messages
        _ = stream
        _ = kwargs
        return LLMResponse(content=self.chat_content, model=self.model_id)


@dataclass
class FakeStreamingProvider(FakeProvider):
    chunks: list[str] | None = None

    async def chat(self, messages, stream=False, **kwargs):
        self.chat_calls += 1
        _ = messages
        _ = kwargs
        if not stream:
            return await super().chat(messages, stream=stream, **kwargs)

        async def _stream():
            for index, chunk in enumerate(self.chunks or ["hello", " world"]):
                yield StreamingLLMResponse(
                    content=chunk,
                    is_finished=index == len(self.chunks or ["hello", " world"]) - 1,
                    model=self.model_id,
                )

        return _stream()


@dataclass
class RaisingProvider(FakeProvider):
    error: Exception = RuntimeError("boom")

    async def chat(self, messages, stream=False, **kwargs):
        self.chat_calls += 1
        _ = messages
        _ = stream
        _ = kwargs
        raise self.error


@pytest.mark.asyncio
async def test_llm_router_chat_does_not_probe_provider_health():
    router = LLMRouter(model_configs=[])
    provider = FakeProvider()
    router._primary = provider
    router._backups = []
    router._providers = {provider.name: provider}
    router._provider_health_ttl_seconds = 30.0

    first = await router.chat([{"role": "user", "content": "hello"}], stream=False)
    second = await router.chat([{"role": "user", "content": "again"}], stream=False)

    assert first.content == "ok"
    assert second.content == "ok"
    assert provider.health_calls == 0
    assert provider.chat_calls == 2


@pytest.mark.asyncio
async def test_llm_router_forces_fresh_health_probe_for_explicit_health_check():
    router = LLMRouter(model_configs=[])
    provider = FakeProvider()
    router._primary = provider
    router._backups = []
    router._providers = {provider.name: provider}
    router._provider_health_ttl_seconds = 30.0

    await router.chat([{"role": "user", "content": "hello"}], stream=False)
    results = await router.health_check()

    assert results == {provider.name: True}
    assert provider.health_calls == 1


@pytest.mark.asyncio
async def test_llm_router_skips_provider_when_recent_failed_health_is_cached():
    router = LLMRouter(model_configs=[])
    provider = FakeProvider(chat_content="should-not-run")
    router._primary = provider
    router._backups = []
    router._providers = {provider.name: provider}
    router._provider_health_ttl_seconds = 30.0
    router._provider_health_cache[provider.name] = (__import__("time").monotonic(), False)
    breaker = circuit_breaker_manager.get_breaker(provider.name)
    breaker.reset()

    with pytest.raises(RuntimeError, match="All providers failed"):
        await router.chat([{"role": "user", "content": "hello"}], stream=False)

    assert provider.health_calls == 0
    assert provider.chat_calls == 0
    assert breaker.stats.failed_requests == 0


@pytest.mark.asyncio
async def test_llm_router_records_streaming_success_only_after_consumption():
    router = LLMRouter(model_configs=[])
    provider = FakeStreamingProvider()
    router._primary = provider
    router._backups = []
    router._providers = {provider.name: provider}
    breaker = circuit_breaker_manager.get_breaker(provider.name)
    breaker.reset()

    stream = await router.chat([{"role": "user", "content": "hello"}], stream=True)

    assert breaker.stats.successful_requests == 0
    assert router._recent_provider_health(provider.name) is None

    chunks = [chunk async for chunk in stream]

    assert "".join(chunk.content for chunk in chunks) == "hello world"
    assert breaker.stats.successful_requests == 1
    assert router._recent_provider_health(provider.name) is True


@pytest.mark.asyncio
async def test_llm_adapter_force_non_streaming_uses_non_streaming_chat():
    class FakeRouter:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def chat(self, messages, stream=False, **kwargs):
            self.calls.append({"messages": messages, "stream": stream, **kwargs})
            return LLMResponse(content="fast", model="fake-model", finish_reason="stop")

    router = FakeRouter()
    adapter = XAgentLLMAdapter(router, force_non_streaming=True)

    chunks = [
        chunk async for chunk in adapter.stream(
            system_prompt="",
            messages=[{"role": "user", "content": "hi"}],
        )
    ]

    assert router.calls and router.calls[0]["stream"] is False
    assert chunks[0].type.value == "text_delta"
    assert chunks[0].delta == "fast"
    assert chunks[1].type.value == "done"


@pytest.mark.asyncio
async def test_llm_router_consumes_preferred_provider_without_forwarding_it():
    router = LLMRouter(model_configs=[])
    primary = FakeProvider(name="primary", chat_content="primary")
    backup = FakeProvider(name="backup", chat_content="backup")
    router._primary = primary
    router._backups = [backup]
    router._providers = {primary.name: primary, backup.name: backup}

    result = await router.chat(
        [{"role": "user", "content": "hello"}],
        stream=False,
        preferred_provider="backup",
    )

    assert result.content == "backup"
    assert primary.chat_calls == 0
    assert backup.chat_calls == 1


@pytest.mark.asyncio
async def test_llm_router_streaming_returns_best_effort_done_when_provider_breaks_after_content():
    router = LLMRouter(model_configs=[])

    @dataclass
    class BrokenStreamingProvider(FakeProvider):
        async def chat(self, messages, stream=False, **kwargs):
            self.chat_calls += 1
            _ = messages
            _ = kwargs
            if not stream:
                return await super().chat(messages, stream=stream, **kwargs)

            async def _stream():
                yield StreamingLLMResponse(content="partial", is_finished=False, model=self.model_id)
                raise RuntimeError("incomplete chunked read")

            return _stream()

    provider = BrokenStreamingProvider()
    router._primary = provider
    router._backups = []
    router._providers = {provider.name: provider}

    stream = await router.chat([{"role": "user", "content": "hello"}], stream=True)
    chunks = [chunk async for chunk in stream]

    assert [chunk.content for chunk in chunks] == ["partial", ""]
    assert chunks[-1].is_finished is True


@pytest.mark.asyncio
async def test_llm_router_logs_structured_reason_when_falling_back_to_backup(monkeypatch):
    router = LLMRouter(model_configs=[])
    primary = RaisingProvider(
        name="primary",
        error=RuntimeError(
            "Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly'}}"
        ),
    )
    backup = FakeProvider(name="backup-bailian", chat_content="backup-ok")
    router._primary = primary
    router._backups = [backup]
    router._providers = {primary.name: primary, backup.name: backup}

    warning_calls: list[tuple[str, dict]] = []
    info_calls: list[tuple[str, dict]] = []

    class FakeLogger:
        def warning(self, message, *, extra=None):
            warning_calls.append((message, extra or {}))

        def info(self, message, *, extra=None):
            info_calls.append((message, extra or {}))

    monkeypatch.setattr("src.services.llm.router.logger", FakeLogger())

    result = await router.chat([{"role": "user", "content": "hello"}], stream=False)

    assert result.content == "backup-ok"
    assert any(
        message == "Provider failed, falling back to next provider"
        and extra["provider_name"] == "primary"
        and extra["next_provider_name"] == "backup-bailian"
        and extra["fallback_reason"] == "allocation_quota_free_tier_only"
        and extra["fallback_trigger"] == "provider_exception"
        and extra["original_primary_provider_name"] == "primary"
        for message, extra in warning_calls
    )
    assert any(
        message == "Provider routing plan created"
        and extra["original_primary_provider_name"] == "primary"
        and extra["provider_attempt_order"] == ["primary", "backup-bailian"]
        and extra["preferred_provider_name"] is None
        for message, extra in info_calls
    )
    assert any(
        message == "Successfully used provider"
        and extra["provider_name"] == "backup-bailian"
        and extra["original_primary_provider_name"] == "primary"
        and extra["fallback_used"] is True
        and extra["fallback_from_provider_name"] == "primary"
        and extra["provider_attempt_index"] == 2
        for message, extra in info_calls
    )


@pytest.mark.asyncio
async def test_llm_router_emits_dedicated_llm_fallback_event(monkeypatch):
    router = LLMRouter(model_configs=[])
    primary = RaisingProvider(
        name="primary",
        error=RuntimeError(
            "Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly'}}"
        ),
    )
    backup = FakeProvider(name="backup-bailian", chat_content="backup-ok")
    router._primary = primary
    router._backups = [backup]
    router._providers = {primary.name: primary, backup.name: backup}

    emitted_events: list[dict] = []

    class FakeFallbackEventLogger:
        def log_event(self, **payload):
            emitted_events.append(payload)

    monkeypatch.setattr(
        "src.services.llm.router.get_llm_fallback_event_logger",
        lambda: FakeFallbackEventLogger(),
        raising=False,
    )

    result = await router.chat([{"role": "user", "content": "hello"}], stream=False)

    assert result.content == "backup-ok"
    assert emitted_events == [
        {
            "session_id": None,
            "original_primary_provider_name": "primary",
            "failed_provider_name": "primary",
            "next_provider_name": "backup-bailian",
            "provider_attempt_order": ["primary", "backup-bailian"],
            "provider_attempt_index": 1,
            "fallback_trigger": "provider_exception",
            "fallback_reason": "allocation_quota_free_tier_only",
            "error_code": "AllocationQuota.FreeTierOnly",
            "status_code": None,
            "request_id": None,
            "error_type": "RuntimeError",
            "error": "Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly'}}",
        }
    ]


@pytest.mark.asyncio
async def test_llm_router_emits_fallback_event_when_circuit_breaker_skips_provider(monkeypatch):
    router = LLMRouter(model_configs=[])
    primary = FakeProvider(name="primary", chat_content="primary-should-not-run")
    backup = FakeProvider(name="backup-bailian", chat_content="backup-ok")
    router._primary = primary
    router._backups = [backup]
    router._providers = {primary.name: primary, backup.name: backup}

    breaker = circuit_breaker_manager.get_breaker(primary.name)
    breaker.reset()
    breaker._state = CircuitState.OPEN
    breaker._stats.state_changed_at = datetime.utcnow()

    emitted_events: list[dict] = []

    class FakeFallbackEventLogger:
        def log_event(self, **payload):
            emitted_events.append(payload)

    monkeypatch.setattr(
        "src.services.llm.router.get_llm_fallback_event_logger",
        lambda: FakeFallbackEventLogger(),
        raising=False,
    )

    result = await router.chat([{"role": "user", "content": "hello"}], stream=False)

    assert result.content == "backup-ok"
    assert emitted_events == [
        {
            "session_id": None,
            "original_primary_provider_name": "primary",
            "failed_provider_name": "primary",
            "next_provider_name": "backup-bailian",
            "provider_attempt_order": ["primary", "backup-bailian"],
            "provider_attempt_index": 1,
            "fallback_trigger": "circuit_breaker_open",
            "fallback_reason": "circuit_breaker_open",
            "error_code": None,
            "status_code": None,
            "request_id": None,
            "error_type": "CircuitBreakerOpen",
            "error": "Circuit breaker open",
        }
    ]


@pytest.mark.asyncio
async def test_llm_router_emits_fallback_event_when_recent_health_probe_failed(monkeypatch):
    router = LLMRouter(model_configs=[])
    primary = FakeProvider(name="primary", chat_content="primary-should-not-run")
    backup = FakeProvider(name="backup-bailian", chat_content="backup-ok")
    router._primary = primary
    router._backups = [backup]
    router._providers = {primary.name: primary, backup.name: backup}
    breaker = circuit_breaker_manager.get_breaker(primary.name)
    breaker.reset()
    router._provider_health_cache[primary.name] = (__import__("time").monotonic(), False)

    emitted_events: list[dict] = []

    class FakeFallbackEventLogger:
        def log_event(self, **payload):
            emitted_events.append(payload)

    monkeypatch.setattr(
        "src.services.llm.router.get_llm_fallback_event_logger",
        lambda: FakeFallbackEventLogger(),
        raising=False,
    )

    result = await router.chat([{"role": "user", "content": "hello"}], stream=False)

    assert result.content == "backup-ok"
    assert emitted_events == [
        {
            "session_id": None,
            "original_primary_provider_name": "primary",
            "failed_provider_name": "primary",
            "next_provider_name": "backup-bailian",
            "provider_attempt_order": ["primary", "backup-bailian"],
            "provider_attempt_index": 1,
            "fallback_trigger": "recent_failed_health_probe",
            "fallback_reason": "recent_failed_health_probe",
            "error_code": None,
            "status_code": None,
            "request_id": None,
            "error_type": "RecentFailedHealthProbe",
            "error": "Recent failed health probe cached for provider",
        }
    ]
