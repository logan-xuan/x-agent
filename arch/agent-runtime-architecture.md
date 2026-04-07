# 通用 Agent Runtime 架构方案

> 目标：先提升单任务循环内拿结果的能力、准确性、稳定性，再扩展长期多 session / subagent 并行编排能力。

---

## 1. 设计目标

本方案解决两个层面的核心问题：

1. 单个任务回合内的收敛控制
   - 避免 agent 在开放式任务中无限循环
   - 提升长任务下的准确性、稳定性、可解释性
   - 控制 token、tool 输出、工具次数、错误重试与上下文膨胀
2. 长期多 session 运行的隔离与编排
   - 支持 session 级生命周期、路由、归档、压缩、回放
   - 支持 bounded subagent 并行，不让主线程上下文失控
   - 为后续 `session_spawn`、lane、route、background task 提供统一 runtime 基座

本方案不是 research 专项优化，而是一套通用 agent runtime。

---

## 2. 总体原则

### 2.1 控制器优先，不靠 prompt 自觉

- 模型可以提出建议，但不能决定是否无限继续
- 是否继续、是否压缩、是否中止、是否 spawn，最终由 runtime controller 决策
- prompt 负责表达意图，controller 负责硬约束

### 2.2 原始大结果不上主上下文

- 长网页、长命令输出、批量搜索结果、超长 tool result 不直接留在活跃消息里
- 主上下文只保留 preview、summary、artifact 引用、必要结构化证据
- 完整内容进入外部存储

### 2.3 历史消息不是单一数组，而是多层视图

- `raw transcript`：完整原始记录
- `active context`：当前真正发给模型的窗口
- `summary chain`：压缩后的 durable 摘要链
- `artifact refs`：外部结果引用

### 2.4 预算是多维的

- 不能只看 token
- 预算至少包括：turn、tool call、tool class、wall time、cost、spawn、并发

### 2.5 子任务必须隔离

- 子任务默认独立 session、独立 budget、独立 transcript
- 主 agent 不回灌子任务的完整原始轨迹，只接收结构化结果

---

## 3. 总体架构

```text
User / Channel Event
-> Session Orchestrator
-> Turn Controller
   -> Context Builder
   -> Budget Manager
   -> Compression Pipeline
   -> Model Caller
   -> Tool Executor
   -> Assessment Engine
-> Final Answer | Continue | Compact | Spawn Child Session | Archive

Supporting Stores:
- Transcript Store
- Artifact Store
- Memory Store
- Session Store
- Telemetry Store
```

### 3.1 核心分层

| 层 | 职责 |
|---|---|
| Session Orchestrator | session 生命周期、lane、route、spawn、archive、announce |
| Turn Controller | 单任务回合内的有界循环 |
| Context Builder | system prompt、历史、memory、artifact、预算信息组装 |
| Budget Manager | 统一预算检查、降级、继续/停止决策 |
| Compression Pipeline | tool result 控制、TTL prune、microcompact、auto-compact、memory flush |
| Tool Executor | 工具校验、执行、超时、熔断、结果标准化 |
| Stores | transcript、artifact、memory、session、telemetry |

---

## 4. 单任务回合控制器

### 4.1 状态机

统一使用如下状态机：

```text
bootstrap
-> plan
-> act
-> observe
-> assess
-> decide
   -> continue
   -> finish
   -> compact
   -> abort
   -> spawn
```

### 4.2 回合状态

```ts
type TurnState = {
  turn: number
  objective: string
  taskFrame: TaskFrame
  activeMessages: Message[]
  activeArtifacts: string[]
  budget: BudgetSnapshot
  repeatedFailures: FailureCluster[]
  toolUsage: Record<string, number>
  spawnCount: number
  lastAssessment?: LoopAssessment
}
```

### 4.3 TaskFrame

`TaskFrame` 是通用任务骨架，不绑定 research：

```ts
type TaskFrame = {
  objective: string
  doneDefinition: string[]
  constraints: string[]
  deliverable: string
  workingPlan: string[]
  unresolved: string[]
  activeArtifacts: string[]
}
```

### 4.4 LoopAssessment

每轮工具执行后都要生成结构化评估，而不是只让模型自由发挥：

