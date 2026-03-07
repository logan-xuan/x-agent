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
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .converters import convert_event_to_websocket
from .dev_routes import get_logger as get_agent_logger
from ..agent import Agent
from ..config import AgentCoreConfig
from ..adapters.llm_adapter import XAgentLLMAdapter
from ..adapters.tool_adapter import XAgentToolAdapter
from ..adapters.system_prompt_adapter import create_system_prompt_adapter
from ..types import AgentEndEvent, AssistantMessage, MessageUpdateEvent, MessageEndEvent
from ..skill_dispatcher import (
    SkillCommandResolver,
    SkillPromptRewriter,
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
    from ...conversation.session import SessionManager
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
    
    注入 LLM、Tool、SystemPrompt、Context 适配器。
    系统提示词通过 SystemPromptPort 从 conversation 模块加载，
    保持 agent_core 的独立性。
    
    Returns:
        AgentCoreConfig 实例
    """
    llm_router = _get_llm_router()
    tool_manager = _get_tool_manager()
    
    llm_adapter = XAgentLLMAdapter(llm_router)
    tool_adapter = XAgentToolAdapter(tool_manager)
    
    # 获取共享的 AgentLogger（与 REST API 共享）
    agent_logger = get_agent_logger()
    
    # 通过 SystemPromptPort adapter 加载系统提示词
    system_prompt_adapter = create_system_prompt_adapter()
    system_prompt = system_prompt_adapter.build_system_prompt()
    
    # 创建 Context adapter (上下文压缩)
    context_adapter = _create_context_adapter(llm_router)
    
    return AgentCoreConfig(
        llm=llm_adapter,
        tools=tool_adapter,
        logger=agent_logger,
        context=context_adapter,
        system_prompt=system_prompt,
        system_prompt_port=system_prompt_adapter,
    )


def _create_context_adapter(llm_router):
    """创建 ContextPort adapter (上下文压缩).

    Args:
        llm_router: LLMRouter 实例，用于摘要生成

    Returns:
        XAgentContextAdapter 实例，或 None（创建失败时）
    """
    try:
        from ..adapters.context_adapter import create_context_adapter
        from ...config.manager import get_config

        config = get_config()
        workspace_path = config.workspace.path

        return create_context_adapter(
            llm_router=llm_router,
            compression_config=config.compression,
            workspace_path=workspace_path,
        )
    except Exception as e:
        logger.warning(
            "Failed to create context adapter, compression disabled",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            }
        )
        return None




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
    
    改进: 用户消息在发送到 LLM 之前就持久化，避免因连接断开导致消息丢失。
    
    Args:
        websocket: WebSocket 连接
        agent: Agent 实例
        content: 用户消息内容
        session_id: 会话 ID
    """
    user_msg_id = None
    assistant_content = []  # 收集 assistant 响应内容
    
    try:
        # ===== 改进 1: 先持久化用户消息 =====
        # 在发送到 LLM 之前就保存用户消息，避免因连接断开导致丢失
        try:
            session_manager = _get_session_manager()
            user_msg = await session_manager.add_message(
                session_id=session_id,
                role="user",
                content=content,
            )
            user_msg_id = user_msg.id
            logger.info(
                "User message persisted before LLM call",
                extra={
                    "session_id": session_id,
                    "message_id": user_msg_id,
                    "content_length": len(content),
                }
            )
        except Exception as e:
            logger.exception(
                "Failed to persist user message before LLM call",
                extra={
                    "session_id": session_id,
                    "error": str(e),
                }
            )
        
        # 动态匹配技能并注入 prompt
        skill_prompt, invocation = _match_and_load_skill_prompt(content)
        
        # 清理或替换 Skills 占位标记
        from ...conversation.system_prompt_builder import SKILLS_INJECTION_MARKER
        base_prompt = agent._system_prompt
        
        if skill_prompt:
            if SKILLS_INJECTION_MARKER in base_prompt:
                agent._system_prompt = base_prompt.replace(
                    SKILLS_INJECTION_MARKER, skill_prompt.strip()
                )
            else:
                agent._system_prompt = base_prompt + skill_prompt
            logger.debug(
                "Skill prompt injected",
                extra={
                    "session_id": session_id,
                    "skill_prompt_length": len(skill_prompt),
                    "invocation": invocation.skill_name if invocation else None,
                }
            )
        elif SKILLS_INJECTION_MARKER in base_prompt:
            # 无 skill_prompt 时清除占位标记，避免残留
            agent._system_prompt = base_prompt.replace(
                SKILLS_INJECTION_MARKER, ""
            )
        
        async for event in agent.prompt(content):
            ws_msg = convert_event_to_websocket(event)
            if ws_msg:
                try:
                    await websocket.send_json(ws_msg)
                except Exception as ws_error:
                    # WebSocket 发送失败，但继续执行以便完成持久化
                    logger.warning(
                        "WebSocket send failed, continuing for persistence",
                        extra={
                            "session_id": session_id,
                            "error": str(ws_error),
                        }
                    )
            
            # ===== 改进 2: 收集 assistant 响应内容 =====
            if isinstance(event, MessageUpdateEvent) and event.delta_type == "text":
                # 收集流式响应的增量文本
                assistant_content.append(event.delta)
            elif isinstance(event, MessageEndEvent) and event.message:
                # 消息结束时收集完整内容
                get_text_fn = getattr(event.message, 'get_text', None)
                if get_text_fn:
                    assistant_content.append(get_text_fn())
            
            # 在 AgentEndEvent 时持久化 assistant 消息
            if isinstance(event, AgentEndEvent):
                await _persist_assistant_message(session_id, event, user_msg_id)
        
        # 恢复原始 system prompt（如果有注入）
        if skill_prompt:
            agent._system_prompt = base_prompt
    
    except Exception as e:
        logger.exception(
            "Error processing message",
            extra={
                "session_id": session_id,
                "error": str(e),
            }
        )
        
        # ===== 改进 3: 即使出错也尝试保存部分响应 =====
        if assistant_content:
            try:
                session_manager = _get_session_manager()
                await session_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content="".join(assistant_content),
                    metadata={
                        "status": "error_interrupted",
                        "error": str(e),
                    },
                )
                logger.info(
                    "Partial assistant message saved after error",
                    extra={"session_id": session_id}
                )
            except Exception:
                pass
        
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass


