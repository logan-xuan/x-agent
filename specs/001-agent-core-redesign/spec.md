# Feature Specification: Agent Core 重构

**Feature Branch**: `001-agent-core-redesign`  
**Created**: 2026-02-28  
**Status**: Draft  
**Input**: 重新设计 agent loop 核心，参考 x-agent 设计模式，前端新建独立聊天页面，后端重构 agent-loop 和编排流程，增加完整日志观测系统

## Overview

对现有 X-Agent 的核心 agent loop 进行重构，采用事件驱动架构，实现更清晰的消息流、工具执行和上下文管理。同时集成记忆系统，支持工具经验学习和智能工具选择。

### Goals

1. **解耦与简化** - 将复杂的 orchestrator 逻辑简化为纯粹的 agent loop
2. **事件驱动** - 通过事件流驱动 UI 更新，支持流式响应
3. **可观测性** - 完整记录每次 LLM 调用和工具执行的详细日志
4. **可中断** - 支持 steering（中断）和 follow-up（追加）消息机制
5. **记忆集成** - 工具调用结果写入记忆，支持经验检索和学习
6. **智能工具选择** - 基于历史经验优化工具选择和参数推荐

### x-Agent 核心设计思想（参考）

本重构参考 x-agent 的核心设计模式：

**1. 双层循环架构**
- 外层循环：处理 follow-up messages（agent 结束后的追加消息）
- 内层循环：处理 tool calls + steering messages（中断消息）

**2. 消息抽象层**
- 整个流程使用 AgentMessage，仅在 LLM 调用边界通过 convertToLlm() 转换
- 支持自定义消息类型扩展

**3. 上下文管道**
- AgentMessage[] → transformContext() → AgentMessage[] → convertToLlm() → Message[] → LLM
- 支持上下文裁剪、压缩和动态注入

**4. 事件流模型**
- agent_start → turn_start → message_start → message_update* → message_end → tool_execution_* → turn_end → agent_end

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 基础对话交互 (Priority: P1)

作为用户，我希望通过新的聊天界面与 AI 进行对话，能够看到 AI 的流式响应，并在需要时中断当前对话。

**Why this priority**: 这是 agent 的核心能力，没有基础对话功能，其他功能都无法使用。

**Independent Test**: 可以通过打开聊天页面、发送消息、观察流式响应来独立测试，验证 agent loop 的基本运作。

**Acceptance Scenarios**:

1. **Given** 用户打开聊天页面, **When** 发送一条文本消息, **Then** AI 开始流式返回响应，用户能实时看到文字逐字出现
2. **Given** AI 正在生成响应, **When** 用户点击"停止"按钮, **Then** AI 立即停止响应，已生成的内容保留在对话中
3. **Given** 对话进行中, **When** 网络连接断开, **Then** 系统显示连接状态，并在恢复后自动重连

---

### User Story 2 - 工具调用与执行 (Priority: P1)

作为用户，当 AI 需要执行工具（如读取文件、搜索等）时，我希望能清晰看到工具的调用过程和执行结果。

**Why this priority**: 工具执行是 agent 的核心能力之一，与基础对话同等重要。

**Independent Test**: 可以通过发送需要工具调用的请求（如"帮我读取某文件"），观察工具调用卡片的显示和执行结果。

**Acceptance Scenarios**:

1. **Given** 用户发送需要工具调用的请求, **When** AI 决定调用工具, **Then** 界面显示工具调用卡片，包含工具名称和参数
2. **Given** 工具正在执行, **When** 执行完成, **Then** 工具卡片显示执行结果和耗时
3. **Given** AI 需要调用多个工具, **When** 用户发送中断消息, **Then** 剩余未执行的工具被跳过，AI 响应中断消息

---

### User Story 3 - 工具执行记忆存储 (Priority: P1)

作为系统，当工具执行完成后，我希望将重要的工具调用结果存储到记忆系统中，便于后续检索和学习。

**Why this priority**: 记忆存储是经验学习的基础，与工具执行同等重要。

**Independent Test**: 可以通过执行工具调用后，查询记忆系统验证是否存储了相关记录。

**Acceptance Scenarios**:

1. **Given** 工具执行成功, **When** 结果包含有价值的信息, **Then** 系统自动将工具调用摘要写入记忆存储
2. **Given** 工具执行失败, **When** 错误信息具有参考价值, **Then** 系统记录错误模式和上下文，便于后续避免
3. **Given** 存在相似的历史工具调用, **When** 用户发起类似请求, **Then** 系统能检索到相关记忆并注入上下文

