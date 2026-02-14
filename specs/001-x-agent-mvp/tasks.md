# Tasks: X-Agent MVP

**Input**: Design documents from `/specs/001-x-agent-mvp/`  
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/, research.md, quickstart.md

**Tests**: 测试任务是可选的，仅在明确请求时实现。

**Organization**: 任务按用户故事分组，支持独立实现和测试。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，无依赖）
- **[Story]**: 任务所属用户故事（如 US1, US2, US3）
- 描述中包含确切的文件路径

## Path Conventions

- **后端**: `backend/src/`, `backend/tests/`
- **前端**: `frontend/src/`, `frontend/tests/`

---

## Phase 1: Setup (项目初始化) ✅

**Purpose**: 项目初始化和基础结构搭建

- [X] T001 Create project directory structure per implementation plan (backend/, frontend/, docs/)
- [X] T002 [P] Initialize Python project with pyproject.toml in backend/ (FastAPI, SQLAlchemy, Pydantic dependencies)
- [X] T003 [P] Initialize React + TypeScript project with Vite in frontend/ (React 18, Tailwind CSS, shadcn/ui)
- [X] T004 Configure linting and formatting tools (ruff for Python, ESLint + Prettier for TypeScript)
- [X] T005 Create x-agent.yaml.example configuration template in backend/
- [X] T006 [P] Setup Git repository with .gitignore (exclude venv, node_modules, logs, config files)

---

## Phase 2: Foundational (基础架构 - 阻塞所有用户故事) ✅

**Purpose**: 核心基础设施，必须在任何用户故事之前完成

**⚠️ CRITICAL**: 此阶段完成前不能开始用户故事开发

### 后端基础设施

- [X] T007 Create backend/src/config/models.py with Pydantic configuration models (ModelConfig, ServerConfig, LoggingConfig)
- [X] T008 Create backend/src/config/loader.py for YAML configuration loading with validation
- [X] T009 Create backend/src/config/manager.py as singleton ConfigManager with hot-reload support
- [X] T010 Create backend/src/config/watcher.py for file change detection using watchdog
- [X] T011 [P] Create backend/src/utils/logger.py with structured JSON logging
- [X] T012 Create backend/src/models/session.py with SQLAlchemy Session model
- [X] T013 [P] Create backend/src/models/message.py with SQLAlchemy Message model
- [X] T014 Create backend/src/services/storage.py for database operations (SQLite with WAL mode)
- [X] T015 Setup backend database connection and initialization in backend/src/main.py

### 前端基础设施

- [X] T016 [P] Create frontend/src/types/index.ts with TypeScript type definitions
- [X] T017 [P] Create frontend/src/services/api.ts for REST API client
- [X] T018 Create frontend/src/services/websocket.ts for WebSocket connection management
- [X] T019 [P] Create frontend/src/utils/logger.ts for frontend logging
- [X] T020 Setup frontend routing and base layout in frontend/src/App.tsx

**Checkpoint**: 基础架构就绪 - 可以开始用户故事开发

---

## Phase 3: User Story 1 - WebChat基础对话 (Priority: P1) 🎯 MVP ✅

**Goal**: 实现用户通过 Web 界面与 AI Agent 进行自然语言对话，支持流式输出

**Independent Test**: 启动系统后，打开 Web 界面，发送任意消息，验证是否能收到 AI 回复并流式显示

### 后端实现

- [X] T021 [P] Create backend/src/services/llm/provider.py with LLMProvider abstract base class
- [X] T022 [P] Create backend/src/services/llm/openai_provider.py implementing OpenAI provider
- [X] T023 [P] Create backend/src/services/llm/bailian_provider.py implementing Bailian provider
- [X] T024 Create backend/src/services/llm/router.py for primary/backup model routing with failover
- [X] T025 Create backend/src/services/llm/failover.py for automatic failover logic
- [X] T026 Create backend/src/core/session.py for session management
- [X] T027 Create backend/src/core/agent.py for Agent core logic with streaming support
- [X] T028 Create backend/src/api/v1/chat.py with REST chat endpoints
- [X] T029 Create backend/src/api/websocket.py with WebSocket handler for real-time chat
- [X] T030 Create backend/src/api/v1/health.py with health check endpoint
- [X] T031 Integrate all routes in backend/src/main.py

