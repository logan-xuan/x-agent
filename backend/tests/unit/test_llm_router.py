"""Unit tests for LLMRouter provider health probe behavior."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.services.llm.circuit_breaker import circuit_breaker_manager
from src.services.llm.router import LLMRouter
from src.services.llm.provider import LLMResponse, StreamingLLMResponse


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
                    is_finished=index == len((self.chunks or ["hello", " world"])) - 1,
                    model=self.model_id,
                )

        return _stream()


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