---

### User Story 4 - 工具选择与经验推荐 (Priority: P2)

作为 AI，在决定调用哪个工具时，我希望能参考历史经验，选择最合适的工具和参数。

**Why this priority**: 智能工具选择能提升效率，但不是核心必需功能。

**Independent Test**: 可以通过发送曾经处理过的类似请求，观察系统是否给出更优的工具选择建议。

**Acceptance Scenarios**:

1. **Given** 用户请求需要工具调用, **When** 存在相似的成功案例, **Then** 系统在选择工具时参考历史成功经验
2. **Given** 某工具在类似场景多次失败, **When** AI 准备调用该工具, **Then** 系统提示可能的风险或替代方案
3. **Given** 工具参数复杂, **When** 历史有成功的参数组合, **Then** 系统建议使用验证过的参数模式

---

### User Story 5 - 经验反思与学习 (Priority: P2)

作为系统，在一次对话完成后，我希望能从工具调用的成功/失败中提取经验教训，持续优化未来的决策。

**Why this priority**: 经验反思是持续改进的机制，提升长期效果。

**Independent Test**: 可以通过查看经验学习日志，验证系统是否从工具调用中提取了有价值的经验。

**Acceptance Scenarios**:

1. **Given** 一次对话包含多个工具调用, **When** 对话结束, **Then** 系统分析工具调用序列，提取成功模式
2. **Given** 某个工具调用失败后通过重试或换方案成功, **When** 系统检测到这种修复模式, **Then** 记录问题-解决方案对到经验库
3. **Given** 用户对 AI 的工具使用给出反馈, **When** 反馈为负面, **Then** 系统记录反馈并调整未来的工具选择偏好

---

### User Story 6 - 日志观测与调试 (Priority: P2)

作为开发者，我希望能查看每次 LLM 调用和工具执行的详细日志，便于调试和问题排查。

**Why this priority**: 日志观测对开发调试至关重要，但不影响终端用户的核心体验。

**Independent Test**: 可以通过打开调试面板，查看当前会话的 LLM 调用记录和工具执行记录。

**Acceptance Scenarios**:

1. **Given** 用户完成一次对话, **When** 打开调试面板, **Then** 能看到该对话的所有日志条目，按时间排序
2. **Given** 调试面板打开, **When** 点击某次 LLM 调用, **Then** 能查看完整的 prompt（system prompt + 历史消息）和响应内容
3. **Given** 有工具被调用, **When** 在调试面板查看, **Then** 能看到工具的入参、执行结果和耗时

---

### User Story 7 - 对话历史管理 (Priority: P3)

作为用户，我希望我的对话历史能够被保存，下次打开页面时能继续之前的对话。

**Why this priority**: 对话持久化是提升用户体验的功能，但不是核心必需。

**Independent Test**: 可以通过发送几条消息后刷新页面，验证对话历史是否保留。

**Acceptance Scenarios**:

1. **Given** 用户进行了一段对话, **When** 刷新页面, **Then** 之前的对话历史仍然显示
2. **Given** 用户想开始新对话, **When** 点击"新建会话", **Then** 创建新的空白会话，之前的会话可以在历史中找到

---

### Edge Cases

- 当 LLM 服务不可用时，系统显示明确的错误信息并允许用户重试
- 当工具执行超时时，系统返回超时错误并允许用户选择继续或中断
- 当用户快速连续发送多条消息时，系统按顺序处理，支持消息队列
- 当 WebSocket 连接断开时，系统自动尝试重连，并在重连期间缓存用户操作
- 当日志量过大时，系统自动清理旧日志，保留最近的记录
- 当记忆存储写入失败时，系统记录错误但不影响主流程
- 当经验检索超时时，系统跳过经验注入，使用默认行为

## Requirements *(mandatory)*

### Functional Requirements

**核心 Agent Loop（参考 x-agent）**

- **FR-001**: 系统 MUST 支持通过 WebSocket 进行实时双向通信
- **FR-002**: 系统 MUST 支持流式响应，用户能实时看到 AI 生成的内容
- **FR-003**: 系统 MUST 支持用户中断正在进行的 AI 响应（steering 机制）
- **FR-004**: 系统 MUST 支持在 AI 完成响应后追加消息（follow-up 机制）
- **FR-005**: 系统 MUST 在 AI 调用工具时顺序执行，并在检测到 steering 消息时跳过剩余工具
- **FR-006**: 系统 MUST 实现双层循环架构：外层处理 follow-up，内层处理 tool calls + steering

