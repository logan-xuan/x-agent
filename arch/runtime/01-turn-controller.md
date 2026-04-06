# Turn Controller 详细方案

> 范围：单个任务回合内的循环控制、预算控制、tool 治理、停止条件和结果收敛。

---

## 1. 设计目标

`TurnController` 负责解决一个核心问题：

如何在一个任务回合内，让 agent 在有限预算下持续推进任务，最终稳定拿到结果，而不是无限继续搜索、调用工具或空转。

它不负责：

- session 路由
- 多 agent 生命周期
- channel 发送与 announce

这些都属于 `SessionOrchestrator` 的职责。

---

## 2. 当前代码映射

当前相关代码分布在：

- `backend/src/agent_core/agent_loop.py`
- `backend/src/agent_core/agent.py`
- `backend/src/agent_core/tool_executor.py`
- `backend/src/agent_core/tool_middleware.py`
- `backend/src/services/llm/router.py`
- `backend/src/tools/manager.py`

当前问题：

- loop 逻辑与预算逻辑容易耦合
- tool 调用次数、重复调用、重复失败缺少统一治理
- “为什么继续”和“什么时候停止”缺少结构化决策对象

目标是将其收敛成以下几个组件：

- `TurnController`
- `BudgetManager`
- `AssessmentEngine`
- `ToolGovernor`
- `ModelInvoker`

---

## 3. 目标模块结构

```text
turn_controller/
├── controller.py
├── state.py
├── assessment.py
├── budget.py
├── tool_governor.py
├── finish_reason.py
└── model_invoker.py
```

---

## 4. 核心状态机

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

### 4.1 各阶段说明

| 阶段 | 作用 |
|---|---|
| `bootstrap` | 初始化任务目标、预算、上下文视图 |
| `plan` | 生成当前轮行动计划 |
| `act` | 发起模型调用或工具调用 |
| `observe` | 收集 assistant 输出与 tool result |
| `assess` | 评估是否推进、是否重复、是否逼近预算 |
| `decide` | 决定继续、结束、压缩、spawn 或中止 |

---

## 5. 状态对象

```ts
type TurnState = {
  turn: number
  objective: string
  taskFrame: TaskFrame
  activeMessages: Message[]
  activeArtifacts: string[]
  budget: BudgetSnapshot
  toolUsage: Record<string, number>
  repeatedFailures: FailureCluster[]
  spawnCount: number
  lastAssessment?: LoopAssessment
}
```

### 5.1 TaskFrame

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

### 5.2 LoopAssessment

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

---

## 6. Budget Manager

### 6.1 硬预算

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

### 6.2 软预算

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

### 6.3 决策输出

```ts
type BudgetDecision =
  | { action: "ok" }
  | { action: "warn"; reason: string }
  | { action: "compact"; reason: string }
  | { action: "stop"; reason: string; finishReason: FinishReason }
```

### 6.4 建议默认值

| 预算项 | 主 agent | child agent |
|---|---:|---:|
| `maxTurns` | 12 | 6 |
| `maxToolCalls` | 24 | 12 |
| `maxParallelTools` | 4 | 3 |
| `maxSpawns` | 3 | 0 |
| `search/fetch maxUses` | 8 | 4 |

---

## 7. Tool Governor

### 7.1 ToolPolicy

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

### 7.2 Tool Governor 职责

- 校验是否允许调用
- 校验是否超过预算
- 识别重复签名调用
- 对高风险工具提高 cost weight
- 在调用前生成执行约束

### 7.3 ToolCallSignature

```ts
type ToolCallSignature = {
  toolName: string
  normalizedArgsHash: string
}
```

用途：

- 去重
- 检测无意义重试
- 检测收益递减

---

## 8. Assessment Engine

### 8.1 作用

Assessment Engine 不负责生成内容，而负责判断这一轮是否真的在推进任务。

### 8.2 核心指标

- `unresolvedCount`
- `noveltyScore`
- `repeatedPatternScore`
- `recentFailureClusters`
- `budgetRemaining`

### 8.3 收益递减规则

建议默认规则：

- 连续 2 轮 `unresolvedCount` 不下降
- 连续 2 轮 `noveltyScore < 0.15`
- 最近 3 次工具调用中，2 次是相同签名
- 最近 3 次失败中，2 次属于同一错误簇

命中上述规则时，优先进入：

- `finish`
- 或 `best_effort_budget_stop`

而不是继续盲目尝试。

---

## 9. FinishReason

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

所有回合结束都应落成结构化 finish reason，而不是只返回自然语言解释。

---

## 10. Turn Controller 伪代码

```ts
async function runTurn(input: TurnInput): Promise<TurnResult> {
  let state = bootstrapTurnState(input)

  while (true) {
    const budgetDecision = budgetManager.check(state)
    if (budgetDecision.action === "stop") {
      return finishWithReason(state, budgetDecision.finishReason)
    }

    if (budgetDecision.action === "compact") {
      state = await compactState(state)
    }

    const llmPlan = await modelInvoker.plan(state)
    const governedPlan = toolGovernor.govern(llmPlan, state)
    const observed = await executePlan(governedPlan, state)

    state = mergeObserved(state, observed)

    const assessment = assessmentEngine.assess(state)
    state.lastAssessment = assessment

    switch (assessment.controllerDecision) {
      case "continue":
        state.turn += 1
        continue
      case "compact":
        state = await compactState(state)
        state.turn += 1
        continue
      case "spawn":
        return requestSpawn(state, assessment)
      case "abort":
        return finishWithReason(state, "controller_abort")
      case "finish":
      default:
        return finishWithAssessment(state, assessment)
    }
  }
}
```

---

## 11. 与现有代码的改造方式

### Phase 1A: 提取状态对象

从以下文件中先提取显式状态对象，不改变功能：

- `agent_core/agent_loop.py`
- `agent_core/agent.py`

目标：

- 消除隐式状态
- 为后续预算和 assessment 留出挂载点

### Phase 1B: 提取 BudgetManager

将以下逻辑从 loop 中抽离：

- turn 限制
- token 预算
- tool 调用总量限制
- per-tool 限制

### Phase 1C: 提取 ToolGovernor

从：

- `agent_core/tool_executor.py`
- `tools/manager.py`

中抽离工具治理逻辑。

### Phase 1D: 引入 AssessmentEngine

先接入只读 assessment，不改变 loop 流程。

验证稳定后，再把“是否继续”的权力从 loop 分支迁移到 assessment/controller。

---

## 12. 验收标准

达到以下条件后，认为 `TurnController` 基线完成：

- 主 loop 拥有显式 `TurnState`
- 所有结束路径都有结构化 `FinishReason`
- 有统一 `BudgetManager`
- 有统一 `ToolGovernor`
- 能识别重复工具调用和重复失败
- 能在预算逼近时稳定收尾，而不是无限继续

---

## 13. 与其它子系统的边界

### 它依赖什么

- `ContextBuilder` 提供 active context
- `CompressionPipeline` 提供 compact 能力
- `SessionOrchestrator` 处理 spawn 请求

### 它不负责什么

- 不负责 session route
- 不负责 child session 生命周期
- 不负责历史压缩存储
- 不负责 channel 发送

这些边界要保持明确，否则 loop 会重新膨胀成大一统控制器。
