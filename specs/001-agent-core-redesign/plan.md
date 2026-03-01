# Implementation Plan: Agent Core 重构

**Branch**: `001-agent-core-redesign` | **Date**: 2026-02-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-agent-core-redesign/spec.md`

## Summary

重新设计 X-Agent 的核心 agent loop，采用 pi-agent 的事件驱动双层循环架构。实现完整的日志观测系统，集成记忆存储和工具经验学习机制。前端新建独立聊天页面，复用现有 UI 组件和交互模式。

## Technical Context

**Language/Version**: Python 3.11+ (Backend) + TypeScript 5.x (Frontend)  
**Primary Dependencies**: FastAPI, asyncio, React 18, TailwindCSS  
**Storage**: 内存存储 (日志) + 现有 MarkdownSync/VectorStore (记忆)  
**Testing**: pytest (Backend), vitest (Frontend)  
**Target Platform**: Local development server  
**Project Type**: Web application (frontend + backend)  
**Performance Goals**: 首字节 <500ms, 中断响应 <200ms, 经验检索 <200ms  
**Constraints**: 单用户场景, 内存日志限制 (1000条)  
**Scale/Scope**: 单会话, 100 LLM 调用记录, 500 工具调用记录

## Module Independence Design (高内聚低耦合)

**核心原则**: `agent_core` 作为系统核心控制器，必须保持独立性，便于移植到其他项目或扩展为独立库。

### 边界定义

```
┌─────────────────────────────────────────────────────────────────┐
│                         agent_core                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Core (零外部依赖)                                           ││
│  │  ├── types.py        # 纯类型定义, 无导入                   ││
│  │  ├── agent_loop.py   # 核心循环, 仅依赖 types              ││
│  │  └── event_stream.py # 事件流, 仅依赖 types                ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Ports (接口定义)                                            ││
│  │  ├── llm_port.py     # LLM 调用接口 (Protocol)              ││
│  │  ├── tool_port.py    # 工具执行接口 (Protocol)              ││
│  │  ├── memory_port.py  # 记忆存储接口 (Protocol)              ││
│  │  └── logger_port.py  # 日志接口 (Protocol)                  ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Adapters (适配器实现)                                       ││
│  │  ├── adapters/llm_adapter.py      # 适配现有 LLM Router    ││
│  │  ├── adapters/memory_adapter.py   # 适配现有 Memory 系统   ││
│  │  └── adapters/logger_adapter.py   # 适配现有日志系统       ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  API Layer (对外接口)                                        ││
│  │  ├── api/websocket.py  # WebSocket 端点                    ││
│  │  └── api/routes.py     # REST API                          ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 依赖注入
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Dependencies                         │
│  ├── services/llm/router.py    # X-Agent LLM 服务              │
│  ├── memory/md_sync.py         # X-Agent 记忆系统              │
│  └── utils/logger.py           # X-Agent 日志系统              │
└─────────────────────────────────────────────────────────────────┘
```

### Port 接口定义 (依赖倒置)

```python
# agent_core/ports/llm_port.py
from typing import Protocol, AsyncIterator
from ..types import AgentMessage, AgentTool, StreamChunk

class LLMPort(Protocol):
    """LLM 调用接口 - agent_core 不关心具体实现"""
    
    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[AgentTool] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """流式生成响应"""
        ...

# agent_core/ports/memory_port.py
class MemoryPort(Protocol):
    """记忆存储接口"""
    
    async def store(self, content: str, metadata: dict) -> str:
        """存储记忆, 返回 ID"""
        ...
    
    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """检索相关记忆"""
        ...

# agent_core/ports/tool_port.py
class ToolPort(Protocol):
    """工具执行接口"""
    
    async def execute(
        self,
        tool_name: str,
        arguments: dict,
        abort_event: asyncio.Event | None = None,
    ) -> ToolResult:
        """执行工具"""
        ...
```

### 依赖注入配置

```python
# agent_core/config.py
from dataclasses import dataclass
from .ports.llm_port import LLMPort
from .ports.memory_port import MemoryPort
from .ports.tool_port import ToolPort

