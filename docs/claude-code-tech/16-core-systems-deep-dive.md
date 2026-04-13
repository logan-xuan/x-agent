# Claude Code 核心技术深度补充分析 (01-11)

> 本文档是对 tech/ 目录下 01-11 号技术文档的深度补充，重点说明技术挑战点、设计亮点和可改进之处。

---

## 目录

- [1. 任务状态机 (01)](#1-任务状态机-01)
- [2. 父子关系管理 (02)](#2-父子关系管理-02)
- [3. 任务回收机制 (03)](#3-任务回收机制-03)
- [4. 多Agent协作 (04)](#4-多agent协作-04)
- [5. 进程内Teammate (05)](#5-进程内teammate-05)
- [6. Plan模式审批 (06)](#6-plan模式审批-06)
- [7. Shutdown协议 (07)](#7-shutdown协议-07)
- [8. 上下文共享 (08)](#8-上下文共享-08)
- [9. 架构总览 (09)](#9-架构总览-09)
- [10. Compact压缩机制 (10)](#10-compact压缩机制-10)
- [11. 工具结果预算 (11)](#11-工具结果预算-11)

---

## 1. 任务状态机 (01)

### 1.1 技术挑战点

#### 挑战 1: 并发状态转换的 TOCTOU 竞态

**问题场景**:
```
T0: generateTaskAttachments 开始读取 task.outputOffset (异步磁盘 I/O)
T1: 用户按 ESC，killAsyncAgent 将 status 改为 'killed'
T2: generateTaskAttachments 完成，尝试应用 outputOffset 更新
    → 如果直接覆盖，会复活已 killed 的任务！
```

**源码级解决方案**:
```typescript
// src/utils/task/framework.ts:226-230
for (const id of offsetIds) {
  const fresh = newTasks[id]
  // Re-check status on fresh state — task may have completed during the await
  if (fresh?.status === 'running') {
    newTasks[id] = { ...fresh, outputOffset: updatedTaskOffsets[id]! }
    changed = true
  }
}
```

**技术亮点**:
- ✅ **乐观锁模式**: 不在 await 前快照，而是对 fresh state 重新验证
- ✅ **避免僵尸化**: 防止已完成的任务被过时更新"复活"
- ✅ **类似数据库的 CAS** (Compare-And-Swap) 语义

#### 挑战 2: 不可变更新与 React 重渲染优化

**问题**: React 的 `setAppState` 每次触发重渲染，即使数据未变。

**解决方案**:
```typescript
// src/utils/task/framework.ts:58-63
const updated = updater(task)
if (updated === task) {
  // Same reference — skip spread to avoid unnecessary re-render
  return prev
}
```

**性能影响**:
- 幂等操作零开销（如重复调用 `completeAgentTask`）
- 避免 React Fiber 树的 diff 计算
- 减少组件树 re-render 传播

#### 挑战 3: 运行时引用与可序列化状态的分离

**问题**: `abortController`、`unregisterCleanup`、`selectedAgent` 不能被序列化。

**解决方案**:
```typescript
// 终止时清除运行时引用
return {
  ...task,
  status: 'completed',
  abortController: undefined,        // 运行时对象
  unregisterCleanup: undefined,      // 运行时回调
  selectedAgent: undefined,          // 释放大对象 (可达数 MB)
}
```

### 1.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **Fresh State Re-Check** | 异步操作后重新验证状态 | 防止 TOCTOU 竞态 |
| **引用相等优化** | `if (updated === task) return prev` | 零开销幂等操作 |
| **宽限期回收** | `PANEL_GRACE_MS = 30_000` | 用户体验与内存平衡 |
| **类型窄化** | `'retain' in task` | TypeScript 编译期安全 |
| **运行时清理** | 终止时清除引用 | 及时释放内存 |

### 1.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **固定宽限期** | 所有任务 30 秒 | 基于任务类型动态调整 | P2 |
| **轮询回收** | 1 秒轮询检查 | `setTimeout` 精确触发 | P3 |
| **状态类型分散** | 每种任务单独定义 | 泛型基类 + 组合模式 | P2 |
| **缺少可观测性** | 无状态转换日志 | 添加转换事件追踪 | P1 |

---

## 2. 父子关系管理 (02)

### 2.1 技术挑战点

#### 挑战 1: AbortController 链的内存安全

**问题**: 父级持有子级引用会导致子级无法 GC（即使子级已废弃）。

**源码级解决方案**:
```typescript
// src/utils/abortController.ts:30-35
function propagateAbort(
  this: WeakRef<AbortController>,
  weakChild: WeakRef<AbortController>,
): void {
  const parent = this.deref()
  weakChild.deref()?.abort(parent?.signal.reason)
}
```

**关键技术**:
- ✅ **双向 WeakRef**: 父级和子级都使用弱引用
- ✅ **模块级函数**: 避免每次调用的闭包分配
- ✅ **自动清理**: 子级 abort 时移除父级监听器

#### 挑战 2: 快速路径优化

**问题**: 如果父级已 abort，设置监听器是无意义的。

**解决方案**:
```typescript
// src/utils/abortController.ts:105-108
if (parent.signal.aborted) {
  child.abort(parent.signal.reason)
  return child  // 快速路径：跳过监听器设置
}
```

### 2.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **双向 WeakRef** | 父级和子级都弱引用 | 完全避免内存泄漏 |
| **模块级函数** | `propagateAbort` 非闭包 | 减少 GC 压力 |
| **快速路径** | 父级已 abort 直接返回 | 减少不必要的监听器 |
| **单向传播** | 子级 abort 不影响父级 | 故障域隔离 |

### 2.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **无层级深度限制** | 可无限嵌套 | 添加最大深度检查 (如 10) | P2 |
| **abort 原因简单** | 仅传递 reason 对象 | 增强结构化上下文信息 | P3 |
| **缺少调试支持** | 无 abort 链路日志 | 添加 abort 追踪 | P2 |

---

## 3. 任务回收机制 (03)

### 3.1 技术挑战点

#### 挑战 1: 双重 GC 策略的协调

**问题**: 主动回收 (`evictTerminalTask`) 和懒惰 GC (`generateTaskAttachments`) 如何协调？

**解决方案**:
```typescript
// 主动回收: 不等待轮询
export function evictTerminalTask(taskId: string, setAppState: SetAppState): void {
  setAppState(prev => {
    const task = prev.tasks?.[taskId]
    if (!task) return prev
    if (!isTerminalTaskStatus(task.status)) return prev
    if (!task.notified) return prev  // 必须已发送通知
    if ('retain' in task && (task.evictAfter ?? Infinity) > Date.now()) {
      return prev  // 宽限期未到
    }
    const { [taskId]: _, ...remainingTasks } = prev.tasks
    return { ...prev, tasks: remainingTasks }
  })
}
```

**设计哲学**:
- 主动回收: 用于确定不再需要的任务（如用户关闭面板）
- 懒惰 GC: 作为安全网，确保最终回收

#### 挑战 2: retain 与 evictAfter 的交互

**问题**: 用户查看任务时如何阻止回收？

**解决方案**:
```typescript
// 用户进入任务视图
function enterTeammateView(taskId: string, setAppState: SetAppState): void {
  updateTaskState(taskId, setAppState, task => ({
    ...task,
    retain: true,
    evictAfter: undefined,  // 清除回收时间
  }))
}

// 用户离开任务视图
function exitTeammateView(taskId: string, setAppState: SetAppState): void {
  updateTaskState(taskId, setAppState, task => {
    if (task.status === 'running') {
      return { ...task, retain: false }
    }
    return {
      ...task,
      retain: false,
      evictAfter: Date.now() + PANEL_GRACE_MS,  // 重新开始 30 秒倒计时
    }
  })
}
```

### 3.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **双重 GC** | 主动 + 懒惰回收 | 及时释放 + 安全网兜底 |
| **retain 机制** | UI 持有阻止回收 | 用户意图优先 |
| **TOCTOU 防护** | fresh state 重新检查 | 并发安全 |
| **消息上限** | `TEAMMATE_MESSAGES_UI_CAP = 50` | 防止内存膨胀 |

### 3.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **固定消息上限** | 50 条硬编码 | 基于内存压力动态调整 | P2 |
| **无优先级回收** | 所有任务同等对待 | 优先回收低优先级任务 | P3 |
| **无消息压缩** | 消息原样存储 | 添加压缩减少内存 | P3 |

---

## 4. 多Agent协作 (04)

### 4.1 技术挑战点

#### 挑战 1: 文件邮箱的并发安全

**问题**: 多个 Agent 同时写入同一邮箱文件可能导致数据损坏。

**解决方案**:
```typescript
// src/utils/teammateMailbox.ts
async function writeToMailbox(recipientName: string, message: TeammateMessage): Promise<void> {
  const lockFilePath = `${inboxPath}.lock`
  
  // 获取文件锁 (带重试)
  let release: (() => Promise<void>) | undefined
  try {
    release = await lockfile.lock(inboxPath, {
      lockfilePath: lockFilePath,
      retries: { retries: 10, minTimeout: 5, maxTimeout: 100 },
    })
    
    const messages = await readMailbox(recipientName)
    messages.push({ ...message, read: false })
    await writeFile(inboxPath, jsonStringify(messages, null, 2), 'utf-8')
  } finally {
    if (release) await release()
  }
}
```

**技术亮点**:
- ✅ **proper-lockfile**: 支持重试和超时
- ✅ **finally 块**: 确保锁一定被释放
- ✅ **原子写入**: `writeFile` 一次性写入

#### 挑战 2: 消息路由的多层解析

**问题**: 支持多种寻址方式（名称、agentId、广播、跨会话）。

**解决方案**:
```typescript
// 路由优先级
1. agentNameRegistry.get(to)        // O(1) 查找
2. toAgentId(to)                    // 解析 agentId 格式
3. parseAddress(to)                 // bridge/uds/other 协议
4. mailbox fallback                 // 文件邮箱兜底
```

### 4.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **文件锁** | proper-lockfile + 重试 | 并发安全 |
| **多层路由** | registry → agentId → mailbox | 灵活支持多种场景 |
| **自动恢复** | 发送消息时自动 resume | 用户体验优先 |
| **广播支持** | `to: "*"` 广播 | 简化多播 |

### 4.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **轮询开销** | 定期轮询邮箱文件 | inotify/FSEvents 监听 | P2 |
| **无消息顺序** | 依赖时间戳 | 添加序列号保证顺序 | P2 |
| **无 ACK 机制** | 无确认 | 添加消息确认 | P1 |
| **无消息过期** | 永久保留 | 添加 TTL 自动清理 | P2 |

---

## 5. 进程内Teammate (05)

### 5.1 技术挑战点

#### 挑战 1: AsyncLocalStorage 上下文隔离

**问题**: 多个 teammate 共享同一进程，如何隔离上下文？

**解决方案**:
```typescript
// src/utils/teammateContext.ts
const teammateContextStorage = new AsyncLocalStorage<TeammateContext>()

export function runWithTeammateContext<T>(
  context: TeammateContext,
  fn: () => T,
): T {
  return teammateContextStorage.run(context, fn)
}
```

**工作原理**:
- AsyncLocalStorage 基于 AsyncHook 实现
- 每个异步调用链有独立的存储
- 类似线程局部存储 (TLS)

#### 挑战 2: 独立 AbortController 设计

**问题**: 为什么 teammate 不链接到 leader 的 AbortController？

**源码注释**:
```typescript
// Teammate 使用独立的 AbortController
// 不链接到 leader，因为 teammate 应该在 leader 查询中断时继续运行
const abortController = createAbortController()
```

**设计哲学**: Teammate 是长期运行的协作单元，不应因 leader 的临时查询中断而终止。

### 5.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **AsyncLocalStorage** | 上下文隔离 | 干净的并发模型 |
| **独立 controller** | 不链接到 leader |  teammate 生命周期独立 |
| **轻量级** | 无需启动新进程 | 毫秒级创建 |
| **低开销** | 共享内存空间 | 资源效率高 |

### 5.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **故障隔离弱** | 共享进程 | Worker Threads 隔离 | P3 |
| **无法多核** | 单线程 | 考虑 Worker Threads | P3 |
| **内存共享风险** | 需小心避免意外共享 | 添加内存审计工具 | P2 |

---

## 6. Plan模式审批 (06)

### 6.1 技术挑战点

#### 挑战 1: 权限模式继承

**问题**: Leader 批准后，teammate 应该获得什么权限？

**解决方案**:
```
Leader 是 'plan' 模式 → Teammate 获得 'default' 模式 (提升权限)
Leader 是 'auto' 模式 → Teammate 继承 'auto' 模式
Leader 是 'acceptEdits' → Teammate 继承 'acceptEdits'
```

**优先级规则**:
1. `bypassPermissions`: 始终优先
2. `acceptEdits`: 始终优先
3. `auto`: 始终优先
4. 其他: 使用 Agent 定义的模式

### 6.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **安全性** | 防止未经审批执行危险操作 | 安全优先 |
| **可追溯** | 计划文件提供审计记录 | 合规性 |
| **灵活性** | Leader 可提供反馈要求修改 | 迭代改进 |
| **权限继承** | 批准时自动提升权限 | 执行计划有足够权限 |

### 6.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **无超时机制** | 可能无限等待审批 | 添加超时 (如 5 分钟) | P1 |
| **无部分批准** | 只能全部批准或拒绝 | 支持逐条审批 | P2 |
| **无计划版本控制** | 修改后无历史 | 添加版本历史 | P2 |
| **单一审批者** | 只有 Team Lead | 支持多审批者 | P3 |

---

## 7. Shutdown协议 (07)

### 7.1 技术挑战点

#### 挑战 1: 协商式关闭

**问题**: Teammate 可能正在执行关键操作，立即关闭会导致数据损坏。

**解决方案**:
```typescript
// Leader 发送关闭请求
{
  type: 'shutdown_request',
  requestId: string,
  from: string,
  reason?: string,
  timestamp: string
}

// Teammate 可以拒绝
{
  type: 'shutdown_rejected',
  requestId: string,
  from: string,
  reason: string,  // 拒绝原因
  timestamp: string
}
```

### 7.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **协商式关闭** | Teammate 可以拒绝 | 避免数据损坏 |
| **可追溯** | requestId 关联请求和响应 | 审计友好 |
| **后端感知** | 响应包含 backendType | Leader 知道如何处理 |
| **优雅退出** | 给 teammate 清理机会 | 资源安全释放 |

### 7.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **无强制关闭** | 不响应无法关闭 | 添加强制关闭 (超时后) | P1 |
| **无超时机制** | Leader 可能无限等待 | 添加超时 (如 30 秒) | P1 |
| **无批量关闭** | 逐个发送请求 | 支持批量关闭 | P2 |

---

## 8. 上下文共享 (08)

### 8.1 技术挑战点

#### 挑战 1: 工具集继承的灵活性

**问题**: 子 Agent 应该继承哪些工具？

**解决方案**:
```typescript
// 工具继承规则
tools: ['*']                     // 继承所有工具
tools: ['Read', 'Write']         // 只继承指定工具
useExactTools: true              // 使用父 Agent 的精确工具集 (用于 fork)
```

#### 挑战 2: 权限继承的优先级

**问题**: 多层权限如何继承？

**优先级规则**:
1. `bypassPermissions`: 始终优先
2. `acceptEdits`: 始终优先
3. `auto (TRANSCRIPT_CLASSIFIER)`: 始终优先
4. 其他: 使用 Agent 定义的模式

### 8.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **灵活继承** | 选择性继承上下文 | 适应不同场景 |
| **权限隔离** | 子 Agent 不自动获得父级所有权限 | 安全优先 |
| **缓存共享** | 避免重复文件读取 | 性能优化 |
| **工具控制** | 精确控制子 Agent 可用工具 | 最小权限原则 |

### 8.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **上下文大小** | 大量历史消息浪费 token | 添加智能过滤 | P1 |
| **缓存一致性** | 父级修改文件后子级缓存过期 | 添加失效通知 | P2 |
| **权限复杂性** | 多层继承规则难理解 | 添加可视化工具 | P2 |

---

## 9. 架构总览 (09)

### 9.1 技术挑战点

本文档是架构总览图，详见 01-08 和 10-11 的深度分析。

### 9.2 核心架构决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 任务管理 | AppState 集中式 | 单一数据源，易于追踪 |
| 通信机制 | 文件邮箱 + 直接调用 | 跨进程兼容 + 高性能 |
| 上下文隔离 | AsyncLocalStorage | 干净的并发模型 |
| 状态更新 | 不可变模式 | React 最佳实践 |
| 内存管理 | 回收机制 + 消息上限 | 防止内存泄漏 |

---

## 10. Compact压缩机制 (10)

### 10.1 技术挑战点

#### 挑战 1: 分层压缩策略的协调

**问题**: 5 层压缩 (Micro → Auto → Reactive → Manual) 如何协调？

**解决方案**:
```
Layer 0: API Context Management (服务端清理)
  ↓
Layer 1: MicroCompact (每次 API 调用前轻量清理)
  ↓
Layer 2: AutoCompact (token 超阈值触发全量摘要)
  ↓
Layer 3: ReactiveCompact (API 413 错误时的最后防线)
  ↓
Layer 4: Manual Compact (/compact 命令)
```

#### 挑战 2: Prompt Cache 稳定性

**问题**: 压缩后如何保持 prompt cache 命中？

**解决方案**:
```typescript
// ContentReplacementState: 一旦 seen 命运冻结
type ContentReplacementState = {
  seenIds: Set<string>              // 已处理过的 tool_use_id
  replacements: Map<string, string> // 被替换的 ID → 预览字符串
}
```

**关键设计**:
- 已替换的永远替换（重放缓存的预览）
- 未替换的永远不替换（保护 cache）
- 保证跨轮次的 prompt 前缀字节相同

#### 挑战 3: Session Memory 零 LLM 调用

**问题**: 如何避免 LLM 摘要的 API 调用？

**解决方案**:
```typescript
// 当 session memory 已提取时，直接用其内容替代 LLM 摘要
trySessionMemoryCompaction(messages, agentId, threshold)
  ├── 等待进行中的 session memory 提取完成
  ├── 读取已提取的 session memory 内容
  ├── 计算保留消息范围
  └── 成功 → 返回 CompactionResult (无 LLM 调用!)
```

### 10.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **分层递进** | Micro → Auto → Reactive | 从轻量到重量级逐层兜底 |
| **缓存感知** | 与 prompt cache 深度集成 | 减少 API 费用 |
| **熔断保护** | 连续失败 3 次后停止重试 | 避免无效调用 |
| **Fork Path** | 复用主对话的 prompt cache | 压缩 API 费用降低 98% |
| **Session Memory** | 零 LLM 调用压缩 | 节省完整 API 调用 |
| **<analysis> 草稿区** | 先组织思路再输出摘要 | 提升摘要质量 |
| **PTL 自救** | 压缩请求本身超限时丢弃最旧内容 | 避免死锁 |

### 10.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **摘要质量不可控** | LLM 自主决定摘要内容 | 添加质量评估 | P2 |
| **无增量压缩** | 总是全量摘要 | 支持增量摘要 | P2 |
| **缓存命中率低** | Fork Path 98% cache miss | 优化缓存策略 | P1 |
| **无压缩预览** | 用户看不到压缩后效果 | 添加压缩预览 | P3 |

---

## 11. 工具结果预算 (11)

### 11.1 技术挑战点

#### 挑战 1: 三层预算的协调

**问题**: 工具级、结果级、消息级预算如何协调？

**解决方案**:
```
Layer 1: 工具内部截断
  ├── BashTool: stdout 截断到 30K chars
  ├── FileReadTool: 内容截断到 25K tokens
  └── WebFetchTool: Haiku 摘要 + MAX_MARKDOWN_LENGTH
  ↓
Layer 2: 结果级持久化
  ├── 单结果 > 50K chars → 写入磁盘 + 2KB 预览
  └── FileReadTool: Infinity (不走持久化，避免循环)
  ↓
Layer 3: 消息级聚合预算
  ├── 单消息所有 tool_result 总和 > 200K → 最大的写入磁盘
  └── 跨轮次状态追踪保证 prompt cache 稳定
```

#### 挑战 2: FileReadTool 的特殊处理

**问题**: 为什么 FileReadTool 的 `maxResultSizeChars = Infinity`？

**原因**: 将 FileRead 的输出持久化到文件，然后模型再用 FileRead 读取该文件，会形成循环。

**解决方案**: FileReadTool 通过自己的 token 级截断（25K tokens）自行保证输出大小。

#### 挑战 3: Prompt Cache 稳定性保证

**问题**: 跨轮次替换如何保证 prompt cache 不失效？

**解决方案**:
```typescript
// Turn 1: 模型调用 Grep(A), Grep(B), Grep(C)
// C(90K) → 预览(2K)
// state.seenIds = {A, B, C}
// state.replacements = {C → preview}

// Turn 2: 模型继续对话
// A: frozen (80K, 不替换 — 模型已见过完整内容)
// B: frozen (60K, 不替换)
// C: mustReapply → 重放缓存的 preview (字节相同!)
// → prompt cache 前缀完全一致 ✓
```

### 11.2 设计亮点

| 亮点 | 实现 | 价值 |
|------|------|------|
| **三层递进防线** | 工具内 → 单结果 → 消息级 | 任一层失效不崩溃 |
| **Prompt Cache 稳定** | 一旦 seen 命运冻结 | 最大化 cache 命中 |
| **FileRead 特殊处理** | Infinity 跳过持久化 | 避免循环 |
| **WebSearch 服务端限制** | max_uses: 8 | 客户端无法绕过 |
| **WebFetch 智能摘要** | Haiku 语义摘要 | 保留信息密度 |
| **空结果注入** | 防止触发停止序列 | 模型兼容性好 |
| **并发与预算协同** | 并发合并到同一消息 | 防止总量爆炸 |

### 11.3 可改进之处

| 问题 | 现状 | 建议 | 优先级 |
|------|------|------|--------|
| **无动态预算** | 固定 200K | 基于上下文窗口动态调整 | P2 |
| **无优先级替换** | 按大小替换 | 优先替换低优先级工具 | P2 |
| **缺少可观测性** | 无预算使用监控 | 添加预算使用面板 | P1 |
| **替换策略粗糙** | 只按大小 | 考虑内容相关性 | P3 |

---

## 总结: 核心设计哲学

### 1. 分层递进 (Layered Defense)

- 任务回收: 主动 + 懒惰 GC
- Compact: Micro → Auto → Reactive → Manual
- 工具预算: 工具内 → 结果级 → 消息级

**价值**: 任一层失效不会导致系统崩溃

### 2. 用户体验优先 (UX First)

- 30 秒宽限期允许查看已完成任务
- retain 机制让用户意图优先于自动回收
- 自动恢复已停止的 agent

### 3. 内存安全 (Memory Safety)

- WeakRef 防止循环引用
- 消息上限防止无限增长
- 运行时引用及时清除

### 4. 并发安全 (Concurrency Safety)

- Fresh State Re-Check 防止 TOCTOU 竞态
- 文件锁确保并发写入安全
- 不可变更新避免副作用

### 5. 类型安全 (Type Safety)

- TypeScript 联合类型保证编译期安全
- 类型守卫实现运行时窄化
- 泛型约束减少重复代码

### 6. 可配置性 (Configurability)

- GrowthBook 远程配置支持动态调整
- 环境变量覆盖关键参数
- 用户设置自定义行为

---

## 附录: 关键文件索引

| 文档 | 核心文件 |
|------|---------|
| 01-任务状态机 | `src/utils/task/framework.ts`, `src/Task.ts` |
| 02-父子关系 | `src/utils/abortController.ts` |
| 03-任务回收 | `src/utils/task/framework.ts`, `src/utils/task/diskOutput.ts` |
| 04-多Agent协作 | `src/tools/TeamCreateTool/`, `src/tools/SendMessageTool/` |
| 05-进程内Teammate | `src/tasks/InProcessTeammateTask/`, `src/utils/teammateContext.ts` |
| 06-Plan模式 | `src/tools/SendMessageTool/`, `src/utils/permissions/` |
| 07-Shutdown协议 | `src/utils/teammateMailbox.ts`, `src/tasks/` |
| 08-上下文共享 | `src/QueryEngine.ts`, `src/tools/AgentTool/` |
| 09-架构总览 | 综合 01-08 |
| 10-Compact机制 | `src/services/compact/` (整个目录) |
| 11-工具预算 | `src/utils/toolResultStorage.ts`, `src/constants/toolLimits.ts` |

---

## 版本信息

- 创建时间: 2026-04-09
- 基于源码版本: Claude Code 最新
- 文档版本: 1.0
- 作者: AI 深度分析
