# Tasks: Runtime 压缩算法重构

**Input**: Design documents from `/specs/003-runtime-compression-redesign/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `quickstart.md`, `contracts/`  
**Tests**: `pytest` 单元测试（遵循 TDD，先写失败用例，再修改实现）  
**Organization**: 任务按用户故事分组，确保每个故事都能独立实现、验证与交付

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行执行（不同文件、无未完成前置依赖）
- **[Story]**: 任务所属用户故事（`US1`、`US2`、`US3`、`US4`）
- 每条任务描述都包含明确文件路径

## Path Conventions

- 后端源码：`backend/src/`
- 单元测试：`backend/tests/unit/`
- 设计与验证文档：`docs/plans/`、`specs/003-runtime-compression-redesign/`

## Phase 1: Setup (共享回归护栏)

**Purpose**: 先固定公共回归边界与兼容性断言，避免重构过程中破坏现有 runtime 压缩入口

- [X] T001 [P] 锁定 `CompressionResult` 兼容性和公共元数据断言于 `backend/tests/unit/test_runtime_compression_pipeline.py`
- [X] T002 [P] 锁定 `CompactResult` 兼容性和桥接元数据断言于 `backend/tests/unit/test_runtime_gateway_adapter.py`

---

## Phase 2: Foundational (阻塞性基础收敛)

**Purpose**: 建立预算状态、verifier 合同和 runtime context 导出面的共享实现接缝

**⚠️ CRITICAL**: 此阶段完成前，不进入用户故事实现

- [X] T003 收敛共享压缩元数据装配与结果兼容层于 `backend/src/runtime/context/compression_pipeline.py`
- [X] T004 [P] 收敛 verifier 输入输出合同与 `preserved_fields` 语义于 `backend/src/runtime/context/compression_verifier.py`
- [X] T005 [P] 保持 runtime context 导出面兼容并暴露新增压缩合同于 `backend/src/runtime/context/__init__.py`

**Checkpoint**: pipeline、verifier 和 bridge 可围绕同一套压缩结果合同继续演进

---

## Phase 3: User Story 1 - 预算驱动的分层压缩决策 (Priority: P1) 🎯 MVP

**Goal**: 让 runtime 压缩围绕 `observe/target/must_fit` 三条预算线选择阶段，并把历史收敛为唯一 collapse 快照

**Independent Test**: 运行 `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q`，验证预算状态、阶段切换、提前停止和唯一快照行为

### Tests for User Story 1

- [X] T006 [P] [US1] 为预算驱动阶段选择、提前停止和压力重算补失败用例于 `backend/tests/unit/test_runtime_compression_pipeline.py`
- [X] T007 [P] [US1] 为唯一 collapse 快照、重复 summary 去除和终态覆盖补失败用例于 `backend/tests/unit/test_runtime_compression_pipeline.py`

### Implementation for User Story 1

- [X] T008 [US1] 实现 `observe/target/must_fit` 驱动的阶段决策与重算循环于 `backend/src/runtime/context/compression_pipeline.py`
- [X] T009 [US1] 实现唯一 collapse 快照重写与历史状态收敛于 `backend/src/runtime/context/compression_pipeline.py`
- [X] T010 [US1] 稳定 normal/emergency 返回路径上的 `budget_state`、`operations` 与阶段停止元数据于 `backend/src/runtime/context/compression_pipeline.py`

**Checkpoint**: US1 完成后，pipeline 能在预算目标满足时提前停止，并只保留一个有效 collapse 状态快照

---

## Phase 4: User Story 2 - 压缩后的语义护栏与失败回滚 (Priority: P1)

**Goal**: 让 verifier 和 rollback 合同稳定保护 objective、unresolved、artifact refs、关键结论与终态一致性

**Independent Test**: 运行 `pytest --no-cov backend/tests/unit/test_runtime_compression_verifier.py -q` 与 `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q`，验证 verifier、rollback 与 must-fit 例外行为

### Tests for User Story 2

- [X] T011 [P] [US2] 为 objective、unresolved、artifact refs、state conflict 和 conclusion fidelity 护栏补失败用例于 `backend/tests/unit/test_runtime_compression_verifier.py`
- [X] T012 [P] [US2] 为 rollback、skip-rollback 审计信息和 must-fit 例外补失败用例于 `backend/tests/unit/test_runtime_compression_pipeline.py`

### Implementation for User Story 2

- [X] T013 [US2] 收紧 verifier 对语义护栏和 `preserved_fields` 合同的实现于 `backend/src/runtime/context/compression_verifier.py`
- [X] T014 [US2] 实现默认回滚、skip-rollback 例外与审计元数据合同于 `backend/src/runtime/context/compression_pipeline.py`

**Checkpoint**: US2 完成后，压缩失败会走可审计回滚路径，且不会为了满足预算而静默丢失关键语义

---

## Phase 5: User Story 3 - runtime 与桥接层的压缩闭环 (Priority: P2)

**Goal**: 让模型输入压缩和显式 compact 共享同一套 runtime 压缩结果契约，并把真实结果透传给 state 与 controller

**Independent Test**: 运行 `pytest --no-cov backend/tests/unit/test_runtime_gateway_adapter.py -q` 与 `pytest --no-cov backend/tests/unit/test_runtime_turn_controller.py -q`，验证 bridge/controller 对压缩结果的透传与消费

### Tests for User Story 3

- [X] T015 [P] [US3] 为 `_runtime_prepare_model_input()` 的压缩事件、artifact refs 与 `budget_state` 透传补回归于 `backend/tests/unit/test_runtime_gateway_adapter.py`
- [X] T016 [P] [US3] 为 compact 结果消费和 state 更新补回归于 `backend/tests/unit/test_runtime_turn_controller.py`

### Implementation for User Story 3

- [X] T017 [US3] 统一 `_runtime_prepare_model_input()` 的压缩结果记录、artifact 更新和 metadata 写入于 `backend/src/gateway/agent_bridge.py`
- [X] T018 [US3] 统一 `_runtime_controller_compact()` 输出的 `CompactResult` 包装合同于 `backend/src/gateway/agent_bridge.py`
- [X] T019 [US3] 调整 `DefaultTurnController._apply_compact_result()` 以一致消费 active messages、artifacts 和 metadata 于 `backend/src/runtime/turn/controller.py`

**Checkpoint**: US3 完成后，bridge/controller 两条压缩入口输出同构元数据，且真实压缩结果能回写 turn state

---

## Phase 6: User Story 4 - 可配置的压缩策略与可观测输出 (Priority: P3)

**Goal**: 保持命名 profile 作为唯一配置入口，并让压缩阶段、预算状态、verifier 结果和 rollback 原因稳定可观测

**Independent Test**: 运行 `pytest --no-cov backend/tests/unit/test_runtime_compression_profiles.py -q` 与 `pytest --no-cov backend/tests/unit/test_runtime_compression_pipeline.py -q`，验证 profile 映射、非法配置拒绝和 telemetry 输出

### Tests for User Story 4

- [X] T020 [P] [US4] 为 profile 映射、防御性拷贝和非法阈值组合补回归于 `backend/tests/unit/test_runtime_compression_profiles.py`
- [X] T021 [P] [US4] 为 runtime 压缩 telemetry 键和可观测输出补回归于 `backend/tests/unit/test_runtime_compression_pipeline.py`

### Implementation for User Story 4

- [X] T022 [US4] 扩展 runtime 压缩 profile 字段校验与约束错误信息于 `backend/src/config/models.py`
- [X] T023 [US4] 对齐命名 profile 验证与 defensive copy 语义于 `backend/src/runtime/context/profile_provider.py`
- [X] T024 [US4] 更新 runtime compression profile 转换和默认装配于 `backend/src/runtime/service.py`

**Checkpoint**: US4 完成后，profile 配置仍是唯一入口，非法配置会在加载期失败，且压缩 telemetry 能稳定观测

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: 收口文档、回归矩阵和实现差异说明

- [X] T025 [P] 更新重构后实现差异与闭环说明于 `docs/plans/runtime-compression-redesign-design.md`
- [X] T026 [P] 更新回归步骤与完成判定于 `specs/003-runtime-compression-redesign/quickstart.md`
- [X] T027 运行并记录聚焦压缩回归矩阵于 `specs/003-runtime-compression-redesign/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Phase 1，阻塞全部用户故事
- **User Story 1 (Phase 3)**: 依赖 Phase 2，优先交付预算驱动阶段决策和唯一 collapse 快照
- **User Story 2 (Phase 4)**: 依赖 Phase 2，建议在 US1 的 pipeline 元数据接缝稳定后推进
- **User Story 3 (Phase 5)**: 依赖 US1 与 US2 完成，以共享稳定的 pipeline/verifier 合同
- **User Story 4 (Phase 6)**: 依赖 US1 完成，建议在 US3 的 telemetry 键稳定后收口配置映射
- **Polish (Phase 7)**: 依赖所有目标用户故事完成

