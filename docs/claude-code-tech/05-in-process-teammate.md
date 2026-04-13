# Claude Code 进程内 Teammate 深度分析

## 一、概述

进程内 Teammate (In-Process Teammate) 是 Claude Code Swarm 系统的**轻量级协作单元**,与 tmux/iTerm2 进程外 Teammate 不同,它们运行在同一个 Node.js 进程中,使用 `AsyncLocalStorage` 实现上下文隔离。

### 1.1 核心特性

| 特性 | 说明 | 价值 |
|------|------|------|
| **零进程开销** | 无需启动新进程 | 毫秒级创建,资源占用极低 |
| **上下文隔离** | AsyncLocalStorage 隔离 | 并发 teammate 互不干扰 |
| **独立生命周期** | 独立 AbortController | leader 查询中断不影响 teammate |
| **持续运行** | 空闲等待循环 | 可接收多个任务,无需重启 |
| **共享资源** | API 客户端、MCP 连接 | 避免重复初始化 |

### 1.2 使用场景

- **并行研究**: 启动多个 researcher 同时分析不同模块
- **任务分发**: leader 将子任务分发给多个 worker
- **快速原型**: 临时启动 teammate 验证想法
- **资源受限**: 不适合启动多个独立进程的场景

---

## 二、核心组件架构

### 2.1 三层架构模型

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    In-Process Teammate Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Layer 1: 身份层 (Identity)                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  TeammateIdentity (AppState.tasks)                                  │   │
│  │  - agentId: "researcher@my-team"                                    │   │
│  │  - agentName: "researcher"                                          │   │
│  │  - teamName: "my-team"                                              │   │
│  │  - parentSessionId: "abc123"                                        │   │
│  │  - planModeRequired: true/false                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              │ 映射                                           │
│                              ▼                                              │
│  Layer 2: 运行时层 (Runtime)                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  TeammateContext (AsyncLocalStorage)                                │   │
│  │  - agentId, agentName, teamName (同 Identity)                        │   │
│  │  - abortController: AbortController (独立,不链接到 parent)           │   │
│  │  - isInProcess: true (标识符)                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              │ runWithTeammateContext()                     │
│                              ▼                                              │
│  Layer 3: 执行层 (Execution)                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  InProcessRunner (inProcessRunner.ts)                               │   │
│  │  - runInProcessTeammate()  主循环                                    │   │
│  │  - runAgent()  实际执行                                             │   │
│  │  - Idle Wait  空闲等待                                              │   │
│  │  - Mailbox Poll  邮箱轮询                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 TeammateContext (AsyncLocalStorage)

**源码**: `src/utils/teammateContext.ts`

```typescript
import { AsyncLocalStorage } from 'async_hooks'

export type TeammateContext = {
  agentId: string           // 如 "researcher@my-team"
  agentName: string         // 如 "researcher"
  teamName: string
  color?: string
  planModeRequired: boolean
  parentSessionId: string   // Leader 的 session ID
  isInProcess: true         // 标识符
  abortController: AbortController
}

const teammateContextStorage = new AsyncLocalStorage<TeammateContext>()

export function runWithTeammateContext<T>(
  context: TeammateContext,
  fn: () => T,
): T {
  return teammateContextStorage.run(context, fn)
}

export function getTeammateContext(): TeammateContext | undefined {
  return teammateContextStorage.getStore()
}
```

**AsyncLocalStorage 工作原理**:

1. **基于 AsyncHook**: Node.js 的 `async_hooks` 模块追踪异步操作的生命周期
2. **传播机制**: 在同一异步调用链中,所有 `await` 后的代码都能访问相同的 store
3. **隔离性**: 不同的异步调用链有独立的 store,互不干扰
4. **类似 TLS**: 类似于线程局部存储 (Thread-Local Storage),但是针对异步操作

**使用示例**:

