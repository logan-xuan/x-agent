# Claude Code 任务状态机深度分析

## 一、概述

任务状态机是 Claude Code 多智能体系统的核心基础设施，负责管理所有后台任务（Agent、Shell、Teammate）的生命周期。本文深入分析其设计哲学、实现细节和架构决策。

---

## 二、状态定义体系

### 2.1 任务类型层次结构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TaskState (联合类型)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ LocalShellTask  │  │ LocalAgentTask  │  │ InProcessTeammateTask       │  │
│  │ (Shell 命令)     │  │ (后台 Agent)    │  │ (进程内 Teammate)            │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ RemoteAgentTask │  │ LocalWorkflow   │  │ MonitorMcpTask              │  │
│  │ (远程 Agent)     │  │ (工作流任务)    │  │ (MCP 监控)                   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 TaskStateBase 基础结构

```typescript
// src/Task.ts
type TaskStateBase = {
  // 核心标识
  id: string                    // 任务唯一 ID
  type: TaskType                // 任务类型标识符
  description: string           // 人类可读描述
  toolUseId?: string            // 关联的工具调用 ID
  
  // 状态追踪
  status: TaskStatus            // 当前状态
  startTime: number             // 启动时间戳
  endTime?: number              // 结束时间戳
  
  // 输出管理
  outputOffset: number          // 输出文件读取偏移量
  
  // 通知控制
  notified: boolean             // 是否已发送完成通知
}
```

### 2.3 LocalAgentTaskState 完整定义

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx
type LocalAgentTaskState = TaskStateBase & {
  type: 'local_agent'
  
  // ═══════════════════════════════════════════════════════════════════════
  // 核心标识
  // ═══════════════════════════════════════════════════════════════════════
  agentId: string               // Agent 唯一标识 (格式: uuid 或 name@team)
  prompt: string                // 原始任务提示词
  selectedAgent?: AgentDefinition  // Agent 定义 (运行时清理)
  agentType: string             // Agent 类型 (如 'Explore', 'Plan')
  model?: string                // 使用的模型
  
  // ═══════════════════════════════════════════════════════════════════════
  // 生命周期控制
  // ═══════════════════════════════════════════════════════════════════════
  abortController?: AbortController  // 取消控制器 (运行时)
  unregisterCleanup?: () => void     // 清理回调注销函数 (运行时)
  
  // ═══════════════════════════════════════════════════════════════════════
  // 执行结果
  // ═══════════════════════════════════════════════════════════════════════
  error?: string                // 错误信息
  result?: AgentToolResult      // 执行结果
  progress?: AgentProgress      // 进度信息
  
  // ═══════════════════════════════════════════════════════════════════════
  // 后台任务管理
  // ═══════════════════════════════════════════════════════════════════════
  isBackgrounded: boolean       // false=前台运行, true=已后台化
  pendingMessages: string[]     // 中途排队的消息 (SendMessage 入队)
  
  // ═══════════════════════════════════════════════════════════════════════
  // UI 保持与回收
  // ═══════════════════════════════════════════════════════════════════════
  retain: boolean               // UI 是否持有此任务 (阻止回收)
  diskLoaded: boolean           // 是否已从磁盘加载 transcript
  evictAfter?: number           // 回收截止时间戳
  
  // ═══════════════════════════════════════════════════════════════════════
  // 进度追踪 (用于计算增量通知)
  // ═══════════════════════════════════════════════════════════════════════
  lastReportedToolCount: number
  lastReportedTokenCount: number
  
  // ═══════════════════════════════════════════════════════════════════════
  // 消息历史 (用于 UI 显示)
  // ═══════════════════════════════════════════════════════════════════════
  messages?: Message[]          // 对话历史 (可选，用于 transcript 查看)
  retrieved: boolean            // 是否已检索结果
}
```

### 2.4 InProcessTeammateTaskState 定义

```typescript
// src/tasks/InProcessTeammateTask/types.ts
type InProcessTeammateTaskState = TaskStateBase & {
  type: 'in_process_teammate'
  
  // ═══════════════════════════════════════════════════════════════════════
  // 身份信息 (与 TeammateContext 形状一致)
  // ═══════════════════════════════════════════════════════════════════════
  identity: {
    agentId: string             // 如 "researcher@my-team"
    agentName: string           // 如 "researcher"
    teamName: string
    color?: string
    planModeRequired: boolean
    parentSessionId: string     // Leader 的 session ID
  }
  
  // ═══════════════════════════════════════════════════════════════════════
  // 执行配置
  // ═══════════════════════════════════════════════════════════════════════
  prompt: string
  model?: string
  selectedAgent?: AgentDefinition
  permissionMode: PermissionMode
  
  // ═══════════════════════════════════════════════════════════════════════
  // 生命周期控制
  // ═══════════════════════════════════════════════════════════════════════
  abortController?: AbortController           // 终止整个 teammate
  currentWorkAbortController?: AbortController // 仅终止当前轮次
  unregisterCleanup?: () => void
  
  // ═══════════════════════════════════════════════════════════════════════
  // Plan 模式审批
  // ═══════════════════════════════════════════════════════════════════════
  awaitingPlanApproval: boolean
  
  // ═══════════════════════════════════════════════════════════════════════
  // 状态
  // ═══════════════════════════════════════════════════════════════════════
  isIdle: boolean               // 是否空闲 (等待工作)
  shutdownRequested: boolean    // 是否收到关闭请求
  
  // ═══════════════════════════════════════════════════════════════════════
  // 消息队列
  // ═══════════════════════════════════════════════════════════════════════
  messages?: Message[]          // 对话历史 (有上限: TEAMMATE_MESSAGES_UI_CAP=50)
  pendingUserMessages: string[] // 待处理的用户消息
  
  // ═══════════════════════════════════════════════════════════════════════
  // UI 状态
  // ═══════════════════════════════════════════════════════════════════════
  spinnerVerb?: string          // 随机 spinner 动词
  pastTenseVerb?: string        // 完成时动词
  inProgressToolUseIDs?: Set<string>  // 正在执行的工具 ID
  
  // ═══════════════════════════════════════════════════════════════════════
  // 回调 (运行时)
  // ═══════════════════════════════════════════════════════════════════════
  onIdleCallbacks?: Array<() => void>  // 空闲时通知回调
}
```

---

## 三、状态转换图

### 3.1 LocalAgentTask 状态机

```
                                    ┌─────────────────────────────────────┐
                                    │                                     │
                                    ▼                                     │
