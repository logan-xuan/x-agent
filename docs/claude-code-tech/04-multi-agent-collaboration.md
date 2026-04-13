# Claude Code 多 Agent 协作深度分析

## 一、概述

多 Agent 协作是 Claude Code Swarm 系统的核心能力，允许多个 Agent 并行工作、相互通信、共享上下文。本文深入分析 TeamCreateTool、SendMessageTool 和文件邮箱机制的设计与实现。

---

## 二、协作架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Multi-Agent Collaboration Architecture                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         ┌─────────────────────┐                             │
│                         │     Team Lead       │                             │
│                         │   (主进程/协调者)    │                             │
│                         └─────────────────────┘                             │
│                                    │                                        │
│                    ┌───────────────┼───────────────┐                       │
│                    │               │               │                       │
│            TeamCreateTool    SendMessageTool   邮箱轮询                     │
│                    │               │               │                       │
│                    ▼               ▼               ▼                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Team File System                              │   │
│  │  ~/.claude/teams/{team_name}/                                       │   │
│  │  ├── team.json          # 团队配置                                   │   │
│  │  └── inboxes/           # 邮箱目录                                   │   │
│  │      ├── team-lead.json                                             │   │
│  │      ├── researcher.json                                            │   │
│  │      └── test-runner.json                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                    │               │               │                       │
│                    ▼               ▼               ▼                       │
│         ┌─────────────┐   ┌─────────────┐   ┌─────────────┐               │
│         │ In-Process  │   │    tmux     │   │   iTerm2    │               │
│         │  Teammate   │   │  Teammate   │   │  Teammate   │               │
│         └─────────────┘   └─────────────┘   └─────────────┘               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、TeamCreateTool - 团队创建

### 3.1 工具定义

```typescript
// src/tools/TeamCreateTool/TeamCreateTool.ts

const inputSchema = z.strictObject({
  team_name: z.string().describe('Name for the new team to create.'),
  description: z.string().optional().describe('Team description/purpose.'),
  agent_type: z.string().optional().describe(
    'Type/role of the team lead (e.g., "researcher", "test-runner").'
  ),
})

type Output = {
  team_name: string
  team_file_path: string
  lead_agent_id: string
}
```

### 3.2 创建流程

```typescript
async function call(input, context) {
  const { team_name, description, agent_type } = input
  const { setAppState, getAppState } = context
  
  // 1. 检查是否已在团队中 (一个 leader 只能管理一个团队)
  const existingTeam = getAppState().teamContext?.teamName
  if (existingTeam) {
    throw new Error(`Already leading team "${existingTeam}"...`)
  }
  
  // 2. 生成唯一团队名 (如果已存在则生成新名称)
  const finalTeamName = generateUniqueTeamName(team_name)
  
  // 3. 生成 Team Lead 的 Agent ID
  const leadAgentId = formatAgentId(TEAM_LEAD_NAME, finalTeamName)
  // 格式: "team-lead@my-team"
  
  // 4. 创建团队文件
  const teamFile: TeamFile = {
    name: finalTeamName,
    description,
    createdAt: Date.now(),
    leadAgentId,
    leadSessionId: getSessionId(),
    members: [{
      agentId: leadAgentId,
      name: TEAM_LEAD_NAME,
      agentType: agent_type || TEAM_LEAD_NAME,
      model: leadModel,
      joinedAt: Date.now(),
      tmuxPaneId: '',
      cwd: getCwd(),
      subscriptions: [],
    }]
  }
  
  // 5. 写入团队文件
  await writeTeamFileAsync(finalTeamName, teamFile)
  
  // 6. 注册会话清理 (会话结束时删除团队)
  registerTeamForSessionCleanup(finalTeamName)
  
  // 7. 重置任务列表 (Team = Project = TaskList)
  const taskListId = sanitizeName(finalTeamName)
  await resetTaskList(taskListId)
  
  // 8. 更新 AppState
  setAppState(prev => ({
    ...prev,
    teamContext: {
      teamName: finalTeamName,
      teamFilePath,
      leadAgentId,
      teammates: {
        [leadAgentId]: {
          name: TEAM_LEAD_NAME,
          agentType: leadAgentType,
          color: assignTeammateColor(leadAgentId),
          // ...
        },
      },
    },
  }))
  
  return { data: { team_name: finalTeamName, lead_agent_id: leadAgentId } }
}
```

