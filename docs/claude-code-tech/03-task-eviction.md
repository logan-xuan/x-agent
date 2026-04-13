# Claude Code 任务回收机制深度分析

## 一、概述

任务回收机制是 Claude Code 内存管理的核心组件，负责在任务完成后及时释放资源，同时保证用户体验不受影响。本文深入分析 30 秒宽限期、evictAfter 时间戳、retain 标志等核心机制。

---

## 二、回收机制核心概念

### 2.1 关键常量定义

```typescript
// src/utils/task/framework.ts

// 标准轮询间隔 (1秒)
export const POLL_INTERVAL_MS = 1000

// killed 任务显示时长 (3秒) - 用于 UI 反馈
export const STOPPED_DISPLAY_MS = 3_000

// 终止任务的面板宽限期 (30秒)
// 用户可以在此期间查看已完成任务的输出
export const PANEL_GRACE_MS = 30_000
```

### 2.2 回收相关字段

```typescript
// LocalAgentTaskState 中的回收相关字段
type LocalAgentTaskState = TaskStateBase & {
  // ...
  
  // UI 是否持有此任务 (阻止回收)
  // 由 enterTeammateView() 设置
  // 与 viewingAgentTaskId 不同 (那是"正在看什么")
  // retain 是"正在持有什么"
  retain: boolean
  
  // 是否已从磁盘加载 transcript
  // 每个 retain 周期只执行一次
  diskLoaded: boolean
  
  // 面板可见性截止时间
  // undefined = 无截止 (运行中或被持有)
  // timestamp = 此时间后隐藏并可被 GC
  // 在终止转换时设置，取消选择时设置，retain 时清除
  evictAfter?: number
}
```

---

## 三、回收流程架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Task Eviction Flow                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐                                                            │
│  │   running   │                                                            │
│  └─────────────┘                                                            │
│         │                                                                   │
│         │ completeAgentTask() / failAgentTask() / killAsyncAgent()         │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Terminal State Transition                         │   │
│  │                                                                      │   │
│  │  if (task.retain) {                                                 │   │
│  │    evictAfter = undefined  // UI 持有，不设置回收时间                 │   │
│  │  } else {                                                           │   │
│  │    evictAfter = Date.now() + PANEL_GRACE_MS  // 30秒后可回收         │   │
│  │  }                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              completed / failed / killed                             │   │
│  │                                                                      │   │
│  │  notified: false  (等待发送通知)                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ enqueueAgentNotification()                                       │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              completed / failed / killed                             │   │
│  │                                                                      │   │
│  │  notified: true  (已发送通知，可被回收)                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ pollTasks() → generateTaskAttachments() → evictedTaskIds         │
│         │ 或 evictTerminalTask() 直接调用                                  │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Eviction Check                                    │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ 1. isTerminalTaskStatus(status) ?                           │    │   │
│  │  │    - completed / failed / killed                            │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                         │ Yes                                        │   │
│  │                         ▼                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ 2. task.notified === true ?                                 │    │   │
│  │  │    - 已发送完成通知                                          │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                         │ Yes                                        │   │
│  │                         ▼                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ 3. 'retain' in task ?                                       │    │   │
│  │  │    - 是 LocalAgentTaskState 类型                             │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                         │ Yes                                        │   │
│  │                         ▼                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ 4. (task.evictAfter ?? Infinity) <= Date.now() ?            │    │   │
│  │  │    - 回收时间已到                                            │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                         │ Yes                                        │   │
│  │                         ▼                                            │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ 5. 从 AppState.tasks 中删除                                  │    │   │
│  │  │    const { [taskId]: _, ...remainingTasks } = prev.tasks    │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、核心函数实现

### 4.1 evictTerminalTask - 主动回收

```typescript
// src/utils/task/framework.ts

/**
 * 主动回收终止状态的任务
 * 任务必须处于终止状态 (completed/failed/killed) 且 notified=true
 * 允许在不等待下一次轮询循环的情况下释放内存
 * generateTaskAttachments() 中的懒惰 GC 作为安全网保留
 */
export function evictTerminalTask(
  taskId: string,
  setAppState: SetAppState,
): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId]
    
    // 任务不存在
    if (!task) return prev
    
    // 非终止状态，不回收
    if (!isTerminalTaskStatus(task.status)) return prev
    
    // 未发送通知，不回收
    if (!task.notified) return prev
    
    // 面板宽限期检查
    // 'retain' in task 缩小类型到 LocalAgentTaskState
    // evictAfter 是可选的，所以用 'evictAfter' in task 会漏掉未设置的情况
    if ('retain' in task && (task.evictAfter ?? Infinity) > Date.now()) {
      return prev  // 宽限期未到，不回收
    }
    
    // 执行回收
    const { [taskId]: _, ...remainingTasks } = prev.tasks
    return { ...prev, tasks: remainingTasks }
  })
}
```

