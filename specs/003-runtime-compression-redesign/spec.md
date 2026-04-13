# Feature Specification: Runtime 压缩算法重构

**Feature Branch**: `003-runtime-compression-redesign`  
**Created**: 2026-04-08  
**Status**: Draft  
**Input**: User description: "我要对系统的压缩算法进行重构,请先参考docs/plans/runtime-comperession-redesign-design.md 并结合最新的代码设计方案"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 预算驱动的分层压缩决策 (Priority: P1)

作为 runtime 控制平面，我希望压缩动作根据明确的预算状态和压力等级选择 `microcompact`、`collapse`、`autocompact` 或 `emergency`，而不是固定顺序串行执行，以便在超限前尽快回收上下文预算并在达标后及时停止。

**Why this priority**: 当前压缩链路已经可用，但仍以固定阶段流水线为主，压缩率不可控，也难以判断为什么进入某个阶段。这是本次重构的核心目标。

**Independent Test**: 可以通过 `backend/tests/unit/test_runtime_compression_pipeline.py` 中的预算、历史占比、阶段切换测试独立验证，不依赖前端和外部渠道。

**Acceptance Scenarios**:

1. **Given** runtime 上下文 token 已进入观察区但未超目标线，**When** 运行压缩流程，**Then** 系统只记录预算状态，不进入重写历史的强压缩阶段。
2. **Given** runtime 上下文存在重复 summary、终态覆盖旧状态或明显重复工具结果，**When** 运行压缩流程，**Then** 系统优先执行语义感知的 `microcompact` 去除低价值冗余。
3. **Given** `microcompact` 后仍高于目标预算或历史占比过高，**When** 运行压缩流程，**Then** 系统进入 `collapse` 或 `autocompact` 并在满足预算目标后立即停止，而不是无条件串行跑完整条链路。

---

### User Story 2 - 压缩后的语义护栏与失败回滚 (Priority: P1)

作为 runtime 执行链路，我希望压缩结果在任何阶段都保留当前 objective、未完成事项、关键结论、仍有效的失败信息和 artifact 引用，并在压缩违反这些护栏时回滚到安全状态，以避免压缩后继续推理时出现语义漂移。

**Why this priority**: 压缩率提升不能以牺牲可用性为代价。当前 verifier 已经覆盖部分字段，但还不足以把“高压缩率”与“可继续工作”稳定地绑定在一起。

**Independent Test**: 可以通过 `backend/tests/unit/test_runtime_compression_verifier.py` 与 `backend/tests/unit/test_runtime_compression_pipeline.py` 的回滚、目标保留、结论保真、状态冲突测试独立验证。

**Acceptance Scenarios**:

1. **Given** 压缩候选结果丢失 objective、unresolved 或 artifact refs，**When** verifier 执行后置校验，**Then** 系统拒绝该候选并根据回滚策略保留安全版本。
2. **Given** 同一任务在压缩后同时保留 `pending/running` 和 `done/failed/cancelled`，**When** verifier 检查状态一致性，**Then** 系统标记冲突并拒绝该压缩结果。
3. **Given** 原始上下文本身已经超过 `must_fit` 且候选结果刚好满足预算，**When** verifier 失败，**Then** 系统允许带审计元数据地保留候选结果，而不是盲目回滚到一个肯定超限的原始上下文。

---

### User Story 3 - runtime 与桥接层的压缩闭环 (Priority: P2)

作为 Gateway 与 turn controller，我希望模型输入压缩和显式 compact 决策都复用同一套 runtime 压缩契约，并把真实的压缩结果、元数据、artifact 与预算状态传回 state、controller 和持久化链路，而不是只在桥接层打标记。

**Why this priority**: 当前 `runtime` 已经是默认入口，但真实闭环仍依赖 `AgentBridge`。如果不把压缩结果通过 bridge/controller 闭环打通，再好的 pipeline 也只是局部优化。

**Independent Test**: 可以通过 `backend/tests/unit/test_runtime_gateway_adapter.py` 和 `backend/tests/unit/test_runtime_turn_controller.py` 独立验证 compact 结果透传、metadata 保留和 state 更新。

