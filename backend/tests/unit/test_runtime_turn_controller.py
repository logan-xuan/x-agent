"""Unit tests for the runtime turn controller skeleton."""

from src.runtime.turn.assessment import DefaultAssessmentEngine
from src.runtime.turn.controller import DefaultTurnController
from src.runtime.turn.state import TurnState
from src.runtime.turn.tool_governor import DefaultToolGovernor
from src.runtime.types import (
    BudgetDecision,
    CompactResult,
    GovernedToolPlan,
    LoopAssessment,
    RouteMeta,
    SessionDescriptor,
    SpawnPacket,
    TaskFrame,
    ToolCallSpec,
    ToolExecutionPlan,
    ToolExecutionResult,
    ToolPolicy,
    TurnRequest,
)


def _request(metadata: dict | None = None) -> TurnRequest:
    return TurnRequest(
        session=SessionDescriptor(session_key="session-1", session_id="session-1"),
        user_input="执行任务",
        task_frame=TaskFrame(objective="执行任务", unresolved=["step-1"]),
        route=RouteMeta(channel="test"),
        metadata=metadata or {},
    )


async def _planner_with_tool(state: TurnState) -> ToolExecutionPlan:
    _ = state
    return ToolExecutionPlan(calls=[ToolCallSpec(tool_name="web_search", arguments={"q": "runtime"})])


async def _executor(plan: ToolExecutionPlan, state: TurnState) -> list[ToolExecutionResult]:
    _ = state
    return [
        ToolExecutionResult(
            tool_name=call.tool_name,
            success=True,
            output="found evidence",
        )
        for call in plan.calls
    ]


def test_turn_controller_returns_spawn_packet_when_assessment_requests_spawn():
    controller = DefaultTurnController(
        planner=_planner_with_tool,
        executor=_executor,
    )
    packet = SpawnPacket(objective="子任务", deliverable="调研摘要")

    result = __import__("asyncio").run(controller.run(_request({"spawn_packet": packet})))

    assert result.kind == "spawn"
    assert result.spawn_packet == packet


def test_turn_controller_finishes_on_no_op_turn():
    controller = DefaultTurnController(max_no_op_turns=2)

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.finish_reason == "diminishing_returns"
    assert result.metadata["turn_index"] == 1


def test_turn_controller_finishes_after_successful_assessment():
    class FinishingAssessment(DefaultAssessmentEngine):
        def assess(self, state: TurnState) -> LoopAssessment:
            assessment = super().assess(state)
            assessment.controller_decision = "finish"
            assessment.finish_reason = "done_definition_satisfied"
            state.request.task_frame.unresolved.clear()
            state.request.task_frame.done_definition = ["deliver"]
            return assessment

    controller = DefaultTurnController(
        assessment_engine=FinishingAssessment(),
        tool_governor=DefaultToolGovernor(),
        planner=_planner_with_tool,
        executor=_executor,
    )

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.finish_reason == "done_definition_satisfied"
    assert result.output_text == "found evidence"


def test_turn_controller_passes_governed_plan_to_executor():
    observed: dict[str, object] = {}

    async def executor(plan: GovernedToolPlan, state: TurnState) -> list[ToolExecutionResult]:
        observed["max_parallelism"] = plan.max_parallelism
        observed["rejected_calls"] = len(plan.rejected_calls)
        _ = state
        return []

    class SinglePassAssessment(DefaultAssessmentEngine):
        def assess(self, state: TurnState) -> LoopAssessment:
            return LoopAssessment(
                turn=state.turn_index,
                unresolved_count=0,
                novelty_score=1.0,
                repeated_pattern_score=0.0,
                controller_decision="finish",
                finish_reason="done_definition_satisfied",
            )

    controller = DefaultTurnController(
        assessment_engine=SinglePassAssessment(),
        tool_governor=DefaultToolGovernor(),
        planner=_planner_with_tool,
        executor=executor,
        max_no_op_turns=2,
    )

    __import__("asyncio").run(controller.run(_request()))

    assert observed["max_parallelism"] == 1
    assert observed["rejected_calls"] == 0


def test_turn_controller_budget_stop_uses_best_effort_summary_not_raw_last_tool_payload():
    controller = DefaultTurnController()
    state = TurnState.from_request(_request())
    state.tool_results.extend(
        [
            ToolExecutionResult(
                tool_name="web_search",
                success=True,
                output="first useful evidence about market trends",
            ),
            ToolExecutionResult(
                tool_name="fetch_web_content",
                success=False,
                error="redirect error from source site",
            ),
        ]
    )

    result = controller._finish_from_budget(
        state,
        BudgetDecision.stop("token budget exhausted", "max_tokens"),
    )

    assert result.output_text is not None
    assert "最佳努力结果" in result.output_text
    assert "web_search" in result.output_text
    assert "fetch_web_content" in result.output_text


def test_turn_controller_injects_generate_image_markdown_into_final_output():
    controller = DefaultTurnController()
    state = TurnState.from_request(_request())
    state.metadata["final_output_text"] = "图片已经生成好了，点击链接查看。"
    state.metadata["runtime_route_decision"] = {
        "policy_id": "skill:imagegen",
        "policy": {
            "postconditions": {
                "require_successful_tool": "generate_image",
            }
        },
    }
    state.tool_results.append(
        ToolExecutionResult(
            tool_name="generate_image",
            success=True,
            output="tool output",
            metadata={
                "assets": [
                    {
                        "public_url": "http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-11/img_demo.png"
                    }
                ]
            },
        )
    )

    output = controller._resolve_output_text(state)

    assert output is not None
    assert output.startswith(
        "![生成图片](http://localhost:8888/api/v1/assets/generated-images/main-agent/2026-04-11/img_demo.png)"
    )
    assert "图片已经生成好了" in output


