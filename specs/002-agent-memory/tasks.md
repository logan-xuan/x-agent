# Tasks: AI Agent 记忆系统

**Input**: Design documents from `/specs/002-agent-memory/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/memory-api.yaml

**Tests**: pytest 单元测试和集成测试（遵循 TDD 原则）

**Organization**: 任务按用户故事分组，支持独立实现和测试

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，无依赖）
- **[Story]**: 所属用户故事 (US1, US2, US3, US4, US5)
- 描述中包含精确文件路径

## Path Conventions

- **Web app**: `backend/src/`, `frontend/src/`
- **Memory files**: `workspace/`

---

## Phase 1: Setup (项目初始化)

**Purpose**: 创建记忆系统基础结构和依赖

- [x] T001 Create workspace directory structure: `workspace/`, `workspace/memory/`
- [x] T002 [P] Add dependencies to `backend/pyproject.toml`: sentence-transformers, watchdog, pyyaml, python-frontmatter
- [x] T003 [P] Create `backend/src/memory/__init__.py` module init with exports
- [x] T004 [P] Create workspace template files: `workspace/SPIRIT.md`, `workspace/OWNER.md`, `workspace/MEMORY.md`, `workspace/TOOLS.md`

---

## Phase 2: Foundational (基础架构)

**Purpose**: 所有用户故事依赖的核心基础设施

**⚠️ CRITICAL**: 此阶段必须完成才能开始用户故事实现

### Database & Models

- [x] T005 Create memory ORM models in `backend/src/memory/models.py`: MemoryEntry, SpiritCache, OwnerCache, DailyLog, ToolDefinition
- [x] T006 [P] Create vector store schema extension in `backend/src/memory/vector_store.py`: sqlite-vss 初始化和连接管理
- [x] T007 [P] Create embedding service in `backend/src/services/embedder.py`: sentence-transformers 加载和推理

### File Infrastructure

- [x] T008 Create file watcher in `backend/src/memory/file_watcher.py`: watchdog 事件处理器基类
- [x] T009 Create Markdown sync base in `backend/src/memory/md_sync.py`: frontmatter 解析和文件读写

### API Infrastructure

- [x] T010 [P] Create memory router stub in `backend/src/api/v1/memory.py`: FastAPI router 注册
- [x] T011 Register memory router in `backend/src/main.py`: 添加 /api/v1/memory 路由

**Checkpoint**: 基础架构就绪，可开始用户故事实现

---

## Phase 3: User Story 1 - AI 身份初始化 (Priority: P1) 🎯 MVP

**Goal**: 首次启动时通过交互式对话引导用户完成身份设定

**Independent Test**: 启动系统，验证 SPIRIT.md 和 OWNER.md 是否正确生成

### Tests for User Story 1

- [x] T012 [P] [US1] Unit test for SpiritLoader in `backend/tests/unit/test_spirit_loader.py`
- [x] T013 [P] [US1] Unit test for identity API in `backend/tests/unit/test_identity_api.py`

### Implementation for User Story 1

- [x] T014 [P] [US1] Create SpiritConfig model in `backend/src/memory/models.py`: SPIRIT.md 数据结构
- [x] T015 [P] [US1] Create OwnerProfile model in `backend/src/memory/models.py`: OWNER.md 数据结构
- [x] T016 [US1] Implement SpiritLoader in `backend/src/memory/spirit_loader.py`: 加载/解析 SPIRIT.md 和 OWNER.md
- [x] T017 [US1] Implement identity initialization logic in `backend/src/memory/spirit_loader.py`: 首次启动检测和引导流程
- [x] T018 [US1] Implement identity status API in `backend/src/api/v1/memory.py`: GET /identity/status
- [x] T019 [US1] Implement identity init API in `backend/src/api/v1/memory.py`: POST /identity/init
- [x] T020 [US1] Implement spirit CRUD APIs in `backend/src/api/v1/memory.py`: GET/PUT /identity/spirit
- [x] T021 [US1] Implement owner CRUD APIs in `backend/src/api/v1/memory.py`: GET/PUT /identity/owner
- [x] T022 [US1] Add hot-reload support for identity files in `backend/src/memory/file_watcher.py`

**Checkpoint**: US1 完成，身份初始化可独立测试

---

## Phase 4: User Story 2 - 上下文自动加载 (Priority: P1)

**Goal**: 每次响应前自动加载相关上下文信息

**Independent Test**: 发送消息后检查 AI 是否引用了之前的对话或用户偏好

### Tests for User Story 2

- [x] T023 [P] [US2] Unit test for ContextBuilder in `backend/tests/unit/test_context_builder.py`
- [x] T024 [P] [US2] Integration test for context loading in `backend/tests/integration/test_context_flow.py`

### Implementation for User Story 2

- [x] T025 [P] [US2] Create ToolDefinition model in `backend/src/memory/models.py`: TOOLS.md 数据结构
- [x] T026 [US2] Implement ContextBuilder in `backend/src/memory/context_builder.py`: 多级上下文加载逻辑
- [x] T027 [US2] Implement context load API in `backend/src/api/v1/memory.py`: POST /context/load
- [x] T028 [US2] Implement context reload API in `backend/src/api/v1/memory.py`: POST /context/reload
- [x] T029 [US2] Integrate ContextBuilder with Agent core in `backend/src/core/agent.py`: 响应前自动加载
- [x] T030 [US2] Add logging for context loading in `backend/src/memory/context_builder.py`

**Checkpoint**: US2 完成，上下文加载可独立测试

---

## Phase 5: User Story 3 - 每日记记记录 (Priority: P2)

**Goal**: 自动记录每天的重要对话和决策

**Independent Test**: 检查 memory/ 目录下是否生成当日日志文件

### Tests for User Story 3

- [x] T031 [P] [US3] Unit test for daily log in `backend/tests/unit/test_daily_log.py`
- [x] T032 [P] [US3] Integration test for memory recording in `backend/tests/integration/test_memory_flow.py`

### Implementation for User Story 3

- [x] T033 [P] [US3] Create DailyLog model in `backend/src/memory/models.py`: 每日日志数据结构
- [x] T034 [P] [US3] Create MemoryEntry model in `backend/src/memory/models.py`: 记忆条目数据结构
- [x] T035 [US3] Implement daily log manager in `backend/src/memory/md_sync.py`: 创建/追加日志条目
- [x] T036 [US3] Implement importance detection in `backend/src/memory/importance_detector.py`: AI 自动识别重要内容
- [x] T037 [US3] Implement memory entries API in `backend/src/api/v1/memory.py`: GET/POST /memory/entries
- [x] T038 [US3] Implement single entry API in `backend/src/api/v1/memory.py`: GET/DELETE /memory/entries/{id}
- [x] T039 [US3] Implement daily log API in `backend/src/api/v1/memory.py`: GET /memory/daily/{date}
- [x] T040 [US3] Integrate memory recording with WebSocket handler in `backend/src/api/websocket.py`

**Checkpoint**: US3 完成，每日记忆可独立测试

---

## Phase 6: User Story 4 - 混合搜索能力 (Priority: P2)

**Goal**: 通过语义理解快速检索相关记忆

**Independent Test**: 使用语义相似查询验证是否能检索到相关记忆

### Tests for User Story 4

- [x] T041 [P] [US4] Unit test for hybrid search in `backend/tests/unit/test_hybrid_search.py`
- [x] T042 [P] [US4] Unit test for vector store in `backend/tests/unit/test_vector_store.py`

### Implementation for User Story 4

- [x] T043 [US4] Implement vector store operations in `backend/src/memory/vector_store.py`: 插入/搜索/删除向量
- [x] T044 [US4] Implement text similarity search in `backend/src/memory/hybrid_search.py`: BM25/TF-IDF 实现
- [x] T045 [US4] Implement hybrid search in `backend/src/memory/hybrid_search.py`: 0.7 向量 + 0.3 文本 评分
- [x] T046 [US4] Implement search API in `backend/src/api/v1/memory.py`: POST /search
- [x] T047 [US4] Implement similar search API in `backend/src/api/v1/memory.py`: GET /search/similar/{id}
- [x] T048 [US4] Add search result ranking and pagination in `backend/src/memory/hybrid_search.py`

**Checkpoint**: US4 完成，混合搜索可独立测试

---

## Phase 7: User Story 5 - 记忆双写同步 (Priority: P3) ✅

**Goal**: 记忆文件变更时自动同步到向量数据库

**Independent Test**: 修改 .md 文件后检查向量数据库是否同步更新

### Tests for User Story 5

- [x] T049 [P] [US5] Unit test for file watcher in `backend/tests/unit/test_file_watcher.py`
- [x] T050 [P] [US5] Integration test for sync in `backend/tests/integration/test_sync_flow.py`

### Implementation for User Story 5

- [x] T051 [US5] Implement file event handler in `backend/src/memory/file_watcher.py`: 处理 .md 文件变更事件
- [x] T052 [US5] Implement bidirectional sync in `backend/src/memory/md_sync.py`: Markdown ↔ 向量存储同步
- [x] T053 [US5] Implement sync error handling in `backend/src/memory/md_sync.py`: 错误日志和重试机制
- [x] T054 [US5] Implement file recovery from vector store in `backend/src/memory/md_sync.py`: 损坏文件重建
- [x] T055 [US5] Start file watcher in `backend/src/main.py`: 启动时初始化监听

**Checkpoint**: US5 完成，双写同步可独立测试 ✅

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: 完善和优化

- [ ] T056 [P] Update API documentation with memory endpoints
- [ ] T057 [P] Add performance logging for vector operations in `backend/src/memory/vector_store.py`
- [ ] T058 Run quickstart.md validation: test all API endpoints
- [ ] T059 [P] Add frontend support for memory visualization (optional)
- [ ] T060 Code cleanup and remove debug logs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Setup 完成 - **阻塞所有用户故事**
- **User Stories (Phase 3-7)**: 全部依赖 Foundational 完成
  - US1 和 US2 可以并行（同优先级 P1）
  - US3 和 US4 可以并行（同优先级 P2）
  - US5 最后实现（P3）
- **Polish (Phase 8)**: 依赖所有用户故事完成

### User Story Dependencies

| Story | Priority | Depends On | Can Start After |
|-------|----------|------------|-----------------|
| US1 身份初始化 | P1 | Foundational | Phase 2 完成 |
| US2 上下文加载 | P1 | Foundational, US1 (partial) | Phase 2 完成 |
| US3 每日记记 | P2 | Foundational, US1 | Phase 2 完成 |
| US4 混合搜索 | P2 | Foundational, US3 | US3 完成 |
| US5 双写同步 | P3 | Foundational, US3, US4 | US4 完成 |

### Parallel Opportunities

**Phase 1 (Setup)**:
```bash
# 并行执行
T002: Add dependencies to pyproject.toml
T003: Create memory/__init__.py
T004: Create workspace template files
```

**Phase 2 (Foundational)**:
```bash
# 并行执行
T006: Create vector store schema
T007: Create embedding service
T010: Create memory router stub
```

**Phase 3 (US1 Tests)**:
```bash
# 并行执行
T012: Unit test for SpiritLoader
T013: Unit test for identity API
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (**CRITICAL**)
3. Complete Phase 3: User Story 1 (身份初始化)
4. Complete Phase 4: User Story 2 (上下文加载)
5. **STOP and VALIDATE**: 测试身份初始化和上下文加载
6. 可部署 MVP

### Incremental Delivery

| Milestone | Stories | Value Delivered |
|-----------|---------|-----------------|
| MVP | US1 + US2 | AI 具备身份认知，可个性化响应 |
| V1.1 | +US3 | 每日记忆可追溯 |
| V1.2 | +US4 | 智能搜索历史记忆 |
| V1.3 | +US5 | 数据自动同步保障 |

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Tasks** | 60 |
| **US1 (P1)** | 11 tasks |
| **US2 (P1)** | 8 tasks |
| **US3 (P2)** | 10 tasks |
| **US4 (P2)** | 8 tasks |
| **US5 (P3)** | 7 tasks |
| **Setup** | 4 tasks |
| **Foundational** | 7 tasks |
| **Polish** | 5 tasks |
| **Parallel Opportunities** | 25+ tasks |

---

## Notes

- [P] 任务 = 不同文件，无依赖，可并行
- [Story] 标签映射任务到用户故事
- 每个用户故事可独立完成和测试
- 遵循 TDD：测试先行，确保失败后再实现
- 每个任务或逻辑组完成后提交
- 任何 checkpoint 可停止验证故事独立性