```typescript
// Leader 创建 teammate
const context = createTeammateContext({
  agentId: "researcher@my-team",
  agentName: "researcher",
  teamName: "my-team",
  abortController: createAbortController(),
  // ...
})

// 启动执行
runWithTeammateContext(context, async () => {
  // 在这里,任何调用 getTeammateContext() 的代码
  // 都会获得上面创建的 context
  await runAgent(...)  // runAgent 内部可以获取 teammate 身份
})
```

### 2.3 InProcessTeammateTaskState

**源码**: `src/tasks/InProcessTeammateTask/types.ts`

```typescript
export type InProcessTeammateTaskState = TaskStateBase & {
  type: 'in_process_teammate'
  
  // 身份信息 (与 TeammateContext 形状一致)
  identity: TeammateIdentity
  
  // 执行配置
  prompt: string
  model?: string
  selectedAgent?: AgentDefinition
  permissionMode: PermissionMode
  
  // 生命周期控制
  abortController?: AbortController           // 终止整个 teammate
  currentWorkAbortController?: AbortController // 仅终止当前轮次
  unregisterCleanup?: () => void
  
  // Plan 模式审批
  awaitingPlanApproval: boolean
  
  // 状态
  isIdle: boolean               // 是否空闲 (等待工作)
  shutdownRequested: boolean    // 是否收到关闭请求
  
  // 消息队列
  messages?: Message[]          // 对话历史 (上限: 50 条)
  pendingUserMessages: string[] // 待处理的用户消息
  
  // UI 状态
  spinnerVerb?: string          // 随机 spinner 动词
  pastTenseVerb?: string        // 完成时动词
  inProgressToolUseIDs?: Set<string>
  
  // 回调 (运行时)
  onIdleCallbacks?: Array<() => void>  // 空闲时通知回调
}
```

---

## 三、Spawn 流程深度分析

### 3.1 完整调用链

```
User: spawn teammate
    ↓
spawnMultiAgent.ts: handleSpawnInProcess()
    ↓
InProcessBackend.spawn()
    ↓
spawnInProcessTeammate()
    ├── 1. 生成 agentId (formatAgentId)
    ├── 2. 创建独立 AbortController
    ├── 3. 创建 TeammateIdentity
    ├── 4. 创建 TeammateContext
    ├── 5. 注册 Perfetto 追踪 (可选)
    ├── 6. 构建 InProcessTeammateTaskState
    ├── 7. 注册清理回调
    └── 8. registerTask() → AppState.tasks
    ↓
startInProcessTeammate() (fire-and-forget)
    ↓
runInProcessTeammate()
    └── runWithTeammateContext(context, async () => {
          runAgent()  // 实际执行
        })
```

### 3.2 spawnInProcessTeammate 源码分析

**源码**: `src/utils/swarm/spawnInProcess.ts:104-216`

