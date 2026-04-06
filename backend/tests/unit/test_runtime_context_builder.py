"""Unit tests for the runtime context builder skeleton."""

import pytest

from src.runtime.context import DefaultContextBuilder
from src.runtime.types import ArtifactRef, BudgetSnapshot, RouteMeta, SessionDescriptor, TaskFrame, TurnBudgetProfile
from src.runtime.context.builder import ContextBuildRequest


@pytest.mark.asyncio
async def test_context_builder_supports_full_minimal_and_none_modes():
    builder = DefaultContextBuilder()
    session = SessionDescriptor(session_key="s1", session_id="s1")
    task_frame = TaskFrame(
        objective="Summarize the task",
        unresolved=["find sources"],
        constraints=["be concise"],
    )
    request = ContextBuildRequest(
        session=session,
        task_frame=task_frame,
        raw_messages=[
            {"role": "system", "content": "legacy system"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
        metadata={
            "stable_prefix": "Stable prefix",
            "semi_stable_sections": ["Workspace summary", "Tool index"],
            "artifact_refs": [
                ArtifactRef(id="artifact:1", kind="tool", title="A", preview="P"),
            ],
            "budget": BudgetSnapshot.from_profile(TurnBudgetProfile(), profile_name="default"),
            "summary_chain": [{"role": "system", "content": "[summary]"}],
        },
    )

    full_result = await builder.build(request)
    minimal_result = await builder.build(ContextBuildRequest(**{**request.__dict__, "prompt_mode": "minimal"}))
    none_result = await builder.build(ContextBuildRequest(**{**request.__dict__, "prompt_mode": "none"}))

    assert "Stable prefix" in full_result.system_prompt
    assert "Workspace summary" in full_result.system_prompt
    assert "Objective: Summarize the task" in full_result.system_prompt
    assert "Workspace summary" not in minimal_result.system_prompt
    assert none_result.system_prompt == ""
    assert full_result.active_messages[0]["role"] == "system"


@pytest.mark.asyncio
async def test_context_builder_uses_active_history_not_full_raw_transcript():
    builder = DefaultContextBuilder()
    session = SessionDescriptor(session_key="s1", session_id="s1")
    raw_messages = [{"role": "user", "content": f"m{i}"} for i in range(20)]

    result = await builder.build(
        ContextBuildRequest(
            session=session,
            task_frame=TaskFrame(objective="Task"),
            raw_messages=raw_messages,
            metadata={"summary_chain": [{"role": "system", "content": "[summary]"}]},
        )
    )

    assert len(result.active_messages) < len(raw_messages)
    assert result.active_messages[0]["content"] == "[summary]"
