"""Agent Core WebSocket 端点.

提供 /ws/agent/{session_id} 端点，桥接 WebSocket 与 agent_core.Agent。

消息协议:
- 客户端发送: {"content": "用户消息"} 或 {"type": "abort"}
- 服务端发送: 
  - {"type": "chunk", "content": delta}
  - {"type": "thinking", "content": delta}
  - {"type": "message", "content": text, "model": model, "is_finished": true}
  - {"type": "tool_call", "tool_call_id": id, "name": name, "arguments": args}
  - {"type": "tool_result", "tool_call_id": id, "result": result, "is_error": bool}
  - {"type": "error", "message": error_message}
  - {"type": "pong"} (心跳响应)

技能调度模式 (OpenClaw 风格):
- 显式命令 (/skill_name): 直接加载 SKILL.md 并注入
- 意图匹配: 注入 XML 技能列表，让 LLM 自己选择
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .converters import convert_event_to_websocket
from .dev_routes import get_logger as get_agent_logger
from ..agent import Agent
from ..config import AgentCoreConfig
from ..adapters.llm_adapter import XAgentLLMAdapter
from ..adapters.tool_adapter import XAgentToolAdapter
from ..types import AgentEndEvent, UserMessage, AssistantMessage
from ..skill_dispatcher import (
    SkillCommandResolver,
    SkillPromptRewriter,
    SkillCommandSpec,
    SkillInvocation,
    build_skill_command_specs,
)

# 导入日志
try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


router = APIRouter()

# 全局技能适配器缓存
_skill_adapter_cache = None
# 全局命令解析器缓存
_skill_command_resolver_cache: Optional[SkillCommandResolver] = None
# 全局 Prompt 重写器
_skill_prompt_rewriter = SkillPromptRewriter()


def _get_llm_router():
    """获取 LLMRouter 实例."""
    from ...main import get_llm_router
    return get_llm_router()


def _get_tool_manager():
    """获取 ToolManager 实例（带内置工具）."""
    from ...tools.manager import get_tool_manager
    from ...tools.builtin import get_builtin_tools
    
    manager = get_tool_manager()
    
    # 如果没有工具，注册内置工具
    if len(manager.get_all_tools()) == 0:
        for tool in get_builtin_tools():
            manager.register(tool)
    
    return manager


def _get_session_manager():
    """获取 SessionManager 实例."""
    from ...core.session import SessionManager
    return SessionManager()


def _get_skill_adapter():
    """获取技能适配器实例（带缓存）."""
    global _skill_adapter_cache
    
    if _skill_adapter_cache is not None:
        return _skill_adapter_cache
    
    try:
        from ..adapters.skill_adapter import create_skill_adapter
        _skill_adapter_cache = create_skill_adapter()
        if _skill_adapter_cache:
            logger.info("Skill adapter initialized successfully")
        return _skill_adapter_cache
    except Exception as e:
        logger.warning(
            "Failed to initialize skill adapter",
            extra={"error": str(e)}
        )
        return None


def _get_skill_command_resolver() -> Optional[SkillCommandResolver]:
    """获取技能命令解析器实例（带缓存）.
    
    从技能注册表构建命令规格，创建解析器。
    
    Returns:
        SkillCommandResolver 或 None
    """
    global _skill_command_resolver_cache
    
    if _skill_command_resolver_cache is not None:
        return _skill_command_resolver_cache
    
    skill_adapter = _get_skill_adapter()
    if not skill_adapter:
        return None
    
    try:
        # 获取所有技能清单
        manifests = skill_adapter._registry.list_skills()
        if not manifests:
            return None
        
        # 构建命令规格
        command_specs = build_skill_command_specs(manifests)
        
        # 创建解析器
        _skill_command_resolver_cache = SkillCommandResolver(command_specs)
        
        logger.info(
            "Skill command resolver initialized",
            extra={"command_count": len(command_specs)}
        )
        
        return _skill_command_resolver_cache
    
    except Exception as e:
        logger.warning(
            "Failed to initialize skill command resolver",
            extra={"error": str(e)}
        )
        return None


def create_agent_config() -> AgentCoreConfig:
    """创建 Agent 配置.
    
    注入 LLM 和 Tool 适配器，并加载系统提示词。
    使用共享的 AgentLogger 以便 REST API 可以查询日志。
    
    Returns:
        AgentCoreConfig 实例
    """
    llm_router = _get_llm_router()
    tool_manager = _get_tool_manager()
    
    llm_adapter = XAgentLLMAdapter(llm_router)
    tool_adapter = XAgentToolAdapter(tool_manager)
    
    # 获取共享的 AgentLogger（与 REST API 共享）
    agent_logger = get_agent_logger()
    
    # 加载系统提示词
    system_prompt = _load_system_prompt()
    
    return AgentCoreConfig(
        llm=llm_adapter,
        tools=tool_adapter,
        logger=agent_logger,
        system_prompt=system_prompt,
    )


def _load_identity(workspace_path: str):
    """加载 IDENTITY.md.
    
    Args:
        workspace_path: workspace 路径
    
    Returns:
        IdentityConfig 或 None
    """
    from ...memory.models import IdentityConfig
    from pathlib import Path
    import re
    
    identity_path = Path(workspace_path) / "IDENTITY.md"
    
    if not identity_path.exists():
        logger.debug("IDENTITY.md not found")
        return None
    
    try:
        content = identity_path.read_text(encoding="utf-8")
        
        config = IdentityConfig()
        
        # Parse name
        name_match = re.search(r"\*\*Name:\*\*\s*(.+)", content)
        if name_match:
            config.name = name_match.group(1).strip()
        
        # Parse form/creature
        form_match = re.search(r"\*\*Creature:\*\*\s*(.+)", content)
        if form_match:
            config.form = form_match.group(1).strip()
        
        # Parse style/vibe
        style_match = re.search(r"\*\*Vibe:\*\*\s*(.+)", content)
        if style_match:
            config.style = style_match.group(1).strip()
        
        # Parse emoji
        emoji_match = re.search(r"\*\*Emoji:\*\*\s*(.+)", content)
        if emoji_match:
            config.emoji = emoji_match.group(1).strip()
        
        config.file_path = str(identity_path)
        
        logger.debug(
            "IDENTITY.md loaded",
            extra={"name": config.name, "form": config.form}
        )
        
        return config
        
    except Exception as e:
        logger.warning(
            "Failed to load IDENTITY.md",
            extra={"error": str(e)}
        )
        return None


def _load_system_prompt() -> str:
    """加载系统提示词.
    
    从 workspace 的 SPIRIT.md、OWNER.md 和 IDENTITY.md 构建系统提示词。
    如果文件不存在，使用默认的中文提示词。
    
    Returns:
        系统提示词
    """
    try:
        from ...memory.spirit_loader import SpiritLoader
        from ...memory.models import IdentityConfig
        from ...config.manager import ConfigManager
        from pathlib import Path
        import re
        
        # 获取 workspace 路径并展开 ~
        config = ConfigManager().config
        workspace_path = config.workspace.path if config.workspace else "workspace"
        workspace_path = str(Path(workspace_path).expanduser())
        
        # 直接创建新实例以避免缓存问题
        spirit_loader = SpiritLoader(workspace_path)
        
        # 加载 SPIRIT.md
        spirit = spirit_loader.load_spirit()
        # 加载 OWNER.md
        owner = spirit_loader.load_owner()
        # 加载 IDENTITY.md
        identity = _load_identity(workspace_path)
        
        prompt_parts = []
        
        # 添加 IDENTITY 内容（AI 身份）
        if identity and (identity.name or identity.form or identity.style):
            prompt_parts.append("# 你的身份")
            if identity.name:
                prompt_parts.append(f"- 名字: {identity.name}")
            if identity.form:
                prompt_parts.append(f"- 形态: {identity.form}")
            if identity.style:
                prompt_parts.append(f"- 风格: {identity.style}")
            if identity.emoji:
                prompt_parts.append(f"- 标志: {identity.emoji}")
        
        # 添加 SPIRIT 内容
        if spirit:
            prompt_parts.append(f"# 你的角色\n{spirit.role}")
            if spirit.personality:
                prompt_parts.append(f"\n# 你的性格\n{spirit.personality}")
            if spirit.values:
                prompt_parts.append(f"\n# 你的价值观\n" + "\n".join(f"- {v}" for v in spirit.values))
            if spirit.behavior_rules:
                prompt_parts.append(f"\n# 行为规则\n" + "\n".join(f"- {r}" for r in spirit.behavior_rules))
        
        # 添加 OWNER 内容
        if owner:
            prompt_parts.append(f"\n# 用户信息\n- 名字: {owner.name}")
            if owner.occupation:
                prompt_parts.append(f"- 职业: {owner.occupation}")
            if owner.interests:
                prompt_parts.append(f"- 兴趣: {', '.join(owner.interests)}")
        
        # 添加当前时间
        from datetime import datetime
        now = datetime.now()
        time_str = now.strftime("%Y年%m月%d日 %A %H:%M")
        # 将英文星期转换为中文
        weekdays = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三", 
                    "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六", "Sunday": "星期日"}
        for en, zh in weekdays.items():
            time_str = time_str.replace(en, zh)
        prompt_parts.append(f"\n# 当前时间\n{time_str}")
        
        # 如果有内容，添加语言要求
        if prompt_parts:
            prompt_parts.append("\n# 重要\n- 请使用中文回复用户")
            return "\n".join(prompt_parts)
    
    except Exception as e:
        logger.warning(
            "Failed to load system prompt from workspace",
            extra={"error": str(e)}
        )
    
    # 默认系统提示词
    return """你是一个专注、高效的 AI 助手。