```typescript
export async function spawnInProcessTeammate(
  config: InProcessSpawnConfig,
  context: SpawnContext,
): Promise<InProcessSpawnOutput> {
  const { name, teamName, prompt, color, planModeRequired, model } = config
  const { setAppState } = context

  // 1. 生成确定性 agentId
  const agentId = formatAgentId(name, teamName)  // "researcher@my-team"
  const taskId = generateTaskId('in_process_teammate')

  try {
    // 2. 创建独立的 AbortController
    //    关键设计: 不链接到 parent,leader 查询中断不影响 teammate
    const abortController = createAbortController()

    // 3. 获取 parent session ID (用于 transcript 关联)
    const parentSessionId = getSessionId()

    // 4. 创建 teammate identity (存储在 AppState.tasks)
    const identity: TeammateIdentity = {
      agentId,
      agentName: name,
      teamName,
      color,
      planModeRequired,
      parentSessionId,
    }

    // 5. 创建 teammate context (用于 AsyncLocalStorage)
    const teammateContext = createTeammateContext({
      agentId,
      agentName: name,
      teamName,
      color,
      planModeRequired,
      parentSessionId,
      abortController,
    })

    // 6. 注册 Perfetto 追踪 (用于性能分析)
    if (isPerfettoTracingEnabled()) {
      registerPerfettoAgent(agentId, name, parentSessionId)
    }

    // 7. 构建任务状态
    const description = `${name}: ${prompt.substring(0, 50)}${prompt.length > 50 ? '...' : ''}`
    const taskState: InProcessTeammateTaskState = {
      ...createTaskStateBase(taskId, 'in_process_teammate', description, context.toolUseId),
      type: 'in_process_teammate',
      status: 'running',
      identity,
      prompt,
      model,
      abortController,
      awaitingPlanApproval: false,
      spinnerVerb: sample(getSpinnerVerbs()),
      pastTenseVerb: sample(TURN_COMPLETION_VERBS),
      permissionMode: planModeRequired ? 'plan' : 'default',
      isIdle: false,
      shutdownRequested: false,
      lastReportedToolCount: 0,
      lastReportedTokenCount: 0,
      pendingUserMessages: [],
      messages: [],
    }

    // 8. 注册清理回调 (进程退出时自动终止)
    const unregisterCleanup = registerCleanup(async () => {
      abortController.abort()
    })
    taskState.unregisterCleanup = unregisterCleanup

    // 9. 注册到 AppState
    registerTask(taskState, setAppState)

    return {
      success: true,
      agentId,
      taskId,
      abortController,
      teammateContext,
    }
  } catch (error) {
    return {
      success: false,
      agentId,
      error: error instanceof Error ? error.message : 'Unknown error',
    }
  }
}
```

### 3.3 独立 AbortController 设计

**关键源码注释**:

```typescript
// Create independent AbortController for this teammate
// Teammates should not be aborted when the leader's query is interrupted
const abortController = createAbortController()
```

**设计哲学**: 

- **Teammate 是长期运行的协作单元**,不应该因为 leader 的临时查询中断而终止
- 例如: leader 被用户 ESC 取消,但 teammate 的研究任务应该继续
- 这与 LocalAgentTask 不同 (后台 agent 链接到 parent 的 AbortController)

**对比**:

| 类型 | AbortController | 行为 |
|------|----------------|------|
| **LocalAgentTask** | `createChildAbortController(parent)` | parent abort → 子级自动 abort |
| **InProcessTeammate** | `createAbortController()` (独立) | parent abort 不影响 teammate |

---

## 四、执行循环与空闲等待

### 4.1 runInProcessTeammate 主循环

**源码**: `src/utils/swarm/inProcessRunner.ts:883-1553`

```typescript
export async function runInProcessTeammate(
  config: InProcessRunnerConfig,
): Promise<InProcessRunnerResult> {
  const { identity, taskId, prompt, teammateContext, abortController, ... } = config

  // 主循环: 持续运行,直到 abort 或 shutdown 被批准
  while (!abortController.signal.aborted) {
    // 1. 执行 agent 工作
    await runWithTeammateContext(teammateContext, async () => {
      return runWithAgentContext(agentContext, async () => {
        // 标记为运行中
        updateTaskState(taskId, task => ({ ...task, status: 'running', isIdle: false }), setAppState)
        
        // 执行实际工作
        const result = await runAgent({
          messages: allMessages,
          abortController,
          // ...
        })
      })
    })

    // 2. 工作完成后,进入空闲状态
    updateTaskState(taskId, task => ({ ...task, isIdle: true }), setAppState)

    // 3. 发送 idle notification 给 leader
    const idleMsg = createIdleNotification(identity.agentName, ...)
    await writeToMailbox(TEAM_LEAD_NAME, idleMsg)

    // 4. 调用 onIdleCallbacks (解除 engine.waitForIdle 的等待)
    taskState.onIdleCallbacks?.forEach(cb => cb())

    // 5. 等待新消息或 shutdown 请求
    while (true) {
      // 检查 shutdown 请求
      if (taskState.shutdownRequested) {
        // 请求模型批准 shutdown
        const approved = await requestModelShutdownApproval()
        if (approved) break  // 退出主循环
      }

      // 轮询邮箱 (每 500ms)
      const messages = await readMailbox(identity.agentName)
      const newMessages = messages.filter(m => !m.read)
      
      if (newMessages.length > 0) {
        // 有新消息,退出等待循环,继续主循环
        markMessagesAsRead(newMessages)
        break
      }

      // 等待 500ms 后再次轮询
      await sleep(500)
    }

    // 6. 处理新消息,添加到 allMessages
    allMessages.push(...createUserMessage(newMessages))
  }

  // 7. 清理资源
  // ...
}
```