---

## 四、SendMessageTool - 消息传递

### 4.1 消息类型

```typescript
// 支持的消息类型
const StructuredMessage = z.discriminatedUnion('type', [
  // 关闭请求
  z.object({
    type: z.literal('shutdown_request'),
    reason: z.string().optional(),
  }),
  // 关闭响应
  z.object({
    type: z.literal('shutdown_response'),
    request_id: z.string(),
    approve: semanticBoolean(),
    reason: z.string().optional(),
  }),
  // Plan 审批响应
  z.object({
    type: z.literal('plan_approval_response'),
    request_id: z.string(),
    approve: semanticBoolean(),
    feedback: z.string().optional(),
  }),
])

const inputSchema = z.object({
  to: z.string().describe(
    'Recipient: teammate name, "*" for broadcast, or address'
  ),
  summary: z.string().optional().describe(
    'A 5-10 word summary shown as preview in the UI'
  ),
  message: z.union([
    z.string().describe('Plain text message content'),
    StructuredMessage(),
  ]),
})
```

### 4.2 消息路由流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SendMessage Routing Flow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SendMessage({ to, message })                                               │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Address Resolution                                │   │
│  │                                                                      │   │
│  │  parseAddress(to) → { scheme, target }                              │   │
│  │                                                                      │   │
│  │  scheme = 'bridge'  → Remote Control 跨会话                         │   │
│  │  scheme = 'uds'     → Unix Domain Socket 本地                       │   │
│  │  scheme = 'other'   → 团队内 teammate                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         │ scheme = 'other' (团队内)                                        │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    In-Process Agent Check                            │   │
│  │                                                                      │   │
│  │  1. 查询 agentNameRegistry.get(to)                                  │   │
│  │  2. 或尝试 toAgentId(to) 解析                                       │   │
│  │  3. 查找 AppState.tasks[agentId]                                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         ├─────────────────────────────────────────────────────────────┐    │
│         │ 找到 LocalAgentTask                                          │    │
│         ▼                                                              │    │
│  ┌─────────────────────────┐                                          │    │
│  │ task.status = running   │                                          │    │
│  │                         │                                          │    │
│  │ queuePendingMessage()   │                                          │    │
│  │ 入队到 pendingMessages  │                                          │    │
│  └─────────────────────────┘                                          │    │
│         │                                                              │    │
│         │ task.status != running                                       │    │
│         ▼                                                              │    │
│  ┌─────────────────────────┐                                          │    │
│  │ resumeAgentBackground() │                                          │    │
│  │ 自动恢复已停止的 agent  │                                          │    │
│  └─────────────────────────┘                                          │    │
│                                                                        │    │
│         │ 未找到 LocalAgentTask                                        │    │
│         ▼                                                              │    │
│  ┌─────────────────────────────────────────────────────────────────────┘   │
│  │                    Mailbox Fallback                                  │   │
│  │                                                                      │   │
│  │  to = '*'  → handleBroadcast() 广播给所有 teammate                  │   │
│  │  to = name → handleMessage() 写入目标邮箱                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、文件邮箱机制

### 5.1 邮箱结构

```typescript
// src/utils/teammateMailbox.ts

type TeammateMessage = {
  from: string        // 发送者名称
  text: string        // 消息内容
  timestamp: string   // ISO 时间戳
  read: boolean       // 是否已读
  color?: string      // 发送者颜色 (UI 显示)
  summary?: string    // 5-10 字摘要 (UI 预览)
}

// 邮箱路径: ~/.claude/teams/{team_name}/inboxes/{agent_name}.json
function getInboxPath(agentName: string, teamName?: string): string {
  const team = teamName || getTeamName() || 'default'
  const safeTeam = sanitizePathComponent(team)
  const safeAgentName = sanitizePathComponent(agentName)
  const inboxDir = join(getTeamsDir(), safeTeam, 'inboxes')
  return join(inboxDir, `${safeAgentName}.json`)
}
```

### 5.2 邮箱操作 (带文件锁)

