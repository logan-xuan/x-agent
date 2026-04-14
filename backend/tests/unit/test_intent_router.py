"""Unit tests for the runtime intent routing engine."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.skill.manifest_parser import ManifestParser


def test_manifest_parser_preserves_routing_frontmatter(tmp_path: Path):
    skill_dir = tmp_path / "imagegen"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: imagegen
description: 根据用户自然语言描述调用内置生图工具生成图片，并返回可访问地址
allowed_tools:
  - generate_image
routing:
  mode: deterministic
  priority: 100
  matcher: text_to_image_request
  action:
    type: force_tool_plan
    tool_name: generate_image
    args:
      prompt: $user_input
---
""",
        encoding="utf-8",
    )

    manifest = ManifestParser().parse(skill_dir)

    assert manifest.routing is not None
    assert manifest.routing["matcher"] == "text_to_image_request"
    assert manifest.routing["action"]["tool_name"] == "generate_image"


def test_imagegen_skill_declares_routing_policy():
    skill_dir = Path(__file__).resolve().parents[2] / "src" / "skills" / "imagegen"
    manifest = ManifestParser().parse(skill_dir)

    assert manifest.routing is not None
    assert manifest.routing["matcher"] == "text_to_image_request"
    assert manifest.routing["action"]["tool_name"] == "generate_image"


def test_intent_router_builds_generate_image_decision_from_skill_policy():
    from src.runtime.routing.intent_router import IntentRouter

    skill_manifest = SimpleNamespace(
        skill_id="imagegen",
        routing={
            "mode": "deterministic",
            "priority": 100,
            "matcher": "text_to_image_request",
            "action": {
                "type": "force_tool_plan",
                "tool_name": "generate_image",
                "args": {"prompt": "$user_input"},
            },
        },
    )
    skill_registry = SimpleNamespace(list_skills=lambda source=None: [skill_manifest])
    router = IntentRouter(skill_registry=skill_registry)

    decision = router.decide(
        user_input="生成一只戴眼镜的白色猫咪",
        available_tool_names={"generate_image", "web_search"},
        turn_index=0,
        metadata={},
    )

    assert decision is not None
    assert decision.policy_id == "skill:imagegen"
    assert decision.tool_plan is not None
    assert len(decision.tool_plan.calls) == 1
    assert decision.tool_plan.calls[0].tool_name == "generate_image"
    assert decision.tool_plan.calls[0].arguments == {"prompt": "生成一只戴眼镜的白色猫咪"}


def test_intent_router_builds_delegate_decision_from_builtin_policy():
    from src.runtime.routing.intent_router import IntentRouter

    skill_registry = SimpleNamespace(list_skills=lambda source=None: [])
    router = IntentRouter(
        skill_registry=skill_registry,
        agent_catalog_provider=lambda: [
            SimpleNamespace(agent_id="main-agent", agent_name="主助手"),
            SimpleNamespace(agent_id="research-agent", agent_name="研究分析员"),
        ],
    )

    decision = router.decide(
        user_input="让研究分析员查询今天上海的天气，只需一句话回复。",
        available_tool_names={"delegate_task", "web_search"},
        turn_index=0,
        metadata={"current_agent_id": "main-agent"},
    )

    assert decision is not None
    assert decision.policy_id == "builtin:delegate-explicit"
    assert decision.tool_plan is not None
    assert len(decision.tool_plan.calls) == 1
    assert decision.tool_plan.calls[0].tool_name == "delegate_task"
    assert decision.tool_plan.calls[0].arguments == {
        "agent_id": "research-agent",
        "task": "查询今天上海的天气，只需一句话回复。",
    }


def test_intent_router_allows_registering_custom_matcher():
    from src.runtime.routing.intent_router import IntentRouter

    skill_registry = SimpleNamespace(list_skills=lambda source=None: [])
    router = IntentRouter(
        skill_registry=skill_registry,
        builtin_policies=[
            {
                "policy_id": "builtin:test-custom",
                "mode": "deterministic",
                "priority": 10,
                "matcher": "custom_ping",
                "required_tools": ["notify"],
                "action": {
                    "type": "force_tool_plan",
                    "tool_name": "notify",
                    "args": {"content": "$match.content"},
                },
            }
        ],
    )
    router.register_matcher(
        "custom_ping",
        lambda user_input, metadata: {"content": "pong"} if user_input == "ping" else None,
    )

    decision = router.decide(
        user_input="ping",
        available_tool_names={"notify"},
        turn_index=0,
        metadata={},
    )

    assert decision is not None
    assert decision.policy_id == "builtin:test-custom"
    assert decision.tool_plan is not None
    assert decision.tool_plan.calls[0].arguments == {"content": "pong"}


@pytest.mark.parametrize(
    ("user_input", "available_tool_names"),
    [
        ("生成一个 cron 表达式，每5分钟执行一次", {"generate_image", "run_in_terminal"}),
        ("帮我写个总结", {"generate_image"}),
    ],
)
def test_intent_router_returns_none_for_non_deterministic_requests(
    user_input: str,
    available_tool_names: set[str],
):
    from src.runtime.routing.intent_router import IntentRouter

    skill_manifest = SimpleNamespace(
        skill_id="imagegen",
        routing={
            "mode": "deterministic",
            "priority": 100,
            "matcher": "text_to_image_request",
            "action": {
                "type": "force_tool_plan",
                "tool_name": "generate_image",
                "args": {"prompt": "$user_input"},
            },
        },
    )
    skill_registry = SimpleNamespace(list_skills=lambda source=None: [skill_manifest])
    router = IntentRouter(skill_registry=skill_registry)

    decision = router.decide(
        user_input=user_input,
        available_tool_names=available_tool_names,
        turn_index=0,
        metadata={},
    )

    assert decision is None