### 4.2 generateTaskAttachments - 懒惰 GC

```typescript
// src/utils/task/framework.ts

/**
 * 为有新输出或状态变化的任务生成附件
 * 由框架调用以创建推送通知
 * 同时执行懒惰 GC
 */
export async function generateTaskAttachments(state: AppState): Promise<{
  attachments: TaskAttachment[]
  updatedTaskOffsets: Record<string, number>
  evictedTaskIds: string[]
}> {
  const attachments: TaskAttachment[] = []
  const updatedTaskOffsets: Record<string, number> = {}
  const evictedTaskIds: string[] = []
  const tasks = state.tasks ?? {}

  for (const taskState of Object.values(tasks)) {
    if (taskState.notified) {
      switch (taskState.status) {
        case 'completed':
        case 'failed':
        case 'killed':
          // 回收终止任务 — 已被消费，可以 GC
          evictedTaskIds.push(taskState.id)
          continue
        case 'pending':
          // 保留 — 尚未运行，但父级已知道它
          continue
        case 'running':
          // 继续到下面的运行逻辑
          break
      }
    }

    if (taskState.status === 'running') {
      // 读取输出增量
      const delta = await getTaskOutputDelta(
        taskState.id,
        taskState.outputOffset,
      )
      if (delta.content) {
        updatedTaskOffsets[taskState.id] = delta.newOffset
      }
    }

    // 注意: 已完成任务不在这里通知
    // 每种任务类型通过 enqueuePendingNotification() 处理自己的完成通知
    // 在这里生成附件会与那些回调竞争，导致双重投递
  }

  return { attachments, updatedTaskOffsets, evictedTaskIds }
}
```

### 4.3 applyTaskOffsetsAndEvictions - 应用回收

```typescript
// src/utils/task/framework.ts

/**
 * 应用 generateTaskAttachments 的 outputOffset 补丁和回收
 * 针对 FRESH prev.tasks 合并补丁 (不是过时的 pre-await 快照)
 * 这样并发状态转换不会被覆盖
 */
export function applyTaskOffsetsAndEvictions(
  setAppState: SetAppState,
  updatedTaskOffsets: Record<string, number>,
  evictedTaskIds: string[],
): void {
  const offsetIds = Object.keys(updatedTaskOffsets)
  if (offsetIds.length === 0 && evictedTaskIds.length === 0) {
    return
  }
  
  setAppState(prev => {
    let changed = false
    const newTasks = { ...prev.tasks }
    
    // 应用 offset 更新
    for (const id of offsetIds) {
      const fresh = newTasks[id]
      // 在 fresh 状态上重新检查 — 任务可能在 await 期间完成
      // 如果不再运行，offset 更新无意义
      if (fresh?.status === 'running') {
        newTasks[id] = { ...fresh, outputOffset: updatedTaskOffsets[id]! }
        changed = true
      }
    }
    
    // 应用回收
    for (const id of evictedTaskIds) {
      const fresh = newTasks[id]
      // 在 fresh 状态上重新检查 terminal+notified
      // (TOCTOU: resume 可能在 generateTaskAttachments await 期间替换了任务)
      if (!fresh || !isTerminalTaskStatus(fresh.status) || !fresh.notified) {
        continue
      }
      // 宽限期检查
      if ('retain' in fresh && (fresh.evictAfter ?? Infinity) > Date.now()) {
        continue
      }
      delete newTasks[id]
      changed = true
    }
    
    return changed ? { ...prev, tasks: newTasks } : prev
  })
}
```

---

## 五、retain 机制详解

### 5.1 retain 标志的作用

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        retain Flag Mechanism                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  retain = false (默认)                    retain = true                     │
│  ┌─────────────────────────┐              ┌─────────────────────────┐      │
│  │                         │              │                         │      │
│  │  任务完成后:             │              │  任务完成后:             │      │
│  │  evictAfter = now + 30s │              │  evictAfter = undefined │      │
│  │                         │              │                         │      │
│  │  30秒后自动回收          │              │  永不自动回收            │      │
│  │                         │              │  (直到 retain=false)    │      │
│  └─────────────────────────┘              └─────────────────────────┘      │
│                                                                             │
│  使用场景:                                                                  │
│  - 后台任务完成                            - 用户正在查看任务 transcript    │
│  - 用户未关注此任务                         - enterTeammateView() 设置      │
│  - 可以安全回收                            - 需要保持任务状态用于 UI 显示   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 retain 与 evictAfter 的交互

