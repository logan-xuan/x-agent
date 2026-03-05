# Tasks: Skill 系统重构

**Input**: Design documents from `/specs/001-skill-system-refactor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: 根据宪法要求（II. 测试驱动开发），所有功能必须先编写测试。

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/src/`, `backend/tests/`
- Adjusted based on plan.md structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [ ] T001 Create skill module directory structure `backend/src/services/skill/`
- [ ] T002 Create skill module `__init__.py` with public exports in `backend/src/services/skill/__init__.py`
- [ ] T003 [P] Create test directory structure `backend/tests/unit/services/skill/`
- [ ] T004 [P] Add M3E-small embedding model dependency to `backend/pyproject.toml`
- [ ] T005 [P] Add jsonschema dependency to `backend/pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and enums that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests for Foundational

- [ ] T006 [P] Unit test for SkillManifest validation in `backend/tests/unit/models/test_skill_manifest.py`
- [ ] T007 [P] Unit test for enum types in `backend/tests/unit/models/test_skill_enums.py`

### Implementation for Foundational

- [ ] T008 [P] Define RiskLevel, DataAccessLevel, ApprovalMode, ExecutionStage enums in `backend/src/models/skill.py`
- [ ] T009 [P] Define SkillSource enum (USER, SYSTEM) in `backend/src/models/skill.py`
- [ ] T010 Implement unified SkillManifest dataclass in `backend/src/models/skill.py` (depends on T008, T009)
- [ ] T011 [P] Define SkillSearchContext and SearchBudget in `backend/src/models/skill.py`
- [ ] T012 [P] Define SkillCard dataclass in `backend/src/models/skill.py`
- [ ] T013 [P] Define SkillExecutionContext dataclass in `backend/src/models/skill.py`
- [ ] T014 [P] Define SkillExecutionResult dataclass in `backend/src/models/skill.py`
- [ ] T015 [P] Define SkillScore dataclass in `backend/src/models/skill.py`
- [ ] T016 [P] Copy manifest-schema.json to `backend/src/services/skill/schemas/manifest-schema.json`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - 技能统一发现与执行 (Priority: P1) 🎯 MVP

**Goal**: 从多个来源（用户自定义、系统内置）发现和加载技能，按优先级返回技能列表

**Independent Test**: 配置不同来源的技能目录，验证系统能正确扫描、注册并按 USER > SYSTEM 优先级返回技能列表

### Tests for User Story 1

- [ ] T017 [P] [US1] Unit test for ManifestParser in `backend/tests/unit/services/skill/test_manifest_parser.py`
- [ ] T018 [P] [US1] Unit test for SkillRegistry in `backend/tests/unit/services/skill/test_registry.py`

### Implementation for User Story 1

- [ ] T019 [US1] Implement ManifestParser with JSON Schema validation in `backend/src/services/skill/manifest_parser.py`
- [ ] T020 [US1] Implement SKILL.md fallback parsing in ManifestParser (兼容现有格式)
- [ ] T021 [US1] Implement SkillRegistry with two-level source support in `backend/src/services/skill/registry.py`
- [ ] T022 [US1] Implement priority-based deduplication (USER > SYSTEM) in registry
- [ ] T023 [US1] Implement cache mechanism with TTL in SkillRegistry
- [ ] T024 [US1] Add structured logging for skill loading in registry
- [ ] T025 [US1] Update API endpoint `/api/v1/skills` to use new registry in `backend/src/api/v1/skills.py`
- [ ] T026 [US1] Add cache clear endpoint `/api/v1/skills/cache/clear`

**Checkpoint**: User Story 1 complete - 技能可被扫描、注册、按优先级返回

---

## Phase 4: User Story 2 - 智能技能匹配与推荐 (Priority: P1)

**Goal**: 根据用户输入智能推荐最相关的技能，支持语义检索和关键词匹配

**Independent Test**: 输入自然语言描述，验证系统返回的技能列表与用户意图的相关性

### Tests for User Story 2

- [ ] T027 [P] [US2] Unit test for SkillEmbedder in `backend/tests/unit/services/skill/test_embedder.py`
- [ ] T028 [P] [US2] Unit test for SkillIndexer in `backend/tests/unit/services/skill/test_indexer.py`
- [ ] T029 [P] [US2] Unit test for SkillScorer in `backend/tests/unit/services/skill/test_scorer.py`
- [ ] T030 [P] [US2] Unit test for SkillDiscovery in `backend/tests/unit/services/skill/test_discovery.py`

### Implementation for User Story 2

- [ ] T031 [US2] Implement SkillEmbedder with M3E-small model in `backend/src/services/skill/embedder.py`
- [ ] T032 [US2] Add embedding cache mechanism in SkillEmbedder
- [ ] T033 [US2] Implement SkillIndexer with sqlite-vss in `backend/src/services/skill/indexer.py`
- [ ] T034 [US2] Implement SkillCapabilityVector generation in indexer
- [ ] T035 [US2] Implement SkillScorer with 5-dimension weighted scoring in `backend/src/services/skill/scorer.py`
- [ ] T036 [US2] Implement semantic similarity scoring (weight: 0.35)
- [ ] T037 [US2] Implement schema fit scoring (weight: 0.25)
- [ ] T038 [US2] Implement policy scoring with risk penalties (weight: 0.20)
- [ ] T039 [US2] Implement SkillDiscovery with multi-recall strategy in `backend/src/services/skill/discovery.py`
- [ ] T040 [US2] Implement keyword matching recall in discovery
- [ ] T041 [US2] Implement tag/domain filtering in discovery
- [ ] T042 [US2] Generate match_reason explanation in SkillCard
- [ ] T043 [US2] Implement `/api/v1/skills/discover` endpoint in `backend/src/api/v1/skills.py`

**Checkpoint**: User Story 2 complete - 语义检索和智能推荐工作正常

---

## Phase 5: User Story 3 - 技能风险控制与确认机制 (Priority: P2)

**Goal**: 高风险操作在执行前需要用户确认，避免意外损失

**Independent Test**: 触发不同风险等级的技能，验证系统是否正确应用确认流程

### Tests for User Story 3

- [ ] T044 [P] [US3] Unit test for risk level enforcement in `backend/tests/unit/services/skill/test_executor.py`

### Implementation for User Story 3

- [ ] T045 [US3] Implement SkillExecutor base structure in `backend/src/services/skill/executor.py`
- [ ] T046 [US3] Implement precondition checking in executor
- [ ] T047 [US3] Implement parameter validation in executor
- [ ] T048 [US3] Implement risk-based confirmation flow (HIGH/CRITICAL → require confirm)
- [ ] T049 [US3] Implement approval_mode enforcement (AUTO/CONFIRM/APPROVAL/MANUAL)
- [ ] T050 [US3] Add confirmation status to SkillExecutionResult

**Checkpoint**: User Story 3 complete - 高风险操作正确触发确认流程

---

## Phase 6: User Story 4 - 渐进式技能执行 (Priority: P2)

**Goal**: 复杂操作分阶段执行，支持预览（dry-run）和回滚

**Independent Test**: 触发支持预演的技能，验证各执行阶段的正确流转

### Tests for User Story 4

- [ ] T051 [P] [US4] Unit test for stage execution in `backend/tests/unit/services/skill/test_executor_stages.py`
- [ ] T052 [P] [US4] Unit test for rollback mechanism in `backend/tests/unit/services/skill/test_executor_rollback.py`

### Implementation for User Story 4

- [ ] T053 [US4] Implement DRY_RUN stage execution in executor
- [ ] T054 [US4] Implement PLAN stage execution in executor
- [ ] T055 [US4] Implement CONFIRM stage with user wait in executor
- [ ] T056 [US4] Implement COMMIT stage execution in executor
- [ ] T057 [US4] Implement ROLLBACK stage and recovery in executor
- [ ] T058 [US4] Implement stage sequence determination based on risk level
- [ ] T059 [US4] Update `/api/v1/skills/{skill_id}/execute` endpoint with stage support

**Checkpoint**: User Story 4 complete - 渐进式执行各阶段正常流转

---

## Phase 7: User Story 5 - 技能参数智能补全 (Priority: P3)

**Goal**: 识别缺失的必要参数并提示用户补充

**Independent Test**: 调用需要参数的技能但不提供全部参数，验证系统的提示行为

### Tests for User Story 5

- [ ] T060 [P] [US5] Unit test for parameter extraction in `backend/tests/unit/services/skill/test_param_extraction.py`

### Implementation for User Story 5

- [ ] T061 [US5] Implement missing parameter detection in executor
- [ ] T062 [US5] Implement context parameter extraction in executor
- [ ] T063 [US5] Implement parameter validation against input_schema
- [ ] T064 [US5] Add missing_params field population in SkillCard
- [ ] T065 [US5] Add schema_fit_score calculation in scorer

**Checkpoint**: User Story 5 complete - 参数缺失时给出明确提示

---

## Phase 8: Integration & Adapter (Agent Core 集成)

**Purpose**: 实现 SkillAdapter 与 agent-core 集成

### Tests for Integration

- [ ] T066 [P] Unit test for SkillAdapter in `backend/tests/unit/agent_core/adapters/test_skill_adapter.py`
- [ ] T067 [P] Integration test for full skill system in `backend/tests/integration/test_skill_system.py`

### Implementation for Integration

- [ ] T068 Implement SkillAdapter combining all components in `backend/src/agent_core/adapters/skill_adapter.py`
- [ ] T069 Implement SkillPort interface methods in adapter
- [ ] T070 Register SkillAdapter in agent_core configuration
- [ ] T071 Add skill-related hooks (ON_SKILL_DISCOVER, BEFORE_SKILL_EXEC, AFTER_SKILL_EXEC)

**Checkpoint**: Agent Core integration complete - SkillAdapter 实现 SkillPort 接口

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T072 [P] Add manifest.json to existing skills (pptx, pdf, etc.) in `backend/src/skills/`
- [ ] T073 [P] Update API documentation for new endpoints
- [ ] T074 Performance optimization: ensure discovery < 200ms
- [ ] T075 Add stats endpoint `/api/v1/skills/stats`
- [ ] T076 Run quickstart.md validation scenarios
- [ ] T077 Code cleanup and remove deprecated skill_registry.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (P1) and US2 (P1) can proceed in parallel after Foundational
  - US3 (P2) and US4 (P2) depend on US1 completion (need registry)
  - US5 (P3) depends on US2 completion (need scorer)
- **Integration (Phase 8)**: Depends on US1-US4 completion
- **Polish (Phase 9)**: Depends on all user stories

### User Story Dependencies

```
Foundational (Phase 2)
    │
    ├── US1: 技能发现与执行 (P1) ──┐
    │                             │
    ├── US2: 智能匹配与推荐 (P1) ──┼── Can run in parallel
    │                             │
    │   ┌─────────────────────────┘
    │   │
    │   ├── US3: 风险控制 (P2) ─── Depends on US1 (needs registry)
    │   │
    │   ├── US4: 渐进执行 (P2) ─── Depends on US1 (needs registry)
    │   │
    │   └── US5: 参数补全 (P3) ─── Depends on US2 (needs scorer)
    │
    └── Integration (Phase 8) ─── Depends on US1-US4
