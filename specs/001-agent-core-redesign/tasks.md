# Tasks: Agent Core 重构

**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Generated**: 2026-02-28

## Overview

本任务列表覆盖 Agent Core 重构的完整实现，采用 Port/Adapter 架构实现高内聚低耦合。

---

## Phase 0: Research & Foundation

> **目标**: 确认技术可行性，理解现有代码，定义 Port 接口

### 0.1 分析 x-agent 源码
- [x] **T0.1.1** 分析 `agent.ts` - 理解 Agent 类结构和状态管理
- [x] **T0.1.2** 分析 `agent-loop.ts` - 理解双层循环架构（外层 follow-up，内层 tool calls + steering）
- [x] **T0.1.3** 提取事件流模型 - 记录事件类型和触发时机
- [x] **T0.1.4** 理解 steering 机制 - 中断和跳过工具的实现方式

### 0.2 分析现有 X-Agent 系统
- [x] **T0.2.1** 分析 `services/llm/router.py` - 确认流式响应接口和 failover 机制
- [x] **T0.2.2** 分析 `memory/md_sync.py` - 理解记忆写入接口
- [x] **T0.2.3** 分析 `memory/hybrid_search.py` - 理解经验检索接口
- [x] **T0.2.4** 分析现有 orchestrator - 理解现有工具执行流程

### 0.3 创建目录结构
- [x] **T0.3.1** 创建 `backend/src/agent_core/` 目录
- [x] **T0.3.2** 创建 `backend/src/agent_core/ports/` 目录
- [x] **T0.3.3** 创建 `backend/src/agent_core/adapters/` 目录
- [x] **T0.3.4** 创建 `backend/src/agent_core/api/` 目录
- [ ] **T0.3.5** 创建 `frontend/src/pages/chat/` 目录结构

**验收条件**: Phase 0 完成后应具备完整的目录结构和对现有系统的理解

---

## Phase 1: Core Types & Ports

> **目标**: 实现核心类型定义和 Port 接口（零外部依赖）

### 1.1 核心类型定义
- [x] **T1.1.1** 创建 `agent_core/__init__.py` - 模块初始化和公开 API
- [x] **T1.1.2** 创建 `agent_core/types.py` - 内容类型定义
  - `TextContent`, `ImageContent`, `ThinkingContent`, `ToolCallContent`
  - `Content` 联合类型
- [x] **T1.1.3** 补充 `types.py` - 消息类型定义
  - `UserMessage`, `AssistantMessage`, `ToolResultMessage`
  - `AgentMessage` 联合类型
- [x] **T1.1.4** 补充 `types.py` - 事件类型定义
  - `AgentStartEvent`, `AgentEndEvent`
  - `TurnStartEvent`, `TurnEndEvent`
  - `MessageStartEvent`, `MessageUpdateEvent`, `MessageEndEvent`
  - `ToolExecutionStartEvent`, `ToolExecutionUpdateEvent`, `ToolExecutionEndEvent`
  - `AgentEvent` 联合类型
- [x] **T1.1.5** 补充 `types.py` - 工具和配置类型
  - `ToolParameter`, `AgentTool`, `ToolResult`
  - `AgentContext`, `AgentLoopConfig`, `AgentState`
- [x] **T1.1.6** 补充 `types.py` - 流式数据类型
  - `StreamChunk` (text_delta, thinking_delta, tool_call, done)

### 1.2 Port 接口定义
- [x] **T1.2.1** 创建 `ports/__init__.py` - 导出所有 Port
- [x] **T1.2.2** 创建 `ports/llm_port.py` - LLM 调用 Protocol
  - `stream()` 方法定义
  - 输入/输出类型约束
- [x] **T1.2.3** 创建 `ports/tool_port.py` - 工具执行 Protocol
  - `execute()` 方法定义
  - `get_tools()` 方法定义
- [x] **T1.2.4** 创建 `ports/memory_port.py` - 记忆存储 Protocol
  - `store()` 方法定义
  - `search()` 方法定义
- [x] **T1.2.5** 创建 `ports/logger_port.py` - 日志 Protocol
  - `log()`, `log_llm_call_start/end()`, `log_tool_call_start/end()` 方法定义

