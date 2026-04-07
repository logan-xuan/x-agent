# Session Orchestrator 详细方案

> 范围：session 生命周期、lane、route、spawn、announce，以及长期多 session 运行的控制平面。

---

## 1. 设计目标

`SessionOrchestrator` 负责解决的问题是：

- 如何把长期运行的 agent 会话视为一等实体
- 如何在多个 session 间做隔离、排队、路由和回传
- 如何让 subagent 变成 bounded child session，而不是无限递归的 prompt 技巧

它不负责：

- 单任务回合内的停止条件
- prompt build 细节
- 压缩算法细节

这些属于 `TurnController` 和 `ContextRuntime`。

---

## 2. 当前代码映射

当前相关代码主要分布在：

- `backend/src/gateway/dispatcher.py`
- `backend/src/gateway/agent_invoker.py`
- `backend/src/gateway/session_resolver.py`
- `backend/src/gateway/message_bus.py`
- `backend/src/gateway/connection_registry.py`
- `backend/src/conversation/session.py`
- `backend/src/conversation/identity.py`
- `backend/src/api/v1/sessions.py`

现状问题：

- session、route、spawn、announce 仍偏分散
- gateway 层与 agent 调度职责未完全收口
- child session 的输入/输出格式还不够明确

---

## 3. 目标模块结构

```text
session_runtime/
├── orchestrator.py
├── session_store.py
├── route_resolver.py
├── lane_scheduler.py
├── spawn_manager.py
├── announcement_manager.py
├── session_types.py
└── lifecycle.py
```

---

## 4. Session 是一等实体

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

### 4.1 核心属性

- `sessionKey`：逻辑身份
- `sessionId`：具体 transcript / state 版本
- `parentSessionKey`：父子关系
- `lane`：执行与并发隔离
- `route`：当前消息入口与输出目的地
- `status`：生命周期状态

---

## 5. Lane 模型

建议至少支持以下 lane：

- `main`
- `followup`
- `subagent`
- `cron`
- `background_tool`

### 5.1 LaneScheduler 职责

- 每条 lane 独立并发限制
- 支持背压和排队深度监控
- subagent 不与主 session 共享同一个执行队列

### 5.2 并发建议

| Lane | 默认并发 |
|---|---:|
| `main` | 1 或 2 |
| `followup` | 2 |
| `subagent` | 4 或 8 |
| `cron` | 2 |
| `background_tool` | 2 |

---

## 6. Route 模型

```ts
type RouteMeta = {
  channel: string
  accountId?: string
  userId?: string
  threadId?: string
  topicId?: string
  originMessageId?: string
}
```

### 6.1 RouteResolver 职责

- 从 gateway event 解析 session route
- 处理 thread/topic/channel 差异
- 为 reply / announce / followup 选择正确目的地

---

## 7. SpawnManager

### 7.1 SpawnPacket

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

### 7.2 ChildResult

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

### 7.3 设计原则

- child session 独立 transcript
- child session 独立 budget
- child 默认 `minimal prompt`
- child 默认不暴露 session tools
- child 默认不能继续 spawn

### 7.4 Parent 接回规则

parent 只接收：

- status
- summary
- unresolved
- artifact refs
- usage

禁止将 child 原始历史直接回灌 parent active context。

---

## 8. AnnouncementManager

### 8.1 职责

- child 结束后生成稳定 announce payload
- 保留 route 信息
- 在 parent 当前忙碌时支持排队或合并

### 8.2 输出结构

```ts
type AnnouncementPayload = {
  targetSessionKey: string
  childSessionKey: string
  status: "success" | "error" | "timeout"
  summary: string
  unresolved: string[]
  artifactRefs: string[]
  statsLine: string
}
```

---

## 9. Session 生命周期

```text
create
-> active
-> idle
-> compacted
-> archived
```

### 9.1 生命周期动作

| 状态 | 动作 |
|---|---|
| `create` | 初始化 state、budget、route |
| `active` | 执行 turn |
| `idle` | 等待后续事件或 followup |
| `compacted` | 历史已压缩，保留 summary chain |
| `archived` | 不再参与调度，只保留诊断与回放数据 |

---

## 10. SessionOrchestrator 接口

```ts
type SessionOrchestrator = {
  resolveOrCreateSession(event: GatewayEvent): Promise<Session>
  enqueueTurn(session: Session, event: GatewayEvent): Promise<void>
  spawnChild(parent: Session, packet: SpawnPacket): Promise<Session>
  completeChild(child: Session, result: ChildResult): Promise<void>
  archiveSession(sessionKey: string): Promise<void>
}
```

---

## 11. Orchestrator 伪代码

```ts
async function handleGatewayEvent(event: GatewayEvent): Promise<void> {
  const session = await sessionOrchestrator.resolveOrCreateSession(event)
  await laneScheduler.enqueue(session.lane, async () => {
    const turnResult = await turnController.run({
      sessionKey: session.sessionKey,
      event,
    })

    if (turnResult.kind === "spawn") {
      await spawnManager.spawnChild(session, turnResult.packet)
      return
    }

    if (turnResult.kind === "final") {
      await announcementManager.deliverTurnResult(session, turnResult)
      await lifecycleManager.maybeArchive(session)
    }
  })
}
```

---

## 12. 与现有代码的改造方式

### Phase 3A: Session 模型显式化

从：

- `conversation/session.py`
- `conversation/identity.py`

中抽出统一 `Session`、`RouteMeta`、`LifecycleState`。

### Phase 3B: Gateway 调度显式化

从：

- `gateway/dispatcher.py`
- `gateway/agent_invoker.py`
- `gateway/session_resolver.py`

中抽出 `SessionOrchestrator + RouteResolver + LaneScheduler`。

### Phase 3C: Child Session 收敛

引入：

- `SpawnPacket`
- `ChildResult`
- `AnnouncementManager`

把 child session 从 ad-hoc 调用模式收敛为统一 child runtime。

---

## 13. 验收标准

达到以下条件后，认为 `SessionOrchestrator` 基线完成：

- session 有显式生命周期
- lane 有显式调度和并发限制
- route 由单独模块解析
- child session 输入输出结构化
- parent 不回灌 child 原始历史
- announce 有稳定协议

---

## 14. 与其它子系统的边界

### 它依赖什么

- 依赖 `TurnController` 执行单任务回合
- 依赖 `ContextRuntime` 构建 active context

### 它不负责什么

- 不负责 prompt build
- 不负责压缩算法
- 不负责回合内预算与停止条件

这些仍然属于其它两个子系统的职责。