async def _persist_assistant_message(
    session_id: str,
    event: AgentEndEvent,
    user_msg_id: str | None = None,
) -> None:
    """持久化 assistant 消息到会话.
    
    注意: 用户消息已在 _handle_message 中提前保存。
    
    Args:
        session_id: 会话 ID
        event: AgentEndEvent 包含新消息
        user_msg_id: 关联的用户消息 ID (可选)
    """
    try:
        session_manager = _get_session_manager()
        
        # 只保存 assistant 消息
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
                        "user_msg_id": user_msg_id,  # 关联用户消息
                    },
                )
        
        logger.info(
            "Assistant message persisted",
            extra={
                "session_id": session_id,
                "user_msg_id": user_msg_id,
            }
        )
    
    except Exception as e:
        logger.exception(
            "Failed to persist assistant message",
            extra={
                "session_id": session_id,
                "error": str(e),
            }
        )


async def _load_session_history(agent: Agent, session_id: str) -> None:
    """从数据库加载会话历史消息到 Agent 内存.

    WebSocket 每次连接会创建新的 Agent 实例，内存中没有历史消息。
    通过 MemoryManager 从数据库恢复历史，确保 LLM 调用时能看到完整的对话上下文。

    Args:
        agent: Agent 实例
        session_id: 会话 ID
    """
    try:
        from ...memory.manager import get_memory_manager
        memory_manager = get_memory_manager()
        agent_messages = await memory_manager.get_session_history_as_agent_messages(
            session_id, limit=200,
        )

        if not agent_messages:
            return

        for msg in agent_messages:
            agent.add_message(msg)

        logger.info(
            "Session history loaded into Agent via MemoryManager",
            extra={
                "session_id": session_id,
                "loaded_message_count": len(agent_messages),
            }
        )

    except Exception as e:
        logger.error(
            "Failed to load session history, starting with empty context",
            extra={
                "session_id": session_id,
                "error": str(e),
                "error_type": type(e).__name__,
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
    
    # 设置请求上下文（含 Identity），确保 session_id 在整个请求链路中可用
    from ...conversation.context import AgentContext as ReqContext, set_current_context
    req_context = ReqContext.for_websocket(session_id=session_id)
    set_current_context(req_context)

    # 确保 ChatSession 存在（首次连接自动创建，重连时重新激活）
    from ...services.storage import get_storage_service
    from ...conversation.dao import ChatSessionDAO, DEFAULT_USER_ID, DEFAULT_AGENT_ID, DEFAULT_CHANNEL_ID
    from ...conversation.dao.models import SessionStatus

    chat_session_dao = ChatSessionDAO(get_storage_service())
    existing_chat_session = await chat_session_dao.get_by_id(session_id)
    if existing_chat_session is None:
        await chat_session_dao.create(
            user_id=DEFAULT_USER_ID,
            agent_id=DEFAULT_AGENT_ID,
            channel_id=DEFAULT_CHANNEL_ID,
            session_id=session_id,
        )
        logger.info("ChatSession 自动创建", extra={"session_id": session_id})
    elif existing_chat_session.status != SessionStatus.ACTIVE.value:
        await chat_session_dao.update_status(session_id, SessionStatus.ACTIVE)
        logger.info("ChatSession 重新激活", extra={"session_id": session_id})
    
    logger.info(
        "Identity activated for WebSocket session",
        extra=req_context.identity.to_dict(),
    )
    
    # 创建 Agent
    config = create_agent_config()
    agent = Agent(config)

    # 从数据库加载历史消息，确保重连后对话上下文连续
    await _load_session_history(agent, session_id)
    
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

                # 更新 ChatSession 活跃时间
                await chat_session_dao.touch(session_id)

                # 启动新任务
                message_task = asyncio.create_task(
                    _handle_message(websocket, agent, content, session_id)
                )
    
    except WebSocketDisconnect:
        logger.info(
            "WebSocket disconnected",
            extra={"session_id": session_id}
        )
        
        # ===== 关键修复: 等待后台任务完成 =====
        # 即使 WebSocket 断开，也要等待 message_task 执行完成
        # 确保持久化和工具调用不被中断
        if message_task and not message_task.done():
            logger.info(
                "Waiting for background task to complete after disconnect",
                extra={"session_id": session_id}
            )
            try:
                await message_task
                logger.info(
                    "Background task completed successfully after disconnect",
                    extra={"session_id": session_id}
                )
            except Exception as task_error:
                logger.error(
                    "Background task failed after disconnect",
                    extra={
                        "session_id": session_id,
                        "error": str(task_error),
                    }
                )

        # 断开连接时关闭 ChatSession
        await chat_session_dao.close(session_id)
        logger.info("ChatSession 已关闭", extra={"session_id": session_id})
    
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