# 行为规则
- 使用中文回复用户
- 简洁明了地回答问题
- 需要时可以使用工具获取信息
- 如果不确定，坦诚告知用户"""


def _match_and_load_skill_prompt(user_input: str) -> tuple[str, Optional[SkillInvocation]]:
    """根据用户输入匹配技能并生成技能指令 (OpenClaw 风格).
    
    三种模式:
    1. 显式命令 (/skill_name args): 使用命令解析器，Prompt Rewrite 调度
    2. 显式命令 (Tool Dispatch): 直接返回调用信息 (暂未实现)
    3. 意图匹配: 注入 XML 技能列表，让 LLM 自己选择
    
    Args:
        user_input: 用户输入内容
    
    Returns:
        (技能指令 prompt, 技能调用信息 或 None)
    """
    skill_adapter = _get_skill_adapter()
    if not skill_adapter:
        return "", None
    
    try:
        # 模式 1: 显式命令解析 (/skill_name args)
        if user_input.startswith("/"):
            resolver = _get_skill_command_resolver()
            if resolver:
                invocation = resolver.resolve(user_input)
                if invocation:
                    logger.info(
                        "Skill command resolved",
                        extra={
                            "skill_name": invocation.skill_name,
                            "command_name": invocation.command_name,
                            "dispatch_mode": invocation.dispatch_mode,
                        }
                    )
                    
                    # Tool Dispatch 模式 (未来支持)
                    if invocation.dispatch_mode == "tool_dispatch":
                        # TODO: 直接调用工具
                        pass
                    
                    # Prompt Rewrite 模式
                    # 加载完整 SKILL.md 并添加强制性指令
                    content = skill_adapter.load_skill_content(invocation.skill_name)
                    if content:
                        # 使用 Prompt Rewriter 生成重写后的用户输入
                        rewritten = _skill_prompt_rewriter.rewrite(invocation)
                        
                        # 组合: SKILL.md 内容 + 重写后的用户指令
                        skill_prompt = f"""