┌─────────────┐  registerAsyncAgent()  ┌─────────────┐                   │
│  (不存在)    │ ─────────────────────→ │   running   │ ←─────────────────┘
└─────────────┘                        └─────────────┘    resumeAgentBackground()
       │                                      │
       │ registerAgentForeground()            │
       ▼                                      │
┌─────────────┐  backgroundAgentTask()        │
│  running    │ ──────────────────────────────┤
│ (前台模式)   │                               │
└─────────────┘                               │
       │                                      │
       │ unregisterAgentForeground()          │
       │ (同步完成，未后台化)                   │
       ▼                                      │
┌─────────────┐                               │
│  (已移除)    │                               │
└─────────────┘                               │
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
                    ▼                         ▼                         ▼
            completeAgentTask()        failAgentTask()          killAsyncAgent()
                    │                         │                         │
                    ▼                         ▼                         ▼
            ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
            │  completed  │           │   failed    │           │   killed    │
            └─────────────┘           └─────────────┘           └─────────────┘
                    │                         │                         │
                    └─────────────────────────┼─────────────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────────┐
                                    │ evictAfter 到期检查  │
                                    └─────────────────────┘
                                              │
                              ┌───────────────┼───────────────┐
                              │               │               │
                              ▼               ▼               ▼
                        retain=true    evictAfter>now   evictAfter<=now
                              │               │               │
                              ▼               ▼               ▼
                        保持不变         保持不变      evictTerminalTask()
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ 从 AppState 移除 │
                                                    └─────────────────┘
```

### 3.2 InProcessTeammateTask 状态机

```
┌─────────────┐  spawnInProcessTeammate()  ┌─────────────┐
│  (不存在)    │ ────────────────────────→  │   running   │
└─────────────┘                            └─────────────┘
                                                  │
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    │                             │                             │
                    │                             │                             │
                    ▼                             ▼                             ▼
          setIdle(true)                 killInProcessTeammate()        任务完成/失败
                    │                             │                             │
                    ▼                             ▼                             ▼
            ┌─────────────┐               ┌─────────────┐               ┌─────────────┐
            │    idle     │               │   killed    │               │ completed/  │
            │ (等待工作)   │               │             │               │   failed    │
            └─────────────┘               └─────────────┘               └─────────────┘
                    │                             │                             │
                    │ 收到新消息                   │                             │
                    │ setIdle(false)              │                             │
                    ▼                             │                             │
            ┌─────────────┐                       │                             │
            │   running   │ ←─────────────────────┴─────────────────────────────┘
            │ (处理中)     │                       (不可恢复)
            └─────────────┘
