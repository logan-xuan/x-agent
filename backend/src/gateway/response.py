"""Gateway 统一响应事件定义。

GatewayEvent 是协议无关的响应事件，各端点负责将其转换为自己协议的格式：
- WebChat: 转为 WebSocket JSON 消息
- CLI: 转为终端输出（Rich 渲染）
- Channel: 转为各平台 API 回复格式

设计原则：
- 与 agent_core 的 AgentEvent 解耦，Gateway 有自己的事件体系
- 每个事件携带来源 Agent 信息，支持多 Agent 场景
- data 字段为通用字典，各事件类型有约定的 key
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GatewayEventType(StrEnum):
    """Gateway 事件类型。

    覆盖 Agent 处理全生命周期的事件：
    - 流式输出：TEXT_CHUNK, THINKING_CHUNK
    - 消息边界：MESSAGE_START, MESSAGE_END
    - 工具调用：TOOL_CALL, TOOL_RESULT
    - 生命周期：AGENT_START, AGENT_END
    - 控制信号：ERROR, PONG
    """

    # 流式输出
    TEXT_CHUNK = "text_chunk"
    THINKING_CHUNK = "thinking_chunk"

    # 消息边界
    MESSAGE_START = "message_start"
    MESSAGE_END = "message_end"

    # 工具调用
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"

    # Agent 生命周期
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"

    # 控制信号
    ERROR = "error"
    PONG = "pong"


@dataclass
class GatewayEvent:
    """Gateway 层的统一响应事件。

    各端点负责将 GatewayEvent 转换为自己协议的格式。

    Attributes:
        type:       事件类型。
        data:       事件数据，不同类型有不同的约定 key（见下方文档）。
        agent_id:   响应来源 Agent 的 ID。
        agent_name: 响应来源 Agent 的名称。

    Data 字段约定：

    TEXT_CHUNK:
        - content (str): 文本增量片段

    THINKING_CHUNK:
        - content (str): 思考过程增量片段

    MESSAGE_START:
        - model (str): 使用的模型名称

    MESSAGE_END:
        - content (str): 完整的消息文本
        - model (str): 使用的模型名称
        - usage (dict): token 使用统计
        - stop_reason (str): 停止原因

    TOOL_CALL:
        - tool_call_id (str): 工具调用 ID
        - name (str): 工具名称
        - arguments (dict): 工具参数

    TOOL_RESULT:
        - tool_call_id (str): 工具调用 ID
        - name (str): 工具名称
        - result (str): 工具执行结果
        - is_error (bool): 是否执行出错

    AGENT_START:
        - trace_id (str): 追踪 ID

    AGENT_END:
        - trace_id (str): 追踪 ID
        - total_duration_ms (float): 总耗时（毫秒）
        - message_count (int): 消息总数

    ERROR:
        - message (str): 错误描述
        - error_type (str): 错误类型名称

    PONG:
        (无额外数据)
    """

    type: GatewayEventType
    data: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    agent_name: str | None = None

    # --- 工厂方法 ---

    @classmethod
    def text_chunk(
        cls,
        content: str,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建文本增量事件。"""
        return cls(
            type=GatewayEventType.TEXT_CHUNK,
            data={"content": content},
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def thinking_chunk(
        cls,
        content: str,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建思考过程增量事件。"""
        return cls(
            type=GatewayEventType.THINKING_CHUNK,
            data={"content": content},
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def message_start(
        cls,
        model: str = "",
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建消息开始事件。"""
        return cls(
            type=GatewayEventType.MESSAGE_START,
            data={"model": model},
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def message_end(
        cls,
        content: str,
        model: str = "",
        usage: dict[str, int] | None = None,
        stop_reason: str = "",
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建消息完成事件。"""
        return cls(
            type=GatewayEventType.MESSAGE_END,
            data={
                "content": content,
                "model": model,
                "usage": usage or {},
                "stop_reason": stop_reason,
            },
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def tool_call(
        cls,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建工具调用事件。"""
        return cls(
            type=GatewayEventType.TOOL_CALL,
            data={
                "tool_call_id": tool_call_id,
                "name": name,
                "arguments": arguments,
            },
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def tool_result(
        cls,
        tool_call_id: str,
        name: str,
        result: str,
        is_error: bool = False,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建工具执行结果事件。"""
        return cls(
            type=GatewayEventType.TOOL_RESULT,
            data={
                "tool_call_id": tool_call_id,
                "name": name,
                "result": result,
                "is_error": is_error,
            },
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def agent_start(
        cls,
        trace_id: str,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建 Agent 开始事件。"""
        return cls(
            type=GatewayEventType.AGENT_START,
            data={"trace_id": trace_id},
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def agent_end(
        cls,
        trace_id: str,
        total_duration_ms: float = 0,
        message_count: int = 0,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建 Agent 结束事件。"""
        return cls(
            type=GatewayEventType.AGENT_END,
            data={
                "trace_id": trace_id,
                "total_duration_ms": total_duration_ms,
                "message_count": message_count,
            },
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def error(
        cls,
        message: str,
        error_type: str = "GatewayError",
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建错误事件。"""
        return cls(
            type=GatewayEventType.ERROR,
            data={"message": message, "error_type": error_type},
            agent_id=agent_id,
            agent_name=agent_name,
        )

    @classmethod
    def pong(
        cls,
        *,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> GatewayEvent:
        """创建心跳响应事件。"""
        return cls(
            type=GatewayEventType.PONG,
            agent_id=agent_id,
            agent_name=agent_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，适用于 JSON 输出。

        Returns:
            包含 type、data、agent_id、agent_name 的字典。
        """
        result: dict[str, Any] = {
            "type": self.type.value,
            **self.data,
        }
        if self.agent_id is not None:
            result["agent_id"] = self.agent_id
        if self.agent_name is not None:
            result["agent_name"] = self.agent_name
        return result