### 1.3 配置和依赖注入
- [x] **T1.3.1** 创建 `agent_core/config.py` - AgentCoreConfig
  - 必需端口：`llm: LLMPort`
  - 可选端口：`memory`, `tools`, `logger`
  - 配置项：`model`, `thinking_level`, `enable_memory`, `enable_experience_learning`

**验收条件**: 
- 所有类型使用 `dataclass` 定义
- Port 使用 `Protocol` 定义（结构化子类型）
- Core 层零外部依赖（仅标准库）
- 运行 `python -c "from agent_core.types import *"` 无错误

---

## Phase 2: Agent Loop Core

> **目标**: 实现 Agent Loop 核心逻辑（双层循环架构）

### 2.1 事件流实现
- [x] **T2.1.1** 创建 `agent_core/event_stream.py` - EventStream 类
  - 异步事件发布/订阅机制
  - 事件缓冲和广播

### 2.2 Agent Loop 核心
- [x] **T2.2.1** 创建 `agent_core/agent_loop.py` - 主函数骨架
  - `agent_loop()` AsyncGenerator 签名
  - trace_id 生成
  - AgentStartEvent 发送
- [x] **T2.2.2** 实现外层循环 - follow-up 消息处理
  - 循环检测 `get_follow_up_messages()` 回调
  - 继续/退出逻辑
- [x] **T2.2.3** 实现内层循环 - tool calls + steering 处理
  - pending_messages 注入
  - tool calls 检测
  - steering 消息检查和工具跳过
- [x] **T2.2.4** 实现 `_stream_assistant_response()` - 流式 LLM 响应
  - 调用 LLMPort.stream()
  - yield MessageStartEvent, MessageUpdateEvent, MessageEndEvent
  - 处理 text_delta, thinking_delta, tool_call
- [x] **T2.2.5** 实现 abort 机制
  - `abort_event` 检测
  - 优雅中断和资源清理

### 2.3 工具执行器
- [x] **T2.3.1** 创建 `agent_core/tool_executor.py` - 工具执行逻辑
  - `execute_tool_calls()` AsyncGenerator
  - yield ToolExecutionStartEvent, ToolExecutionEndEvent
  - 错误处理和超时
- [x] **T2.3.2** 实现工具跳过逻辑
  - steering 消息检测
  - 跳过剩余工具并生成跳过事件

### 2.4 Agent 类封装
- [x] **T2.4.1** 创建 `agent_core/agent.py` - Agent 类
  - 状态管理（AgentState）
  - 消息队列（steering, follow-up）
  - 订阅/取消订阅事件
- [x] **T2.4.2** 实现便捷方法
  - `prompt()`, `steer()`, `follow_up()`, `abort()`, `continue_loop()`

### 2.5 上下文转换
- [x] **T2.5.1** 创建 `agent_core/context_transform.py`
  - `default_convert_to_llm()` - 消息转 LLM 格式
  - `transform_context()` - 上下文裁剪/压缩（可选）

**验收条件**:
- `agent_loop` 为 AsyncGenerator，yield AgentEvent
- 支持 steering 和 follow-up 消息机制
- 支持 abort_event 中断
- 单元测试覆盖核心路径（使用 Mock Port）

---

## Phase 3: Logging & Observability

> **目标**: 实现完整日志观测系统

### 3.1 日志类型定义
- [ ] **T3.1.1** 在 `types.py` 或新建 `logger_types.py` 添加
  - `LogLevel` 枚举（debug, info, warn, error）
  - `LogCategory` 枚举（agent_loop, llm_call, tool_exec, context, websocket, message）
  - `LogEntry` 数据类
- [ ] **T3.1.2** 添加 LLM 调用日志类型
  - `LLMCallLog` - 完整的 prompt/response 记录
- [ ] **T3.1.3** 添加工具调用日志类型
  - `ToolCallLog` - 入参/结果/耗时记录

### 3.2 AgentLogger 实现
- [ ] **T3.2.1** 创建 `agent_core/logger.py` - AgentLogger 类
  - 内存缓存（deque，限制大小）
  - 线程安全（Lock）
  - trace_id 索引
