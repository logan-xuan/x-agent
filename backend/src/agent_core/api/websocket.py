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
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .converters import convert_event_to_websocket
from ..agent import Agent
from ..config import AgentCoreConfig
from ..adapters.llm_adapter import XAgentLLMAdapter
from ..adapters.tool_adapter import XAgentToolAdapter
from ..types import AgentEndEvent, UserMessage, AssistantMessage

# 导入日志
try:
    from ...utils.logger import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


router = APIRouter()


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


def create_agent_config() -> AgentCoreConfig:
    """创建 Agent 配置.
    
    注入 LLM 和 Tool 适配器，并加载系统提示词。
    
    Returns:
        AgentCoreConfig 实例
    """
    llm_router = _get_llm_router()
    tool_manager = _get_tool_manager()
    
    llm_adapter = XAgentLLMAdapter(llm_router)
    tool_adapter = XAgentToolAdapter(tool_manager)
    
    # 加载系统提示词
    system_prompt = _load_system_prompt()
    
    return AgentCoreConfig(
        llm=llm_adapter,
        tools=tool_adapter,
        system_prompt=system_prompt,
    )


def _load_system_prompt() -> str:
    """加载系统提示词.
    
    从 workspace 的 SPIRIT.md 和 OWNER.md 构建系统提示词。
    如果文件不存在，使用默认的中文提示词。
    
    Returns:
        系统提示词
    """
    try:
        from ...memory.spirit_loader import get_spirit_loader
        from ...config.manager import ConfigManager
        
        # 获取 workspace 路径
        config = ConfigManager().config
        workspace_path = config.workspace.path if config.workspace else "workspace"
        
        spirit_loader = get_spirit_loader(workspace_path)
        
        # 加载 SPIRIT.md
        spirit = spirit_loader.load_spirit()
        # 加载 OWNER.md
        owner = spirit_loader.load_owner()
        
        prompt_parts = []
        
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
        async for event in agent.prompt(content):
            ws_msg = convert_event_to_websocket(event)
            if ws_msg:
                await websocket.send_json(ws_msg)
            
            # 在 AgentEndEvent 时持久化消息
            if isinstance(event, AgentEndEvent):
                await _persist_messages(session_id, content, event)
    
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