```ts
type LoopAssessment = {
  turn: number
  unresolvedCount: number
  noveltyScore: number
  repeatedPatternScore: number
  riskLevel: "low" | "medium" | "high"
  budgetRemaining: BudgetSnapshot
  suggestedNextAction: string
  controllerDecision: "continue" | "finish" | "compact" | "abort" | "spawn"
}
```

### 4.5 继续与停止规则

#### 允许继续

仅当以下条件同时满足时允许继续：

- `doneDefinition` 尚未满足
- 预算未耗尽
- 没有命中重复失败熔断
- `noveltyScore` 仍高于阈值，或者 `unresolvedCount` 在下降

#### 直接停止

满足任一条件时进入收尾：

- `doneDefinition` 已满足
- 连续 2 轮 `unresolvedCount` 不下降
- 连续 2 轮 `noveltyScore` 低于阈值
- 同一工具相同参数签名重复超过阈值
- 同一错误簇重复超过阈值
- 达到 `maxTurns`
- 达到 `maxWallTimeMs`
- 达到 `maxTotalTokens` 或 `maxCostUsd`

#### 收尾策略

- 预算正常：输出完整结果
- 预算逼近：输出 best effort + unresolved
- 预算耗尽：强制结束，附带剩余风险与未完成项

---

## 5. 预算体系

### 5.1 硬预算

```ts
type HardBudget = {
  maxTurns: number
  maxWallTimeMs: number
  maxTotalTokens: number
  maxCostUsd?: number
  maxToolCalls: number
  maxToolCallsByName: Record<string, number>
  maxParallelTools: number
  maxSpawns: number
}
```

### 5.2 软预算

```ts
type SoftBudget = {
  compactTriggerTokens: number
  collapseTriggerTokens: number
  recentHistoryTokens: number
  summaryTokens: number
  memoryTokens: number
  toolResultSingleChars: number
  toolResultPerMessageChars: number
}
```

### 5.3 默认预算建议

| 预算项 | 主 agent | subagent |
|---|---:|---:|
| `maxTurns` | 12 | 6 |
| `maxToolCalls` | 24 | 12 |
| `maxParallelTools` | 4 | 3 |
| `maxSpawns` | 3 | 0 |
| `search/fetch maxUses` | 8 | 4 |
| `toolResultSingleChars` | 50000 | 30000 |
| `toolResultPerMessageChars` | 200000 | 100000 |
| `compactTrigger` | 68% context | 60% context |
| `hardInputStop` | 82% context | 75% context |

### 5.4 收益递减检测

收益递减由 controller 判定，不交给模型自由解释。

建议规则：

- 连续 2 轮 `noveltyScore < 0.15`
- 连续 2 轮 `unresolvedCount` 不减少
- 最近 3 次工具调用中，有 2 次是同一调用签名
- 最近 3 次失败中，有 2 次属于同一错误簇

---

## 6. System Prompt Build

### 6.1 三层结构

System prompt 固定为三层，尽量保持前缀稳定，利于 cache：

1. 稳定前缀
   - 安全规则
   - 工具调用契约
   - 输出契约
   - 基础行为约束
2. 半稳定层
   - workspace 摘要
   - skills 元信息
   - 可用工具说明
   - session policy
3. 动态尾部
   - `TaskFrame`
   - 当前 budget
   - active summary
   - recent history
   - active artifact refs

### 6.2 Prompt 模式

```ts
type PromptMode = "full" | "minimal" | "none"
```

- `full`：主 agent 默认使用
- `minimal`：subagent 默认使用，只保留安全、工具、任务、预算、必要 workspace 摘要
- `none`：极简系统任务或内部压缩/合成步骤

### 6.3 Prompt 内容约束

- skill 列表只注入元信息，不直接注入大段 SKILL.md 正文
- bootstrap 文件和 docs 走截断与摘要，不允许无限注入
- budget 信息必须显式注入当前轮，提示模型收尾，但不能替代 runtime 决策

---

## 7. 历史消息模型

### 7.1 四层历史

```text
Raw Transcript
-> Summary Chain
-> Active History View
-> Model Input
```

### 7.2 存储定义