### User Story Dependencies

- **US1 (P1)**: 无用户故事前置依赖，是本次重构的 MVP
- **US2 (P1)**: 可在 Foundational 后启动，但与 US1 共用 `compression_pipeline.py`，建议串行收口
- **US3 (P2)**: 依赖 US1/US2 的压缩结果合同稳定后再打通 bridge/controller 闭环
- **US4 (P3)**: 依赖 US1 的预算状态和阶段元数据稳定，再收口 profile 与观测输出

### Within Each User Story

- 先写测试并确认失败，再进入实现任务
- 先收敛合同与元数据，再调整桥接与配置映射
- 同一文件上的任务按顺序执行，避免并行改动冲突

### Parallel Opportunities

- **Phase 1**: `T001` 和 `T002` 可并行
- **US1**: `T006` 和 `T007` 可并行
- **US2**: `T011` 和 `T012` 可并行
- **US3**: `T015` 和 `T016` 可并行
- **US4**: `T020` 和 `T021` 可并行

---

## Parallel Example: User Story 1

```bash
# 先并行补测试
Task: "为预算驱动阶段选择、提前停止和压力重算补失败用例于 backend/tests/unit/test_runtime_compression_pipeline.py"
Task: "为唯一 collapse 快照、重复 summary 去除和终态覆盖补失败用例于 backend/tests/unit/test_runtime_compression_pipeline.py"
```