**Acceptance Scenarios**:

1. **Given** `DefaultTurnController` 因预算或 assessment 请求 compact，**When** `AgentBridge._runtime_controller_compact()` 被调用，**Then** controller state 必须接收真实压缩后的 messages、artifacts 和 metadata。
2. **Given** `_runtime_prepare_model_input()` 在模型调用前执行压缩，**When** pipeline 生成预算状态和压缩操作列表，**Then** bridge 必须记录压缩事件并更新 `state.active_artifact_refs` 与上下文摘要信息。
3. **Given** pipeline 返回回滚、budget_state 或 verifier 结果，**When** bridge 把压缩结果封装为 `CompactResult`，**Then** 这些元数据不能在桥接层丢失。

---

### User Story 4 - 可配置的压缩策略与可观测输出 (Priority: P3)

作为开发者和运维者，我希望 runtime 压缩策略继续通过命名 profile 与配置模型管理，并能够从日志、持久化元数据和测试输出中观察当前压缩阶段、预算状态、收益和回滚原因，以便安全演进算法。

**Why this priority**: 压缩重构会改变预算判断和上下文形态，没有稳定的配置入口和观测数据，就很难逐步上线和回归验证。

**Independent Test**: 可以通过 `backend/tests/unit/test_runtime_compression_profiles.py`、runtime 配置映射测试，以及压缩元数据断言独立验证。

**Acceptance Scenarios**:

1. **Given** 运行时加载 `runtime.compression_profiles`，**When** profile 被转换为 `CompressionProfile`，**Then** 所有阈值、质量门禁和保留数量必须保持可校验的一致映射。
2. **Given** 某次压缩触发 `microcompact`、`collapse`、`autocompact` 或 `emergency`，**When** 压缩完成，**Then** 结果必须暴露预算状态、阶段操作、verifier 结果和回滚信息。
3. **Given** 新增或调整压缩 profile，**When** 配置不满足约束条件，**Then** 系统必须在配置验证阶段失败，而不是在运行时静默退化。

---

### Edge Cases

