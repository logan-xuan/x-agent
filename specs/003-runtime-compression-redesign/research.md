# Research: Runtime 压缩算法重构

**Feature**: Runtime 压缩算法重构  
**Date**: 2026-04-08  
**Researcher**: Codex

---

## 1. 范围与边界

### 决策：本轮只重构 `runtime` 压缩链路，不改 legacy compression manager

**Decision**: 改动范围限定在 `backend/src/runtime/`、`backend/src/gateway/agent_bridge.py`、`backend/src/config/models.py` 以及对应测试；`services/compression/*` 与 legacy manager 维持现状。

**Rationale**:

- 用户请求明确要求“参考 runtime compression redesign design 并结合最新代码”，现有设计文档也明确写明仅改 `runtime`。
- `docs/architecture-review/06-runtime-orchestration.md` 已明确 `runtime` 是控制平面、`agent_core` 是执行实现层，当前真实压缩闭环已经落在 runtime + AgentBridge 上。
- 如果本轮同时改 legacy compression manager，会把 runtime 收敛和旧链路兼容问题混在一起，破坏 YAGNI 和稳定抽象原则。

**Alternatives considered**:

- 同时统一 legacy compression manager 与 runtime pipeline：范围过大，无法在一次规划中稳定验证。
- 只改测试，不调整 runtime 设计：无法解决固定流水线、重复摘要污染和 compact 闭环不完整的问题。

---

## 2. 压缩主入口与内部结构

### 决策：保留 `DefaultCompressionPipeline` 作为稳定入口，内部引入“预算状态 + 阶段决策 + reducer/verifier”结构

**Decision**: 对外继续保留 `DefaultCompressionPipeline.run()` / `run_emergency()` 入口，以及 `CompressionContext` / `CompressionResult` 基本调用方式；内部新增显式的预算决策和阶段执行结构，避免继续把所有规则堆在单个方法里。

**Rationale**:

- 当前调用方已经直接依赖 `DefaultCompressionPipeline`，包括 `_runtime_prepare_model_input()` 和 `_runtime_controller_compact()` 两条入口。
- 现有代码已经有 `CompressionBudgetState`、`AnalyzedMessage`、`CollapseState` 等对象，说明演进方向已经在向“显式状态”靠拢。
- 保持入口稳定可以降低对 bridge、controller、tests 和 runtime service 的波及范围。

**Alternatives considered**:

- 新建第二套 pipeline 类型替换旧入口：会导致 bridge、测试和 profile provider 同时重写，破坏兼容性。
- 继续在 `run()` 中追加条件分支：短期可行，但会让复杂度继续集中在单文件中，不利于后续维护和测试。

---

## 3. 预算驱动模型

### 决策：用三条预算线驱动阶段选择，并把预算状态显式暴露到结果元数据

**Decision**: 统一使用 `observe_tokens`、`target_tokens`、`must_fit_tokens` 三条预算线驱动压缩阶段决策，并把完整 `budget_state` 挂到 `CompressionResult.metadata`，由 bridge 继续透传。

**Rationale**:

- 现有实现已经在 `_build_budget_state()` 中计算这三条预算线和 `pressure_level`，但阶段切换仍偏向“固定顺序触发”。
- `docs/plans/runtime-compression-redesign-design.md` 的核心设计也是预算驱动状态机，这与现有数据结构天然对齐。
- 最新 review 修复已经说明 `budget_state` 元数据是可审计契约，不能再把它视为可选信息。

**Alternatives considered**:

- 继续只用 `trigger_pct` 判断阶段：无法表达“已经达标就停止”的预算收敛目标。
- 只在日志中记录预算，不进入 result metadata：bridge/controller 无法稳定消费该状态，测试契约也会变弱。

---

## 4. collapse 策略

### 决策：把 collapse 从“再追加一条 summary”重构为“唯一状态快照”

**Decision**: collapse 产物必须表示当前仍可工作的唯一状态快照，保留 objective、constraints、unresolved、finalized tasks、active failures、artifact refs 和关键证据摘要，禁止多条同类 collapse summary 长期叠加。

**Rationale**:

- 当前设计文档已明确“唯一状态快照”是解决重复摘要和过程态污染的核心。
- 现有 `_build_collapse_state()` / `_render_collapse_state()` 已接近该模型，说明只需沿现有实现收敛，而不是另起炉灶。
- 最新测试已经开始锁定 `Collapsed history` 中的 objective、unresolved、artifacts 与 finalized tasks。

**Alternatives considered**:

- 继续允许多条 collapse summary 共存：会持续污染上下文，并放大状态冲突。
- collapse 只保留摘要文本，不保留结构化字段：verifier 与后续桥接层无法稳定提取语义。

---

## 5. autocompact 与回滚