## Parallel Example: User Story 3

```bash
# bridge 与 controller 两侧测试可并行收紧
Task: "为 _runtime_prepare_model_input() 的压缩事件、artifact refs 与 budget_state 透传补回归于 backend/tests/unit/test_runtime_gateway_adapter.py"
Task: "为 compact 结果消费和 state 更新补回归于 backend/tests/unit/test_runtime_turn_controller.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. 完成 Phase 1 和 Phase 2，先锁共享合同
2. 完成 Phase 3，交付预算驱动阶段决策和唯一 collapse 快照
3. 运行 `backend/tests/unit/test_runtime_compression_pipeline.py`
4. 在 US1 独立通过后再进入后续故事

### Safety Gate After MVP

1. 完成 Phase 4，补齐 verifier/rollback 合同
2. 运行 `backend/tests/unit/test_runtime_compression_verifier.py`
3. 确认 must-fit 例外和 rollback 审计信息稳定

### Incremental Delivery

1. 交付 US1：预算驱动压缩主路径稳定
2. 交付 US2：语义护栏和回滚稳定
3. 交付 US3：bridge/controller 闭环打通
4. 交付 US4：配置映射和可观测输出收口

---

## Notes

- 本任务清单严格限定在 runtime 压缩链路，不触碰 legacy compression manager
- `backend/src/runtime/context/compression_pipeline.py` 是高冲突文件，建议按任务顺序串行推进
- `budget_state`、`verifier_result`、`rollback_*` 和 `compression_operations` 视为稳定合同，不在 bridge 层重新发明键名