```ts
type TranscriptStore = {
  rawMessages: Message[]
  summaryMessages: SummaryMessage[]
  artifactRefs: ArtifactRef[]
  compactionCount: number
}
```

### 7.3 视图规则

- `rawMessages` 只用于持久化和诊断
- `active history` 只保留最近窗口 + 摘要链 + 必要附件引用
- 历史不直接等于 transcript 数组
- resume 时先恢复 session state，再重新生成 active view，而不是原样重放所有消息

---

## 8. Compression Pipeline

### 8.1 固定顺序

压缩管道建议固定为以下顺序：

```text
1. single tool result persist
2. per-message aggregate tool budget
3. TTL pruning
4. microcompact
5. context collapse
6. auto-compact
7. memory flush
```

### 8.2 各阶段定义

#### 1. Single tool result persist

- 单条 tool result 超过 `toolResultSingleChars`
- 原始内容写入 `Artifact Store`
- 上下文只保留：
  - preview
  - artifact id
  - file/path/ref
  - origin tool metadata

#### 2. Per-message aggregate tool budget

- 单轮多个并发工具的结果总量超过 `toolResultPerMessageChars`
- 优先替换体积最大的结果
- 替换后保持结果可追踪、可点击、可二次读取

#### 3. TTL pruning

- 仅对旧 tool result 生效
- 只在缓存过期或会话空闲后触发
- 保护最近 assistant tail
- 跳过图像等不可安全裁剪内容

#### 4. Microcompact

- 针对历史大工具输出
- 清掉原始正文，保留精简摘要和引用
- 目标是减小当前调用的输入体积

#### 5. Context collapse

- 将更老的连续块折叠成细粒度摘要
- 保留更多结构，不要过早进入全量 auto-compact

#### 6. Auto-compact

- 当上下文逼近阈值时，将历史前缀固化为 durable summary
- summary 必须带结构化保留项

#### 7. Memory flush

- compact 前执行静默 durable memory capture
- 将长期事实写入 memory store
- 避免用户偏好、长期决策、关键约束长期驻留在 prompt

### 8.3 Compaction 输出结构

摘要不能只有自然语言，必须至少包含：

```ts
type CompactionSummary = {
  summary: string
  decisions: string[]
  openQuestions: string[]
  readFiles: string[]
  modifiedFiles: string[]
  recentFailures: string[]
  activeArtifacts: string[]
}
```

### 8.4 压缩策略设计

压缩策略的目标不是“尽量删内容”，而是：

- 在可控信息损失下，持续把 active context 保持在稳定区间
- 优先保留任务完成所需信息，优先移除可回读、可重建、可持久化的大结果
- 让压缩成为 runtime 的常规机制，而不是溢出后的补救动作

#### 8.4.1 设计原则

##### 1. 先外置，再摘要，最后清除

压缩优先级必须是：

```text
persist to artifact
-> soft trim
-> structured summarize
-> collapse
-> durable compact
-> hard clear
```

能通过 artifact 引用解决的，不应该直接删。

##### 2. 越靠近当前任务的内容，越难被压缩

应优先保护：

- 当前用户目标
- 最近用户消息
- 最近 assistant 决策链
- 最近错误与失败原因
- 当前任务涉及的文件读写记录
- 当前仍未解决的 `unresolved`
- 最近生成的 artifact refs

##### 3. 压缩对象必须是结构化单元

不要对整段历史做粗暴字符串截断。压缩单元应是：

- 单个 tool result
- 一轮 turn 内的 tool result group
- 一段连续历史 segment
- 一段已经结束的任务 phase
- 一个 session prefix

#### 8.4.2 压缩压力分级

建议用 context pressure 做统一压缩分级：

| 压力级别 | 上下文占用 | 动作 |
|---|---:|---|
| `green` | `< 50%` | 不主动压缩，仅做单条结果持久化 |
| `yellow` | `50% - 68%` | aggregate budget、TTL prune、轻量 microcompact |
| `orange` | `68% - 82%` | collapse、auto-compact 预备、memory flush |
| `red` | `> 82%` | 强制 compact / emergency fallback / best-effort finish |

