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