### 4.2 空闲等待机制

**关键设计**:

1. **持续运行**: Teammate 不会因为一次任务完成就退出
2. **邮箱轮询**: 每 500ms 检查一次新消息
3. **自动恢复**: 收到新消息后自动继续工作
4. **Shutdown 协商**: 收到 shutdown 请求时,需要模型批准

**状态流转**:

```
running (执行任务)
    ↓ 任务完成
idle (等待工作)
    ↓ 收到新消息
running (执行新任务)
    ↓ 收到 shutdown 请求
shutdown_requested (等待模型批准)
    ↓ 模型批准
exited (退出)
```

---

## 五、并发模型与上下文隔离

### 5.1 AsyncLocalStorage 隔离机制

```typescript
// 场景: 同时运行 3 个 teammate
const ctx1 = createTeammateContext({ agentId: "r1@team", ... })
const ctx2 = createTeammateContext({ agentId: "r2@team", ... })
const ctx3 = createTeammateContext({ agentId: "r3@team", ... })

// 每个 teammate 在独立的异步调用链中运行
runWithTeammateContext(ctx1, () => runAgent(...))  // 链 1
runWithTeammateContext(ctx2, () => runAgent(...))  // 链 2
runWithTeammateContext(ctx3, () => runAgent(...))  // 链 3

// 在链 1 中调用 getTeammateContext()
// → 返回 ctx1 (不会获得 ctx2 或 ctx3)
```

**工作原理**:

```
Async Hook 追踪:
  AsyncResource 1 (ctx1)
    ├── setTimeout → 仍然在 AsyncResource 1 中
    ├── API 调用 → 仍然在 AsyncResource 1 中
    └── await → 仍然在 AsyncResource 1 中
  
  AsyncResource 2 (ctx2)
    ├── setTimeout → 仍然在 AsyncResource 2 中
    └── ...
  
  → 每个 AsyncResource 有独立的 store
```

### 5.2 身份解析优先级

**源码**: `src/utils/teammate.ts`

```typescript
export function getAgentName(): string | undefined {
  // 1. AsyncLocalStorage (进程内 teammate)
  const inProcessCtx = getTeammateContext()
  if (inProcessCtx) return inProcessCtx.agentName
  
  // 2. dynamicTeamContext (tmux teammate)
  return dynamicTeamContext?.agentName
}

export function getTeamName(teamContext?): string | undefined {
  // 1. AsyncLocalStorage (进程内)
  const inProcessCtx = getTeammateContext()
  if (inProcessCtx) return inProcessCtx.teamName
  
  // 2. dynamicTeamContext (tmux)
  if (dynamicTeamContext?.teamName) return dynamicTeamContext.teamName
  
  // 3. AppState.teamContext (leader)
  return teamContext?.teamName
}
```

---

## 六、Kill 流程深度分析

### 6.1 killInProcessTeammate 源码

**源码**: `src/utils/swarm/spawnInProcess.ts:227-310`