这里的阈值应来自 `BudgetProfile`，而不是写死在 controller。

#### 8.4.3 压缩对象分类

建议将所有可压缩对象统一分类：

```ts
type CompressionUnit =
  | { kind: "tool_result"; id: string; sizeChars: number; turn: number; restorable: boolean }
  | { kind: "tool_group"; id: string; sizeChars: number; turn: number }
  | { kind: "history_segment"; id: string; tokenEstimate: number; age: number }
  | { kind: "session_prefix"; id: string; tokenEstimate: number; compacted: boolean }
  | { kind: "memory_candidate"; id: string; tokenEstimate: number; durable: boolean }
```

每个对象都应具备：

- 大小估算
- 年龄
- 是否可回读
- 是否与当前 unresolved 关联
- 是否包含 read/modified files
- 是否包含失败信息

#### 8.4.4 信息保留等级

建议定义明确的信息保留等级，避免压缩后丢掉真正关键的任务信息：

| 等级 | 必须保留内容 |
|---|---|
| `P0` | 当前目标、doneDefinition、constraints、unresolved、最新用户请求 |
| `P1` | 最近 assistant 决策、最近错误、文件改动、artifact refs |
| `P2` | 最近历史摘要、重要中间结论、重要搜索/工具证据 |
| `P3` | 老旧大结果、已消费完成的命令输出、可回读网页正文 |

压缩时应始终满足：

- `P0` 绝不压缩
- `P1` 只允许摘要，不允许直接清空
- `P2` 可 collapse / compact
- `P3` 优先持久化或清除

#### 8.4.5 各阶段具体策略

##### A. Single Result Persist

触发条件：

- 单个 tool result 超过 `toolResultSingleChars`
- 或单个结果已超过工具自身 `maxResultSizeChars`

处理方式：

- 原始结果落 `Artifact Store`
- 生成稳定 preview
- 上下文保留：
  - tool name
  - preview
  - artifact id
  - 关键 metadata

适用内容：

- 网页正文
- 命令长输出
- 搜索结果集
- 大型 JSON

##### B. Aggregate Tool Budget

触发条件：

- 同一轮多个并发工具结果总和超过 `toolResultPerMessageChars`

处理方式：

- 按结果大小倒序替换
- 替换到预算内为止
- 替换优先级高的对象：
  - `P3`
  - 与当前 unresolved 无关的结果
  - 已有 artifact 的结果

##### C. TTL Pruning

触发条件：

- 会话闲置超过 TTL
- prompt cache 已失效
- 下次请求会重写整段前缀

处理方式：

- 仅处理老旧 tool result
- 保留最近 `N` 个 assistant tail
- 对可裁剪文本做 head/tail 保留
- 对图像、二进制结果、不可安全裁剪结果跳过

##### D. Microcompact

触发条件：

- active context 进入 `yellow`
- 历史工具结果仍然占比较高
- 当前任务还在进行，但不适合全量 compact

处理方式：

- 将旧 tool result 替换为结构化摘要：

```ts
type ToolResultCompactView = {
  tool: string
  outcome: "ok" | "error"
  summary: string
  artifactRef?: string
  keyFacts?: string[]
}
```

适用目标：

- 降低请求体积
- 保留 turn 级可追踪性
- 避免过早把细节合并进大摘要

##### E. Context Collapse

触发条件：

- active history 已过长
- 老历史仍是“多轮 turn 级块”，不适合继续细粒度保留

处理方式：

- 以 segment 为单位折叠
- 每个 segment 输出一条结构化 collapse summary

```ts
type CollapsedSegment = {
  segmentId: string
  coveredTurns: number[]
  summary: string
  decisions: string[]
  unresolvedAtThatTime: string[]
  artifacts: string[]
}
```

设计目标：

- 比 auto-compact 更细
- 保留局部任务阶段信息
- 让后续仍可基于 segment 粒度做补充压缩

##### F. Auto-compact

触发条件：

- 进入 `orange`
- 预估下次调用会超过安全阈值
- 或已经命中 prompt-too-long / context overflow

处理方式：

- 将 session prefix 固化为 durable summary
- 生成新的 summary boundary
- 从 active history 中移除被摘要的原始前缀