**消息与事件**

- **FR-007**: 系统 MUST 支持用户消息（文本和图片）
- **FR-008**: 系统 MUST 支持助手消息（文本、思考内容、工具调用）
- **FR-009**: 系统 MUST 支持工具结果消息（成功结果或错误信息）
- **FR-010**: 系统 MUST 发送事件通知前端 UI 更新（agent_start/end, turn_start/end, message_start/update/end, tool_execution_start/update/end）
- **FR-011**: 系统 MUST 支持上下文转换管道（transformContext → convertToLlm）

**记忆存储集成**

- **FR-012**: 系统 MUST 在工具执行完成后，将重要结果写入记忆存储
- **FR-013**: 系统 MUST 支持工具调用的去重存储，避免重复记录相似内容
- **FR-014**: 系统 MUST 为每个工具调用记录生成摘要，包含工具名、参数摘要、结果摘要、是否成功
- **FR-015**: 系统 MUST 支持通过混合搜索（向量+文本）检索相关的历史工具调用

**工具选择与经验推荐**

- **FR-016**: 系统 MUST 在 LLM 调用前，检索相关的历史工具使用经验
- **FR-017**: 系统 MUST 支持将检索到的经验注入 system prompt 或消息上下文
- **FR-018**: 系统 MUST 跟踪工具的成功率，对于低成功率工具给出警告
- **FR-019**: 系统 SHOULD 支持工具参数的智能推荐，基于历史成功案例

**经验反思与学习**

- **FR-020**: 系统 MUST 在对话结束后，分析工具调用序列，识别成功模式
- **FR-021**: 系统 MUST 检测"失败-重试-成功"的修复模式，提取问题-解决方案对
- **FR-022**: 系统 SHOULD 支持用户反馈机制，用于调整工具选择偏好
- **FR-023**: 系统 MUST 支持经验的定期清理，移除过时或低价值的记录

**日志观测**

- **FR-024**: 系统 MUST 记录每次 LLM 调用的完整信息（模型、prompt、响应、token 用量、耗时）
- **FR-025**: 系统 MUST 记录每次工具调用的完整信息（工具名、入参、结果、耗时、是否出错）
- **FR-026**: 系统 MUST 支持通过 trace_id 关联同一请求链路的所有日志
- **FR-027**: 系统 MUST 提供日志查询接口，支持按 trace_id、类别、级别筛选

**前端界面**

- **FR-028**: 前端 MUST 提供独立的聊天页面
- **FR-029**: 前端 MUST 实时显示消息流式更新
- **FR-030**: 前端 MUST 显示工具调用状态和结果
- **FR-031**: 前端 MUST 提供调试面板，展示日志和 LLM/工具调用详情
- **FR-032**: 前端 MUST 显示连接状态（已连接/断开/重连中）

### Key Entities

**核心消息与事件**

- **AgentMessage**: 代表对话中的一条消息，可以是用户消息、助手消息或工具结果消息
- **AgentEvent**: 代表 agent loop 中发生的事件，用于驱动 UI 更新
- **AgentContext**: 包含系统提示、消息历史和可用工具的上下文
- **AgentState**: agent 的运行时状态，包括是否在流式响应、当前消息、待执行工具等

**日志与观测**

- **LLMCallLog**: LLM 调用的日志记录，包含完整的输入输出和性能指标
- **ToolCallLog**: 工具调用的日志记录，包含入参、结果和执行状态
- **LogEntry**: 通用日志条目，支持不同类别和级别

**记忆与经验**

- **ToolCallMemory**: 工具调用的记忆记录，包含摘要、成功状态、关联上下文
- **ToolExperience**: 从工具调用中提取的经验，包含成功模式、失败教训、参数推荐
- **ErrorPattern**: 错误模式记录，用于识别重复性问题
- **LearnedLesson**: 从失败修复中学到的教训，包含问题-解决方案对

## Assumptions

1. **x-agent 设计模式适用**: 假设 x-agent 的事件驱动、双层循环架构适合 X-Agent 的需求
2. **WebSocket 连接稳定性**: 假设 WebSocket 连接在大多数情况下是稳定的，断线重连是异常情况
3. **日志内存存储**: 假设日志暂时存储在内存中，后续可扩展到持久化存储
4. **单用户场景**: 假设当前主要针对单用户本地使用场景
5. **现有工具可复用**: 假设现有的工具定义和执行逻辑可以复用，只需适配新的接口
6. **现有记忆系统可复用**: 假设现有的 MarkdownSync、HybridSearch 等记忆组件可以复用
7. **经验检索延迟可接受**: 假设经验检索带来的额外延迟（<200ms）对用户体验影响可接受

