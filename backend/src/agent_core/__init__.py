"""Agent Core - 独立可移植的 Agent Loop 核心模块.

采用 Port/Adapter 架构实现高内聚低耦合，Core 层零外部依赖。

Usage:
    from agent_core import Agent, AgentCoreConfig
    from agent_core.types import UserMessage, TextContent
    from agent_core.ports import LLMPort
    
    # 实现 LLMPort
    class MyLLMAdapter:
        async def stream(self, system_prompt, messages, tools=None):
            ...
    
    # 创建配置
    config = AgentCoreConfig(llm=MyLLMAdapter())
    
    # 创建 Agent
    agent = Agent(config)
    
    # 发送消息
    async for event in agent.prompt("Hello"):
        print(event)
"""

from .types import (
    # Content types
    TextContent,
    ImageContent,
    ThinkingContent,
    ToolCallContent,
    Content,
    # Message types
    UserMessage,
    AssistantMessage,
    ToolResultMessage,
    AgentMessage,
    # Event types
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
    AgentEvent,
    # Tool types
    ToolParameter,
    AgentTool,
    ToolResult,
    # Config types
    AgentContext,
    AgentLoopConfig,
    AgentState,
    # Stream types
    StreamChunk,
    StreamChunkType,
    # Log types
    LogLevel,
    LogCategory,
    LogEntry,
    LLMCallLog,
    ToolCallLog,
)

from .config import AgentCoreConfig, create_minimal_config, create_full_config
from .agent import Agent, run_agent_once
from .agent_loop import agent_loop
from .event_stream import EventStream, EventCollector
from .logger import AgentLogger
from .memory_integration import ToolCallMemoryWriter, generate_tool_call_summary, is_important_tool_call
from .experience_learning import ExperienceLearner, format_experience_for_prompt, detect_retry_patterns
from .hooks import (
    HookPoint,
    HookContext,
    HookRegistry,
    get_hook_registry,
    reset_hook_registry,
)
from .middleware import (
    Middleware,
    MiddlewareChain,
    MessageMiddleware,
    ToolMiddleware,
    ToolCallContext,
    ToolCallResult,
    LoggingMessageMiddleware,
    TimingToolMiddleware,
    RetryToolMiddleware,
)
from .registry import (
    ComponentRegistry,
    ComponentStatus,
    get_tool_registry,
    reset_tool_registry,
)

__all__ = [
    # Content
    "TextContent",
    "ImageContent", 
    "ThinkingContent",
    "ToolCallContent",
    "Content",
    # Messages
    "UserMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "AgentMessage",
    # Events
    "AgentStartEvent",
    "AgentEndEvent",
    "TurnStartEvent",
    "TurnEndEvent",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "MessageEndEvent",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "ToolExecutionEndEvent",
    "AgentEvent",
    # Tools
    "ToolParameter",
    "AgentTool",
    "ToolResult",
    # Config
    "AgentContext",
    "AgentLoopConfig",
    "AgentState",
    "AgentCoreConfig",
    "create_minimal_config",
    "create_full_config",
    # Stream
    "StreamChunk",
    "StreamChunkType",
    # Log
    "LogLevel",
    "LogCategory",
    "LogEntry",
    "LLMCallLog",
    "ToolCallLog",
    # Core
    "Agent",
    "run_agent_once",
    "agent_loop",
    "EventStream",
    "EventCollector",
    # Logger
    "AgentLogger",
    # Memory & Experience
    "ToolCallMemoryWriter",
    "generate_tool_call_summary",
    "is_important_tool_call",
    "ExperienceLearner",
    "format_experience_for_prompt",
    "detect_retry_patterns",
    # Hooks
    "HookPoint",
    "HookContext",
    "HookRegistry",
    "get_hook_registry",
    "reset_hook_registry",
    # Middleware
    "Middleware",
    "MiddlewareChain",
    "MessageMiddleware",
    "ToolMiddleware",
    "ToolCallContext",
    "ToolCallResult",
    "LoggingMessageMiddleware",
    "TimingToolMiddleware",
    "RetryToolMiddleware",
    # Registry
    "ComponentRegistry",
    "ComponentStatus",
    "get_tool_registry",
    "reset_tool_registry",
]

__version__ = "0.1.0"