summary 至少保留：

- objective
- decisions
- open questions
- read files
- modified files
- recent failures
- active artifacts

##### G. Memory Flush

触发条件：

- 即将进入 auto-compact
- 当前 `totalTokens` 已接近 `contextWindow - reserveTokensFloor - softThreshold`

处理方式：

- 运行一轮静默 durable memory capture
- 将长期事实写入 memory store
- 不要求产生用户可见回复

#### 8.4.6 压缩选择规则

压缩不是见大就压，而是做选择。

建议为每个 `CompressionUnit` 计算一个压缩优先级分数：

```text
priority =
  size_weight
  + age_weight
  + restorable_weight
  - unresolved_relevance_weight
  - recentness_weight
  - failure_preservation_weight
  - file_change_preservation_weight
```

含义：

- 越大、越旧、越容易回读，越应该先压
- 越靠近当前 unresolved、越新、越包含错误和文件改动，越应保留

#### 8.4.7 永不直接压缩的内容

以下内容不允许被普通压缩器直接删除：

- 当前用户最后一条消息
- 当前 `TaskFrame`
- 当前预算信息
- 最近一轮 assistant 的行动决策
- 最近一轮失败原因
- 最近一轮文件读写摘要
- 当前 unresolved 列表
- 当前轮新增的 artifact refs

这些对象只允许：

- 保留原文
- 或被单独提炼为高优先级结构化摘要

#### 8.4.8 压缩后校验

每次压缩后都必须做 post-check：

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

若 post-check 不通过：

- 回滚当前压缩结果
- 升级到更高一级压缩策略
- 或直接进入 best-effort 收尾

#### 8.4.9 压缩失败回退

压缩流程必须有可预期的失败回退：

1. 正常结构化压缩失败
   - 使用 fallback summary
2. fallback summary 仍失败
   - 丢弃更老的 `P3` 内容，仅保留 `P0/P1`
3. 仍无法进入安全上下文
   - 新建 session / reset session
   - 输出 best effort 提示

禁止行为：

- 在同一坏上下文中无限重复 compact
- 压缩失败后继续追加更多大结果

#### 8.4.10 压缩策略与调参

压缩策略需要长期观测和调参，至少应记录：

- 每级压缩触发次数
- 每级压缩平均释放 token
- 压缩后仍溢出的比率
- fallback summary 触发次数
- 由于压缩失败导致 reset session 的次数
- 哪类工具最容易产生高压缩成本输出

建议后续把压缩相关参数抽成独立 profile：

```ts
type CompressionProfile = {
  singleResultChars: number
  aggregateResultChars: number
  ttlMs: number
  microcompactTriggerPct: number
  collapseTriggerPct: number
  autocompactTriggerPct: number
  preserveRecentAssistants: number
  minCompressionGainTokens: number
}
```

#### 8.4.11 CompressionProfile 配置 schema

建议把压缩参数从通用 budget 中独立出来，形成可切换的 profile。

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

##### 字段约束建议

- `pressure.yellowPct < orangePct < redPct < hardStopPct <= 0.95`
- `persist.singleResultChars <= persist.aggregateResultChars`
- `pruning.preserveRecentAssistants >= 1`
- `autocompact.maxHistoryShare` 建议范围 `0.35 - 0.60`
- `quality.minCompressionGainTokens` 不宜过小，否则会出现频繁无效压缩

##### 默认 profile 建议

