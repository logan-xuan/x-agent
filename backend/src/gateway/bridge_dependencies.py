"""Shared dependency lookups for gateway bridge collaborators."""

from __future__ import annotations

from pathlib import Path

from ..agent_core.skill_dispatcher import (
    SkillCommandResolver,
    SkillInvocation,
    SkillPromptRewriter,
    build_skill_command_specs,
)

try:
    from ..utils.logger import get_logger

    logger = get_logger(__name__)
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


_skill_adapter_cache: dict[str, object | None] = {}
_skill_command_resolver_cache: dict[str, SkillCommandResolver | None] = {}
_skill_prompt_rewriter = SkillPromptRewriter()
_AUTO_DISPATCH_PRIORITY_THRESHOLD = 10


def get_llm_router():
    """获取 LLMRouter 实例。"""
    from ..main import get_llm_router as get_llm_router_fn

    return get_llm_router_fn()


def get_tool_manager():
    """获取 ToolManager 实例（带内置工具）。"""
    from ..tools.builtin import get_builtin_tools
    from ..tools.manager import get_tool_manager as get_tool_manager_fn

    manager = get_tool_manager_fn()
    if len(manager.get_all_tools()) == 0:
        for tool in get_builtin_tools():
            manager.register(tool)
    return manager


def get_session_manager():
    """获取 SessionManager 实例。"""
    from ..conversation.session import SessionManager

    return SessionManager()


def _fallback_workspace_path() -> Path:
    from ..config.manager import ConfigManager

    config = ConfigManager().config
    return Path(config.workspace.path).expanduser().resolve()


def resolve_skill_workspace_path(agent_id: str | None = None) -> Path:
    """Resolve the workspace used for skill discovery.

    Priority:
    1. Explicit agent_id
    2. Current request context agent_id
    3. Global workspace.path from config
    """
    resolved_agent_id = agent_id

    if not resolved_agent_id:
        try:
            from ..conversation.context import get_current_context

            ctx = get_current_context()
            if ctx is not None and getattr(ctx, "agent_id", ""):
                resolved_agent_id = str(ctx.agent_id)
        except Exception:
            resolved_agent_id = None

    if resolved_agent_id:
        try:
            from ..conversation.dao.models import Agent as AgentORM

            agent = AgentORM.from_config(resolved_agent_id)
            workspace = getattr(agent, "workspace", "") if agent is not None else ""
            if workspace:
                return Path(workspace).expanduser().resolve()
        except Exception as exc:
            logger.warning(
                "Failed to resolve agent workspace for skills",
                extra={"agent_id": resolved_agent_id, "error": str(exc)},
            )

    return _fallback_workspace_path()


def get_skill_adapter(agent_id: str | None = None):
    """获取技能适配器实例（按 workspace 缓存）。"""
    workspace_path = resolve_skill_workspace_path(agent_id)
    cache_key = str(workspace_path)

    if cache_key in _skill_adapter_cache:
        return _skill_adapter_cache[cache_key]

    try:
        from ..agent_core.adapters.skill_adapter import create_skill_adapter

        adapter = create_skill_adapter(workspace_path=workspace_path)
        _skill_adapter_cache[cache_key] = adapter
        if adapter:
            logger.info("Skill adapter initialized successfully")
        return adapter
    except Exception as exc:
        logger.warning(
            "Failed to initialize skill adapter",
            extra={"error": str(exc), "workspace_path": str(workspace_path)},
        )
        _skill_adapter_cache[cache_key] = None
        return None


def get_skill_registry(agent_id: str | None = None):
    """Return the skill registry for the resolved workspace."""
    skill_adapter = get_skill_adapter(agent_id)
    if not skill_adapter:
        return None
    return getattr(skill_adapter, "_registry", None)


def get_skill_command_resolver(agent_id: str | None = None) -> SkillCommandResolver | None:
    """获取技能命令解析器实例（按 workspace 缓存）。"""
    workspace_path = resolve_skill_workspace_path(agent_id)
    cache_key = str(workspace_path)

    if cache_key in _skill_command_resolver_cache:
        return _skill_command_resolver_cache[cache_key]

    skill_adapter = get_skill_adapter(agent_id)
    if not skill_adapter:
        return None

    try:
        manifests = skill_adapter._registry.list_skills()
        if not manifests:
            return None

        command_specs = build_skill_command_specs(manifests)
        resolver = SkillCommandResolver(command_specs)
        _skill_command_resolver_cache[cache_key] = resolver

        logger.info(
            "Skill command resolver initialized",
            extra={"command_count": len(command_specs)},
        )
        return resolver
    except Exception as exc:
        logger.warning(
            "Failed to initialize skill command resolver",
            extra={"error": str(exc), "workspace_path": str(workspace_path)},
        )
        _skill_command_resolver_cache[cache_key] = None
        return None