### 决策：保留 verifier 回滚机制，但按失败类型做“回滚或带审计接受”的区别处理

**Decision**: verifier 仍是压缩结果接受前的最后护栏；当候选结果满足 `must_fit_tokens` 而原始上下文本身不满足时，允许保留候选并显式记录“未回滚原因”，否则优先回滚到安全版本。

**Rationale**:

- 这条分支已经存在于当前 `compression_pipeline.py`，说明代码已经在处理“原始上下文无法 fit”的特殊情况。
- 设计文档明确要求压缩失败不能无差别继续压缩，也不能无脑回滚。
- 这类差异化处理最适合通过 verifier + rollback metadata 合同表达，而不是散落在 bridge 或 controller 中。

**Alternatives considered**:

- verifier 失败一律回滚：当原始上下文必然超限时，这会把系统带回不可执行状态。
- verifier 失败一律保留候选：会破坏 objective、结论和 unresolved 的护栏价值。

---

## 6. bridge 与 controller 的压缩闭环

### 决策：把模型输入压缩和显式 compact 决策统一到同一套结果契约

**Decision**: `_runtime_prepare_model_input()` 和 `_runtime_controller_compact()` 都继续使用 `DefaultCompressionPipeline`，并统一透传 `operations`、`budget_state`、`verifier_result`、`rollback_*`、artifact refs 等结果字段。

**Rationale**:

- 这两条链路是当前 runtime 压缩的真实入口，一个面向模型输入，一个面向 controller compact。
- 最新代码已经在 `_runtime_controller_compact()` 中把 `CompressionResult` 封装成 `CompactResult`，说明闭环只差契约收敛和字段补齐。
- 如果两条链路各自维护不同 metadata 结构，测试、持久化与排障成本都会持续上升。

**Alternatives considered**:

- 只优化模型输入压缩，不处理 controller compact：turn controller 仍会停留在“打标记但不真正消费压缩结果”的半闭环状态。
- 让 bridge 自己重新组装压缩元数据：会形成与 pipeline 并行的第二套契约。

---

## 7. 配置策略

### 决策：优先复用现有 `RuntimeCompressionProfileConfig`，只在现有字段无法表达目标时做增量扩展

**Decision**: `RuntimeCompressionProfileConfig` 与 `CompressionProfileProvider` 继续作为命名 profile 的唯一配置入口；本轮优先利用已有 pressure、persist、pruning、microcompact、collapse、autocompact、quality 等字段完成重构，只有证明确有表达缺口时才新增字段。

**Rationale**:

- 当前配置模型已经相当完整，并且 `runtime/service.py` 已把配置装配到共享 runtime services。
- 配置校验逻辑已经覆盖阈值顺序、history share、gain token 等关键约束。
- 增量扩展比重写 profile schema 风险低，也更符合稳定抽象原则。

**Alternatives considered**:

- 重写 profile schema：需要同时修改 config models、runtime service、profile provider 与现有配置文件，风险高。
- 把关键阈值硬编码到 pipeline：会削弱运行时调优能力，也破坏现有配置入口。

---

## 8. 测试与验证策略

### 决策：以现有 unit suites 为主线，先锁契约再做实现调整

**Decision**: 以 `backend/tests/unit/test_runtime_compression_pipeline.py`、`test_runtime_compression_verifier.py`、`test_runtime_gateway_adapter.py`、`test_runtime_turn_controller.py`、`test_runtime_compression_profiles.py` 为主验证面，采用“先加/收紧测试，再重构实现”的方式推进。

**Rationale**:

- 现有测试已经覆盖 summary 去重、collapse 快照、budget metadata、rollback、bridge compact 透传和 profile provider，是高信号基线。
- 宪章要求测试驱动开发和回归保护，这类算法重构尤其需要靠测试锁定行为边界。
- 单元测试比端到端测试更适合快速验证多种预算与语义边界组合。

**Alternatives considered**:

- 以人工对话验证为主：难以覆盖重复摘要、回滚和 compact metadata 这类细粒度契约。
- 先大改代码再补测试：高风险，不符合现有项目约束。

---

## 9. 研究结论汇总

本次 runtime 压缩重构的可执行方案应遵循以下主线：

1. 保持 `runtime` 作用域，避免牵连 legacy compression manager。
2. 保持 `DefaultCompressionPipeline` 入口稳定，内部按预算驱动重构阶段执行结构。
3. 让 `collapse` 产出唯一状态快照，清除摘要叠加。
4. 保持 verifier + rollback 机制，并对“原始上下文无法 fit”场景做可审计例外处理。
5. 打通 `_runtime_prepare_model_input()` 与 `_runtime_controller_compact()` 的共享契约。
6. 继续使用命名 profile 作为唯一压缩配置入口。
7. 以现有 runtime unit suites 为回归护栏推进实现。
