# Context 与 Compression 详细方案

> 范围：system prompt build、历史消息分层、artifact store、compression pipeline、memory flush。

---

## 1. 设计目标

本章节解决的问题是：

- 如何构建稳定、可控、可缓存的模型输入上下文
- 如何在长任务和长 session 中防止上下文膨胀
- 如何把“历史记录”和“模型输入”解耦

目标不是简单压缩字符串，而是建立一套有结构的信息保留与降级机制。

---

## 2. 当前代码映射（已对齐 runtime 实现）

当前相关能力主要分布在：

- `backend/src/runtime/context/builder.py`
- `backend/src/runtime/context/history_view.py`
- `backend/src/runtime/context/artifact_store.py`
- `backend/src/runtime/context/compression_pipeline.py`
- `backend/src/runtime/context/compression_verifier.py`
- `backend/src/runtime/context/profile_provider.py`
- `backend/src/runtime/context/memory_flush.py`
- `backend/src/gateway/agent_bridge.py`（`_runtime_prepare_model_input` 触发压缩）
- `backend/src/runtime/session/orchestrator.py`
- `backend/src/runtime/repositories.py`

现状说明：

- prompt build、history view、compression pipeline 已收敛到 `runtime/context`。
- 压缩触发与 emergency fallback 在 runtime turn 主链路中生效。
- memory flush 目前仍为 `NoopMemoryFlusher` 占位实现。

---

## 3. 目标模块结构

```text
backend/src/runtime/context/
├── builder.py
├── history_view.py
├── artifact_store.py
├── compression_pipeline.py
├── compression_verifier.py
├── profile_provider.py
└── memory_flush.py
```

---

## 4. 上下文分层

### 4.1 四层模型

```text
Raw Transcript
-> Summary Chain
-> Active History View
-> Final Model Input
```

### 4.2 含义

| 层 | 含义 |
|---|---|
| `Raw Transcript` | 完整原始会话记录，仅用于持久化、诊断、回放 |
| `Summary Chain` | durable 历史摘要链 |
| `Active History View` | 当前轮真正参与推理的历史视图 |
| `Final Model Input` | system prompt + active history + artifacts + budget |

关键原则：

- 模型输入永远不等于 raw transcript
- resume 时重新构建 active view，而不是直接回放全部原始消息

---

## 5. System Prompt Build V2

### 5.1 三层结构

system prompt 固定为三层：

1. 稳定前缀
   - 安全规则
   - 工具契约
   - 输出契约
2. 半稳定层
   - workspace 摘要
   - skills 元信息
   - 可用工具说明
   - session policy
3. 动态尾部
   - `TaskFrame`
   - 当前 budget
   - active summary
   - active artifact refs
   - recent history

### 5.2 PromptMode

```ts
type PromptMode = "full" | "minimal" | "none"
```

- `full`：主 agent
- `minimal`：child / subagent
- `none`：内部合成、压缩、提炼任务

### 5.3 设计约束

- 尽量保持前缀稳定，提高 cache 命中率
- skills 默认只注入索引元信息
- 大型 bootstrap 文件必须截断或摘要
- budget 信息作为动态尾部注入

---

## 6. Artifact Store

### 6.1 职责

Artifact Store 用来承接不适合长期保留在 active context 的大结果。

进入 Artifact Store 的典型内容：

- 长网页正文
- 长命令输出
- 大型搜索结果集
- 大型 JSON / 结构化抓取结果
- 大型代码片段列表

### 6.2 数据结构

```ts
type ArtifactRef = {
  id: string
  kind: "web" | "bash" | "search" | "file" | "tool" | "summary"
  title: string
  preview: string
  location?: string
  createdAt: number
  metadata: Record<string, unknown>
}
```

### 6.3 上下文中的保留形式

active context 只保留：

- artifact id
- kind
- preview
- origin tool
- location/path/url

---

## 7. Compression Pipeline

### 7.1 固定阶段