```

### Parallel Opportunities

**Within Phase 2 (Foundational)**:
```bash
# Can run in parallel:
T006, T007  # Tests
T008, T009, T011-T016  # Enums and dataclasses (different parts of same file or different files)
```

**Within Phase 3 (US1)**:
```bash
# Tests can run in parallel:
T017, T018
```

**Within Phase 4 (US2)**:
```bash
# Tests can run in parallel:
T027, T028, T029, T030
```

**Cross-Story Parallelism**:
```bash
# After Foundational, US1 and US2 can start in parallel:
# Developer A: T017-T026 (US1)
# Developer B: T027-T043 (US2)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test registry and API independently
5. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Registry works → Deploy (MVP!)
3. Add User Story 2 → Semantic search works → Deploy
4. Add User Story 3+4 → Risk control and staging works → Deploy
5. Add User Story 5 → Parameter completion → Deploy
6. Integration → Agent Core integration → Deploy

### Suggested MVP Scope

**MVP = Phase 1 + Phase 2 + Phase 3 (User Story 1)**

This delivers:
- Unified skill registry with two-level sources
- Priority-based deduplication (USER > SYSTEM)
- Basic skill listing API
- Cache management

---

## Task Summary

| Phase | Tasks | Parallelizable |
|-------|-------|----------------|
| Phase 1: Setup | 5 | 3 |
| Phase 2: Foundational | 11 | 9 |
| Phase 3: US1 (P1) | 10 | 2 |
| Phase 4: US2 (P1) | 17 | 4 |
| Phase 5: US3 (P2) | 7 | 1 |
| Phase 6: US4 (P2) | 9 | 2 |
| Phase 7: US5 (P3) | 6 | 1 |
| Phase 8: Integration | 6 | 2 |
| Phase 9: Polish | 6 | 2 |
| **Total** | **77** | **26** |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- TDD required: Write tests first, ensure they FAIL before implementation
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
