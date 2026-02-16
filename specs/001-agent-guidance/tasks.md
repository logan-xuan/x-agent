# Tasks: Agent 核心主引导流程

**Input**: Design documents from `/specs/001-agent-guidance/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: 宪法要求单元测试覆盖（II. 测试驱动开发），本任务清单包含测试任务。

**Organization**: 任务按用户场景分组，支持独立实现和测试。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件，无依赖）
- **[Story]**: 所属用户场景（US1, US2, US3, US4）
- 描述中包含精确文件路径

## Path Conventions

- **项目类型**: 单项目（后端）
- **源码路径**: `backend/src/`
- **测试路径**: `tests/`
- **工作空间**: `workspace/`

---

## Phase 1: Setup (项目初始化)

**Purpose**: 项目基础设施和依赖配置

- [x] T001 Create core module directories per implementation plan (backend/src/core/, backend/src/services/, backend/src/models/, backend/src/utils/)
- [x] T002 [P] Add dependencies to backend/pyproject.toml: watchdog, APScheduler, aiofiles, filelock
- [x] T003 [P] Create workspace directory structure: workspace/, workspace/memory/
- [x] T004 [P] Create default template files in backend/src/services/templates/

---

## Phase 2: Foundational (基础模块)

**Purpose**: 所有用户场景依赖的核心基础设施

**⚠️ CRITICAL**: 用户场景工作必须在此阶段完成后开始

### 数据模型

- [x] T005 [P] Create SessionType enum in backend/src/models/session.py
- [x] T006 [P] Create Session model with validation in backend/src/models/session.py
- [x] T007 [P] Create FileLoadResult model in backend/src/models/context.py
- [x] T008 [P] Create ContextFile model in backend/src/models/context.py
- [x] T009 [P] Create AgentContext aggregate model in backend/src/models/context.py
- [x] T010 [P] Create MemoryEntry model in backend/src/models/context.py

### 工具模块

- [x] T011 Create async file utilities with path validation in backend/src/utils/file_utils.py
- [x] T012 Create file lock manager for concurrent access in backend/src/utils/file_utils.py

### 模板服务

- [x] T013 Implement TemplateService with default templates in backend/src/services/template_service.py

**Checkpoint**: 基础模型和工具就绪，用户场景实现可以开始

---

## Phase 3: User Story 1 - 首次启动引导 (Priority: P1) 🎯 MVP

**Goal**: Agent 首次在 workspace 启动时，读取 BOOTSTRAP.md 完成初始化

**Independent Test**: 在全新 workspace 目录测试，验证 Agent 正确识别并遵循 BOOTSTRAP.md 指引

### Tests for User Story 1

- [x] T014 [P] [US1] Unit test for BOOTSTRAP.md detection in tests/unit/test_context_loader.py
- [x] T015 [P] [US1] Unit test for bootstrap initialization flow in tests/unit/test_context_loader.py

### Implementation for User Story 1

- [x] T016 [US1] Implement bootstrap detection logic in backend/src/core/context_loader.py
- [x] T017 [US1] Implement bootstrap execution and cleanup in backend/src/core/context_loader.py
- [x] T018 [US1] Add logging for bootstrap operations in backend/src/core/context_loader.py

**Checkpoint**: 首次启动引导功能完整可用，可独立测试

---

## Phase 4: User Story 2 - 每次会话启动流程 (Priority: P1)

**Goal**: 会话开始时自动加载上下文文件，确保连续性

**Independent Test**: 在完整 workspace 中测试，验证按正确顺序加载所有文件

### Tests for User Story 2

- [x] T019 [P] [US2] Unit test for context loading order in tests/unit/test_context_loader.py
- [x] T020 [P] [US2] Unit test for main session MEMORY.md loading in tests/unit/test_context_loader.py
- [x] T021 [P] [US2] Unit test for shared context MEMORY.md exclusion in tests/unit/test_context_loader.py

### Implementation for User Story 2

- [x] T022 [P] [US2] Implement SessionDetector for interaction mode detection in backend/src/core/session_detector.py
- [x] T023 [US2] Implement context file loading with order in backend/src/core/context_loader.py
- [x] T024 [US2] Implement daily memory file loading (today + yesterday) in backend/src/core/context_loader.py
- [x] T025 [US2] Implement MEMORY.md conditional loading in backend/src/core/context_loader.py
- [x] T026 [US2] Add graceful degradation for missing files in backend/src/core/context_loader.py

### API for User Story 2

- [x] T027 [US2] Implement POST /context/load endpoint in backend/src/api/v1/context.py
- [x] T028 [US2] Implement POST /session/detect endpoint in backend/src/api/v1/session.py
- [x] T029 [US2] Implement GET /context/files endpoint in backend/src/api/v1/context.py

**Checkpoint**: 会话启动流程完整可用，主会话/共享上下文区分正确

---

## Phase 5: User Story 3 - 用户提问时的流程重载 (Priority: P1)

**Goal**: 每次用户提问时重载 AGENTS.md 获取最新指导

**Independent Test**: 修改 AGENTS.md 后提问，验证 Agent 使用更新后的内容

### Tests for User Story 3

- [x] T030 [P] [US3] Unit test for AGENTS.md reload detection in tests/unit/test_file_watcher.py
- [x] T031 [P] [US3] Unit test for reload performance (<1000ms) in tests/unit/test_file_watcher.py

### Implementation for User Story 3

- [x] T032 [US3] Implement FileWatcher with watchdog in backend/src/core/file_watcher.py
- [x] T033 [US3] Implement AGENTS.md change detection in backend/src/core/file_watcher.py
- [x] T034 [US3] Implement context reload with caching in backend/src/core/context_loader.py
- [x] T035 [US3] Implement reload performance optimization (<1000ms) in backend/src/core/context_loader.py

### API for User Story 3

- [x] T036 [US3] Implement POST /context/reload endpoint in backend/src/api/v1/context.py

**Checkpoint**: 重载机制完整可用，性能符合要求

---

## Phase 6: User Story 4 - 记忆维护与更新 (Priority: P2)

**Goal**: 定期将每日笔记重要内容提炼到 MEMORY.md

**Independent Test**: 创建测试 memory 文件，验证正确识别重要内容并更新 MEMORY.md

### Tests for User Story 4

- [x] T037 [P] [US4] Unit test for important content detection in tests/unit/test_memory_maintenance.py
- [x] T038 [P] [US4] Unit test for MEMORY.md update in tests/unit/test_memory_maintenance.py
- [x] T039 [P] [US4] Unit test for outdated content cleanup in tests/unit/test_memory_maintenance.py

### Implementation for User Story 4

- [x] T040 [US4] Implement MemoryEntry importance scoring in backend/src/services/memory_maintenance.py
- [x] T041 [US4] Implement daily memory parsing in backend/src/services/memory_maintenance.py
- [x] T042 [US4] Implement MEMORY.md update logic in backend/src/services/memory_maintenance.py
- [x] T043 [US4] Implement scheduled task with APScheduler in backend/src/services/memory_maintenance.py
- [x] T044 [US4] Add file lock for concurrent write safety in backend/src/services/memory_maintenance.py

### API for User Story 4

- [x] T045 [US4] Implement POST /memory/maintenance endpoint in backend/src/api/v1/memory.py

**Checkpoint**: 记忆维护功能完整可用，定时任务配置正确

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 跨场景优化和完善

- [x] T046 [P] Integration test for full guidance flow in tests/integration/test_guidance_flow.py
- [x] T047 [P] Add structured logging with context IDs in backend/src/core/context_loader.py
- [x] T048 [P] Configure workspace default files (AGENTS.md, SPIRIT.md, OWNER.md)
- [x] T049 Run quickstart.md validation scenarios
- [x] T050 Security hardening: path traversal prevention in backend/src/utils/file_utils.py

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (Foundational) ───── BLOCKS ALL USER STORIES
    │
    ├──► Phase 3 (US1) ────┐
    │                      │
    ├──► Phase 4 (US2) ────┼──► Phase 7 (Polish)
    │                      │
    ├──► Phase 5 (US3) ────┤
    │                      │
    └──► Phase 6 (US4) ────┘
```