def get_agent_logger():
    """获取共享的 AgentLogger 实例。"""
    from ..agent_core.api.dev_routes import get_logger as get_agent_logger_fn

    return get_agent_logger_fn()


def _load_rewritten_skill_prompt(skill_adapter, invocation: SkillInvocation) -> str:
    """Load skill content and build a forced skill prompt."""
    content = skill_adapter.load_skill_content(invocation.skill_name)
    if not content:
        return ""

    rewritten = _skill_prompt_rewriter.rewrite_simple(invocation)
    return (
        f"\n# 技能指令 (/{invocation.skill_name})\n\n"
        f"⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。\n\n"
        f"以下已经是完整技能说明，不要再次尝试定位其他 `SKILL.md` 文件路径。\n\n"
        f"{content}\n\n---\n\n{rewritten}\n"
    )


def _resolve_auto_dispatch_invocation(
    skill_adapter, user_input: str
) -> tuple[SkillInvocation | None, int | None]:
    """Resolve a high-priority auto-trigger skill for plain-text requests."""
    if user_input.startswith("/"):
        return None, None

    matcher = getattr(skill_adapter, "match_skills_by_intent", None)
    if not callable(matcher):
        return None, None

    manifest = matcher(user_input)
    if manifest is None:
        match_skills = getattr(skill_adapter, "match_skills", None)
        if callable(match_skills):
            candidates = match_skills(user_input, top_k=3, min_score=0.1)
            manifest = next(
                (
                    candidate
                    for candidate in candidates
                    if getattr(candidate, "auto_trigger", False)
                    and not getattr(candidate, "disable_model_invocation", False)
                    and getattr(candidate, "user_invocable", True)
                ),
                None,
            )

    if not manifest:
        return None, None

    if not getattr(manifest, "auto_trigger", False):
        return None, None

    if getattr(manifest, "disable_model_invocation", False):
        return None, None

    if not getattr(manifest, "user_invocable", True):
        return None, None

    priority = int(getattr(manifest, "priority", 999))
    if priority > _AUTO_DISPATCH_PRIORITY_THRESHOLD:
        return None, priority

    return (
        SkillInvocation(
            skill_name=manifest.skill_id,
            command_name=manifest.skill_id,
            args=user_input.strip() or None,
            dispatch_mode="prompt_rewrite",
        ),
        priority,
    )


def match_and_load_skill_prompt(
    user_input: str,
    *,
    agent_id: str | None = None,
) -> tuple[str, SkillInvocation | None]:
    """根据用户输入匹配技能并生成技能指令。"""
    skill_adapter = get_skill_adapter(agent_id)
    if not skill_adapter:
        return "", None

    try:
        auto_invocation, auto_priority = _resolve_auto_dispatch_invocation(skill_adapter, user_input)
        if auto_invocation:
            logger.info(
                "Skill auto-dispatched by intent",
                extra={
                    "skill_name": auto_invocation.skill_name,
                    "priority": auto_priority,
                },
            )
            skill_prompt = _load_rewritten_skill_prompt(skill_adapter, auto_invocation)
            if skill_prompt:
                return skill_prompt, auto_invocation

        if user_input.startswith("/"):
            resolver = get_skill_command_resolver(agent_id)
            if resolver:
                invocation = resolver.resolve(user_input)
                if invocation:
                    logger.info(
                        "Skill command resolved",
                        extra={
                            "skill_name": invocation.skill_name,
                            "command_name": invocation.command_name,
                            "dispatch_mode": invocation.dispatch_mode,
                        },
                    )

                    skill_prompt = _load_rewritten_skill_prompt(skill_adapter, invocation)
                    if skill_prompt:
                        return skill_prompt, invocation

            command = user_input.split()[0][1:]
            content = skill_adapter.load_skill_content(command)
            if content:
                logger.info("Skill matched by direct command", extra={"skill_id": command})
                return (
                    f"\n\n# 技能指令 (/{command})\n\n"
                    f"⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。\n\n"
                    f"{content}"
                ), None

        skills_prompt = skill_adapter.build_skills_xml_prompt()
        if skills_prompt:
            logger.debug(
                "Skills XML prompt generated",
                extra={
                    "user_input": user_input[:50],
                    "prompt_length": len(skills_prompt),
                },
            )
            return f"\n\n{skills_prompt}", None

        return "", None
    except Exception as exc:
        logger.warning("Failed to generate skill prompt", extra={"error": str(exc)})
        return "", None