- 原始上下文本身已经超出 `must_fit_tokens`，但回滚后只会更糟，系统如何在“预算必须满足”和“语义护栏失败”之间做出可审计选择？
- 同一任务跨多轮留下多条 `collapse` / `autocompact` summary 时，系统如何保证只保留一个当前有效的状态快照？
- 最近窗口中存在高价值失败信息和大工具结果时，系统如何避免 `autocompact` 先裁掉关键证据？
- `microcompact` 去掉重复状态后，如果后续 `collapse` 或 `autocompact` 失败并回滚，系统如何保留 artifact 更新和 budget_state 元数据？
- 当不同 profile 的 `trigger_pct`、`max_history_share`、`retain_recent_messages` 组合出现冲突时，系统如何在配置加载阶段阻止非法组合进入运行态？
- `turn controller` 的显式 compact 与模型调用前的隐式压缩同时存在时，系统如何避免两条路径产生不一致的 summary 结构和 metadata 键名？

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 在 runtime 压缩中显式区分观察线、目标线和必须适配线，并基于当前预算状态决定压缩动作。
- **FR-002**: 系统 MUST 保留 `DefaultCompressionPipeline` 作为 runtime 压缩主入口，避免破坏现有调用方对入口对象的依赖。
- **FR-003**: 系统 MUST 将压缩阶段从“固定顺序流水线”重构为“预算驱动的分层决策”，并允许在目标已满足时提前停止。
- **FR-004**: 系统 MUST 让 `microcompact` 优先处理重复 summary、终态覆盖旧状态、重复工具结果和明显低价值话术。
- **FR-005**: 系统 MUST 让 `collapse` 生成唯一的历史状态快照，而不是持续叠加新的 summary 文本。
- **FR-006**: 系统 MUST 让 `autocompact` 围绕预算目标逐步收口，并在每一步后重算 token 与阶段状态。
- **FR-007**: 系统 MUST 保留 `emergency` 作为兜底路径，但 MUST 防止它成为常态主路径。
- **FR-008**: 系统 MUST 在压缩结果中保留当前 objective、unresolved、关键结论、有效失败信息和 artifact refs，除非这些信息被明确标记为 out-of-band 且有稳定替代载体。
- **FR-009**: 系统 MUST 通过 verifier 对压缩结果执行后置校验，至少覆盖 objective、一致的 unresolved、artifact refs、状态冲突、关键结论与压缩收益。
- **FR-010**: 系统 MUST 在 verifier 失败时执行可审计的回滚逻辑，并显式暴露 rollback 是否发生、原因以及跳过回滚的条件。
- **FR-011**: 系统 MUST 让 `_runtime_prepare_model_input()` 和 `_runtime_controller_compact()` 两条 runtime 压缩入口共享同一套压缩结果契约。
- **FR-012**: 系统 MUST 让 `AgentBridge` 将压缩后的 messages、artifact refs、operations、budget_state、verifier 结果和 rollback 元数据透传给 controller state 与后续持久化逻辑。
- **FR-013**: 系统 MUST 保持 `CompressionContext`、`CompressionResult`、`CompactResult` 的外部使用方式向后兼容，新增字段应采用增量扩展而不是破坏性替换。
- **FR-014**: 系统 MUST 继续支持通过 `RuntimeCompressionProfileConfig` 和 `CompressionProfileProvider` 管理命名压缩 profile。
- **FR-015**: 系统 MUST 对压缩 profile 做加载期校验，防止非法阈值、错误预算顺序和不合理保留策略进入运行态。
- **FR-016**: 系统 MUST 记录 runtime 压缩事件，至少包含压缩前后 token、执行阶段、预算状态、verifier 结果和 rollback 信息。
- **FR-017**: 系统 MUST 为本次重构补齐单元测试，覆盖 pipeline、verifier、profile provider、gateway bridge 和 turn controller 的关键压缩契约。
- **FR-018**: 系统 MUST 不修改 legacy compression manager 的行为边界，本轮改动仅作用于 runtime 压缩链路。

### Key Entities *(include if feature involves data)*

- **CompressionBudgetState**: runtime 压缩的预算快照，描述 `current_tokens`、`observe_tokens`、`target_tokens`、`must_fit_tokens`、压力等级、历史占比和溢出风险。
- **CompressionPlan / Stage Decision**: 压缩阶段决策结果，决定当前进入观察、`microcompact`、`collapse`、`autocompact` 还是 `emergency`，并给出停止条件。
- **CollapseState Snapshot**: collapse 产生的唯一状态快照，保留 objective、constraints、unresolved、finalized tasks、active failures、artifact refs 和关键证据摘要。
- **CompressionResult**: runtime pipeline 输出，包含压缩后的 messages、artifact refs、估算 token、operations、metadata、verifier 结果和 rollback 信息。
- **CompressionVerifyRequest / CompressionPostCheck**: verifier 的输入输出对象，用于表达压缩候选、校验结果和失败原因。
- **RuntimeCompressionProfile**: 运行时压缩策略配置，定义各阶段阈值、结果持久化规则、质量门禁和最近消息保留策略。
- **CompressionTelemetry Record**: 压缩事件审计记录，面向桥接层、持久化和调试接口暴露运行态信息。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 在高历史占比、重复 summary 和终态覆盖场景下，runtime 压缩能够在不进入 `emergency` 的情况下把上下文压回目标预算线以下。
- **SC-002**: 对 objective、unresolved、artifact refs、关键结论和终态冲突的压缩护栏，都有对应的自动化测试，并在重构后保持通过。
- **SC-003**: `AgentBridge` 的模型输入压缩路径和 controller compact 路径都能输出一致的压缩元数据结构，且不丢失 `budget_state`、`verifier_result` 和 `rollback_*` 信息。
- **SC-004**: 新方案不会引入对 legacy compression manager 的行为回归，runtime 外部调用入口仍保持兼容。
- **SC-005**: profile 配置非法时，系统在配置加载阶段直接失败；profile 合法时，`CompressionProfileProvider` 和 runtime config 映射测试通过。