```typescript
// 写入邮箱 (带文件锁)
async function writeToMailbox(
  recipientName: string,
  message: Omit<TeammateMessage, 'read'>,
  teamName?: string,
): Promise<void> {
  await ensureInboxDir(teamName)
  const inboxPath = getInboxPath(recipientName, teamName)
  const lockFilePath = `${inboxPath}.lock`

  // 确保邮箱文件存在
  try {
    await writeFile(inboxPath, '[]', { encoding: 'utf-8', flag: 'wx' })
  } catch (error) {
    if (getErrnoCode(error) !== 'EEXIST') throw error
  }

  // 获取文件锁 (带重试)
  let release: (() => Promise<void>) | undefined
  try {
    release = await lockfile.lock(inboxPath, {
      lockfilePath: lockFilePath,
      retries: { retries: 10, minTimeout: 5, maxTimeout: 100 },
    })

    // 读取现有消息
    const messages = await readMailbox(recipientName, teamName)
    
    // 追加新消息
    messages.push({ ...message, read: false })
    
    // 写回文件
    await writeFile(inboxPath, jsonStringify(messages, null, 2), 'utf-8')
  } finally {
    if (release) await release()
  }
}
```

### 5.3 结构化消息类型

```typescript
// 空闲通知 (teammate 完成工作时发送)
type IdleNotificationMessage = {
  type: 'idle_notification'
  from: string
  timestamp: string
  idleReason?: 'available' | 'interrupted' | 'failed'
  summary?: string
  completedTaskId?: string
  completedStatus?: 'resolved' | 'blocked' | 'failed'
  failureReason?: string
}

// 权限请求 (worker 向 leader 请求权限)
type PermissionRequestMessage = {
  type: 'permission_request'
  request_id: string
  agent_id: string
  tool_name: string
  tool_use_id: string
  description: string
  input: Record<string, unknown>
  permission_suggestions: unknown[]
}

// Plan 审批请求
type PlanApprovalRequestMessage = {
  type: 'plan_approval_request'
  from: string
  timestamp: string
  planFilePath: string
  planContent: string
  requestId: string
}

// 关闭请求
type ShutdownRequestMessage = {
  type: 'shutdown_request'
  requestId: string
  from: string
  reason?: string
  timestamp: string
}
```

---

## 六、消息流转时序图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Message Flow Sequence                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Team Lead                    Mailbox                     Teammate          │
│      │                           │                            │             │
│      │  SendMessage(to: "researcher", message: "...")         │             │
│      │ ─────────────────────────────────────────────────────→ │             │
│      │                           │                            │             │
│      │                    writeToMailbox()                    │             │
│      │                    ┌──────┴──────┐                     │             │
│      │                    │ lock file   │                     │             │
│      │                    │ read JSON   │                     │             │
│      │                    │ append msg  │                     │             │
│      │                    │ write JSON  │                     │             │
│      │                    │ unlock      │                     │             │
│      │                    └──────┬──────┘                     │             │
│      │                           │                            │             │
│      │                           │     useInboxPoller()       │             │
│      │                           │ ←──────────────────────────│             │
│      │                           │     readUnreadMessages()   │             │
│      │                           │                            │             │
│      │                           │     markMessagesAsRead()   │             │
│      │                           │ ←──────────────────────────│             │
│      │                           │                            │             │
│      │                           │     消息作为 attachment    │             │
│      │                           │     注入到 agent context   │             │
│      │                           │ ─────────────────────────→ │             │
│      │                           │                            │             │
│      │                           │                            │ 处理消息    │
│      │                           │                            │ ...         │
│      │                           │                            │             │
│      │                           │     SendMessage(to: "team-lead", ...)    │
│      │                           │ ←──────────────────────────│             │
│      │                           │                            │             │
│      │     useInboxPoller()      │                            │             │
│      │ ←─────────────────────────│                            │             │
│      │                           │                            │             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 七、协作模式