```text
1. single result persist
2. per-message aggregate budget
3. TTL pruning
4. microcompact
5. context collapse
6. auto-compact
7. memory flush
```

### 7.2 CompressionProfile

```ts
type CompressionProfile = {
  mode: "balanced" | "aggressive" | "conservative"
  pressure: {
    yellowPct: number
    orangePct: number
    redPct: number
    hardStopPct: number
  }
  persist: {
    singleResultChars: number
    aggregateResultChars: number
    artifactPreviewChars: number
    artifactPreviewHeadChars: number
    artifactPreviewTailChars: number
  }
  pruning: {
    enabled: boolean
    ttlMs: number
    preserveRecentAssistants: number
    minPrunableToolChars: number
    softTrimMaxChars: number
    softTrimHeadChars: number
    softTrimTailChars: number
    hardClearEnabled: boolean
    hardClearPlaceholder: string
  }
  microcompact: {
    enabled: boolean
    triggerPct: number
    maxUnitsPerPass: number
    preserveErrorResults: boolean
  }
  collapse: {
    enabled: boolean
    triggerPct: number
    maxSegmentTokens: number
    minSegmentTurns: number
  }
  autocompact: {
    enabled: boolean
    triggerPct: number
    reserveTokensFloor: number
    maxHistoryShare: number
    fallbackSummaryMaxChars: number
  }
  memoryFlush: {
    enabled: boolean
    softThresholdTokens: number
  }
  quality: {
    minCompressionGainTokens: number
    requirePostCheck: boolean
    rollbackOnInvariantFailure: boolean
  }
}
```

### 7.3 CompressionContext

```ts
type CompressionContext = {
  sessionKey: string
  turn: number
  taskFrame: TaskFrame
  profile: CompressionProfile
  modelContextWindow: number
  estimatedInputTokens: number
  messages: Message[]
  activeArtifacts: ArtifactRef[]
  budget: BudgetSnapshot
}
```

### 7.5 真实触发与持久化链路（代码现状）

当前压缩主链路为：

1. `gateway/dispatcher.py` 进入 runtime turn（`execute_runtime_turn`）。
2. `gateway/agent_bridge.py::_runtime_prepare_model_input` 组装 `CompressionContext` 并执行 `DefaultCompressionPipeline.run(...)`。
3. 若常规压缩后仍超限，则执行 `run_emergency(...)`。
4. `compression_verifier.py` 对压缩结果做 post-check；若失败且 profile 允许，则回滚到原始 messages/artifacts。
5. 压缩操作通过 orchestrator/repository 记录为 compression events，并与 transcript/snapshot/summary 一并持久化。

说明：`runtime_event_timeline` 回放在网关层由 `gateway/dispatcher.py` 完成。


## 8. 信息保留等级

| 等级 | 内容 |
|---|---|
| `P0` | objective、doneDefinition、constraints、最新用户请求、unresolved |
| `P1` | 最近 assistant 决策、最近失败、文件改动、artifact refs |
| `P2` | 最近历史摘要、重要中间结论 |
| `P3` | 老旧工具输出、可回读网页正文、已消费长结果 |

压缩规则：

- `P0` 不压
- `P1` 只能摘要，不能直接删除
- `P2` 可 collapse / compact
- `P3` 优先 persist 或清除

---

## 9. CompressionPipeline 伪代码

