"""上下文转换工具.

提供消息格式转换和上下文处理功能。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import (
        AgentMessage,
        UserMessage,
        AssistantMessage,
        ToolResultMessage,
        TextContent,
        ImageContent,
        ThinkingContent,
        ToolCallContent,
        Content,
    )


def convert_message_to_llm(message: "AgentMessage") -> dict[str, Any]:
    """将 AgentMessage 转换为 LLM API 格式.
    
    Args:
        message: Agent 消息
    
    Returns:
        dict: LLM API 格式的消息
    """
    from .types import UserMessage, AssistantMessage, ToolResultMessage
    
    if isinstance(message, UserMessage):
        return _convert_user_message(message)
    elif isinstance(message, AssistantMessage):
        return _convert_assistant_message(message)
    elif isinstance(message, ToolResultMessage):
        return _convert_tool_result_message(message)
    else:
        raise ValueError(f"Unknown message type: {type(message)}")


def _convert_user_message(message: "UserMessage") -> dict[str, Any]:
    """转换用户消息."""
    from .types import TextContent, ImageContent
    
    content_list = []
    for c in message.content:
        if isinstance(c, TextContent):
            content_list.append({
                "type": "text",
                "text": c.text,
            })
        elif isinstance(c, ImageContent):
            content_list.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": c.mime_type,
                    "data": c.data,
                },
            })
    
    # 如果只有一个文本内容，简化为字符串
    if len(content_list) == 1 and content_list[0]["type"] == "text":
        return {
            "role": "user",
            "content": content_list[0]["text"],
        }
    
    return {
        "role": "user",
        "content": content_list,
    }


def _convert_assistant_message(message: "AssistantMessage") -> dict[str, Any]:
    """转换助手消息 (OpenAI 格式)."""
    from .types import TextContent, ThinkingContent, ToolCallContent
    import json
    
    # 提取文本内容
    text_parts = []
    tool_calls = []
    
    for c in message.content:
        if isinstance(c, TextContent):
            text_parts.append(c.text)
        elif isinstance(c, ToolCallContent):
            # OpenAI 格式的 tool_calls
            tool_calls.append({
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": json.dumps(c.arguments) if isinstance(c.arguments, dict) else c.arguments,
                }
            })
    
    result: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts) if text_parts else None,
    }
    
    if tool_calls:
        result["tool_calls"] = tool_calls
    
    return result


def _convert_tool_result_message(message: "ToolResultMessage") -> dict[str, Any]:
    """转换工具结果消息 (OpenAI 格式)."""
    from .types import TextContent
    
    # 提取文本内容
    text_parts = []
    for c in message.content:
        if isinstance(c, TextContent):
            text_parts.append(c.text)
    
    content = "".join(text_parts)
    if message.is_error and not content.startswith("Error:"):
        content = f"Error: {content}"
    
    # OpenAI 格式: role=tool, tool_call_id, content
    return {
        "role": "tool",
        "tool_call_id": message.tool_call_id,
        "content": content,
    }


def convert_messages_to_llm(messages: "list[AgentMessage]") -> list[dict[str, Any]]:
    """将消息列表转换为 LLM API 格式.
    
    Args:
        messages: Agent 消息列表
    
    Returns:
        list: LLM API 格式的消息列表
    """
    return [convert_message_to_llm(m) for m in messages]


def content_to_dict(content: "Content") -> dict[str, Any]:
    """将 Content 转换为字典.
    
    Args:
        content: 内容对象
    
    Returns:
        dict: 字典表示
    """
    from .types import TextContent, ImageContent, ThinkingContent, ToolCallContent
    
    if isinstance(content, TextContent):
        return {"type": "text", "text": content.text}
    elif isinstance(content, ImageContent):
        return {
            "type": "image",
            "data": content.data[:50] + "..." if len(content.data) > 50 else content.data,
            "mime_type": content.mime_type,
        }
    elif isinstance(content, ThinkingContent):
        return {"type": "thinking", "thinking": content.thinking}
    elif isinstance(content, ToolCallContent):
        return {
            "type": "tool_call",
            "id": content.id,
            "name": content.name,
            "arguments": content.arguments,
        }
    else:
        return {"type": "unknown"}


def message_to_dict(message: "AgentMessage") -> dict[str, Any]:
    """将 AgentMessage 转换为字典.
    
    Args:
        message: Agent 消息
    
    Returns:
        dict: 字典表示
    """
    from .types import UserMessage, AssistantMessage, ToolResultMessage
    
    if isinstance(message, UserMessage):
        return {
            "role": "user",
            "content": [content_to_dict(c) for c in message.content],
            "timestamp": message.timestamp,
        }
    elif isinstance(message, AssistantMessage):
        return {
            "role": "assistant",
            "content": [content_to_dict(c) for c in message.content],
            "model": message.model,
            "provider": message.provider,
            "stop_reason": message.stop_reason,
            "usage": message.usage,
            "timestamp": message.timestamp,
        }
    elif isinstance(message, ToolResultMessage):
        return {
            "role": "tool_result",
            "tool_call_id": message.tool_call_id,
            "tool_name": message.tool_name,
            "content": [content_to_dict(c) for c in message.content],
            "is_error": message.is_error,
            "timestamp": message.timestamp,
        }
    else:
        return {"role": "unknown"}


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """估算消息列表的 token 数量.
    
    Args:
        messages: LLM 格式的消息列表
    
    Returns:
        int: 估算的 token 数量
    """
    # 简单估算：每 4 个字符约等于 1 个 token
    text = str(messages)
    return len(text) // 4


def truncate_string(s: str, max_len: int = 500) -> str:
    """截断字符串.
    
    Args:
        s: 原始字符串
        max_len: 最大长度
    
    Returns:
        str: 截断后的字符串
    """
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."