- [ ] **T3.2.2** 实现日志记录方法
  - `log()` - 通用日志
  - `log_llm_call_start/end()` - LLM 调用日志
  - `log_tool_call_start/end()` - 工具调用日志
- [ ] **T3.2.3** 实现日志查询方法
  - `get_logs()` - 按条件过滤
  - `get_llm_call()`, `get_llm_calls_by_trace()`
  - `get_tool_call()`, `get_tool_calls_by_llm()`
- [ ] **T3.2.4** 实现实时订阅
  - `subscribe()` - 返回 asyncio.Queue
  - `unsubscribe()` - 取消订阅
  - `_broadcast()` - 广播新日志

### 3.3 Agent Loop 日志集成
- [ ] **T3.3.1** 在 `agent_loop.py` 添加日志调用
  - `agent_loop_start/end`
  - `llm_call_start/end`（含完整 prompt 和响应）
  - `tool_call_start/end`（含入参和结果）
  - `steering_messages_injected`
  - `follow_up_messages`
  - `agent_loop_error/aborted`

**验收条件**:
- 内存日志限制：1000 条通用日志，100 条 LLM 调用，500 条工具调用
- 支持按 trace_id, category, level 查询
- 支持实时订阅新日志

---

## Phase 4: Adapters (适配 X-Agent)

> **目标**: 实现适配器连接 X-Agent 现有系统

### 4.1 LLM 适配器
- [ ] **T4.1.1** 创建 `adapters/__init__.py` - 导出所有适配器
- [ ] **T4.1.2** 创建 `adapters/llm_adapter.py` - XAgentLLMAdapter
  - 实现 `LLMPort` Protocol
  - 包装 `services/llm/router.py` 的 `chat()` 方法
  - 转换流式响应为 `StreamChunk`
- [ ] **T4.1.3** 处理 LLM 错误转换
  - 将 X-Agent 错误转换为 agent_core 标准格式

### 4.2 工具适配器
- [ ] **T4.2.1** 创建 `adapters/tool_adapter.py` - XAgentToolAdapter
  - 实现 `ToolPort` Protocol
  - 包装现有工具执行逻辑
  - 支持 abort_event 传递

### 4.3 记忆适配器
- [ ] **T4.3.1** 创建 `adapters/memory_adapter.py` - XAgentMemoryAdapter
  - 实现 `MemoryPort` Protocol
  - 包装 `memory/md_sync.py` 的写入方法
  - 包装 `memory/hybrid_search.py` 的搜索方法
- [ ] **T4.3.2** 实现异步写入
  - 非阻塞记忆存储

### 4.4 日志适配器
- [ ] **T4.4.1** 创建 `adapters/logger_adapter.py` - XAgentLoggerAdapter
  - 实现 `LoggerPort` Protocol
  - 包装 `utils/logger.py` 的日志方法
  - 添加 trace_id 上下文

**验收条件**:
- 每个 Adapter 正确实现对应的 Port Protocol
- 适配器可独立测试（使用 Mock 外部系统）
- 错误转换为 agent_core 标准格式

---

## Phase 5: Memory & Experience Integration

> **目标**: 集成记忆存储和经验学习

### 5.1 记忆集成
- [ ] **T5.1.1** 创建 `agent_core/memory_integration.py`
  - 工具调用结果写入逻辑
  - 记忆摘要生成
- [ ] **T5.1.2** 实现工具调用记忆写入
  - 执行后自动调用 MemoryPort.store()
  - 过滤不重要的工具调用
  - 去重存储逻辑

### 5.2 经验学习
- [ ] **T5.2.1** 创建 `agent_core/experience_learning.py`
  - 经验检索逻辑
  - 经验注入上下文
- [ ] **T5.2.2** 实现 LLM 调用前经验检索
  - 调用 MemoryPort.search()
  - 相关经验注入 system prompt 或消息
- [ ] **T5.2.3** 实现对话结束后经验提取
  - 分析工具调用序列
  - 提取成功模式和失败教训

**验收条件**:
- 工具执行后自动写入记忆（通过 MemoryPort）
- LLM 调用前检索相关经验（通过 MemoryPort）
- 经验检索延迟 <200ms