```ts
async function runCompressionPipeline(input: CompressionContext): Promise<CompressionResult> {
  let ctx = input
  const tokensBefore = estimateTokens(ctx.messages)
  const operations: CompressionOperation[] = []
  const collectedArtifacts: ArtifactRef[] = []

  for (const stage of COMPRESSION_PIPELINE) {
    if (!stage.shouldRun(ctx)) {
      continue
    }

    const beforeTokens = estimateTokens(ctx.messages)
    const stageResult = await stage.run(ctx)
    const afterTokens = estimateTokens(stageResult.messages)
    const gained = beforeTokens - afterTokens

    if (gained < ctx.profile.quality.minCompressionGainTokens) {
      if (stage.name !== "persist" && stage.name !== "memory_flush") {
        continue
      }
    }

    ctx = {
      ...ctx,
      messages: stageResult.messages,
      activeArtifacts: [...ctx.activeArtifacts, ...(stageResult.newArtifacts ?? [])],
      estimatedInputTokens: afterTokens,
    }

    collectedArtifacts.push(...(stageResult.newArtifacts ?? []))
    operations.push(...(stageResult.operations ?? []))

    const pressurePct = afterTokens / ctx.modelContextWindow
    if (pressurePct < ctx.profile.pressure.yellowPct) {
      break
    }
  }

  const postCheck = compressionVerifier.verify({
    before: input.messages,
    after: ctx.messages,
    taskFrame: input.taskFrame,
    artifacts: ctx.activeArtifacts,
  })

  return finalizeCompression(input, ctx, operations, collectedArtifacts, postCheck, tokensBefore)
}
```

---

## 10. Emergency Compression（当前实现）

当常规 pipeline 后仍过长时，当前实现会执行 `run_emergency(...)`，行为是：

1. 保留开头 system（若存在）
2. 插入一条 `[Emergency context summary]` 的 system 摘要（包含 objective / unresolved / artifact ids）
3. 保留最近 `retain_recent_messages` 尾部消息
4. 返回 `operations=["emergency_compact"]`

说明：当前 emergency 路径并不会在该层直接做 session reset；它提供 fallback summary 与可回滚标记，后续处置由上层 runtime 控制流决定。

---

## 11. Compression Verifier


```ts
type CompressionPostCheck = {
  tokensBefore: number
  tokensAfter: number
  freedTokens: number
  preservedObjective: boolean
  preservedUnresolved: boolean
  preservedRecentFailures: boolean
  preservedArtifactRefs: boolean
}
```

必须验证：

- objective 仍可恢复
- unresolved 未丢失
- 最近失败信息仍可恢复
- artifact refs 未损坏
- role ordering 没有被破坏

post-check 失败时：

- 优先回滚
- 再尝试更高等级压缩
- 最后才允许 fallback summary 或 session reset

---

## 12. 与现有代码的一致性结论（2026-04）

### 12.1 已落地

- Prompt Build / Context Build 已落地到 `runtime/context/builder.py`。
- Active History View 已落地到 `runtime/context/history_view.py`。
- Artifact Store 已落地到 `runtime/context/artifact_store.py`。
- Compression Pipeline / Verifier / Profile Provider 已落地到 `runtime/context/` 目录。
- Gateway -> Runtime 的压缩触发已接入主链路（`gateway/agent_bridge.py`）。

### 12.2 尚未完全收口

- `memory_flush.py` 当前是 noop 实现（`NoopMemoryFlusher`），仅保留扩展点。
- WebSocket 端点仍保留部分 session/outbox/cached-agent 协调逻辑，协议层与编排层边界仍可继续收敛。
- profile 选择仍依赖 metadata 约定，类型化契约仍可加强。

### 12.3 测试证据

- `backend/tests/unit/test_runtime_compression_pipeline.py` 覆盖了 persist、collapse、autocompact、emergency、post-check 开关等核心行为。
- `backend/tests/unit/test_runtime_compression_verifier.py` 覆盖了 role ordering、artifact refs、objective、recent failures 等不变量校验。

---

## 13. 验收标准

达到以下条件后，认为 Context & Compression 基线完成：

- prompt build 分层明确
- active context 不直接等于 raw transcript
- 大结果能稳定进入 artifact store
- compression pipeline 独立可测试
- 有统一 profile
- 有 post-check 和 emergency fallback

---

## 14. 与其它子系统的边界

### 它服务谁

- 为 `TurnController` 提供稳定的模型输入
- 为 `SessionOrchestrator` 提供可归档、可回放的 session 视图

### 它不负责什么

- 不决定是否继续循环
- 不决定是否 spawn
- 不负责 route 和 channel 发送

这些仍然属于 controller 和 orchestrator 的职责。