def test_turn_controller_blocks_unverified_output_when_route_postcondition_fails():
    controller = DefaultTurnController()
    state = TurnState.from_request(_request())
    state.metadata["final_output_text"] = "已生成 1 张图片，点击查看。"
    state.metadata["runtime_route_decision"] = {
        "policy_id": "skill:imagegen",
        "policy": {
            "postconditions": {
                "require_successful_tool": "generate_image",
            }
        },
    }
    state.tool_results.append(
        ToolExecutionResult(
            tool_name="generate_image",
            success=False,
            error="provider timeout",
        )
    )

    output = controller._resolve_output_text(state)

    assert output == "未完成可验证的结果输出：deterministic route 要求工具 `generate_image` 成功执行。"
    assert state.metadata["output_contract_violation"] == (
        "deterministic route 要求工具 `generate_image` 成功执行。"
    )




def test_turn_controller_requests_synthesis_when_all_planned_search_calls_are_rejected():
    observed: dict[str, object] = {}

    async def planner(state: TurnState) -> ToolExecutionPlan:
        instruction = state.metadata.get("runtime_synthesis_instruction")
        if instruction:
            observed["synthesis_instruction"] = instruction
            state.metadata["final_output_text"] = "synthesized from retained evidence"
            state.metadata["final_candidate_ready"] = True
            return ToolExecutionPlan()
        return ToolExecutionPlan(
            calls=[ToolCallSpec(tool_name="web_search", arguments={"q": "runtime redesign"})]
        )

    async def executor(plan: GovernedToolPlan, state: TurnState) -> list[ToolExecutionResult]:
        observed.setdefault("executed_calls", []).append([call.tool_name for call in plan.calls])
        _ = state
        return []

    controller = DefaultTurnController(
        planner=planner,
        executor=executor,
        tool_governor=DefaultToolGovernor(
            policies_by_name={
                "web_search": ToolPolicy(max_uses_per_turn=0),
            }
        ),
    )

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.output_text == "synthesized from retained evidence"
    assert observed["executed_calls"] == [[], []]
    assert "web_search" in str(observed["synthesis_instruction"])
    assert "直接完成综合分析" in str(observed["synthesis_instruction"])



def test_turn_controller_compact_path_consumes_explicit_compact_result():
    async def planner(state: TurnState) -> ToolExecutionPlan:
        _ = state
        return ToolExecutionPlan()

    async def compact_fn(state: TurnState, reason: str) -> CompactResult:
        assert reason == "assessment_compact"
        _ = state
        return CompactResult(
            active_messages=[{"role": "system", "content": "[Collapsed history] compacted runtime snapshot"}],
            active_artifact_refs=[],
            output_text="compacted runtime snapshot",
            task_frame=TaskFrame(objective="执行任务", unresolved=["step-2"]),
            metadata={"compaction_source": "pipeline"},
        )

    class CompactThenFinishAssessment(DefaultAssessmentEngine):
        def assess(self, state: TurnState) -> LoopAssessment:
            if not state.metadata.get("compaction_source"):
                return LoopAssessment(
                    turn=state.turn_index,
                    unresolved_count=1,
                    novelty_score=0.0,
                    repeated_pattern_score=1.0,
                    controller_decision="compact",
                )
            state.metadata["final_candidate_ready"] = True
            return LoopAssessment(
                turn=state.turn_index,
                unresolved_count=0,
                novelty_score=1.0,
                repeated_pattern_score=0.0,
                controller_decision="finish",
                finish_reason="done_definition_satisfied",
            )

    controller = DefaultTurnController(
        planner=planner,
        compact_fn=compact_fn,
        assessment_engine=CompactThenFinishAssessment(),
    )

    result = __import__("asyncio").run(controller.run(_request()))

    assert result.kind == "final"
    assert result.output_text == "compacted runtime snapshot"
    assert result.updated_task_frame.unresolved == ["step-2"]
    assert result.metadata["turn_index"] == 1
    assert result.metadata["compaction_source"] == "pipeline"
    assert result.artifact_refs == []


def test_turn_controller_metadata_includes_runtime_compression_keys():
    controller = DefaultTurnController()
    state = TurnState.from_request(_request())
    state.metadata.update(
        {
            "budget_state": {"pressure_level": "orange"},
            "verifier_result": {"ok": True, "reasons": []},
            "rollback_applied": False,
            "rollback_reason": None,
            "compression_operations": ["collapse"],
            "runtime_context_summary": "collapse",
        }
    )

    metadata = controller._metadata(state)

    assert metadata["budget_state"]["pressure_level"] == "orange"
    assert metadata["verifier_result"]["ok"] is True
    assert metadata["rollback_applied"] is False
    assert metadata["rollback_reason"] is None
    assert metadata["compression_operations"] == ["collapse"]
    assert metadata["runtime_context_summary"] == "collapse"


def test_turn_controller_metadata_exposes_runtime_model_budget_from_request_metadata():
    controller = DefaultTurnController()
    state = TurnState.from_request(
        _request(
            {
                "_runtime_model_budget_hints": {
                    "max_context_tokens": 200000,
                    "discounted_context_window": 114800,
                    "reserved_output_tokens": 24000,
                }
            }
        )
    )

    metadata = controller._metadata(state)

    assert metadata["runtime_model_budget"]["max_context_tokens"] == 200000
    assert metadata["runtime_model_budget"]["discounted_context_window"] == 114800
