"""AgentEvent 到 WebSocket JSON 的转换器.

将 agent_core 的事件类型转换为前端可用的 WebSocket 消息格式。

Event Mapping:
- MessageUpdateEvent (text) -> {"type": "chunk", "content": delta}
- MessageUpdateEvent (thinking) -> {"type": "thinking", "content": delta}
- MessageEndEvent -> {"type": "message", "content": text, "model": model, "is_finished": true}
- ToolExecutionStartEvent -> {"type": "tool_call", "tool_call_id": id, "name": name, "arguments": args}
- ToolExecutionEndEvent -> {"type": "tool_result", "tool_call_id": id, "result": result, "is_error": bool}

Internal events (not sent to WebSocket):
- AgentStartEvent, AgentEndEvent
- TurnStartEvent, TurnEndEvent
- MessageStartEvent
"""

from __future__ import annotations

from typing import Any

from ..types import (
    AgentEvent,
    AgentStartEvent,
    AgentEndEvent,
    TurnStartEvent,
    TurnEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    MessageEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolExecutionEndEvent,
    AssistantMessage,
    TextContent,
)


def convert_event_to_websocket(event: AgentEvent) -> dict[str, Any] | None:
    """将 AgentEvent 转换为 WebSocket JSON 消息.
    
    Args:
        event: AgentEvent 实例
        
    Returns:
        WebSocket JSON 消息字典，如果是内部事件则返回 None
    """
    if isinstance(event, MessageUpdateEvent):
        return _convert_message_update(event)
    
    if isinstance(event, MessageEndEvent):
        return _convert_message_end(event)
    
    if isinstance(event, ToolExecutionStartEvent):
        return _convert_tool_start(event)
    
    if isinstance(event, ToolExecutionEndEvent):
        return _convert_tool_end(event)
    
    if isinstance(event, ToolExecutionUpdateEvent):
        return _convert_tool_update(event)
    
    # 内部事件不发送
    if isinstance(event, (
        AgentStartEvent,
        AgentEndEvent,
        TurnStartEvent,
        TurnEndEvent,
        MessageStartEvent,
    )):
        return None
    
    return None


def _convert_message_update(event: MessageUpdateEvent) -> dict[str, Any] | None:
    """转换消息更新事件."""
    if not event.delta:
        return None
    
    if event.delta_type == "text":
        return {
            "type": "chunk",
            "content": event.delta,
        }
    
    if event.delta_type == "thinking":
        return {
            "type": "thinking",
            "content": event.delta,
        }
    
    # tool_call delta 暂不处理 (由 ToolExecutionStartEvent 处理)
    return None


def _convert_message_end(event: MessageEndEvent) -> dict[str, Any] | None:
    """转换消息结束事件."""
    if not event.message or not isinstance(event.message, AssistantMessage):
        return None
    
    msg = event.message
    
    # 如果是工具调用，不发送 message 事件（等工具执行完再发送最终消息）
    if msg.stop_reason == "tool_use":
        return None
    
    # 获取文本内容
    text_parts = []
    for content in msg.content:
        if isinstance(content, TextContent):
            text_parts.append(content.text)
    
    return {
        "type": "message",
        "content": "".join(text_parts),
        "model": msg.model,
        "provider": msg.provider,
        "stop_reason": msg.stop_reason,
        "usage": msg.usage,
        "is_finished": True,
    }


def _convert_tool_start(event: ToolExecutionStartEvent) -> dict[str, Any]:
    """转换工具执行开始事件."""
    return {
        "type": "tool_call",
        "tool_call_id": event.tool_call_id,
        "name": event.tool_name,
        "arguments": event.arguments,
    }


def _convert_tool_update(event: ToolExecutionUpdateEvent) -> dict[str, Any] | None:
    """转换工具执行更新事件."""
    if event.partial_result is None:
        return None
    
    return {
        "type": "tool_update",
        "tool_call_id": event.tool_call_id,
        "name": event.tool_name,
        "partial_result": event.partial_result,
    }


def _convert_tool_end(event: ToolExecutionEndEvent) -> dict[str, Any]:
    """转换工具执行结束事件."""
    result_content = ""
    result_details = {}
    
    if event.result:
        # 提取文本内容
        text_parts = []
        for content in event.result.content:
            if isinstance(content, TextContent):
                text_parts.append(content.text)
        result_content = "".join(text_parts)
        result_details = event.result.details
    
    return {
        "type": "tool_result",
        "tool_call_id": event.tool_call_id,
        "name": event.tool_name,
        "result": result_content,
        "details": result_details,
        "is_error": event.is_error,
        "duration_ms": event.duration_ms,
    }