```

---

## 四、状态转换函数详解

### 4.1 注册异步 Agent

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx
function registerAsyncAgent({
  agentId,
  description,
  prompt,
  selectedAgent,
  setAppState,
  parentAbortController,  // 可选的父级 AbortController
  toolUseId
}): LocalAgentTaskState {
  
  // 1. 初始化输出文件符号链接
  void initTaskOutputAsSymlink(agentId, getAgentTranscriptPath(asAgentId(agentId)))
  
  // 2. 创建 AbortController
  //    - 如果有父级，创建子级 (父级 abort 时自动 abort)
  //    - 否则创建独立的 controller
  const abortController = parentAbortController 
    ? createChildAbortController(parentAbortController) 
    : createAbortController()
  
  // 3. 构建任务状态
  const taskState: LocalAgentTaskState = {
    ...createTaskStateBase(agentId, 'local_agent', description, toolUseId),
    type: 'local_agent',
    status: 'running',
    agentId,
    prompt,
    selectedAgent,
    agentType: selectedAgent.agentType ?? 'general-purpose',
    abortController,
    retrieved: false,
    lastReportedToolCount: 0,
    lastReportedTokenCount: 0,
    isBackgrounded: true,      // 立即后台化
    pendingMessages: [],
    retain: false,
    diskLoaded: false,
  }
  
  // 4. 注册清理回调 (进程退出时自动 kill)
  const unregisterCleanup = registerCleanup(async () => {
    killAsyncAgent(agentId, setAppState)
  })
  taskState.unregisterCleanup = unregisterCleanup
  
  // 5. 注册到 AppState
  registerTask(taskState, setAppState)
  
  return taskState
}
```

### 4.2 完成 Agent 任务

```typescript
function completeAgentTask(result: AgentToolResult, setAppState: SetAppState): void {
  const taskId = result.agentId
  
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => {
    // 幂等性检查: 只处理 running 状态
    if (task.status !== 'running') {
      return task  // 返回原对象，不触发状态更新
    }
    
    // 清理资源
    task.unregisterCleanup?.()
    
    return {
      ...task,
      status: 'completed',
      result,
      endTime: Date.now(),
      // 回收时间: 如果 UI 持有则不设置，否则 30 秒后回收
      evictAfter: task.retain ? undefined : Date.now() + PANEL_GRACE_MS,
      // 清理运行时引用
      abortController: undefined,
      unregisterCleanup: undefined,
      selectedAgent: undefined,  // 释放 AgentDefinition 内存
    }
  })
  
  // 触发输出文件清理 (异步，不阻塞)
  void evictTaskOutput(taskId)
}
```

### 4.3 终止 Agent 任务

```typescript
function killAsyncAgent(taskId: string, setAppState: SetAppState): void {
  let killed = false
  
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => {
    if (task.status !== 'running') {
      return task
    }
    
    killed = true
    
    // 触发 abort 信号
    task.abortController?.abort()
    
    // 注销清理回调
    task.unregisterCleanup?.()
    
    return {
      ...task,
      status: 'killed',
      endTime: Date.now(),
      evictAfter: task.retain ? undefined : Date.now() + PANEL_GRACE_MS,
      abortController: undefined,
      unregisterCleanup: undefined,
      selectedAgent: undefined,
    }
  })
  
  if (killed) {
    void evictTaskOutput(taskId)
  }
}
```

---

## 五、技术挑战点

### 5.1 并发状态转换的 TOCTOU 竞态

**问题**: 在异步操作（如 `generateTaskAttachments` 读取磁盘输出）期间，任务状态可能已被其他操作修改。

**技术挑战**:
```
T0: generateTaskAttachments 开始读取 task.outputOffset
T1: 用户按 ESC，killAsyncAgent 将 status 改为 'killed'
T2: generateTaskAttachments 完成，尝试更新 outputOffset
    → 如果直接应用，会覆盖 killed 状态！
```

**解决方案**: Fresh State Re-Check 模式
```typescript
// src/utils/task/framework.ts:226-230
for (const id of offsetIds) {
  const fresh = newTasks[id]
  // 在 fresh 状态上重新检查 — 任务可能在 await 期间完成
  // 如果不再运行，offset 更新无意义
  if (fresh?.status === 'running') {
    newTasks[id] = { ...fresh, outputOffset: updatedTaskOffsets[id]! }
    changed = true
  }
}
```