```ts
const DEFAULT_COMPRESSION_PROFILE: CompressionProfile = {
  mode: "balanced",
  pressure: {
    yellowPct: 0.50,
    orangePct: 0.68,
    redPct: 0.82,
    hardStopPct: 0.90,
  },
  persist: {
    singleResultChars: 50_000,
    aggregateResultChars: 200_000,
    artifactPreviewChars: 2_000,
    artifactPreviewHeadChars: 900,
    artifactPreviewTailChars: 700,
  },
  pruning: {
    enabled: true,
    ttlMs: 5 * 60 * 1000,
    preserveRecentAssistants: 3,
    minPrunableToolChars: 50_000,
    softTrimMaxChars: 4_000,
    softTrimHeadChars: 1_500,
    softTrimTailChars: 1_500,
    hardClearEnabled: true,
    hardClearPlaceholder: "[Old tool result content cleared]",
  },
  microcompact: {
    enabled: true,
    triggerPct: 0.50,
    maxUnitsPerPass: 8,
    preserveErrorResults: true,
  },
  collapse: {
    enabled: true,
    triggerPct: 0.68,
    maxSegmentTokens: 12_000,
    minSegmentTurns: 2,
  },
  autocompact: {
    enabled: true,
    triggerPct: 0.82,
    reserveTokensFloor: 20_000,
    maxHistoryShare: 0.50,
    fallbackSummaryMaxChars: 8_000,
  },
  memoryFlush: {
    enabled: true,
    softThresholdTokens: 4_000,
  },
  quality: {
    minCompressionGainTokens: 1_000,
    requirePostCheck: true,
    rollbackOnInvariantFailure: true,
  },
}
```

##### profile 使用建议

| Profile | 场景 |
|---|---|
| `conservative` | 高准确性代码修改、复杂调试、重要任务 |
| `balanced` | 默认交互、普通长任务 |
| `aggressive` | 高工具输出、高抓取量、低成本优先任务 |

#### 8.4.12 CompressionPipeline 接口设计

压缩逻辑不应散落在各处条件分支中，而应由统一 pipeline 编排。

##### 核心接口

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

type CompressionResult = {
  messages: Message[]
  newArtifacts: ArtifactRef[]
  operations: CompressionOperation[]
  tokensBefore: number
  tokensAfter: number
  freedTokens: number
  postCheck: CompressionPostCheck
}

type CompressionOperation =
  | { stage: "persist"; count: number; ids: string[] }
  | { stage: "aggregate_budget"; count: number; ids: string[] }
  | { stage: "ttl_prune"; count: number; ids: string[] }
  | { stage: "microcompact"; count: number; ids: string[] }
  | { stage: "collapse"; count: number; ids: string[] }
  | { stage: "autocompact"; count: number; ids: string[] }
  | { stage: "memory_flush"; count: number; ids: string[] }
```

##### Stage 接口

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

type CompressionStageResult = {
  messages: Message[]
  newArtifacts?: ArtifactRef[]
  operations?: CompressionOperation[]
}
```

##### Pipeline 约束

- 每个 stage 只做一类压缩动作
- stage 之间只通过 `CompressionContext` 和 `CompressionStageResult` 传值
- 每个 stage 完成后立即刷新 token estimate
- 任一 stage 不能绕过 post-check 直接提交危险结果

#### 8.4.13 CompressionPipeline 执行顺序

```ts
const COMPRESSION_PIPELINE: CompressionStage[] = [
  persistStage,
  aggregateBudgetStage,
  ttlPruneStage,
  microcompactStage,
  collapseStage,
  autocompactStage,
  memoryFlushStage,
]
```

执行时机建议：

- 每轮模型调用前执行一次
- 工具执行结束后，如新增结果较大，可追加一次轻量预压缩
- 收到 `prompt_too_long` / `context overflow` 时，允许 emergency rerun

