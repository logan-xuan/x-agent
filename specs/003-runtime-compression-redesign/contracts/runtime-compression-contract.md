# Contract: Runtime 压缩主契约

**Feature Branch**: `003-runtime-compression-redesign`  
**Date**: 2026-04-08

## 1. 目标

本契约定义 runtime 压缩在以下边界上的稳定行为：

- `DefaultCompressionPipeline` 的输入输出
- verifier 的后置校验语义
- `AgentBridge` / `DefaultTurnController` 消费压缩结果的方式

本契约面向内部模块，不是对外 HTTP API。

## 2. 主入口

### 2.1 Pipeline 入口

```python
await DefaultCompressionPipeline.run(ctx: CompressionContext) -> CompressionResult
await DefaultCompressionPipeline.run_emergency(ctx: CompressionContext) -> CompressionResult
```

### 2.2 Bridge compact 入口

```python
await AgentBridge._runtime_controller_compact(state, reason: str) -> CompactResult
```

### 2.3 模型输入压缩入口

```python
await AgentBridge._runtime_prepare_model_input(state, system_prompt, available_tools)
    -> tuple[str, list[dict[str, Any]]]
```

## 3. 输入契约

### CompressionContext 必备字段

- `session_key`
- `turn`
- `task_frame`
- `profile`
- `model_context_window`
- `estimated_input_tokens`
- `messages`
- `active_artifacts`
- `budget`

### task_frame 语义要求

- `objective` 为空时允许压缩继续，但不能伪造 objective。
- `unresolved` 是 verifier 的基准语义，压缩后不能无理由消失。
- `active_artifacts` 与 `active_artifacts` / `artifact_refs` 必须一致建模。

## 4. 输出契约

### CompressionResult 必备字段

- `messages`
- `active_artifacts`
- `estimated_input_tokens`
- `operations`
- `metadata`
- `rollback_applied`
- `rollback_reason`

### operations 约束

`operations` 允许包含但不限于以下值：

- `persist`
- `aggregate_budget`
- `ttl_prune`
- `microcompact`
- `collapse`
- `autocompact`
- `memory_flush`
- `emergency_compact`
- `rollback`

### metadata 必备键

压缩结果必须尽量保持以下键稳定：

- `objective_out_of_band`
- `budget_state`
- `verification`
- `verifier_result`
- `rollback`
- `rollback_applied`
- `rollback_reason`

其中：

- `budget_state` 必须是结构化对象，而不是仅写入日志。
- `rollback` 必须说明是否发生回滚、原因以及跳过回滚的情况。

## 5. 语义护栏契约

### 5.1 必须保留

压缩后必须保留或以等价方式表达：

- 当前 objective
- 当前 unresolved
- 当前仍有效的 artifact refs
- 最近关键结论
- 当前仍有效的失败信息

### 5.2 必须拒绝

以下情况 verifier 必须拒绝：

- objective 丢失或与任务帧冲突
- unresolved 与任务帧偏离
- artifact refs 丢失
- 同一任务同时保留运行态和终态
- 关键结论丢失
- 压缩收益低于 profile 设定下限

### 5.3 回滚策略

- 默认情况下 verifier 失败应回滚到安全版本。
- 若候选结果已满足 `must_fit_tokens` 且原始上下文本身不满足，则允许保留候选，但必须记录“未回滚原因”。

## 6. collapse 契约

### 6.1 collapse 产物结构

`collapse` 产物必须表达为唯一状态快照，至少包含：

- `Objective`
- `Constraints`
- `Unresolved`
- `Finalized tasks`
- `Active failures`
- `Artifacts`
- `Evidence summaries`

### 6.2 禁止行为

- 禁止在旧 `collapse summary` 之上继续叠加新 `collapse summary`
- 禁止同时保留多个互相冲突的状态快照

## 7. bridge/controller 契约

### 7.1 bridge 透传要求

`AgentBridge._runtime_controller_compact()` 必须透传：

- 压缩后的 messages
- active artifact refs
- `compression_operations`
- `budget_state`
- `verifier_result`
- `rollback_*`

### 7.2 controller 消费要求

`DefaultTurnController._apply_compact_result()` 必须能够把 `CompactResult` 中的：

- `active_messages`
- `active_artifact_refs`
- `output_text`
- `task_frame`
- `metadata`

更新到当前 turn state。

## 8. 兼容性约束

- 不允许移除 `DefaultCompressionPipeline` 入口。
- 不允许让 `CompressionResult` 变成与现有调用方不兼容的新类型。
- 新增字段必须以增量兼容方式加入。
- 本轮不改 legacy compression manager 行为。