**设计亮点**: 
- 不在 await 前快照状态，而是对 fresh state 重新验证
- 避免 "zombifying"（僵尸化）已完成的任务
- 类似于数据库的乐观锁机制

### 5.2 不可变更新与引用相等优化

**问题**: React 的 `setAppState` 每次都会触发重渲染，即使数据未变。

**技术挑战**: 如何避免不必要的重渲染？

**解决方案**:
```typescript
// src/utils/task/framework.ts:58-63
const updated = updater(task)
if (updated === task) {
  // Updater returned the same reference (early-return no-op).
  // Skip the spread so s.tasks subscribers don't re-render on unchanged state.
  return prev
}
```

**性能影响**:
- 幂等操作（如重复调用 `completeAgentTask`）零开销
- 避免 React 组件无意义的 re-render
- 减少 React Fiber 树的 diff 计算

### 5.3 运行时引用与可序列化状态的分离

**问题**: `abortController`、`unregisterCleanup`、`selectedAgent` 等是运行时对象，不能被序列化或恢复。

**解决方案**: 状态分离
```typescript
// 终止时清除运行时引用
return {
  ...task,
  status: 'completed',
  abortController: undefined,        // 运行时对象
  unregisterCleanup: undefined,      // 运行时回调
  selectedAgent: undefined,          // 释放大对象内存
  // 保留可序列化字段
  result, endTime, evictAfter
}
```

**设计亮点**:
- 任务状态可随时快照到磁盘（`AppState.tasks` 可序列化）
- 运行时引用在需要时重建
- 及时释放大对象（`AgentDefinition` 可达数 MB）

### 5.4 任务替换时的 UI 状态保留

**问题**: `resumeAgentBackground` 会替换整个任务对象，但用户的 `retain`、`messages`、`diskLoaded` 不应重置。

**解决方案**:
```typescript
// src/utils/task/framework.ts:115-127
const merged = existing && 'retain' in existing
  ? {
      ...task,
      retain: existing.retain,           // 保留 UI 持有状态
      startTime: existing.startTime,     // 保持面板排序稳定
      messages: existing.messages,       // 保留对话历史
      diskLoaded: existing.diskLoaded,   // 保留磁盘加载状态
      pendingMessages: existing.pendingMessages,
    }
  : task
```

**设计哲学**: 用户意图（正在查看）优先于系统操作（恢复任务）

---

## 六、设计亮点

### 6.1 分层状态管理架构

```typescript
// 层 1: 基础类型约束 (TaskStateBase)
// 层 2: 任务类型扩展 (LocalAgentTaskState, InProcessTeammateTaskState)
// 层 3: 运行时引用 (abortController, unregisterCleanup)
// 层 4: UI 状态 (retain, diskLoaded, messages)
// 层 5: 回收控制 (evictAfter, notified)
```

**亮点**: 每层关注点不同，类型系统保证安全性

### 6.2 宽限期回收机制

```typescript
export const PANEL_GRACE_MS = 30_000  // 30 秒

// 任务完成时
evictAfter: task.retain ? undefined : Date.now() + PANEL_GRACE_MS
```

**为什么是 30 秒？**
- 用户需要时间查看已完成任务的输出
- 太短：用户来不及查看，体验差
- 太长：内存占用久，影响性能
- 30 秒是经验值，平衡用户体验和内存压力

### 6.3 幂等状态转换

```typescript
function completeAgentTask(result, setAppState) {
  updateTaskState(taskId, setAppState, task => {
    if (task.status !== 'running') {
      return task  // 幂等性保护
    }
    // ...
  })
}
```

**防护场景**:
- 网络重试导致重复完成消息
- 用户快速多次点击完成按钮
- 进程崩溃恢复后的状态同步

### 6.4 通知与回收的解耦

```
任务完成 → notified = false → 发送通知 → notified = true → 可回收
                                      ↓
                              30 秒宽限期后
                                      ↓
                              evictTerminalTask
```

**设计亮点**:
- 不依赖时序：即使通知延迟，回收也会等待
- 双重保障：`generateTaskAttachments` 懒惰 GC 作为安全网
- 主动回收：`evictTerminalTask` 不依赖轮询

### 6.5 类型守卫与类型窄化

```typescript
// 'retain' in task 窄化到 LocalAgentTaskState
if ('retain' in task && (task.evictAfter ?? Infinity) > Date.now()) {
  return prev
}
```

