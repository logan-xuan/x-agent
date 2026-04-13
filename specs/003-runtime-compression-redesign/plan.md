# Implementation Plan: Runtime 压缩算法重构

**Branch**: `003-runtime-compression-redesign` | **Date**: 2026-04-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-runtime-compression-redesign/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

将 runtime 压缩从当前“固定阶段流水线 + 局部语义规则”的实现，重构为“预算驱动 + 语义护栏 + 唯一状态快照 + bridge/controller 闭环”的上下文治理机制。方案以 `DefaultCompressionPipeline` 为稳定入口，围绕 `compression_pipeline.py`、`compression_verifier.py`、`AgentBridge` 压缩入口、runtime 配置映射和现有 unit tests 收敛设计，不修改 legacy compression manager。

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI、Pydantic v2、SQLAlchemy、runtime/context + runtime/turn + gateway/agent_bridge、pytest、pytest-asyncio  
**Storage**: SQLite/SQLAlchemy 驱动的 runtime summaries、snapshots、artifacts；pipeline 内部使用 artifact store 和内存对象  
**Testing**: pytest、pytest-asyncio、runtime unit suites（compression pipeline / verifier / gateway adapter / turn controller / profiles）  
**Target Platform**: 本地或服务端 Python 后端进程，FastAPI + runtime 控制平面  
**Project Type**: 以 `backend/` 为主的单仓库 Web 服务，当前特性为后端内部架构重构  
**Performance Goals**: 在进入模型调用前把上下文收敛到预算目标内；优先通过 `microcompact`/`collapse`/`autocompact` 避免 `emergency` 成为常态；压缩结果必须在单轮 runtime 内保持可交互延迟  
**Constraints**: 仅改 runtime 压缩链路；保持 `DefaultCompressionPipeline`、`CompressionContext`、`CompressionResult`、`CompactResult` 外部使用方式兼容；必须保留 objective/unresolved/artifact/关键结论；必须先补/收紧测试再重构实现；不得修改 legacy compression manager  
**Scale/Scope**: 预计影响 `backend/src/runtime/context/*`、`backend/src/gateway/agent_bridge.py`、`backend/src/runtime/turn/controller.py`、`backend/src/runtime/service.py`、`backend/src/config/models.py` 与 5 组 runtime unit tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 宪法原则 | 状态 | 说明 |
|---------|------|------|
| I. 代码质量优先 | ✅ PASS | 通过拆分预算决策、collapse 快照、verifier 规则，降低 `compression_pipeline.py` 内部复杂度，新增类型需保持完整注解 |
| II. 测试驱动开发 | ✅ PASS | 以现有 runtime unit suites 为主线，先锁压缩契约，再调整实现 |
| III. 关注点分离 | ✅ PASS | 保持 pipeline、verifier、bridge/controller、config provider 的职责边界，避免把所有策略继续堆到 bridge |
| IV. 可调试性设计 | ✅ PASS | 预算状态、阶段操作、verifier 结果、rollback 原因都要进入元数据和压缩事件 |
| V. 用户体验一致性 | ✅ PASS | 虽为内部特性，但需保证 bridge/controller 两条路径对压缩元数据的暴露一致 |
| VI. 性能优先 | ✅ PASS | 以预算驱动减少无效阶段和重复 summary，目标是更早收敛、减少 emergency 兜底 |
| VII. 组合优于继承 | ✅ PASS | 优先新增阶段决策器、reducer、verifier 组件，而不是加深继承层次 |
| VIII. 稳定抽象原则 | ✅ PASS | 保持 `CompressionContext`、`CompressionResult`、profile provider 和 bridge compact 合同稳定，内部做增量重构 |
| IX. YAGNI 原则 | ✅ PASS | 本轮仅覆盖 runtime 压缩、bridge 闭环与配置映射，不扩展到 legacy manager 或前端展示能力 |

**宪法合规结论**: ✅ Phase 0 研究与 Phase 1 设计均符合当前宪法要求，无需申请例外。

## Project Structure

### Documentation (this feature)

```text
specs/003-runtime-compression-redesign/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── runtime-compression-contract.md
│   └── runtime-compression-profile-contract.md
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── config/
│   │   └── models.py
│   ├── gateway/
│   │   └── agent_bridge.py
│   ├── runtime/
│   │   ├── service.py
│   │   ├── context/
│   │   │   ├── compression_pipeline.py
│   │   │   ├── compression_verifier.py
│   │   │   ├── profile_provider.py
│   │   │   └── builder.py
│   │   └── turn/
│   │       └── controller.py
│   └── services/
│       └── storage.py
└── tests/
    └── unit/
        ├── test_runtime_compression_pipeline.py
        ├── test_runtime_compression_verifier.py
        ├── test_runtime_gateway_adapter.py
        ├── test_runtime_turn_controller.py
        └── test_runtime_compression_profiles.py
```

**Structure Decision**: 本特性只修改 `backend/`，核心工作集中在 `runtime/context` 的压缩算法与 verifier、`gateway/agent_bridge.py` 的压缩闭环、`runtime/service.py` / `config/models.py` 的 profile 映射，以及对应的 runtime unit tests。

## Phase Completion Status

### Phase 0: Research ✅ COMPLETE

**输出**: [research.md](./research.md)

- 保持 runtime-only scope，不改 legacy compression manager
- 保持 `DefaultCompressionPipeline` 稳定入口，内部重构为预算驱动阶段决策
- collapse 改为唯一状态快照
- verifier 与 rollback 采用“默认回滚 + must-fit 例外”的合同
- 统一模型输入压缩与 controller compact 两条入口
- 继续使用命名 profile 作为唯一配置入口

### Phase 1: Design ✅ COMPLETE

**输出**:

- [data-model.md](./data-model.md)
- [contracts/runtime-compression-contract.md](./contracts/runtime-compression-contract.md)
- [contracts/runtime-compression-profile-contract.md](./contracts/runtime-compression-profile-contract.md)
- [quickstart.md](./quickstart.md)
- Agent context update（执行后同步到 agent 文件）

### Post-Design Constitution Check ✅ PASS

- 设计保持 runtime 边界清晰，没有扩大到 legacy compression manager
- 设计以测试契约驱动，不依赖模糊口头约束
- 设计把压缩元数据视为可观测合同，而不是内部细节

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 无 | - | - |