## Success Criteria *(mandatory)*

### Measurable Outcomes

**响应性能**

- **SC-001**: 用户发送消息后，首个响应字符在 500ms 内开始显示
- **SC-002**: 用户点击"停止"后，响应在 200ms 内停止
- **SC-003**: WebSocket 断开后，系统在 5 秒内自动尝试重连

**日志观测**

- **SC-004**: 工具调用的入参和结果能在调试面板中 100% 完整显示
- **SC-005**: 每次 LLM 调用的 token 用量和耗时能准确记录
- **SC-006**: 调试面板能显示最近 100 条 LLM 调用记录和 500 条工具调用记录
- **SC-007**: 开发者能通过 trace_id 追踪一次完整请求的所有相关日志

**记忆与经验**

- **SC-008**: 工具调用记忆存储成功率达到 95% 以上
- **SC-009**: 经验检索延迟控制在 200ms 以内
- **SC-010**: 相似场景下，系统能检索到相关历史经验的准确率达到 80%
- **SC-011**: 经验注入后，重复性错误发生率降低 50%

## Out of Scope

- 多用户会话隔离和权限管理
- 日志的持久化存储和长期归档
- 复杂的上下文压缩和 token 管理策略
- 与现有 orchestrator 的兼容层
- 生产环境的安全加固
- 跨会话的经验迁移和共享
- 自动化的经验验证和质量评估

## UI Design Reference（前端设计范式）

新的聊天页面应**复用现有 `frontend/src/` 的 UI 组件和交互模式**，保持视觉和交互一致性。

### 参考现有组件

| 组件 | 路径 | 复用说明 |
|------|------|----------|
| ChatWindow | `components/chat/ChatWindow.tsx` | 整体布局结构（Header + MessageList + Input） |
| MessageList | `components/chat/MessageList.tsx` | 消息列表渲染和滚动逻辑 |
| MessageItem | `components/chat/MessageItem.tsx` | 单条消息渲染（用户/助手/系统） |
| MessageInput | `components/chat/MessageInput.tsx` | 输入框和发送按钮交互 |
| TerminalCard | `components/chat/TerminalCard.tsx` | 工具调用卡片展示参考 |
| DevModeWindow | `components/dev/DevModeWindow.tsx` | 调试面板布局参考 |
| UI 基础组件 | `components/ui/*` | Button、Badge、Card、Spinner 等基础组件 |

### 参考现有 Hooks

| Hook | 路径 | 复用说明 |
|------|------|----------|
| useChat | `hooks/useChat.ts` | WebSocket 消息处理、状态管理模式参考 |
| useWebSocket | `hooks/useWebSocket.ts` | WebSocket 连接管理、重连逻辑参考 |

### 现有 UI 交互模式

**1. 连接状态指示**
- 三态显示：已连接（绿点）、连接中（黄点闪烁）、已断开（红点）
- 断开时显示遮罩层和重连提示

**2. 消息流式更新**
- `streamingContent` 状态保存流式内容
- 实时追加显示，完成后转为完整消息

**3. 工具调用展示**
- 工具调用嵌入 assistant 消息中
- 状态流转：executing → completed/error/needs_confirmation
- 结果展示在工具卡片内

**4. 会话管理**
- localStorage 持久化 session_id
- 支持新建会话和加载历史

**5. WebSocket 消息类型**
- `chunk`: 流式内容块
- `message/final_answer`: 完整消息
- `tool_call`: 工具调用开始
- `tool_result`: 工具执行结果
- `error`: 错误消息
- `system`: 系统日志

### 新增交互需求

在复用现有模式的基础上，新增以下交互：

1. **停止按钮** - 在流式响应时显示，点击发送 abort 命令
2. **调试面板增强** - 展示 LLM 调用详情和工具调用日志
3. **经验提示** - 在工具调用时显示相关历史经验（可选）

## Technical Reference

详细技术设计参考：`arch/agent-core-loop-tech.md`

该文档包含：
- 完整的类型定义（Python + TypeScript）
- Agent Loop 核心实现伪代码
- 日志系统详细设计
- 前端组件架构
- WebSocket API 协议