@dataclass
class AgentCoreConfig:
    """Agent Core 配置 - 通过依赖注入连接外部系统"""
    
    # 必需的端口
    llm: LLMPort
    
    # 可选的端口 (有默认实现)
    memory: MemoryPort | None = None
    tools: list[ToolPort] = field(default_factory=list)
    
    # 配置项
    model: str = ""
    thinking_level: str = "off"
    enable_memory: bool = True
    enable_experience_learning: bool = True
```

### 移植性保证

| 场景 | 方案 |
|------|------|
| 移植到新项目 | 仅需实现 `LLMPort` 接口 |
| 更换 LLM 提供商 | 新增 Adapter, 不改 Core |
| 更换记忆存储 | 实现 `MemoryPort`, 注入配置 |
| 作为独立库发布 | Core + Ports 可独立打包 |

### 依赖规则

1. **Core 层** - 零外部导入, 仅依赖标准库和 types
2. **Ports 层** - 仅定义 Protocol, 无实现
3. **Adapters 层** - 可依赖外部系统, 实现 Ports
4. **API 层** - 可依赖 FastAPI 等框架

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Check Item | Status | Notes |
|------------|--------|-------|
| 代码质量优先 | PASS | 使用类型注解, 结构化日志 |
| 测试驱动开发 | PASS | 核心模块需单元测试 |
| 关注点分离 | PASS | agent_core 独立模块, Port/Adapter 分离 |
| 可调试性设计 | PASS | 完整日志系统, trace_id 追踪 |
| 性能优先 | PASS | 流式响应, 异步 I/O |
| 组合优于继承 | PASS | 函数式 agent_loop, 依赖注入 |
| YAGNI | PASS | 仅实现确认需求, 不做多用户支持 |
| **高内聚低耦合** | PASS | Core 零依赖, 通过 Port 隔离外部系统 |

## Project Structure

### Documentation (this feature)

```text
specs/001-agent-core-redesign/
├── spec.md              # 功能规范
├── plan.md              # 本文件
├── checklists/
│   └── requirements.md  # 质量检查清单
└── tasks.md             # 任务列表 (待生成)
```

### Source Code (repository root)

```text
backend/src/
├── agent_core/                    # [NEW] Agent Core 模块 (独立可移植)
│   ├── __init__.py
│   │
│   ├── # === Core Layer (零外部依赖) ===
│   ├── types.py                   # 核心类型定义
│   ├── agent_loop.py              # Agent Loop 核心实现
│   ├── agent.py                   # Agent 类封装
│   ├── event_stream.py            # 异步事件流
│   ├── config.py                  # 配置与依赖注入
│   │
│   ├── # === Ports Layer (接口定义) ===
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── llm_port.py            # LLM 调用接口
│   │   ├── tool_port.py           # 工具执行接口
│   │   ├── memory_port.py         # 记忆存储接口
│   │   └── logger_port.py         # 日志接口
│   │
│   ├── # === Adapters Layer (适配现有系统) ===
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── llm_adapter.py         # 适配 X-Agent LLM Router
│   │   ├── memory_adapter.py      # 适配 X-Agent Memory 系统
│   │   ├── tool_adapter.py        # 适配 X-Agent 工具系统
│   │   └── logger_adapter.py      # 适配 X-Agent 日志系统
│   │
│   ├── # === Internal Services ===
│   ├── logger.py                  # 内置日志实现
│   ├── tool_executor.py           # 工具执行器
│   ├── context_transform.py       # 上下文转换
│   ├── memory_integration.py      # 记忆集成逻辑
│   └── experience_learning.py     # 经验学习逻辑
│   │
│   └── # === API Layer ===
│       api/
│       ├── __init__.py
│       ├── websocket.py           # WebSocket 端点
│       └── routes.py              # REST API (日志查询)
│
├── memory/                        # [EXTERNAL] 现有记忆系统
│   └── ...
├── services/
│   └── llm/                       # [EXTERNAL] 现有 LLM 服务
│       └── router.py
└── ...