#### 8.4.14 CompressionPipeline 伪代码

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

    const beforeStageTokens = estimateTokens(ctx.messages)
    const stageResult = await stage.run(ctx)

    const nextMessages = stageResult.messages
    const nextArtifacts = stageResult.newArtifacts ?? []
    const afterStageTokens = estimateTokens(nextMessages)
    const gained = beforeStageTokens - afterStageTokens

    if (gained < ctx.profile.quality.minCompressionGainTokens) {
      // 小于最小收益阈值时，允许跳过提交，但 persist/memory_flush 例外
      if (stage.name !== "persist" && stage.name !== "memory_flush") {
        continue
      }
    }

    ctx = {
      ...ctx,
      messages: nextMessages,
      activeArtifacts: [...ctx.activeArtifacts, ...nextArtifacts],
      estimatedInputTokens: afterStageTokens,
    }

    collectedArtifacts.push(...nextArtifacts)
    operations.push(...(stageResult.operations ?? []))

    const pressurePct = afterStageTokens / ctx.modelContextWindow
    if (pressurePct < ctx.profile.pressure.yellowPct) {
      // 已降到稳定区间，可以提前结束后续高成本压缩
      break
    }
  }

  const tokensAfter = estimateTokens(ctx.messages)
  const postCheck = verifyCompressionInvariants({
    before: input.messages,
    after: ctx.messages,
    taskFrame: input.taskFrame,
    artifacts: ctx.activeArtifacts,
  })

  if (input.profile.quality.requirePostCheck && !isCompressionPostCheckPassed(postCheck)) {
    if (input.profile.quality.rollbackOnInvariantFailure) {
      return buildRollbackCompressionResult(input, tokensBefore, postCheck)
    }
  }

  return {
    messages: ctx.messages,
    newArtifacts: collectedArtifacts,
    operations,
    tokensBefore,
    tokensAfter,
    freedTokens: Math.max(0, tokensBefore - tokensAfter),
    postCheck,
  }
}
```

#### 8.4.15 Emergency Compression 伪代码

当正常压缩后仍然过长，或者模型直接返回 `prompt_too_long` / `context overflow`：

```ts
async function runEmergencyCompression(ctx: CompressionContext): Promise<CompressionResult> {
  const narrowedProfile = {
    ...ctx.profile,
    collapse: { ...ctx.profile.collapse, enabled: true },
    autocompact: { ...ctx.profile.autocompact, enabled: true },
  }

  const result = await runCompressionPipeline({
    ...ctx,
    profile: narrowedProfile,
  })

  if (result.tokensAfter / ctx.modelContextWindow <= narrowedProfile.pressure.redPct) {
    return result
  }

  return buildFallbackSummaryCompressionResult(ctx)
}
```

#### 8.4.16 验证接口

压缩后验证建议独立成一个小模块：

```ts
type CompressionInvariantVerifier = {
  verify(params: {
    before: Message[]
    after: Message[]
    taskFrame: TaskFrame
    artifacts: ArtifactRef[]
  }): CompressionPostCheck
}
```

必须验证：

- objective 仍可恢复
- unresolved 未丢失
- 最近失败信息仍可恢复
- 当前 artifact refs 仍存在
- 不能出现 role ordering 损坏

---

## 9. Tool 治理

### 9.1 Tool Policy

每个工具必须声明自己的 runtime 约束：

```ts
type ToolPolicy = {
  maxResultSizeChars: number
  maxUsesPerTurn: number
  maxUsesPerSession: number
  maxParallelism: number
  defaultTimeoutMs: number
  compactable: boolean
  persistLargeOutput: boolean
  allowInSubagent: boolean
  costWeight: number
  repeatSignatureLimit: number
}
```

### 9.2 通用规则

- 原始大结果默认不上 active context
- 工具结果先 normalize 再判断是否 inline
- 同一工具重复失败要进入熔断逻辑
- 重复签名调用超过阈值禁止继续执行

### 9.3 工具调用签名

建议对工具输入做 canonical hash：

```ts
type ToolCallSignature = {
  toolName: string
  normalizedArgsHash: string
}
```

用途：

- 识别无意义重复调用
- 做回合内去重
- 触发收益递减和熔断

---

## 10. Artifact Store

### 10.1 定位

Artifact Store 是控制上下文膨胀的核心组件。

所有以下内容都应该优先进入 Artifact Store：

- 长网页正文
- 长命令输出
- 大型搜索结果集
- 大型结构化抓取结果
- 大型代码片段集合

### 10.2 数据结构

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

### 10.3 主上下文只保留

- `artifact id`
- `preview`
- `kind`
- `origin tool`
- 需要时的 `location/path/url`

---

## 11. Session Orchestrator

### 11.1 Session 是一等实体

```ts
type Session = {
  sessionKey: string
  sessionId: string
  parentSessionKey?: string
  lane: "main" | "followup" | "subagent" | "cron" | "background_tool"
  modelProfile: string
  budgetProfile: string
  summaryRef?: string
  memoryRef?: string
  route: RouteMeta
  status: "active" | "idle" | "compacted" | "archived"
}
```

### 11.2 职责

- session create / load / patch / archive
- queue lane 管理
- route 到 channel / thread / topic
- parent-child session 关系管理
- followup / background task / subagent 生命周期管理

### 11.3 Lane

建议最少支持：

- `main`
- `followup`
- `subagent`
- `cron`
- `background_tool`

每条 lane 有独立并发与背压配置。

---

## 12. Subagent 架构

### 12.1 设计原则

- 先把单任务循环做好，再开放 subagent
- subagent 不是复制主 agent，而是有界 child runtime
- 主 agent 不回灌 child transcript，只拿结构化结果

### 12.2 SpawnPacket

```ts
type SpawnPacket = {
  objective: string
  deliverable: string
  constraints: string[]
  parentSummary: string
  selectedArtifacts: string[]
  toolAllowlist: string[]
  budgetProfile: string
  timeoutMs: number
}
```

### 12.3 ChildResult

```ts
type ChildResult = {
  status: "success" | "error" | "timeout"
  summary: string
  unresolved: string[]
  artifactRefs: string[]
  usage: Usage
  durationMs: number
}
```

### 12.4 默认约束

- 子 session 独立 transcript
- 子 session 独立 budget
- prompt mode 默认 `minimal`
- 默认不暴露 session tools
- 默认禁止再 spawn
- child 结束后自动 archive 或进入 idle

### 12.5 主线程接回结果方式

主线程只接收：

- `status`
- `summary`
- `unresolved`
- `artifact refs`
- `usage`

禁止直接把 child 原始消息历史回灌到主上下文。

---

## 13. 稳定性与恢复

### 13.1 校验

每次模型调用前必须经过：

- role ordering 校验
- transcript sanitize
- tool result normalize
- context token estimate

### 13.2 失败处理

#### 工具失败

- 单次失败：进入错误观测
- 重复失败：触发 breaker
- breaker 后：禁止继续同签名重试

#### 压缩失败

- 尝试 fallback summary
- fallback 失败则新 session 重启
- 不允许在坏上下文上无限重试

#### 上下文溢出

- 先尝试主动 compact
- 失败则 fallback summary
- 再失败则 reset session 并输出 best effort 错误结果

---

## 14. 观测与调参

必须记录以下 telemetry：

- turn count
- token input / output / cache read / cache write
- compaction count
- prune count
- tool result persisted count
- repeated signature hit count
- breaker hit count
- spawn count
- lane queue depth
- finish reason

### 14.1 FinishReason

```ts
type FinishReason =
  | "done_definition_satisfied"
  | "max_turns"
  | "max_wall_time"
  | "max_tokens"
  | "max_cost"
  | "diminishing_returns"
  | "breaker"
  | "controller_abort"
  | "best_effort_budget_stop"