### 前端实现

- [X] T032 [P] Create frontend/src/components/chat/MessageItem.tsx for individual message display
- [X] T033 [P] Create frontend/src/components/chat/MessageList.tsx for message history list
- [X] T034 Create frontend/src/components/chat/MessageInput.tsx for user input with send button
- [X] T035 Create frontend/src/components/chat/ChatWindow.tsx as main chat container
- [X] T036 [P] Create frontend/src/hooks/useWebSocket.ts for WebSocket connection management
- [X] T037 Create frontend/src/hooks/useChat.ts for chat state management
- [X] T038 Integrate chat components in frontend/src/App.tsx
- [X] T039 Add basic styling with Tailwind CSS for chat interface

**Checkpoint**: User Story 1 应该完全可用，可独立测试

---

## Phase 4: User Story 2 - 工程架构搭建 (Priority: P1) ✅

**Goal**: 完善模块化 + 插件式架构，前后端分离部署，WebSocket 实时通信

**Independent Test**: 项目结构符合模块化设计，前后端独立启动，WebSocket 连接正常建立

### 后端架构完善

- [X] T040 Create backend/src/plugins/base.py with Plugin base class and interface
- [X] T041 Create backend/src/core/context.py for context management
- [X] T042 Add request/response middleware in backend/src/main.py for tracing ID
- [X] T043 Implement error handling middleware with unified response format
- [X] T044 Add CORS configuration and middleware
- [X] T045 Create backend startup/shutdown lifecycle management

### 前端架构完善

- [X] T046 [P] Setup shadcn/ui components (Button, Input, Card, ScrollArea)
- [X] T047 Create frontend/src/components/ui/ for shared UI components
- [X] T048 Add loading states and error handling in chat components
- [X] T049 Implement WebSocket reconnection logic with exponential backoff
- [X] T050 Add connection status indicator in UI

### 部署和文档

- [X] T051 Create backend startup script (start.sh or python -m)
- [X] T052 Create frontend startup script (pnpm dev)
- [X] T053 Create combined startup script at project root
- [X] T054 Update quickstart.md with verified setup instructions

**Checkpoint**: User Stories 1 和 2 都应该独立工作

---

## Phase 5: User Story 3 - 配置管理 (Priority: P2) ✅

**Goal**: 实现高内聚配置系统，支持一主多备自动切换，热重载

**Independent Test**: 修改配置文件后无需重启服务即可生效，模拟主模型故障验证自动切换

### 配置系统完善

- [X] T055 Add configuration validation with detailed error messages in backend/src/config/
- [X] T056 Implement API key encryption at rest (SecretStr) and masking in logs
- [X] T057 Add configuration reload endpoint for manual refresh
- [X] T058 Create configuration validation endpoint
- [X] T059 Add configuration change event broadcasting

### 故障转移优化

- [X] T060 Implement health check for each model provider
- [X] T061 Add circuit breaker pattern for failing providers
- [X] T062 Implement provider priority-based fallback logic
- [X] T063 Add failover event logging and metrics

### 前端配置界面

- [X] T064 [P] Create frontend/src/components/settings/ for settings UI
- [X] T065 Add configuration display (read-only) in web interface
- [X] T066 Add model status indicator (healthy/unhealthy)
- [X] T067 Implement configuration reload trigger from UI

**Checkpoint**: 所有用户故事应该独立功能完整

---

## Phase 6: Polish & Cross-Cutting Concerns ✅

**Purpose**: 影响多个用户故事的改进

- [X] T068 [P] Add comprehensive error handling across all modules
- [X] T069 [P] Implement input validation (empty message, max length)
- [X] T070 Add rate limiting for API endpoints
- [X] T071 Implement request timeout handling
- [X] T072 Add database connection pooling
- [X] T073 [P] Optimize frontend bundle size
- [X] T074 Add responsive design for mobile devices
- [X] T075 Implement graceful shutdown handling
- [X] T076 Add startup configuration validation
- [ ] T077 Create comprehensive README.md
- [X] T078 Run quickstart.md validation (follow all steps)
- [X] T079 Perform end-to-end testing of complete flow

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖 - 可立即开始
- **Foundational (Phase 2)**: 依赖 Setup 完成 - 阻塞所有用户故事
- **User Stories (Phase 3-5)**: 都依赖 Foundational 阶段完成
  - 用户故事可以并行开发（如果有足够人手）
  - 或按优先级顺序执行（P1 → P2）