**TypeScript 技巧**:
- 使用 `'field' in object` 进行类型窄化
- 避免使用 `task.evictAfter !== undefined`（会漏掉未设置的字段）
- 编译期类型安全 + 运行期防御

---

## 七、可改进之处

### 7.1 状态类型分散导致重复代码

**问题**: 每种任务类型单独定义 `TaskState`，字段重复度高。

**当前状态**:
```
LocalAgentTaskState: 20+ 字段
InProcessTeammateTaskState: 25+ 字段
LocalShellTaskState: 15+ 字段
```

**改进建议**: 使用泛型基类 + 组合模式
```typescript
// 方案 1: 泛型基类
abstract class TaskStateBase<T extends TaskType> {
  id: string
  type: T
  status: TaskStatus
  // ... 公共字段
}

// 方案 2: 组合模式
type TaskState = TaskStateBase & (
  | LocalAgentExtensions
  | InProcessTeammateExtensions
  | LocalShellExtensions
)
```

### 7.2 固定宽限期不适应不同场景

**问题**: 所有任务统一 30 秒宽限期。

**改进建议**: 基于任务类型动态调整
```typescript
function getGracePeriod(task: TaskState): number {
  switch (task.type) {
    case 'local_agent': return 30_000    // Agent 需要时间查看
    case 'local_shell': return 5_000     // Shell 输出简短，5 秒足够
    case 'in_process_teammate': return 60_000  // Teammate 对话长，60 秒
    default: return 30_000
  }
}
```

### 7.3 轮询回收效率低

**问题**: 依赖 1 秒轮询检查 `evictAfter`，不够精确。

**当前实现**:
```typescript
// pollTasks() 每 1 秒调用一次
setInterval(pollTasks, POLL_INTERVAL_MS)  // 1000ms
```

**改进建议**: 使用 `setTimeout` 精确触发
```typescript
function scheduleEviction(taskId: string, evictAfter: number) {
  const delay = evictAfter - Date.now()
  setTimeout(() => evictTerminalTask(taskId, setAppState), delay)
}
```

**权衡**: 
- ✅ 精确触发，减少不必要的轮询
- ❌ 增加定时器管理复杂度
- ⚠️ 大量任务时可能有数千个定时器

### 7.4 缺少任务状态可观测性

**问题**: 难以追踪任务状态转换的完整链路。

**改进建议**: 添加状态转换日志/追踪
```typescript
function updateTaskState<T extends TaskState>(...) {
  const oldStatus = task.status
  const updated = updater(task)
  
  if (updated.status !== oldStatus) {
    logEvent('task_status_transition', {
      taskId: task.id,
      from: oldStatus,
      to: updated.status,
      timestamp: Date.now()
    })
  }
}
```

### 7.5 消息上限固定不灵活

**问题**: `TEAMMATE_MESSAGES_UI_CAP = 50` 硬编码。

**改进建议**: 基于内存压力动态调整
```typescript
function getDynamicMessageCap(): number {
  const memUsage = process.memoryUsage()
  const rssMB = memUsage.rss / 1024 / 1024
  
  if (rssMB > 1024) return 20        // 高内存压力，减少到 20
  if (rssMB > 512) return 35         // 中等压力
  return 50                          // 正常
}
```

---

## 八、总结

任务状态机的设计体现了以下核心原则：

1. **单向状态流**: running → completed/failed/killed，不可逆转
2. **幂等操作**: 重复调用状态转换函数是安全的
3. **资源生命周期**: 状态转换时自动清理运行时资源
4. **用户体验优先**: 宽限期机制允许用户查看已完成任务
5. **内存管理**: 通过 evict 机制和消息上限控制内存使用
6. **并发安全**: Fresh State Re-Check 防止 TOCTOU 竞态
7. **类型安全**: TypeScript 联合类型 + 类型守卫保证编译期安全

这套设计为 Claude Code 的多智能体系统提供了可靠的任务生命周期管理基础，特别是在并发控制、内存优化和用户体验之间取得了良好平衡。

### 核心技术决策总结

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 状态更新模式 | 不可变更新 | React 最佳实践，避免副作用 |
| 回收策略 | 宽限期 + 轮询 | 平衡精确度和复杂度 |
| 运行时引用 | 终止时清除 | 及时释放内存，保持可序列化 |
| 并发防护 | Fresh State Re-Check | 避免僵尸状态，乐观锁模式 |
| 类型设计 | 联合类型 + 类型守卫 | 编译期安全，运行时窄化 |

### 6.1 updateTaskState 核心函数