---

## Phase 6: WebSocket API

> **目标**: 实现 WebSocket 端点

### 6.1 WebSocket 处理器
- [ ] **T6.1.1** 创建 `agent_core/api/__init__.py`
- [ ] **T6.1.2** 创建 `agent_core/api/websocket.py` - WebSocket 端点
  - FastAPI WebSocket 路由
  - 连接管理（连接/断开）
  - 心跳检测

### 6.2 命令处理
- [ ] **T6.2.1** 实现客户端命令解析
  - `prompt` - 发送新消息
  - `steer` - 发送 steering 消息
  - `follow_up` - 发送 follow-up 消息
  - `abort` - 中断当前处理
- [ ] **T6.2.2** 实现事件推送
  - 监听 agent_loop 事件
  - 转换为 JSON 并推送给客户端

### 6.3 REST API
- [ ] **T6.3.1** 创建 `agent_core/api/routes.py` - REST 端点
  - `GET /api/v1/agent/logs` - 日志查询
  - `GET /api/v1/agent/llm-calls` - LLM 调用详情
  - `GET /api/v1/agent/tool-calls` - 工具调用详情
- [ ] **T6.3.2** 实现分页和过滤
  - trace_id, category, level 过滤
  - limit, offset 分页

### 6.4 路由注册
- [ ] **T6.4.1** 在 X-Agent 主应用注册 agent_core 路由
  - 注册 WebSocket 端点
  - 注册 REST API 路由

**验收条件**:
- WebSocket 端点可正常连接和通信
- REST API 返回正确的日志数据
- 支持 abort 命令中断处理

---

## Phase 7: Frontend Implementation

> **目标**: 实现前端聊天页面

### 7.1 类型定义
- [ ] **T7.1.1** 创建 `frontend/src/pages/chat/types.ts`
  - 内容类型（TextContent, ImageContent, ThinkingContent, ToolCallContent）
  - 消息类型（UserMessage, AssistantMessage, ToolResultMessage）
  - 事件类型（AgentEvent 联合类型）
  - 状态类型（AgentState）
  - 命令类型（AgentCommand）
  - 日志类型（LogEntry, LLMCallLog, ToolCallLog）

### 7.2 useAgent Hook
- [ ] **T7.2.1** 创建 `pages/chat/hooks/useAgent.ts`
  - WebSocket 连接管理
  - 自动重连逻辑
- [ ] **T7.2.2** 实现状态管理
  - 处理 AgentEvent 更新状态
  - 管理 messages, streamMessage, pendingToolCalls
- [ ] **T7.2.3** 实现命令发送
  - `prompt()`, `steer()`, `followUp()`, `abort()`, `continueLoop()`

### 7.3 主页面组件
- [ ] **T7.3.1** 创建 `pages/chat/index.tsx` - 入口文件
- [ ] **T7.3.2** 创建 `pages/chat/ChatPage.tsx` - 主页面
  - 布局参考 `ChatWindow.tsx`
  - 连接状态指示
  - 消息输入和发送

### 7.4 消息组件
- [ ] **T7.4.1** 创建 `pages/chat/components/AgentChatWindow.tsx`
  - 整体布局（Header + MessageList + Input）
- [ ] **T7.4.2** 创建 `pages/chat/components/AgentMessageList.tsx`
  - 消息列表渲染
  - 滚动逻辑
- [ ] **T7.4.3** 创建 `pages/chat/components/AgentMessageItem.tsx`
  - 单条消息渲染
  - 用户/助手/工具结果消息样式
- [ ] **T7.4.4** 创建 `pages/chat/components/ToolCallCard.tsx`
  - 工具调用卡片
  - 参考 `TerminalCard.tsx`

### 7.5 调试面板
- [ ] **T7.5.1** 创建 `pages/chat/components/DebugPanel.tsx`
  - 日志列表视图
  - LLM 调用详情视图
  - 工具调用详情视图
- [ ] **T7.5.2** 实现数据获取
  - 调用 REST API 获取日志
  - 轮询更新