```typescript
export function killInProcessTeammate(
  taskId: string,
  setAppState: SetAppStateFn,
): boolean {
  let killed = false
  let teamName: string | null = null
  let agentId: string | null = null

  setAppState((prev: AppState) => {
    const task = prev.tasks[taskId]
    if (!task || task.type !== 'in_process_teammate') return prev
    
    const teammateTask = task as InProcessTeammateTaskState
    if (teammateTask.status !== 'running') return prev

    // 捕获身份信息 (用于后续清理)
    teamName = teammateTask.identity.teamName
    agentId = teammateTask.identity.agentId

    // 1. 中止 controller
    teammateTask.abortController?.abort()

    // 2. 调用清理回调
    teammateTask.unregisterCleanup?.()

    killed = true

    // 3. 调用 onIdleCallbacks (解除等待者阻塞)
    teammateTask.onIdleCallbacks?.forEach(cb => cb())

    // 4. 更新任务状态
    return {
      ...prev,
      tasks: {
        ...prev.tasks,
        [taskId]: {
          ...teammateTask,
          status: 'killed',
          endTime: Date.now(),
          abortController: undefined,
          unregisterCleanup: undefined,
          onIdleCallbacks: undefined,
        },
      },
    }
  })

  if (!killed) return false

  // 5. 从 teamContext.teammates 移除
  setAppState(prev => {
    if (!prev.teamContext) return prev
    const { [agentId]: _, ...remainingTeammates } = prev.teamContext.teammates
    return {
      ...prev,
      teamContext: { ...prev.teamContext, teammates: remainingTeammates },
    }
  })

  // 6. 回收任务输出
  void evictTaskOutput(taskId)

  // 7. 延迟回收任务状态 (30 秒宽限期)
  setTimeout(() => evictTerminalTask(taskId, setAppState), 0)

  return true
}
```

### 6.2 Kill 流程时序图

```
User: kill teammate
    ↓
InProcessTeammateTask.kill()
    ↓
killInProcessTeammate(taskId)
    │
    ├── 1. abortController.abort()
    │       └── 中断 runAgent() 执行
    │
    ├── 2. unregisterCleanup()
    │       └── 取消进程退出回调
    │
    ├── 3. onIdleCallbacks.forEach(cb => cb())
    │       └── 解除 engine.waitForIdle() 的等待
    │
    ├── 4. 更新任务状态 → 'killed'
    │       └── 清除运行时引用
    │
    ├── 5. 从 teamContext.teammates 移除
    │
    ├── 6. evictTaskOutput(taskId)
    │       └── 删除输出文件
    │
    └── 7. evictTerminalTask(taskId)
            └── 30 秒后从 AppState.tasks 移除
```

---

## 七、与进程外 Teammate 对比

### 7.1 详细对比表

| 特性 | In-Process | tmux/iTerm2 |
|------|------------|-------------|
| **进程模型** | 共享 Node.js 进程 | 独立进程 |
| **上下文隔离** | AsyncLocalStorage | 环境变量 (CLI args) |
| **通信方式** | 直接函数调用 + 邮箱 | 仅邮箱 |
| **创建开销** | 毫秒级 (< 10ms) | 秒级 (1-3s) |
| **资源占用** | 极低 (仅内存) | 高 (完整进程) |
| **启动时间** | < 10ms | 1-3s (启动 Claude Code) |
| **API 客户端** | 共享 | 独立 |
| **MCP 连接** | 共享 | 独立 |
| **故障隔离** | 弱 (共享进程) | 强 (独立进程) |
| **多核利用** | 否 (单线程) | 是 (多进程) |
| **内存泄漏风险** | 中 (需注意) | 低 (进程退出即清理) |
| **调试难度** | 高 (共享进程) | 低 (独立进程日志) |
| **跨平台** | 是 | 部分 (tmux 不支持 Windows) |

### 7.2 选择指南

**使用 In-Process 当**:
- 需要快速启动多个 teammate
- 资源受限 (内存/CPU)
- teammate 任务轻量
- 不需要强故障隔离

**使用 tmux/iTerm2 当**:
- 需要强故障隔离
- teammate 任务重量级
- 需要利用多核
- 需要独立调试

---

## 八、技术挑战点

### 8.1 AsyncLocalStorage 传播边界

**问题**: AsyncLocalStorage 只在同一异步调用链中传播,跨 `Promise.all` 可能丢失上下文。