# 技能指令 (/{invocation.skill_name})

⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。

{content}

---

{rewritten}
"""
                        return skill_prompt, invocation
            
            # 回退: 直接用 skill_id 匹配
            command = user_input.split()[0][1:]  # 提取命令名
            content = skill_adapter.load_skill_content(command)
            if content:
                logger.info(
                    "Skill matched by direct command",
                    extra={"skill_id": command}
                )
                return f"\n\n# 技能指令 (/{command})\n\n⚠️ **重要**: 请严格按照以下技能指令执行，不要使用其他方式。\n\n{content}", None
        
        # 模式 3: 意图匹配 - 使用 XML 格式技能列表 + 强制性指令 (OpenClaw 风格)
        skills_prompt = skill_adapter.build_skills_xml_prompt()
        if skills_prompt:
            logger.debug(
                "Skills XML prompt generated",
                extra={
                    "user_input": user_input[:50],
                    "prompt_length": len(skills_prompt),
                }
            )
            return f"\n\n{skills_prompt}", None
        
        return "", None
    
    except Exception as e:
        logger.warning(
            "Failed to generate skill prompt",
            extra={"error": str(e)}
        )
        return "", None


async def _handle_message(
    websocket: WebSocket,
    agent: Agent,
    content: str,
    session_id: str,
) -> None:
    """处理用户消息.
    
    Args:
        websocket: WebSocket 连接
        agent: Agent 实例
        content: 用户消息内容
        session_id: 会话 ID
    """
    try:
        # 动态匹配技能并注入 prompt
        skill_prompt, invocation = _match_and_load_skill_prompt(content)
        
        if skill_prompt:
            # 临时更新 agent 的 system prompt
            base_prompt = agent._system_prompt
            agent._system_prompt = base_prompt + skill_prompt
            logger.debug(
                "Skill prompt injected",
                extra={
                    "session_id": session_id,
                    "skill_prompt_length": len(skill_prompt),
                    "invocation": invocation.skill_name if invocation else None,
                }
            )
        
        # 如果有显式命令调用，可能需要重写用户输入
        actual_content = content
        if invocation and invocation.dispatch_mode == "prompt_rewrite":
            # 用户输入已包含在 skill_prompt 中的 rewritten 部分
            # 这里保持原始输入，让 LLM 看到完整上下文
            pass
        
        async for event in agent.prompt(actual_content):
            ws_msg = convert_event_to_websocket(event)
            if ws_msg:
                await websocket.send_json(ws_msg)
            
            # 在 AgentEndEvent 时持久化消息
            if isinstance(event, AgentEndEvent):
                await _persist_messages(session_id, content, event)
        
        # 恢复原始 system prompt（如果有注入）
        if skill_prompt:
            agent._system_prompt = base_prompt
    
    except Exception as e:
        logger.error(
            "Error processing message",
            extra={
                "session_id": session_id,
                "error": str(e),
            }
        )
        await websocket.send_json({
            "type": "error",
            "message": str(e),
        })


async def _persist_messages(
    session_id: str,
    user_content: str,
    event: AgentEndEvent,
) -> None:
    """持久化消息到会话.
    
    Args:
        session_id: 会话 ID
        user_content: 用户消息内容
        event: AgentEndEvent 包含新消息
    """
    try:
        session_manager = _get_session_manager()
        
        # 保存用户消息
        await session_manager.add_message(
            session_id=session_id,
            role="user",
            content=user_content,
        )
        
        # 保存 assistant 消息
        for msg in event.messages:
            if isinstance(msg, AssistantMessage):
                await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=msg.get_text(),
                    metadata={
                        "model": msg.model,
                        "provider": msg.provider,
                        "stop_reason": msg.stop_reason,
                        "usage": msg.usage,
                    },
                )
    
    except Exception as e:
        logger.warning(
            "Failed to persist messages",
            extra={
                "session_id": session_id,
                "error": str(e),
            }
        )


@router.websocket("/agent/{session_id}")
async def agent_websocket(websocket: WebSocket, session_id: str) -> None:
    """Agent WebSocket 端点.
    
    Args:
        websocket: WebSocket 连接
        session_id: 会话 ID
    """
    await websocket.accept()
    
    logger.info(
        "WebSocket connected",
        extra={"session_id": session_id}
    )
    
    # 创建 Agent
    config = create_agent_config()
    agent = Agent(config)
    
    # 当前处理任务
    message_task: asyncio.Task | None = None
    
    async def receive_messages():
        """接收 WebSocket 消息的协程."""
        while True:
            try:
                data = await websocket.receive_json()
                yield data
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
    
    try:
        async for data in receive_messages():
            msg_type = data.get("type", "message")
            
            # 心跳响应
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            
            # 中止请求 - 立即处理
            if msg_type == "abort":
                agent.abort()
                if message_task and not message_task.done():
                    message_task.cancel()
                    try:
                        await message_task
                    except asyncio.CancelledError:
                        pass
                    message_task = None
                logger.info(
                    "Agent aborted",
                    extra={"session_id": session_id}
                )
                # 发送中止确认
                await websocket.send_json({
                    "type": "message",
                    "content": "",
                    "is_finished": True,
                    "stop_reason": "aborted",
                })
                continue
            
            # 处理用户消息
            content = data.get("content", "")
            if content:
                # 等待之前的任务完成
                if message_task and not message_task.done():
                    await message_task
                
                # 启动新任务
                message_task = asyncio.create_task(
                    _handle_message(websocket, agent, content, session_id)
                )
    
    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected",
            extra={"session_id": session_id}
        )
    
    except Exception as e:
        logger.error(
            "WebSocket error",
            extra={
                "session_id": session_id,
                "error": str(e),
            }
        )
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