```typescript
// src/utils/task/framework.ts
function updateTaskState<T extends TaskState>(
  taskId: string,
  setAppState: SetAppState,
  updater: (task: T) => T,
): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId] as T | undefined
    if (!task) {
      return prev  // 任务不存在，不更新
    }
    
    const updated = updater(task)
    
    // 优化: 如果 updater 返回相同引用，跳过更新
    // 避免不必要的 React 重渲染
    if (updated === task) {
      return prev
    }
    
    return {
      ...prev,
      tasks: {
        ...prev.tasks,
        [taskId]: updated,
      },
    }
  })
}
```

### 6.2 registerTask 注册函数

```typescript
function registerTask(task: TaskState, setAppState: SetAppState): void {
  let isReplacement = false
  
  setAppState(prev => {
    const existing = prev.tasks[task.id]
    isReplacement = existing !== undefined
    
    // 重要: 替换时保留 UI 状态
    // resumeAgentBackground 会替换任务，但用户的 retain 不应重置
    const merged = existing && 'retain' in existing
      ? {
          ...task,
          retain: existing.retain,           // 保留 UI 持有状态
          startTime: existing.startTime,     // 保持面板排序稳定
          messages: existing.messages,       // 保留对话历史
          diskLoaded: existing.diskLoaded,   // 保留磁盘加载状态
          pendingMessages: existing.pendingMessages,
        }
      : task
    
    return { ...prev, tasks: { ...prev.tasks, [task.id]: merged } }
  })
  
  // 替换 (resume) 不是新启动，跳过 SDK 事件
  if (isReplacement) return
  
  // 发送 task_started SDK 事件
  enqueueSdkEvent({
    type: 'system',
    subtype: 'task_started',
    task_id: task.id,
    tool_use_id: task.toolUseId,
    description: task.description,
    task_type: task.type,
    // ...
  })
}
```

---

## 十、架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Task State Machine                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         AppState.tasks                               │   │
│  │  {                                                                   │   │
│  │    [taskId]: TaskState,                                              │   │
│  │    [taskId]: TaskState,                                              │   │
│  │    ...                                                               │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         │                          │                          │            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐    │
│  │ registerTask()  │      │ updateTaskState │      │ evictTerminal   │    │
│  │                 │      │      ()         │      │    Task()       │    │
│  │ - 创建新任务     │      │                 │      │                 │    │
│  │ - 合并已存在任务 │      │ - 幂等状态转换   │      │ - 检查终止状态   │    │
│  │ - 发送 SDK 事件  │      │ - 不可变更新    │      │ - 检查 notified │    │
│  └─────────────────┘      │ - 引用相等优化   │      │ - 检查 evictAfter│   │
│                           └─────────────────┘      │ - 从 tasks 移除  │    │
│                                                    └─────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      状态转换触发点                                   │   │
│  │                                                                      │   │
│  │  AgentTool.call()  ──→  registerAsyncAgent()  ──→  running          │   │
│  │  runAgent() 完成   ──→  completeAgentTask()   ──→  completed        │   │
│  │  runAgent() 异常   ──→  failAgentTask()       ──→  failed           │   │
│  │  ESC / kill 命令   ──→  killAsyncAgent()      ──→  killed           │   │
│  │  pollTasks() 轮询  ──→  evictTerminalTask()   ──→  (移除)           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 十一、关键常量

```typescript
// src/utils/task/framework.ts

// 标准轮询间隔
export const POLL_INTERVAL_MS = 1000

// killed 任务显示时长 (用于 UI 反馈)
export const STOPPED_DISPLAY_MS = 3_000

// 终止任务的面板宽限期 (30 秒)
// 用户可以在此期间查看已完成任务的输出
export const PANEL_GRACE_MS = 30_000

// src/tasks/InProcessTeammateTask/types.ts

// Teammate 消息 UI 上限
// 防止内存膨胀 (BQ 分析显示 500+ 轮次会话达到 ~20MB RSS/agent)
export const TEAMMATE_MESSAGES_UI_CAP = 50
```

---

## 十二、总结

任务状态机的设计体现了以下核心原则：

1. **单向状态流**: running → completed/failed/killed，不可逆转
2. **幂等操作**: 重复调用状态转换函数是安全的
3. **资源生命周期**: 状态转换时自动清理运行时资源
4. **用户体验优先**: 宽限期机制允许用户查看已完成任务
5. **内存管理**: 通过 evict 机制和消息上限控制内存使用

这套设计为 Claude Code 的多智能体系统提供了可靠的任务生命周期管理基础。
