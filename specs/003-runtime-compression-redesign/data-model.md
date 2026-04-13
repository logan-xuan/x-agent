# Data Model: Runtime 压缩算法重构

**Feature Branch**: `003-runtime-compression-redesign`  
**Date**: 2026-04-08  
**Status**: Draft

## 实体概览

```text
CompressionContext
    ├── TaskFrame
    ├── BudgetSnapshot
    ├── CompressionProfile
    ├── messages[]
    └── active_artifacts[]
           │
           ▼
MessageSemanticView / AnalyzedMessage[]
           │
           ├── CompressionBudgetState
           ├── CompressionStageDecision
           └── CollapseState
                   │
                   ▼
             CompressionResult
                   │
                   ├── CompressionVerifyRequest
                   ├── CompressionPostCheck
                   └── BridgeCompactEnvelope / CompactResult
```

---

## 核心实体

### 1. CompressionContext

runtime 压缩主入口的输入对象，描述一次压缩所需的完整上下文。

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| session_key | str | ✅ | 当前 runtime session 唯一键 |
| turn | int | ✅ | 当前 turn 索引 |
| task_frame | TaskFrame | ✅ | 当前任务语义，包括 objective、unresolved 等 |
| profile | CompressionProfile | ✅ | 当前使用的压缩 profile |
| model_context_window | int | ✅ | 模型可用上下文窗口 |
| estimated_input_tokens | int | ✅ | 压缩前估算 token |
| messages | list[dict] | ✅ | 待压缩消息序列 |
| active_artifacts | list[ArtifactRef] | ✅ | 当前上下文引用的 artifact |
| budget | BudgetSnapshot | ✅ | 当前 turn 的预算快照 |
| metadata | dict[str, Any] | ❌ | 运行时附加元数据，如 recent_failures、now_ms |

**关系**:

- `CompressionContext` 持有一个 `TaskFrame`
- `CompressionContext` 持有一个 `BudgetSnapshot`
- `CompressionContext` 持有多个消息和 artifact 引用

---

### 2. AnalyzedMessage

消息语义分析结果，是 `microcompact`、`collapse` 和 verifier 的共同输入。

| 字段 | 类型 | 说明 |
|------|------|------|
| raw | dict[str, Any] | 原始消息 |
| index | int | 在上下文中的位置 |
| role | str | 消息角色 |
| content | str | 文本内容 |
| semantic_priority | str | 语义优先级，典型值为 `P0/P1/P2/P3` |
| message_kind | str | 消息类别，如 objective、summary、status、result、chatter |
| message_signature | str \| None | 用于去重的签名 |
| task_id | str \| None | 提取出的任务标识 |
| state_label | str \| None | 提取出的状态标签 |
| superseded_by_terminal | bool | 是否已被终态覆盖 |
| compressible | bool | 是否允许被压缩 |
| droppable | bool | 是否可直接丢弃 |

**作用**:

- 驱动重复摘要识别
- 驱动终态覆盖旧状态
- 驱动低价值消息裁剪

---

### 3. CompressionBudgetState

压缩阶段决策使用的预算状态对象。

| 字段 | 类型 | 说明 |
|------|------|------|
| current_tokens | int | 当前估算 token |
| observe_tokens | int | 观察线 |
| target_tokens | int | 压缩目标线 |
| must_fit_tokens | int | 必须适配线 |
| remaining_tokens | int | 距离必须适配线的剩余空间 |
| pressure_level | str | 压力等级，如 `normal/yellow/orange/red` |
| repeated_summary_ratio | float | 重复摘要占比 |
| history_share_ratio | float | 历史消息占比 |
| overflow_risk | bool | 是否已经逼近或超过必须适配线 |

**关系**:

- 由 `CompressionContext + AnalyzedMessage[]` 推导产生
- 被 `CompressionStageDecision` 与 `CompressionResult.metadata` 复用

---

### 4. CompressionStageDecision

压缩阶段选择结果，决定本轮压缩应该进入哪个动作层。

| 字段 | 类型 | 说明 |
|------|------|------|
| phase | str | 当前阶段：`normal`、`microcompact`、`collapse`、`autocompact`、`emergency` |
| reason | str | 进入当前阶段的原因 |
| stop_when_met | bool | 达标后是否立即停止 |
| target_tokens | int | 当前阶段应收敛到的 token 目标 |
| metadata | dict[str, Any] | 阶段决策附加信息 |

**状态迁移**:

```text
normal
  -> microcompact
  -> collapse
  -> autocompact
  -> emergency

microcompact
  -> normal
  -> collapse

collapse
  -> normal
  -> autocompact

autocompact
  -> normal
  -> emergency
```

---

### 5. CollapseState

`collapse` 阶段维护的唯一历史状态快照。