### 7.1 Leader-Worker 模式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Leader-Worker Pattern                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         ┌─────────────────────┐                             │
│                         │     Team Lead       │                             │
│                         │   (协调/分配任务)    │                             │
│                         └─────────────────────┘                             │
│                                    │                                        │
│              ┌─────────────────────┼─────────────────────┐                 │
│              │                     │                     │                 │
│              ▼                     ▼                     ▼                 │
│       ┌───────────┐         ┌───────────┐         ┌───────────┐           │
│       │ Worker 1  │         │ Worker 2  │         │ Worker 3  │           │
│       │ researcher│         │test-runner│         │code-review│           │
│       └───────────┘         └───────────┘         └───────────┘           │
│              │                     │                     │                 │
│              │                     │                     │                 │
│              └─────────────────────┼─────────────────────┘                 │
│                                    │                                        │
│                         idle_notification                                   │
│                                    │                                        │
│                                    ▼                                        │
│                         ┌─────────────────────┐                             │
│                         │     Team Lead       │                             │
│                         │   (汇总/决策)        │                             │
│                         └─────────────────────┘                             │
│                                                                             │
│  特点:                                                                      │
│  - Leader 分配任务，Worker 执行                                             │
│  - Worker 完成后发送 idle_notification                                      │
│  - Leader 汇总结果，做出决策                                                │
│  - 适合: 并行任务、分治问题                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Plan 审批模式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Plan Approval Pattern                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Teammate (planModeRequired=true)              Team Lead                    │
│      │                                              │                       │
│      │  1. 进入 Plan 模式                           │                       │
│      │     创建 plan.md                             │                       │
│      │                                              │                       │
│      │  2. plan_approval_request                    │                       │
│      │ ────────────────────────────────────────────→│                       │
│      │     { planFilePath, planContent, requestId } │                       │
│      │                                              │                       │
│      │                                              │ 3. 审核 plan          │
│      │                                              │                       │
│      │  4a. plan_approval_response (approved=true)  │                       │
│      │ ←────────────────────────────────────────────│                       │
│      │     { permissionMode: 'default' }            │                       │
│      │                                              │                       │
│      │  5. 退出 Plan 模式                           │                       │
│      │     执行 plan                                │                       │
│      │                                              │                       │
│  ════════════════════════════════════════════════════════════════════════  │
│                                                                             │
│      │  4b. plan_approval_response (approved=false) │                       │
│      │ ←────────────────────────────────────────────│                       │
│      │     { feedback: "需要修改..." }              │                       │
│      │                                              │                       │
│      │  5. 修改 plan                                │                       │
│      │     重新提交审批                             │                       │
│      │                                              │                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 八、设计哲学分析

### 8.1 优秀设计

| 设计点 | 实现 | 哲学 |
|--------|------|------|
| **文件邮箱** | JSON 文件 + 文件锁 | 简单可靠，跨进程兼容 |
| **消息路由** | 多层解析 (registry → agentId → mailbox) | 灵活支持多种寻址方式 |
| **结构化消息** | discriminatedUnion 类型 | 类型安全，协议清晰 |
| **自动恢复** | 发送消息时自动 resume 已停止的 agent | 用户体验优先 |
| **广播支持** | to: "*" 广播给所有 teammate | 简化多播场景 |
| **文件锁** | proper-lockfile 带重试 | 并发安全 |

### 8.2 可改进点

| 问题 | 现状 | 建议 |
|------|------|------|
| **轮询开销** | 定期轮询邮箱文件 | 可使用 inotify/FSEvents 监听 |
| **消息持久化** | 仅文件存储 | 可添加 SQLite 支持更复杂查询 |
| **消息顺序** | 依赖时间戳 | 可添加序列号保证顺序 |
| **消息确认** | 无确认机制 | 可添加 ACK 机制 |
| **消息过期** | 无过期机制 | 可添加 TTL 自动清理 |

---

## 九、总结

多 Agent 协作的设计体现了以下核心原则：

1. **简单可靠**: 文件邮箱机制简单易懂，跨进程兼容
2. **类型安全**: 结构化消息使用 Zod 验证，协议清晰
3. **灵活路由**: 多层消息路由支持多种寻址方式
4. **用户友好**: 自动恢复、广播等特性提升体验
5. **并发安全**: 文件锁确保多 agent 并发写入安全

这套设计为 Claude Code 的 Swarm 系统提供了可靠的通信基础。
