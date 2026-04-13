"""Agent Core 核心类型定义.

本模块定义了 agent_core 的所有核心类型，包括：
- 内容类型 (Content)
- 消息类型 (Message)
- 事件类型 (Event)
- 工具类型 (Tool)
- 配置类型 (Config)
- 流式数据类型 (Stream)

设计原则：
- 零外部依赖，仅使用 Python 标准库
- 使用 dataclass 定义所有类型
- 使用 Union 类型实现类型联合
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ============================================================
# 内容类型 (Content Types)
# ============================================================


@dataclass
class TextContent:
    """文本内容."""

    type: str = field(default="text", init=False)
    text: str = ""


@dataclass
class ImageContent:
    """图片内容."""

    type: str = field(default="image", init=False)
    data: str = ""  # base64 encoded
    mime_type: str = "image/png"  # image/png, image/jpeg, image/gif, image/webp


@dataclass
class ThinkingContent:
    """思考内容 (reasoning/extended thinking)."""

    type: str = field(default="thinking", init=False)
    thinking: str = ""


@dataclass
class ToolCallContent:
    """工具调用内容."""

    type: str = field(default="tool_call", init=False)
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


# Content 联合类型
Content = TextContent | ImageContent | ThinkingContent | ToolCallContent


# ============================================================
# 消息类型 (Message Types)
# ============================================================


@dataclass
class UserMessage:
    """用户消息."""

    role: str = field(default="user", init=False)
    content: list[TextContent | ImageContent] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    @classmethod
    def from_text(cls, text: str) -> UserMessage:
        """从文本创建用户消息."""
        return cls(content=[TextContent(text=text)])

    @classmethod
    def from_text_and_images(
        cls, text: str, images: list[tuple[str, str]] | None = None
    ) -> UserMessage:
        """从文本和图片创建用户消息.

        Args:
            text: 文本内容
            images: 图片列表，每项为 (base64_data, mime_type)
        """
        content: list[TextContent | ImageContent] = [TextContent(text=text)]
        if images:
            for data, mime_type in images:
                content.append(ImageContent(data=data, mime_type=mime_type))
        return cls(content=content)


@dataclass
class AssistantMessage:
    """助手消息."""

    role: str = field(default="assistant", init=False)
    content: list[Content] = field(default_factory=list)

    # 模型信息
    model: str = ""
    provider: str = ""

    # 停止原因: "end_turn" | "tool_use" | "max_tokens" | "error" | "aborted"
    stop_reason: str = ""

    # Token 使用统计
    usage: dict[str, int] = field(default_factory=dict)

    # 错误信息
    error_message: str | None = None

    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    def get_text(self) -> str:
        """获取消息的文本内容."""
        parts = []
        for c in self.content:
            if isinstance(c, TextContent):
                parts.append(c.text)
        return "".join(parts)

    def get_tool_calls(self) -> list[ToolCallContent]:
        """获取消息中的工具调用."""
        return [c for c in self.content if isinstance(c, ToolCallContent)]

    def has_tool_calls(self) -> bool:
        """检查消息是否包含工具调用."""
        return any(isinstance(c, ToolCallContent) for c in self.content)


@dataclass
class ToolResultMessage:
    """工具结果消息."""

    role: str = field(default="tool_result", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    content: list[TextContent | ImageContent] = field(default_factory=list)
    is_error: bool = False

    # 详细信息 (用于 UI 展示)
    details: dict[str, Any] = field(default_factory=dict)

    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    @classmethod
    def from_text(
        cls,
        tool_call_id: str,
        tool_name: str,
        text: str,
        is_error: bool = False,
        details: dict[str, Any] | None = None,
    ) -> ToolResultMessage:
        """从文本创建工具结果消息."""
        return cls(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=[TextContent(text=text)],
            is_error=is_error,
            details=details or {},
        )


# AgentMessage 联合类型
AgentMessage = UserMessage | AssistantMessage | ToolResultMessage


# ============================================================
# 事件类型 (Event Types)
# ============================================================


@dataclass
class AgentStartEvent:
    """Agent 开始事件."""

    type: str = field(default="agent_start", init=False)
    trace_id: str = ""
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class AgentEndEvent:
    """Agent 结束事件."""

    type: str = field(default="agent_end", init=False)
    messages: list[AgentMessage] = field(default_factory=list)
    trace_id: str = ""
    total_duration_ms: float = 0
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class TurnStartEvent:
    """Turn 开始事件.

    一个 Turn 包含一次 LLM 调用及其可能的工具调用。
    """

    type: str = field(default="turn_start", init=False)
    turn_index: int = 0
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class TurnEndEvent:
    """Turn 结束事件."""

    type: str = field(default="turn_end", init=False)
    turn_index: int = 0
    message: AssistantMessage | None = None
    tool_results: list[ToolResultMessage] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class MessageStartEvent:
    """消息开始事件."""

    type: str = field(default="message_start", init=False)
    message: AgentMessage | None = None
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class MessageUpdateEvent:
    """消息更新事件 (流式).

    用于流式响应时的增量更新。
    """

    type: str = field(default="message_update", init=False)
    message: AgentMessage | None = None
    delta: str = ""  # 增量文本
    delta_type: str = ""  # "text" | "thinking" | "tool_call"
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class MessageEndEvent:
    """消息结束事件."""

    type: str = field(default="message_end", init=False)
    message: AgentMessage | None = None
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class ToolExecutionStartEvent:
    """工具执行开始事件."""

    type: str = field(default="tool_execution_start", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class ToolExecutionUpdateEvent:
    """工具执行更新事件.

    用于工具执行过程中的进度更新。
    """

    type: str = field(default="tool_execution_update", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    partial_result: Any = None
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass
class ToolExecutionEndEvent:
    """工具执行结束事件."""

    type: str = field(default="tool_execution_end", init=False)
    tool_call_id: str = ""
    tool_name: str = ""
    result: ToolResult | None = None
    is_error: bool = False
    duration_ms: float = 0
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


# AgentEvent 联合类型
AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


# ============================================================
# 工具类型 (Tool Types)
# ============================================================


@dataclass
class ToolParameter:
    """工具参数定义."""

    name: str
    type: str  # "string" | "number" | "boolean" | "object" | "array"
    description: str
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None


@dataclass
class AgentTool:
    """Agent 工具定义."""

    name: str
    label: str  # UI 显示名称
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    # 工具分类 (可选)
    category: str = ""

    # 风险等级 (可选): "low" | "medium" | "high"
    risk_level: str = "low"

    def to_llm_tool(self) -> dict[str, Any]:
        """转换为 LLM 工具格式 (OpenAI function calling 格式)."""
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


@dataclass
class ToolResult:
    """工具执行结果."""

    content: list[TextContent | ImageContent] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(cls, text: str, details: dict[str, Any] | None = None) -> ToolResult:
        """从文本创建工具结果."""
        return cls(
            content=[TextContent(text=text)],
            details=details or {},
        )

    @classmethod
    def from_error(cls, error: str, details: dict[str, Any] | None = None) -> ToolResult:
        """从错误创建工具结果."""
        d = details or {}
        d["error"] = error
        return cls(
            content=[TextContent(text=f"Error: {error}")],
            details=d,
        )


# ============================================================
# 配置类型 (Config Types)
# ============================================================


@dataclass
class AgentContext:
    """Agent 上下文.

    包含 LLM 调用所需的所有上下文信息。
    """

    system_prompt: str = ""
    messages: list[AgentMessage] = field(default_factory=list)
    tools: list[AgentTool] = field(default_factory=list)


@dataclass
class AgentLoopConfig:
    """Agent Loop 配置.

    控制 agent_loop 的行为。
    """

    # 模型配置
    model: str = ""
    provider: str = ""

    # 推理配置
    thinking_level: str = "off"  # "off" | "minimal" | "low" | "medium" | "high"
    temperature: float | None = None
    max_tokens: int | None = None

    # 上下文转换 (可选)
    convert_to_llm: Callable[[list[AgentMessage]], list[dict]] | None = None
    transform_context: Callable[[list[AgentMessage]], Awaitable[list[AgentMessage]]] | None = None

    # 动态消息回调 (可选)
    get_steering_messages: Callable[[], Awaitable[list[AgentMessage]]] | None = None
    get_follow_up_messages: Callable[[], Awaitable[list[AgentMessage]]] | None = None


@dataclass
class AgentState:
    """Agent 状态.

    跟踪 Agent 的运行时状态。
    """

    # 配置
    system_prompt: str = ""
    model: str = ""
    provider: str = ""
    thinking_level: str = "off"
    tools: list[AgentTool] = field(default_factory=list)

    # 消息历史
    messages: list[AgentMessage] = field(default_factory=list)

    # 运行状态
    is_streaming: bool = False
    stream_message: AgentMessage | None = None
    pending_tool_calls: set[str] = field(default_factory=set)

    # 错误状态
    error: str | None = None

    # 当前 trace
    current_trace_id: str | None = None


# ============================================================
# 流式数据类型 (Stream Types)
# ============================================================


class StreamChunkType(Enum):
    """流式数据块类型."""

    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL = "tool_call"
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamChunk:
    """流式数据块.

    用于 LLMPort.stream() 返回的流式数据。
    """

    type: StreamChunkType

    # text_delta / thinking_delta
    delta: str = ""

    # tool_call
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)

    # done
    stop_reason: str = ""  # "end_turn" | "tool_use" | "max_tokens"
    usage: dict[str, int] | None = None

    # error
    error: str = ""

    @classmethod
    def text(cls, delta: str) -> StreamChunk:
        """创建文本增量块."""
        return cls(type=StreamChunkType.TEXT_DELTA, delta=delta)

    @classmethod
    def thinking(cls, delta: str) -> StreamChunk:
        """创建思考增量块."""
        return cls(type=StreamChunkType.THINKING_DELTA, delta=delta)

    @classmethod
    def tool(cls, tool_call_id: str, tool_name: str, arguments: dict[str, Any]) -> StreamChunk:
        """创建工具调用块."""
        return cls(
            type=StreamChunkType.TOOL_CALL,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    @classmethod
    def done(cls, stop_reason: str, usage: dict[str, int] | None = None) -> StreamChunk:
        """创建完成块."""
        return cls(
            type=StreamChunkType.DONE,
            stop_reason=stop_reason,
            usage=usage,
        )

    @classmethod
    def err(cls, error: str) -> StreamChunk:
        """创建错误块."""
        return cls(type=StreamChunkType.ERROR, error=error)


# ============================================================
# 日志类型 (Logger Types)
# ============================================================


class LogLevel(Enum):
    """日志级别."""

    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class LogCategory(Enum):
    """日志分类."""

    AGENT_LOOP = "agent_loop"
    LLM_CALL = "llm_call"
    TOOL_EXEC = "tool_exec"
    CONTEXT = "context"
    WEBSOCKET = "websocket"
    MESSAGE = "message"
    MEMORY = "memory"


@dataclass
class LogEntry:
    """日志条目."""

    id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    level: LogLevel = LogLevel.INFO
    category: LogCategory = LogCategory.AGENT_LOOP

    # 追踪上下文
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""

    # 日志内容
    event: str = ""
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    # 耗时统计
    duration_ms: float | None = None

    # 错误信息
    error: str | None = None
    error_type: str | None = None
    stack_trace: str | None = None


@dataclass
class LLMCallLog:
    """LLM 调用日志."""

    call_id: str = ""
    trace_id: str = ""

    # 请求信息
    model: str = ""
    provider: str = ""

    # Prompt 详情
    system_prompt: str = ""
    messages: list[dict] = field(default_factory=list)
    message_count: int = 0
    estimated_tokens: int = 0

    # 配置
    temperature: float | None = None
    max_tokens: int | None = None
    thinking_level: str | None = None
    tools: list[dict] | None = None

    # 响应信息
    response_content: list[dict] | None = None
    stop_reason: str | None = None

    # Token 使用
    usage: dict[str, int] | None = None

    # 耗时
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: float | None = None
    time_to_first_token_ms: float | None = None

    # 状态
    status: str = "pending"  # pending, streaming, completed, error
    error: str | None = None


@dataclass
class ToolCallLog:
    """工具调用日志."""

    call_id: str = ""
    trace_id: str = ""
    llm_call_id: str = ""
    tool_call_id: str = ""  # LLM 返回的工具调用 ID，用于关联工具结果

    # 工具信息
    tool_name: str = ""
    tool_description: str = ""

    # 入参
    arguments: dict[str, Any] = field(default_factory=dict)
    arguments_raw: str = ""

    # 执行结果
    result: Any | None = None
    result_content: list[dict] | None = None
    is_error: bool = False

    # 耗时
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: float | None = None

    # 状态
    status: str = "pending"  # pending, executing, completed, error, skipped
    error: str | None = None
    error_type: str | None = None