| 字段 | 类型 | 说明 |
|------|------|------|
| objective | str | 当前目标 |
| active_constraints | list[str] | 当前仍有效的约束 |
| unresolved | list[str] | 当前未完成事项 |
| finalized_tasks | list[str] | 已完成任务的最终状态 |
| active_failures | list[str] | 当前仍有效的失败/错误 |
| artifact_refs | list[str] | 当前仍被引用的 artifact id |
| evidence_summaries | list[str] | 对当前判断仍有价值的关键结论和证据摘要 |

**不变式**:

- 同一段旧历史只能对应一个有效 `CollapseState`
- `objective`、`unresolved` 和 `artifact_refs` 不能为空洞化表达
- `finalized_tasks` 与 `active_failures` 不得同时保留互相冲突的状态

---

### 6. CompressionResult

pipeline 的统一输出对象。

| 字段 | 类型 | 说明 |
|------|------|------|
| messages | list[dict[str, Any]] | 压缩后的消息 |
| active_artifacts | list[ArtifactRef] | 压缩后仍激活的 artifact |
| estimated_input_tokens | int | 压缩后估算 token |
| operations | list[str] | 本轮执行过的压缩动作 |
| metadata | dict[str, Any] | 压缩元数据 |
| verifier_result | CompressionPostCheck \| None | verifier 检查结果 |
| rollback_applied | bool | 是否执行了回滚 |
| rollback_reason | str \| None | 回滚原因 |

**核心元数据键**:

- `budget_state`
- `objective_out_of_band`
- `verification`
- `verifier_result`
- `rollback`
- `rollback_applied`
- `rollback_reason`

---

### 7. CompressionVerifyRequest / CompressionPostCheck

verifier 的输入输出对象。

#### CompressionVerifyRequest

| 字段 | 类型 | 说明 |
|------|------|------|
| task_frame | TaskFrame | 原始任务语义 |
| original_messages | list[Any] | 压缩前消息 |
| compressed_messages | list[Any] | 压缩后消息 |
| original_artifacts | list[ArtifactRef] | 压缩前 artifact |
| compressed_artifacts | list[ArtifactRef] | 压缩后 artifact |
| metadata | dict[str, Any] | 校验所需的推导元数据 |

#### CompressionPostCheck

| 字段 | 类型 | 说明 |
|------|------|------|
| ok | bool | 校验是否通过 |
| reasons | list[str] | 失败原因列表 |
| preserved_fields | dict[str, bool] | 各项语义护栏是否保留 |

**保留字段重点**:

- objective
- unresolved
- recent_failures
- artifact_refs
- role_ordering
- state_conflicts
- compression_gain
- conclusion_fidelity

---

### 8. RuntimeCompressionProfile

命名压缩 profile 的运行时实例。

| 维度 | 子对象 | 说明 |
|------|--------|------|
| pressure | CompressionPressureConfig | 观察线、目标线、必须适配线阈值 |
| persist | CompressionPersistConfig | 大工具结果持久化阈值 |
| pruning | CompressionPruningConfig | TTL、软裁剪和硬清理规则 |
| microcompact | CompressionMicrocompactConfig | 轻量去噪策略 |
| collapse | CompressionCollapseConfig | 历史收敛策略 |
| autocompact | CompressionAutocompactConfig | 强制预算收口策略 |
| memory_flush | CompressionMemoryFlushConfig | 记忆刷新阈值 |
| quality | CompressionQualityConfig | verifier 与 rollback 质量门禁 |
| retain_recent_messages | int | 最近窗口保留消息数 |

**关系**:

- 由 `RuntimeCompressionProfileConfig` 经 `CompressionProfileProvider` 转换而来
- 被 `CompressionContext` 引用

---

### 9. BridgeCompactEnvelope

bridge/controller 路径消费的压缩结果封装，当前实现对应 `CompactResult`。

| 字段 | 类型 | 说明 |
|------|------|------|
| active_messages | list[dict[str, Any]] | bridge 需要替换到 state 的消息 |
| active_artifact_refs | list[ArtifactRef] | 当前仍有效的 artifact |
| output_text | str \| None | 可作为摘要输出的文本 |
| task_frame | TaskFrame \| None | 更新后的任务帧 |
| metadata | dict[str, Any] | 透传的压缩元数据 |

**作用**:

- 连接 `DefaultCompressionPipeline` 与 `DefaultTurnController`
- 让 compact 不再只是“请求过压缩”，而是“真正消费压缩结果”

---

## 设计约束

### 关键不变式

1. objective、unresolved、artifact refs 不能被静默丢失。
2. 同一任务不能同时保留运行态和终态。
3. `collapse` 必须收敛为唯一状态快照。
4. `CompressionResult` 的外部使用方式必须保持兼容。
5. budget_state、verifier_result 和 rollback 信息必须能从 pipeline 一路透传到 bridge。

### 重点关系

- `CompressionContext` 是所有压缩动作的输入根对象。
- `AnalyzedMessage` 与 `CompressionBudgetState` 是阶段选择和语义处理的中间层。
- `CollapseState` 是中度压缩时的唯一快照表示。
- `CompressionResult` 是 pipeline 的统一输出。
- `BridgeCompactEnvelope` 是 turn controller 消费压缩结果的适配层。
