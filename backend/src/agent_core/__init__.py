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

from .agent import Agent, run_agent_once
from .agent_bus import (
    AgentBus,
    AgentBusMessage,
    AgentMessageType,
    get_agent_bus,
    reset_agent_bus,
)
from .agent_loop import agent_loop
from .builtin_middlewares import (
    ApprovalMiddleware,
    LoggingMiddleware,
    RetryMiddleware,
    TimingMiddleware,
    ValidationMiddleware,
)
from .collaboration import (
    CollaborationMode,
    CollaborationPort,
    CollaborationStatus,
    DiscussionContribution,
    DiscussionPlan,
    LeaderWorkerPlan,
    PipelinePlan,
    PipelineStage,
    WorkerTask,
)
from .config import AgentCoreConfig, create_full_config, create_minimal_config
from .event_stream import EventCollector, EventStream
from .experience_learning import (
    ExperienceLearner,
    detect_retry_patterns,
    format_experience_for_prompt,
)
from .hooks import (
    HookContext,
    HookPoint,
    HookRegistry,
    get_hook_registry,
    reset_hook_registry,
)
from .logger import AgentLogger
from .middleware import (
    LoggingMessageMiddleware,
    MessageMiddleware,
    Middleware,
    MiddlewareChain,
    RetryToolMiddleware,
    TimingToolMiddleware,
    ToolCallContext,
    ToolCallResult,
    ToolMiddleware,
)
from .ports.delegate_port import (
    DelegatePort,
    DelegateResult,
    DelegateTask,
)
from .prompt import (
    PromptPipeline,
    PromptSection,
)
from .registry import (
    ComponentRegistry,
    ComponentStatus,
    get_tool_registry,
    reset_tool_registry,
)
from .shared_context import (
    MessageBoardPost,
    SharedContext,
    SharedContextEntry,
)
from .tool_middleware import (
    MiddlewareAction,
    ToolMiddlewarePipeline,
)
from .types import (
    # Config types
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    # Event types
    AgentStartEvent,
    AgentState,
    AgentTool,
    AssistantMessage,
    Content,
    ImageContent,
    LLMCallLog,
    LogCategory,
    LogEntry,
    # Log types
    LogLevel,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    # Stream types
    StreamChunk,
    StreamChunkType,
    # Content types
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolCallLog,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    # Tool types
    ToolParameter,
    ToolResult,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
    # Message types
    UserMessage,
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
    # Experience
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
    # Tool Middleware Pipeline
    "MiddlewareAction",
    "ToolMiddlewarePipeline",
    # Builtin Middlewares
    "TimingMiddleware",
    "RetryMiddleware",
    "ApprovalMiddleware",
    "LoggingMiddleware",
    "ValidationMiddleware",
    # Registry
    "ComponentRegistry",
    "ComponentStatus",
    "get_tool_registry",
    "reset_tool_registry",
    # Prompt
    "PromptSection",
    "PromptPipeline",
    # Agent Bus
    "AgentBus",
    "AgentBusMessage",
    "AgentMessageType",
    "get_agent_bus",
    "reset_agent_bus",
    # Delegate
    "DelegatePort",
    "DelegateTask",
    "DelegateResult",
    # Shared Context
    "SharedContext",
    "SharedContextEntry",
    "MessageBoardPost",
    # Collaboration
    "CollaborationMode",
    "CollaborationStatus",
    "CollaborationPort",
    "LeaderWorkerPlan",
    "WorkerTask",
    "PipelinePlan",
    "PipelineStage",
    "DiscussionPlan",
    "DiscussionContribution",
]

__version__ = "0.1.0"