```typescript
// 任务完成时的逻辑
function completeAgentTask(result: AgentToolResult, setAppState: SetAppState): void {
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => {
    if (task.status !== 'running') return task
    
    return {
      ...task,
      status: 'completed',
      result,
      endTime: Date.now(),
      // 关键: retain 决定是否设置回收时间
      evictAfter: task.retain ? undefined : Date.now() + PANEL_GRACE_MS,
      // 清理运行时引用
      abortController: undefined,
      unregisterCleanup: undefined,
      selectedAgent: undefined,
    }
  })
}

// 用户进入任务视图时
function enterTeammateView(taskId: string, setAppState: SetAppState): void {
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => ({
    ...task,
    retain: true,
    evictAfter: undefined,  // 清除回收时间
  }))
}

// 用户离开任务视图时
function exitTeammateView(taskId: string, setAppState: SetAppState): void {
  updateTaskState<LocalAgentTaskState>(taskId, setAppState, task => {
    if (task.status === 'running') {
      return { ...task, retain: false }  // 运行中不设置回收时间
    }
    return {
      ...task,
      retain: false,
      evictAfter: Date.now() + PANEL_GRACE_MS,  // 重新开始 30 秒倒计时
    }
  })
}
```

---

## 六、输出文件回收

### 6.1 磁盘输出管理

```typescript
// src/utils/task/diskOutput.ts

/**
 * 回收任务输出文件
 * 在任务终止时调用
 */
export async function evictTaskOutput(taskId: string): Promise<void> {
  const outputPath = getTaskOutputPath(taskId)
  try {
    await unlink(outputPath)
  } catch (error) {
    // 文件可能不存在，忽略错误
    if (getErrnoCode(error) !== 'ENOENT') {
      logError(`Failed to evict task output: ${error}`)
    }
  }
}

/**
 * 获取任务输出路径
 */
export function getTaskOutputPath(taskId: string): string {
  return join(getTaskOutputDir(), `${taskId}.txt`)
}

/**
 * 初始化任务输出为符号链接
 * 指向 agent transcript 文件
 */
export async function initTaskOutputAsSymlink(
  taskId: string,
  transcriptPath: string,
): Promise<void> {
  const outputPath = getTaskOutputPath(taskId)
  await ensureDir(dirname(outputPath))
  
  try {
    await symlink(transcriptPath, outputPath)
  } catch (error) {
    if (getErrnoCode(error) !== 'EEXIST') {
      throw error
    }
  }
}
```

---

## 七、内存管理策略

### 7.1 消息上限机制

```typescript
// src/tasks/InProcessTeammateTask/types.ts

/**
 * task.messages (AppState UI 镜像) 中保留的最大消息数
 *
 * task.messages 仅用于缩放 transcript 对话框，只需要最近的上下文
 * 完整对话存储在本地 allMessages 数组 (inProcessRunner) 和磁盘上
 *
 * BQ 分析 (第 9 轮, 2026-03-20) 显示:
 * - 500+ 轮次会话每个 agent 约 20MB RSS
 * - swarm 突发时每个并发 agent 约 125MB
 * - Whale 会话 9a990de8 在 2 分钟内启动 292 个 agent，达到 36.8GB
 * 
 * 主要成本是这个数组持有每条消息的第二份完整副本
 */
export const TEAMMATE_MESSAGES_UI_CAP = 50

/**
 * 追加消息到数组，限制结果在 TEAMMATE_MESSAGES_UI_CAP 条目内
 * 通过丢弃最旧的消息实现
 * 总是返回新数组 (AppState 不可变性)
 */
export function appendCappedMessage<T>(
  prev: readonly T[] | undefined,
  item: T,
): T[] {
  if (prev === undefined || prev.length === 0) {
    return [item]
  }
  if (prev.length >= TEAMMATE_MESSAGES_UI_CAP) {
    // 丢弃最旧的消息，保留最新的 49 条 + 新消息
    const next = prev.slice(-(TEAMMATE_MESSAGES_UI_CAP - 1))
    next.push(item)
    return next
  }
  return [...prev, item]
}
```

