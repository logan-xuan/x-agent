"""Deterministic intent routing for high-confidence runtime requests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..types import ToolCallSpec, ToolExecutionPlan


@dataclass
class RouteDecision:
    """Normalized deterministic routing outcome."""

    policy_id: str
    tool_plan: ToolExecutionPlan | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class IntentRouter:
    """Resolve deterministic tool plans before handing control to the LLM."""

    def __init__(
        self,
        *,
        skill_registry: Any,
        agent_catalog_provider: Any | None = None,
        builtin_policies: list[dict[str, Any]] | None = None,
    ) -> None:
        self._skill_registry = skill_registry
        self._agent_catalog_provider = agent_catalog_provider or (lambda: [])
        self._builtin_policies = builtin_policies or self._default_builtin_policies()
        self._matchers: dict[str, Any] = {
            "text_to_image_request": lambda user_input, metadata: self._match_text_to_image_request(
                user_input
            ),
            "explicit_delegate_request": lambda user_input, metadata: self._match_explicit_delegate_request(
                user_input,
                current_agent_id=str(metadata.get("current_agent_id", "")),
            ),
        }

    def register_matcher(self, name: str, matcher: Any) -> None:
        """Register a custom matcher for deterministic routing."""
        self._matchers[name] = matcher

    def decide(
        self,
        *,
        user_input: str,
        available_tool_names: set[str],
        turn_index: int,
        metadata: dict[str, Any],
    ) -> RouteDecision | None:
        """Return a deterministic route when one policy clearly applies."""
        policies = [*self._builtin_policies, *self._skill_policies()]
        policies.sort(key=lambda policy: int(policy.get("priority", 999)))

        context = {
            "user_input": (user_input or "").strip(),
            "available_tool_names": set(available_tool_names),
            "turn_index": turn_index,
            "metadata": dict(metadata),
        }
        for policy in policies:
            decision = self._evaluate_policy(policy, context)
            if decision is not None:
                return decision
        return None

    def _skill_policies(self) -> list[dict[str, Any]]:
        skills = self._skill_registry.list_skills() if self._skill_registry is not None else []
        policies: list[dict[str, Any]] = []
        for manifest in skills:
            routing = getattr(manifest, "routing", None)
            if not isinstance(routing, dict):
                continue
            policy = dict(routing)
            policy.setdefault("policy_id", f"skill:{manifest.skill_id}")
            policy.setdefault("priority", getattr(manifest, "priority", 999))
            policies.append(policy)
        return policies

    def _default_builtin_policies(self) -> list[dict[str, Any]]:
        return [
            {
                "policy_id": "builtin:delegate-explicit",
                "mode": "deterministic",
                "priority": 50,
                "matcher": "explicit_delegate_request",
                "required_tools": ["delegate_task"],
                "first_turn_only": True,
                "disallow_resume": True,
                "action": {
                    "type": "force_tool_plan",
                    "tool_name": "delegate_task",
                    "args": {
                        "agent_id": "$match.agent_id",
                        "task": "$match.task",
                    },
                },
            }
        ]

    def _evaluate_policy(
        self,
        policy: dict[str, Any],
        context: dict[str, Any],
    ) -> RouteDecision | None:
        if policy.get("mode") not in {None, "deterministic"}:
            return None
        if policy.get("first_turn_only") and context["turn_index"] != 0:
            return None
        if policy.get("disallow_resume") and context["metadata"].get("runtime_resume_from_child"):
            return None

        required_tools = set(policy.get("required_tools") or self._derive_required_tools(policy))
        if required_tools and not required_tools.issubset(context["available_tool_names"]):
            return None

        match = self._run_matcher(str(policy.get("matcher") or ""), context)
        if match is None:
            return None

        action = policy.get("action") or {}
        if action.get("type") != "force_tool_plan":
            return None

        tool_name = str(action.get("tool_name") or "").strip()
        if not tool_name:
            return None
        arguments = self._resolve_arg_templates(action.get("args") or {}, context, match)
        return RouteDecision(
            policy_id=str(policy.get("policy_id") or "unknown"),
            tool_plan=ToolExecutionPlan(
                calls=[ToolCallSpec(tool_name=tool_name, arguments=arguments)]
            ),
            reason=str(match.get("reason") or ""),
            metadata={
                "policy": dict(policy),
                "match": dict(match),
            },
        )

    def _derive_required_tools(self, policy: dict[str, Any]) -> list[str]:
        action = policy.get("action") or {}
        tool_name = action.get("tool_name")
        return [tool_name] if isinstance(tool_name, str) and tool_name else []

    def _run_matcher(
        self,
        matcher_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        matcher = self._matchers.get(matcher_name)
        if matcher is None:
            return None
        return matcher(context["user_input"], context["metadata"])

    def _resolve_arg_templates(
        self,
        args: dict[str, Any],
        context: dict[str, Any],
        match: dict[str, Any],
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for key, value in args.items():
            resolved[key] = self._resolve_template_value(value, context, match)
        return resolved

    def _resolve_template_value(
        self,
        value: Any,
        context: dict[str, Any],
        match: dict[str, Any],
    ) -> Any:
        if isinstance(value, str):
            if value == "$user_input":
                return context["user_input"]
            if value.startswith("$match."):
                return match.get(value.removeprefix("$match."))
            return value
        if isinstance(value, list):
            return [self._resolve_template_value(item, context, match) for item in value]
        if isinstance(value, dict):
            return {
                key: self._resolve_template_value(item, context, match)
                for key, item in value.items()
            }
        return value

    def _match_text_to_image_request(self, user_input: str) -> dict[str, Any] | None:
        text = (user_input or "").strip()
        if not text:
            return None

        normalized = re.sub(r"\s+", " ", text)
        lower_text = normalized.lower()

        unsupported_edit_markers = (
            "图生图",
            "重绘",
            "局部重绘",
            "编辑图片",
            "修改图片",
            "改图",
            "抠图",
            "去背景",
            "image to image",
            "inpaint",
            "outpaint",
        )
        if any(marker in lower_text for marker in unsupported_edit_markers):
            return None

        explicit_visual_pattern = re.compile(
            r"(生成|画|绘制|做|创建|出)(一张|一个|个|张)?"
            r"(图|图片|海报|插画|配图|封面图|封面|头像|壁纸|艺术照)"
        )
        explicit_english_pattern = re.compile(
            r"\b(generate|create|draw|make)\b.*\b"
            r"(image|picture|poster|illustration|artwork|cover|avatar|wallpaper)\b"
        )
        if explicit_visual_pattern.search(normalized) or explicit_english_pattern.search(lower_text):
            return {"reason": "explicit image noun pattern"}

        leading_generation_pattern = re.compile(
            r"^(?:请)?(?:帮我|给我|替我)?(?:生成|画|绘制|做|创建|来一张|来个|画个)(?:\s|$|一|个|张)"
        )
        leading_english_generation_pattern = re.compile(
            r"^(?:please\s+)?(?:generate|draw|create|make)\b"
        )
        non_image_artifact_markers = (
            "代码",
            "脚本",
            "命令",
            "sql",
            "json",
            "yaml",
            "markdown",
            "md",
            "文档",
            "文章",
            "文案",
            "故事",
            "笑话",
            "总结",
            "摘要",
            "方案",
            "计划",
            "任务",
            "ppt",
            "pdf",
            "表格",
            "excel",
            "cron",
            "表达式",
            "链接",
            "url",
            "uuid",
            "id",
            "接口",
            "回复",
        )
        if (
            leading_generation_pattern.search(normalized)
            or leading_english_generation_pattern.search(lower_text)
        ) and not any(marker in lower_text for marker in non_image_artifact_markers):
            return {"reason": "leading generation verb pattern"}
        return None

    def _match_explicit_delegate_request(
        self,
        user_input: str,
        *,
        current_agent_id: str,
    ) -> dict[str, Any] | None:
        text = (user_input or "").strip()
        if not text or "让" not in text:
            return None

        agents = list(self._agent_catalog_provider() or [])
        if not agents:
            return None

        alias_to_agent_id: dict[str, str] = {}
        for agent in agents:
            agent_id = str(getattr(agent, "agent_id", "") or "").strip()
            agent_name = str(getattr(agent, "agent_name", "") or "").strip()
            if not agent_id:
                continue
            alias_to_agent_id[agent_id.lower()] = agent_id
            if agent_name:
                alias_to_agent_id[agent_name.lower()] = agent_id

        ordered_aliases = sorted(alias_to_agent_id.keys(), key=len, reverse=True)
        lower_text = text.lower()
        for alias in ordered_aliases:
            if alias == current_agent_id.lower():
                continue
            needle = f"让{alias}"
            index = lower_text.find(needle)
            if index < 0:
                continue
            remaining = text[index + len(needle) :]
            remaining = re.sub(r"^(帮我|帮忙|去|来|给我)?", "", remaining).strip(" ，,")
            if not remaining:
                continue
            return {
                "reason": "explicit delegate pattern",
                "agent_id": alias_to_agent_id[alias],
                "task": remaining,
            }
        return None


__all__ = ["IntentRouter", "RouteDecision"]