### 7.6 路由配置
- [ ] **T7.6.1** 在 `App.tsx` 或路由配置中添加 `/chat` 路由

**验收条件**:
- 聊天页面可正常访问和使用
- 流式消息实时显示
- 工具调用卡片正确展示
- 调试面板显示完整日志

---

## Phase 8: Integration & Testing

> **目标**: 集成测试和端到端验证

### 8.1 单元测试
- [ ] **T8.1.1** 创建 `tests/unit/agent_core/` 目录
- [ ] **T8.1.2** 测试 `types.py` - 类型创建和序列化
- [ ] **T8.1.3** 测试 `agent_loop.py` - 使用 Mock Port
  - 基本消息处理
  - 工具调用流程
  - abort 机制
  - steering 和 follow-up 消息
- [ ] **T8.1.4** 测试 `logger.py`
  - 日志记录和查询
  - 内存限制
  - 实时订阅

### 8.2 Port 测试
- [ ] **T8.2.1** 测试 `llm_adapter.py` - 正确实现 LLMPort
- [ ] **T8.2.2** 测试 `memory_adapter.py` - 正确实现 MemoryPort
- [ ] **T8.2.3** 测试 `tool_adapter.py` - 正确实现 ToolPort

### 8.3 集成测试
- [ ] **T8.3.1** 测试 WebSocket API
  - 连接/断开
  - 命令发送和事件接收
- [ ] **T8.3.2** 测试 REST API
  - 日志查询
  - 分页和过滤

### 8.4 端到端测试
- [ ] **T8.4.1** 测试完整流程
  - 前端发送消息 → 后端处理 → 前端更新
  - 工具调用流程
  - abort 流程

### 8.5 移植性测试
- [ ] **T8.5.1** 测试仅使用 Core + Mock Ports 运行
  - 验证 Core 层零外部依赖
  - 验证可独立打包

### 8.6 性能测试
- [ ] **T8.6.1** 验证首字节延迟 <500ms
- [ ] **T8.6.2** 验证中断响应 <200ms
- [ ] **T8.6.3** 验证经验检索 <200ms

**验收条件**:
- 单元测试覆盖率 >80%
- 所有集成测试通过
- 性能指标达标

---

## Task Summary

| Phase | 任务数 | 状态 |
|-------|--------|------|
| Phase 0: Research & Foundation | 14 | Pending |
| Phase 1: Core Types & Ports | 12 | Pending |
| Phase 2: Agent Loop Core | 14 | Pending |
| Phase 3: Logging & Observability | 10 | Pending |
| Phase 4: Adapters | 8 | Pending |
| Phase 5: Memory & Experience | 6 | Pending |
| Phase 6: WebSocket API | 8 | Pending |
| Phase 7: Frontend | 14 | Pending |
| Phase 8: Testing | 12 | Pending |
| **Total** | **98** | - |

---

## Dependencies Graph

```
Phase 0 (Research)
    │
    ▼
Phase 1 (Types & Ports) ──────────────────┐
    │                                      │
    ▼                                      │
Phase 2 (Agent Loop Core)                  │
    │                                      │
    ├───────────────┐                      │
    ▼               ▼                      │
Phase 3          Phase 4                   │
(Logging)        (Adapters) ◄──────────────┘
    │               │
    └───────┬───────┘
            │
            ▼
      Phase 5 (Memory & Experience)
            │
            ▼
      Phase 6 (WebSocket API)
            │
            ▼
      Phase 7 (Frontend)
            │
            ▼
      Phase 8 (Testing)
```

---

## Critical Path

1. **T1.1.2** types.py 核心类型 → **T1.2.2** LLMPort → **T2.2.1** agent_loop 骨架
2. **T4.1.2** LLM 适配器 → **T6.1.2** WebSocket 端点 → **T7.2.1** useAgent Hook
3. **T8.4.1** 端到端测试验证完整流程

---

## Notes

- 所有 Phase 1 任务完成后，运行 `python -c "from agent_core import *"` 验证无错误
- 所有 Phase 2 任务完成后，可使用 Mock Port 运行 agent_loop 单元测试
- Phase 4-5 可并行开发
- Phase 7 可在 Phase 6 完成后立即开始