### User Story Dependencies

| User Story | Depends On | Can Start After |
|------------|------------|-----------------|
| US1 (首次启动) | Foundational | Phase 2 完成 |
| US2 (会话启动) | Foundational | Phase 2 完成 |
| US3 (流程重载) | Foundational, US2 | Phase 2 完成（可并行） |
| US4 (记忆维护) | Foundational | Phase 2 完成 |

### Parallel Opportunities

**Phase 1 (Setup)**: T002, T003, T004 可并行
**Phase 2 (Foundational)**: T005-T010 可并行（数据模型）
**Within Each User Story**: 所有 [P] 标记任务可并行

---

## Parallel Example: User Story 2

```bash
# 并行启动 US2 测试:
Task: T019 - Unit test for context loading order
Task: T020 - Unit test for main session MEMORY.md loading
Task: T021 - Unit test for shared context MEMORY.md exclusion

# 并行启动 US2 实现:
Task: T022 - Implement SessionDetector
# T023-T026 依赖 T022 完成后执行
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. ✅ Complete Phase 1: Setup
2. ✅ Complete Phase 2: Foundational (CRITICAL)
3. ✅ Complete Phase 3: User Story 1 (首次启动)
4. ✅ Complete Phase 4: User Story 2 (会话启动)
5. **STOP and VALIDATE**: 测试基础引导流程
6. 可部署 MVP 版本

### Incremental Delivery

| 交付阶段 | 包含场景 | 价值 |
|---------|---------|------|
| MVP | US1 + US2 | 基础引导流程可用 |
| v1.1 | + US3 | 支持动态重载 |
| v1.2 | + US4 | 完整记忆管理 |

---

## Summary

| 指标 | 数值 |
|------|------|
| **总任务数** | 50 |
| **Phase 1 (Setup)** | 4 |
| **Phase 2 (Foundational)** | 9 |
| **Phase 3 (US1)** | 5 |
| **Phase 4 (US2)** | 11 |
| **Phase 5 (US3)** | 7 |
| **Phase 6 (US4)** | 9 |
| **Phase 7 (Polish)** | 5 |
| **并行机会** | 18 个任务可并行 |
| **MVP 范围** | Phase 1-4 (US1 + US2) |

---

## Notes

- [P] 任务 = 不同文件，无依赖，可并行
- [Story] 标签映射任务到具体用户场景
- 每个用户场景可独立完成和测试
- 测试先行（TDD），确保测试失败后再实现
- 每个任务或逻辑组完成后提交
- 可在任何 Checkpoint 停止验证场景独立性