```

---

## 15. 实施顺序

### Phase 1: 单任务循环内核

先完成：

- Turn Controller
- Budget Manager
- Tool Policy Engine
- Artifact Store
- 收益递减与 breaker

交付目标：

- 单个任务回合在长任务中能稳定收敛
- tool result 不再轻易打爆上下文
- 有明确 `maxTurns`、tool 次数、预算中止逻辑

### Phase 2: Context 与压缩体系

完成：

- Context Builder
- 多层历史视图
- TTL prune
- microcompact
- auto-compact
- memory flush

交付目标：

- 历史消息与上下文彻底解耦
- 支持长 session，但 active context 保持稳定

### Phase 3: Session Orchestrator

完成：

- Session Store
- lane / route
- lifecycle / archive
- announce / followup

交付目标：

- 支持长期运行 session
- 支持 background task、channel route、session archive

### Phase 4: Subagent

完成：

- `session_spawn`
- SpawnPacket / ChildResult
- child lane
- child budget profile
- child archive

交付目标：

- 支持 bounded 并行
- 不把主线程上下文拖死

---

## 16. 最终结论

最终 runtime 应该是：

- 一个受 controller 硬约束的单任务执行系统
- 一个支持长期 session 生命周期的编排系统
- 一套统一的上下文构建、压缩、预算、工具治理内核

换句话说：

- **先解决“单个任务回合如何稳定拿到结果”**
- **再解决“多个 session / subagent 如何长期并行运行”**

如果第一层没做好，第二层只会把混乱并行化。