frontend/src/
├── pages/
│   └── chat/                      # [NEW] 独立聊天页面
│       ├── index.tsx
│       ├── ChatPage.tsx
│       ├── components/
│       │   ├── AgentChatWindow.tsx
│       │   ├── AgentMessageList.tsx
│       │   ├── AgentMessageItem.tsx
│       │   ├── ToolCallCard.tsx
│       │   └── DebugPanel.tsx
│       ├── hooks/
│       │   └── useAgent.ts
│       └── types.ts
├── components/                    # [REUSE] 现有组件
│   ├── chat/
│   └── ui/
└── hooks/                         # [REUSE] 现有 hooks
    ├── useChat.ts
    └── useWebSocket.ts
```

**Structure Decision**: 
- `agent_core` 采用 **Port/Adapter 架构** 实现高内聚低耦合
- Core 层零外部依赖，可独立移植
- 通过 Adapters 连接 X-Agent 现有系统
- 前端独立页面，复用现有 UI 组件

## Implementation Phases

### Phase 0: Research & Foundation

**目标**: 确认技术可行性, 理解现有代码

| 任务 | 说明 |
|------|------|
| 分析 pi-agent 源码 | 理解双层循环、事件流、steering 机制 |
| 分析现有 orchestrator | 理解现有工具执行、LLM 调用流程 |
| 分析现有 memory 系统 | 确认 MarkdownSync, HybridSearch 接口 |
| 确认 LLM router 接口 | 确认流式响应接口 |
| **定义 Port 接口** | 设计 LLMPort, MemoryPort, ToolPort |

### Phase 1: Core Types & Ports

**目标**: 实现核心类型定义和 Port 接口

| 文件 | 说明 |
|------|------|
| `agent_core/types.py` | 消息、事件、配置等类型定义 (零依赖) |
| `agent_core/ports/llm_port.py` | LLM 调用 Protocol |
| `agent_core/ports/tool_port.py` | 工具执行 Protocol |
| `agent_core/ports/memory_port.py` | 记忆存储 Protocol |
| `agent_core/ports/logger_port.py` | 日志 Protocol |
| `agent_core/config.py` | 依赖注入配置 |

**关键设计决策**:
- 使用 `dataclass` 定义所有类型
- 使用 `Protocol` 定义接口 (结构化子类型)
- Core 层仅依赖标准库

### Phase 2: Agent Loop Core

**目标**: 实现 Agent Loop 核心逻辑

| 文件 | 说明 |
|------|------|
| `agent_core/agent_loop.py` | 双层循环核心实现 |
| `agent_core/agent.py` | Agent 类封装 (管理状态和订阅) |
| `agent_core/event_stream.py` | 事件流实现 |
| `agent_core/tool_executor.py` | 工具执行器 |

**关键设计决策**:
- `agent_loop` 为 AsyncGenerator, yield 事件
- 支持 `abort_event` 中断机制
- 支持 `get_steering_messages` 和 `get_follow_up_messages` 回调
- 通过 Port 接口调用外部系统

### Phase 3: Logging & Observability

**目标**: 实现完整日志观测系统

| 文件 | 说明 |
|------|------|
| `agent_core/logger.py` | 内置 AgentLogger 实现 |
| `agent_core/api/routes.py` | 日志查询 REST API |

**日志记录点**:
- `agent_loop_start/end`
- `llm_call_start/end` (含完整 prompt 和响应)
- `tool_call_start/end` (含入参和结果)
- `steering_messages_injected`
- `follow_up_messages`
- `agent_loop_error/aborted`

### Phase 4: Adapters (适配 X-Agent)

**目标**: 实现适配器连接 X-Agent 现有系统

| 文件 | 说明 |
|------|------|
| `agent_core/adapters/llm_adapter.py` | 适配 `services/llm/router.py` |
| `agent_core/adapters/memory_adapter.py` | 适配 `memory/md_sync.py`, `hybrid_search.py` |
| `agent_core/adapters/tool_adapter.py` | 适配现有工具系统 |
| `agent_core/adapters/logger_adapter.py` | 适配 `utils/logger.py` |

**适配策略**:
- 每个 Adapter 实现对应的 Port Protocol
- 处理 X-Agent 特有的配置和初始化
- 错误转换为 agent_core 标准格式

### Phase 5: Memory & Experience Integration

**目标**: 集成记忆存储和经验学习

| 文件 | 说明 |
|------|------|
| `agent_core/memory_integration.py` | 工具调用记忆写入逻辑 |
| `agent_core/experience_learning.py` | 经验提取与检索逻辑 |

**集成点**:
- 工具执行后自动写入记忆 (通过 MemoryPort)
- LLM 调用前检索相关经验 (通过 MemoryPort)
- 对话结束后提取经验教训

### Phase 6: WebSocket API

**目标**: 实现 WebSocket 端点

| 文件 | 说明 |
|------|------|
| `agent_core/api/websocket.py` | WebSocket 处理器 |

**WebSocket 协议**:
```
客户端 → 服务端:
  { type: "prompt", content: "...", images: [...] }
  { type: "steer", content: "..." }
  { type: "follow_up", content: "..." }
  { type: "abort" }