**解决方案**:
```typescript
// ✅ 正确: 每个 teammate 在独立的调用链中
runWithTeammateContext(ctx1, () => runAgent(...))
runWithTeammateContext(ctx2, () => runAgent(...))

// ⚠️ 错误: Promise.all 可能导致上下文混乱
await Promise.all([
  runWithTeammateContext(ctx1, () => runAgent(...)),
  runWithTeammateContext(ctx2, () => runAgent(...)),
])
```

### 8.2 内存共享风险

**问题**: 多个 teammate 共享同一进程,需要避免意外的状态共享。

**解决方案**:
- **不可变 AppState**: 使用 `setAppState(prev => ({ ...prev, ... }))` 
- **独立 allMessages**: 每个 teammate 维护自己的消息数组
- **克隆 FileState**: `cloneFileStateCache()` 避免共享文件缓存

### 8.3 故障隔离弱

**问题**: 一个 teammate 崩溃可能影响整个进程。

**当前缓解**:
- AbortController 独立,一个 teammate abort 不影响其他
- 错误捕获在 runAgent 层,不会传播到其他 teammate

**限制**:
- Node.js 进程崩溃会影响所有 teammate
- 内存泄漏会影响所有 teammate

---

## 九、设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **AsyncLocalStorage** | 上下文隔离 | 干净的并发模型,类似 TLS |
| **独立 AbortController** | 不链接到 leader | teammate 生命周期独立 |
| **空闲等待循环** | 邮箱轮询 + sleep | 支持多任务,无需重启 |
| **轻量级创建** | 无进程启动 | 毫秒级,< 10ms |
| **资源共享** | API 客户端、MCP | 避免重复初始化 |
| **Perfetto 集成** | registerPerfettoAgent | 性能分析可视化 |
| **双重身份** | Identity (持久化) + Context (运行时) | 状态分离 |
| **Shutdown 协商** | 模型批准机制 | 优雅退出 |

---

## 十、可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **故障隔离弱** | 共享进程 | Worker Threads 隔离 | P3 |
| **无法利用多核** | 单线程 | 考虑 Worker Threads | P3 |
| **内存共享风险** | 需小心避免 | 添加内存审计工具 | P2 |
| **消息上限固定** | 50 条硬编码 | 基于内存压力动态调整 | P2 |
| **轮询效率低** | 500ms 轮询邮箱 | inotify 监听文件变化 | P3 |
| **缺少调试支持** | 共享进程日志 | 添加 teammate 级日志过滤 | P2 |
| **无资源监控** | 无内存/CPU 监控 | 添加资源使用面板 | P3 |

---

## 十一、关键文件索引

| 文件 | 作用 | 行数 |
|------|------|------|
| `src/utils/teammateContext.ts` | AsyncLocalStorage 实现 | 96 |
| `src/utils/swarm/spawnInProcess.ts` | Spawn/Kill 逻辑 | 265 |
| `src/utils/swarm/inProcessRunner.ts` | 执行循环 | 1553 |
| `src/utils/swarm/backends/InProcessBackend.ts` | Backend 接口 | 144 |
| `src/tasks/InProcessTeammateTask/types.ts` | 类型定义 | ~100 |
| `src/tasks/InProcessTeammateTask/InProcessTeammateTask.tsx` | Task 组件 | 84 |
| `src/utils/teammate.ts` | 身份解析工具 | 156 |

---

## 十二、总结

进程内 Teammate 的设计体现了以下核心原则:

1. **轻量级**: 无需启动新进程,毫秒级创建
2. **上下文隔离**: AsyncLocalStorage 提供干净的并发模型
3. **独立生命周期**: 独立 AbortController,不依赖 leader
4. **持续运行**: 空闲等待循环支持多任务
5. **资源共享**: 共享 API 客户端和 MCP 连接

这套设计为 Claude Code 的 Swarm 系统提供了**快速、低开销**的协作选项,特别适合资源受限和需要快速启动多个 teammate 的场景。