### 7.2 内存压力分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Memory Pressure Analysis                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  问题场景 (BQ 分析数据):                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Whale 会话 9a990de8:                                               │   │
│  │  - 2 分钟内启动 292 个 agent                                        │   │
│  │  - 峰值内存: 36.8 GB                                                │   │
│  │  - 每个 agent 平均: ~126 MB                                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  内存组成:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  1. task.messages[] - UI 显示用的消息副本                           │   │
│  │     - 500+ 轮次: ~20 MB/agent                                       │   │
│  │     - 解决方案: TEAMMATE_MESSAGES_UI_CAP = 50                       │   │
│  │                                                                      │   │
│  │  2. allMessages[] - 完整对话历史 (inProcessRunner 本地)             │   │
│  │     - 必须保留用于 API 调用                                         │   │
│  │     - 解决方案: 磁盘持久化 + 按需加载                               │   │
│  │                                                                      │   │
│  │  3. AgentDefinition - Agent 定义对象                                │   │
│  │     - 包含 system prompt、tools 等                                  │   │
│  │     - 解决方案: 终止时清除 selectedAgent                            │   │
│  │                                                                      │   │
│  │  4. AbortController - 运行时控制器                                  │   │
│  │     - 解决方案: 终止时清除                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  回收策略:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  1. 及时回收: 任务终止后 30 秒自动回收                              │   │
│  │  2. 主动回收: evictTerminalTask() 不等待轮询                        │   │
│  │  3. 消息上限: 50 条消息上限防止无限增长                             │   │
│  │  4. 引用清理: 终止时清除 selectedAgent, abortController            │   │
│  │  5. 磁盘清理: evictTaskOutput() 删除输出文件                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 八、回收时序图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Eviction Timeline                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  时间轴 ──────────────────────────────────────────────────────────────→    │
│                                                                             │
│  T0: 任务完成                                                               │
│  │   completeAgentTask()                                                   │
│  │   status: running → completed                                           │
│  │   evictAfter: T0 + 30s (如果 retain=false)                              │
│  │   notified: false                                                       │
│  │                                                                          │
│  T1: 发送通知 (T0 + ~0ms)                                                   │
│  │   enqueueAgentNotification()                                            │
│  │   notified: true                                                        │
│  │   evictTaskOutput() - 删除磁盘输出                                      │
│  │                                                                          │
│  T2: 轮询检查 (T0 + 1s, 2s, ...)                                           │
│  │   pollTasks() → generateTaskAttachments()                               │
│  │   检查: isTerminal && notified && evictAfter <= now                     │
│  │   结果: 加入 evictedTaskIds (如果条件满足)                              │
│  │                                                                          │
│  T3: 宽限期结束 (T0 + 30s)                                                  │
│  │   evictAfter <= Date.now()                                              │
│  │   applyTaskOffsetsAndEvictions()                                        │
│  │   从 AppState.tasks 中删除                                              │
│  │                                                                          │
│  ════════════════════════════════════════════════════════════════════════  │
│                                                                             │
│  特殊情况: 用户在 T0-T3 期间查看任务                                        │
│                                                                             │
│  T0: 任务完成                                                               │
│  │   evictAfter: T0 + 30s                                                  │
│  │                                                                          │
│  T1.5: 用户进入任务视图                                                     │
│  │   enterTeammateView()                                                   │
│  │   retain: true                                                          │
│  │   evictAfter: undefined  ← 清除回收时间                                 │
│  │                                                                          │
│  T3: 原宽限期结束                                                           │
│  │   evictAfter === undefined                                              │
│  │   不回收 ← 用户仍在查看                                                 │
│  │                                                                          │
│  T4: 用户离开任务视图                                                       │
│  │   exitTeammateView()                                                    │
│  │   retain: false                                                         │
│  │   evictAfter: T4 + 30s  ← 重新开始倒计时                                │
│  │                                                                          │
│  T4 + 30s: 新宽限期结束                                                     │
│  │   从 AppState.tasks 中删除                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 九、设计哲学分析

### 9.1 优秀设计

| 设计点 | 实现 | 哲学 |
|--------|------|------|
| **宽限期机制** | 30 秒 PANEL_GRACE_MS | 用户体验优先，允许查看已完成任务 |
| **retain 标志** | UI 持有阻止回收 | 用户意图优先于自动回收 |
| **双重 GC** | 主动 + 懒惰回收 | 及时释放 + 安全网兜底 |
| **TOCTOU 防护** | fresh 状态重新检查 | 防止并发状态转换导致的错误回收 |
| **消息上限** | 50 条 UI 消息上限 | 平衡内存使用和用户体验 |
| **引用清理** | 终止时清除运行时引用 | 及时释放大对象 |

### 9.2 可改进点

| 问题 | 现状 | 建议 |
|------|------|------|
| **固定宽限期** | 30 秒硬编码 | 可配置化，支持用户自定义 |
| **轮询回收** | 依赖 1 秒轮询 | 可使用 setTimeout 精确触发 |
| **消息上限固定** | 50 条固定 | 可根据内存压力动态调整 |
| **无优先级** | 所有任务同等对待 | 可添加优先级，优先回收低优先级任务 |
| **无压缩** | 消息原样存储 | 可添加消息压缩减少内存占用 |

---

## 十、总结

任务回收机制的设计体现了以下核心原则：

1. **用户体验优先**: 30 秒宽限期允许用户查看已完成任务
2. **意图感知**: retain 标志让用户意图优先于自动回收
3. **双重保障**: 主动回收 + 懒惰 GC 确保资源最终被释放
4. **并发安全**: TOCTOU 防护确保状态一致性
5. **内存控制**: 消息上限和引用清理控制内存增长

这套设计在用户体验和资源管理之间取得了良好的平衡。
