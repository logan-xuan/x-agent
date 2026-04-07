# Runtime Compression Redesign Design

## 背景

当前压缩体系已具备 runtime 主链路能力（builder + pipeline + verifier + emergency），但仍处于 runtime 与 legacy 并存迁移态，导致链路判定、契约一致性与校验强度存在不稳定因素。

## 设计目标

1. 以 runtime 路径作为唯一在线压缩主链路。
2. 统一上下文与压缩契约，消除跨层隐式约定。
3. 强化压缩后校验与回滚真实性，避免“弱校验通过”。
4. 在保证质量前提下维持时延与成本稳定。

## 非目标

- 不在本阶段引入全新外部存储系统。
- 不改变 Gateway 对外协议格式。
- 不在本阶段做激进语义压缩模型替换。

## 现状基线（代码锚点）

- 主链路入口：`backend/src/gateway/dispatcher.py`、`backend/src/gateway/agent_bridge.py`
- 压缩执行：`backend/src/runtime/context/compression_pipeline.py`
- 后验校验：`backend/src/runtime/context/compression_verifier.py`
- 回合触发：`backend/src/runtime/turn/controller.py`
- 预算控制：`backend/src/runtime/turn/budget.py`
- 会话持久化：`backend/src/runtime/session/orchestrator.py`、`backend/src/runtime/repositories.py`
- 并存兼容路径：`backend/src/agent_core/adapters/context_adapter.py`、`backend/src/services/compression/manager.py`

## 目标架构

### 分层职责

1. **Gateway Layer**
   - 仅处理路由、会话绑定、事件映射。
   - 不做压缩策略决策。

2. **Turn Layer**
   - 仅输出 compact/stop/continue 决策。
   - 不持有压缩阶段细节。

3. **Context Governance Layer（唯一压缩域）**
   - 统一执行 context build、pipeline stages、verifier、rollback、emergency。
   - 输出唯一 `CompressionResult` 作为模型输入依据。

4. **Persistence Layer**
   - 记录 transcript/summary/snapshot/compression events/artifacts。
   - 不二次改写压缩决策。

## 统一契约

### 输入契约（CompressionContext）

- messages
- system prompt 片段（稳定层/动态层）
- tool schemas
- objective
- unresolved
- recent_failures
- active artifacts
- budget snapshot
- model window / token pressure

### 输出契约（CompressionResult）

- compressed_messages
- updated_artifacts
- summary
- operations（按阶段顺序）
- verifier_result
- rollback_applied
- rollback_reason（若有）

## 目标流程

1. `dispatcher` 进入 runtime turn。
2. `controller` 给出是否 compact。
3. context 层构建输入并执行固定阶段 pipeline：
   - persist
   - aggregate
   - ttl prune
   - microcompact
   - collapse
   - autocompact
   - memory flush
   - verifier
4. verifier 失败且允许回滚时，恢复原始输入并记录原因。
5. 常规压缩后仍超窗，进入 emergency compact。
6. 模型调用后由 orchestrator/repositories 做事实持久化。

## 校验与回滚设计

### 必检不变量

- objective preserved
- unresolved preserved
- recent_failures preserved
- artifact refs preserved
- role ordering valid

### 真实性要求

- verifier 必须消费真实 before/after 快照。
- 禁止使用同源 metadata 直接“喂给”压缩后结果来绕过关键校验。

### 回滚策略

- post-check fail + rollback enabled：强制回滚。
- 回滚事件必须落地到 compression events，并携带原因与阶段上下文。

## 测试与验收

### 回归场景

1. 大工具输出持久化与压力重算。
2. 高压触发 collapse/autocompact。
3. emergency summary + tail 保留。
4. verifier 失败触发 rollback。
5. resume 场景下上下文重建与压缩一致性。

### 验收口径

- 正确性：不变量失败可稳定拦截并回滚。
- 稳定性：timeout 与 rollback 率无异常上升。
- 性能：first-byte 与 token 成本不劣化。

## 分阶段落地

### Phase 0：观测对齐

- 统一压缩指标字段与事件口径（pressure/operations/verifier/rollback/emergency）。

### Phase 1：契约收敛

- 对齐 context adapter/runtime pipeline/gateway metadata 字段。

### Phase 2：单主链路切换

- runtime 设为唯一在线压缩路径。
- legacy manager 仅保留灰度兜底开关。

### Phase 3：校验增强

- verifier 改为真实快照输入。
- 补齐失败注入测试。

### Phase 4：应急策略演进

- emergency 从固定逻辑升级为可配置策略机（保留优先级规则）。

## 风险与缓解

- **风险**：切换期间链路识别错误。
  - **缓解**：分阶段灰度 + 回滚开关。
- **风险**：校验增强导致误回滚增多。
  - **缓解**：先观测、再收紧阈值，保留按阶段降级策略。
- **风险**：性能抖动。
  - **缓解**：对关键场景建立基线并做回归门禁。

## 交付

- 本设计文档：`docs/plans/2026-04-07-runtime-compression-redesign-design.md`
- 对应架构分析：`arch/compact/compact.md`
