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

## 2. 当前代码映射

当前相关能力主要分布在：

- `backend/src/conversation/system_prompt_builder.py`
- `backend/src/conversation/context_loader.py`
- `backend/src/conversation/session.py`
- `backend/src/services/context/`
- `backend/src/services/compression/`
- `backend/src/memory/manager.py`
- `backend/src/memory/context_builder.py`

现状问题：

- prompt build、history、memory、compression 的职责边界还不够清晰
- 历史消息和 active context 还不完全是两套视图
- 压缩逻辑需要收敛为统一 pipeline

---

## 3. 目标模块结构

```text
context_runtime/
├── system_prompt_builder_v2.py
├── context_builder.py
├── history_view_builder.py
├── artifact_store.py
├── compression_pipeline.py
├── compression_profile.py
├── compression_verifier.py
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

### 7.4 CompressionStage

```ts
type CompressionStage = {
  name:
    | "persist"
    | "aggregate_budget"
    | "ttl_prune"
    | "microcompact"
    | "collapse"
    | "autocompact"
    | "memory_flush"

  shouldRun(ctx: CompressionContext): boolean
  run(ctx: CompressionContext): Promise<CompressionStageResult>
}
```

---

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

## 10. Emergency Compression

正常 pipeline 后仍过长，或者命中 `prompt_too_long/context_overflow` 时：

1. 强制启用 collapse + autocompact
2. 缩窄保留范围到 `P0/P1`
3. 生成 fallback summary
4. 仍失败则 reset session / best effort 结束

禁止：

- 在坏上下文上无限重复 compact
- compact 失败后继续追加新大结果

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

## 12. 与现有代码的改造方式

### Phase 2A: Prompt Build 收敛

从：

- `conversation/system_prompt_builder.py`
- `conversation/context_loader.py`

抽出新的 `SystemPromptBuilderV2` 与 `ContextBuilder`。

### Phase 2B: Artifact Store 收敛

将：

- `services/context/`
- 未来的大结果持久化逻辑

统一收敛成 `ArtifactStore`。

### Phase 2C: CompressionPipeline 收敛

从：

- `services/compression/manager.py`
- `services/compression/compressor.py`
- `memory/manager.py`

中抽出统一 pipeline。

### Phase 2D: Active History View 收敛

把 `conversation/session.py` 中与原始历史/当前上下文混杂的部分拆开，形成：

- raw transcript
- summary chain
- active history view

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