- **Polish (Final Phase)**: 依赖所有用户故事完成

### User Story Dependencies

- **User Story 1 (P1)**: Foundational 完成后可开始 - 不依赖其他故事
- **User Story 2 (P1)**: Foundational 完成后可开始 - 可与 US1 并行
- **User Story 3 (P2)**: Foundational 完成后可开始 - 依赖 US1/2 的基础功能

### Within Each User Story

- 模型在服务对象之前
- 服务对象在端点/组件之前
- 核心实现在集成之前
- 故事完成后再进入下一个优先级

### Parallel Opportunities

- 所有标记 [P] 的 Setup 任务可并行
- 所有标记 [P] 的 Foundational 任务可并行（在 Phase 2 内）
- Foundational 完成后，所有用户故事可并行开发
- 前后端开发可并行（通过 API 契约对齐）

---

## Parallel Example: User Story 1

```bash
# 后端模型可并行开发:
Task: "Create backend/src/services/llm/provider.py"
Task: "Create backend/src/services/llm/openai_provider.py"
Task: "Create backend/src/services/llm/bailian_provider.py"

# 前端组件可并行开发:
Task: "Create frontend/src/components/chat/MessageItem.tsx"
Task: "Create frontend/src/components/chat/MessageList.tsx"
Task: "Create frontend/src/components/chat/MessageInput.tsx"
```

---

## Implementation Strategy

### MVP First (仅 User Story 1)

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（关键 - 阻塞所有故事）
3. 完成 Phase 3: User Story 1
4. **STOP and VALIDATE**: 独立测试 User Story 1
5. 如准备就绪，部署/演示

### 增量交付

1. 完成 Setup + Foundational → 基础就绪
2. 添加 User Story 1 → 独立测试 → 部署/演示（MVP!）
3. 添加 User Story 2 → 独立测试 → 部署/演示
4. 添加 User Story 3 → 独立测试 → 部署/演示
5. 每个故事都在不破坏之前功能的前提下增加价值

### 并行团队策略

多人开发时：

1. 团队一起完成 Setup + Foundational
2. Foundational 完成后：
   - 开发者 A: User Story 1 (后端)
   - 开发者 B: User Story 1 (前端)
   - 开发者 C: User Story 2 (架构完善)
3. 故事独立完成并集成

---

## Task Summary

| 阶段 | 任务数 | 说明 |
|------|--------|------|
| Phase 1: Setup | 6 | 项目初始化 |
| Phase 2: Foundational | 14 | 基础架构 |
| Phase 3: US1 (P1) | 19 | WebChat 基础对话 |
| Phase 4: US2 (P1) | 15 | 工程架构搭建 |
| Phase 5: US3 (P2) | 13 | 配置管理 |
| Phase 6: Polish | 12 | 完善和优化 |
| **总计** | **79** | |

### 按用户故事统计

- **US1 (WebChat基础对话)**: 19 个任务
- **US2 (工程架构搭建)**: 15 个任务
- **US3 (配置管理)**: 13 个任务

### 并行机会

- Setup 阶段: 4 个任务可并行
- Foundational 阶段: 7 个任务可并行
- US1 后端: 5 个 Provider 相关任务可并行
- US1 前端: 4 个组件任务可并行

### 建议 MVP 范围

**仅实现 User Story 1 (WebChat基础对话)** 即可交付 MVP：
- 用户可以打开 Web 界面
- 可以发送消息
- 可以接收 AI 流式回复
- 对话历史持久化

这将验证核心架构和用户体验，为后续功能奠定基础。

---

## Notes

- [P] 任务 = 不同文件，无依赖
- [Story] 标签将任务映射到特定用户故事以便追溯
- 每个用户故事应该可以独立完成和测试
- 每个任务后或逻辑组后提交代码
- 在任何检查点停止以独立验证故事
- 避免：模糊任务、相同文件冲突、破坏独立性的跨故事依赖