服务端 → 客户端:
  { type: "agent_start", trace_id: "..." }
  { type: "message_update", message: {...}, delta: "..." }
  { type: "tool_execution_start", tool_call_id: "...", tool_name: "..." }
  { type: "agent_end", messages: [...] }
  { type: "error", error: "..." }
```

### Phase 7: Frontend Implementation

**目标**: 实现前端聊天页面

| 文件 | 说明 |
|------|------|
| `pages/chat/types.ts` | 前端类型定义 |
| `pages/chat/hooks/useAgent.ts` | Agent 状态管理 hook |
| `pages/chat/ChatPage.tsx` | 主页面组件 |
| `pages/chat/components/DebugPanel.tsx` | 调试面板 |

**复用现有组件**:
- 布局参考 `ChatWindow.tsx`
- 消息渲染参考 `MessageItem.tsx`
- 工具卡片参考 `TerminalCard.tsx`
- 基础组件复用 `components/ui/*`

### Phase 8: Integration & Testing

**目标**: 集成测试和端到端验证

| 任务 | 说明 |
|------|------|
| 单元测试 | agent_loop, logger (使用 Mock Port) |
| Port 测试 | 验证 Adapter 正确实现 Port |
| 集成测试 | WebSocket API, 日志查询 API |
| 端到端测试 | 前端发送消息 → 后端处理 → 前端更新 |
| 移植性测试 | 仅使用 Core + Mock Ports 运行 |

## Key Technical Decisions

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 消息类型系统 | TypedDict vs dataclass | dataclass | 类型安全, IDE 支持更好 |
| 事件流实现 | Callback vs AsyncGenerator | AsyncGenerator | 更符合 Python async 模式 |
| 日志存储 | 文件 vs 内存 vs DB | 内存 | 简单, 单用户场景足够 |
| 前端状态管理 | Redux vs Hook | Hook (useAgent) | 简单, 局部状态足够 |
| WebSocket 库 | websockets vs FastAPI WS | FastAPI WS | 与现有项目一致 |

## Risk & Mitigation

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 现有 LLM router 不支持流式 | 高 | 确认接口, 必要时适配 |
| 记忆系统写入影响性能 | 中 | 异步写入, 非阻塞 |
| 经验检索延迟过高 | 中 | 设置超时, 可降级跳过 |
| WebSocket 连接不稳定 | 低 | 自动重连, 状态恢复 |

## Dependencies

**后端依赖**:
- 现有 `services/llm/router.py` - LLM 调用
- 现有 `memory/md_sync.py` - 记忆写入
- 现有 `memory/hybrid_search.py` - 经验检索
- 现有 `services/error_learning.py` - 错误学习

**前端依赖**:
- 现有 `hooks/useWebSocket.ts` - WebSocket 连接模式
- 现有 `components/ui/*` - 基础组件
- 现有 `components/chat/*` - 聊天组件参考

## Technical Reference

详细技术设计: `arch/pi-agent-loop-tech.md`

包含:
- 完整 Python 类型定义
- Agent Loop 伪代码实现
- 日志系统详细设计
- 前端 TypeScript 类型定义
- useAgent hook 实现
- DebugPanel 组件实现
- REST API 端点定义
