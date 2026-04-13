# Claude Code Compact 压缩机制深度分析

## 一、概述

Compact（上下文压缩）是 Claude Code 的核心上下文管理系统，负责在对话 token 接近模型上下文窗口极限时，通过多层策略压缩历史消息，确保会话可以持续进行。系统采用分层架构：MicroCompact（微压缩）在每次 API 调用前轻量清理工具结果；AutoCompact（自动压缩）在 token 超过阈值时触发全量摘要；ReactiveCompact（响应式压缩）作为 API 返回 prompt-too-long 错误时的最后防线。

### 核心设计哲学

1. **分层递进**: MicroCompact → AutoCompact → ReactiveCompact，从轻量到重量级逐层兜底
2. **缓存感知**: 压缩策略与 Anthropic API 的 prompt cache 机制深度集成，尽量保留缓存命中
3. **熔断保护**: 连续失败自动熔断，避免无效重试浪费 API 调用
4. **上下文恢复**: 压缩后自动恢复关键文件、技能、计划等上下文附件

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Query Main Loop (query.ts)                          │
│                                                                             │
│  User Message → [Snip] → [MicroCompact] → [AutoCompact] → API Call         │
│                                                      ↓                      │
│                                              prompt_too_long?               │
│                                              ↓ Yes        ↓ No             │
│                                     [ReactiveCompact]   Stream Response     │
│                                              ↓                              │
│                                     Retry API Call                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 压缩层级关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Layer 0: API Context Management (apiMicrocompact.ts)                       │
│  ├── clear_tool_uses_20250919 策略 (服务端清理工具结果)                       │
│  └── clear_thinking_20251015 策略 (服务端清理 thinking blocks)               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 1: MicroCompact (microCompact.ts)                                    │
│  ├── Time-Based MC: 空闲超时后清理旧工具结果 (缓存已过期)                     │
│  └── Cached MC: 通过 cache_edits API 删除工具结果 (保留缓存)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 2: AutoCompact (autoCompact.ts)                                      │
│  ├── Session Memory Compact: 用已提取的会话记忆替代 LLM 摘要                  │
│  └── Legacy Compact: 调用 LLM 生成对话摘要 (compact.ts)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 3: ReactiveCompact (reactiveCompact.ts)                              │
│  └── API 返回 413/prompt_too_long 后的紧急压缩                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Layer 4: Manual Compact (/compact 命令)                                    │
│  ├── Full Compact: 全量压缩                                                 │
│  └── Partial Compact: 基于消息选择器的局部压缩                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心数据结构

### 3.1 CompactionResult — 压缩结果

```typescript
// src/services/compact/compact.ts
interface CompactionResult {
  boundaryMarker: SystemMessage        // 压缩边界标记 (分隔压缩前后)
  summaryMessages: UserMessage[]       // LLM 生成的摘要消息
  attachments: AttachmentMessage[]     // 恢复的上下文附件 (文件/技能/计划)
  hookResults: HookResultMessage[]     // SessionStart hooks 结果
  messagesToKeep?: Message[]           // 保留的原始消息 (Session Memory / Partial)
  userDisplayMessage?: string          // 展示给用户的提示信息
  preCompactTokenCount?: number        // 压缩前 token 数
  postCompactTokenCount?: number       // 压缩 API 调用的 token 用量
  truePostCompactTokenCount?: number   // 压缩后实际上下文 token 数
  compactionUsage?: TokenUsage         // 压缩 API 调用的详细用量
}
```

### 3.2 AutoCompactTrackingState — 自动压缩追踪

```typescript
// src/services/compact/autoCompact.ts
type AutoCompactTrackingState = {
  compacted: boolean              // 本轮是否已压缩
  turnCounter: number             // 距上次压缩的轮次数
  turnId: string                  // 当前轮次唯一 ID
  consecutiveFailures?: number    // 连续失败次数 (熔断器)
}
```

### 3.3 RecompactionInfo — 重压缩诊断上下文

```typescript
// src/services/compact/compact.ts
type RecompactionInfo = {
  isRecompactionInChain: boolean       // 是否同一链路内的重复压缩
  turnsSincePreviousCompact: number    // 距上次压缩的轮次
  previousCompactTurnId?: string       // 上次压缩的轮次 ID
  autoCompactThreshold: number         // 自动压缩阈值
  querySource?: QuerySource            // 查询来源
}
```

### 3.4 MicrocompactResult — 微压缩结果

```typescript
// src/services/compact/microCompact.ts
type MicrocompactResult = {
  messages: Message[]                  // 处理后的消息数组
  compactionInfo?: {
    pendingCacheEdits?: {
      trigger: 'auto'
      deletedToolIds: string[]         // 被删除的工具调用 ID
      baselineCacheDeletedTokens: number // 基线累计删除 token 数
    }
  }
}
```

### 3.5 SessionMemoryCompactConfig — 会话记忆压缩配置

```typescript
// src/services/compact/sessionMemoryCompact.ts
type SessionMemoryCompactConfig = {
  minTokens: number              // 压缩后最少保留 token (默认 10,000)
  minTextBlockMessages: number   // 最少保留的文本消息数 (默认 5)
  maxTokens: number              // 压缩后最多保留 token (默认 40,000)
}
```

### 3.6 TimeBasedMCConfig — 基于时间的微压缩配置

```typescript
// src/services/compact/timeBasedMCConfig.ts
type TimeBasedMCConfig = {
  enabled: boolean               // 是否启用
  gapThresholdMinutes: number    // 触发阈值 (默认 60 分钟)
  keepRecent: number             // 保留最近 N 个工具结果 (默认 5)
}
```

### 3.7 ContextEditStrategy — API 层上下文编辑策略

```typescript
// src/services/compact/apiMicrocompact.ts
type ContextEditStrategy =
  | {
      type: 'clear_tool_uses_20250919'
      trigger?: { type: 'input_tokens'; value: number }
      keep?: { type: 'tool_uses'; value: number }
      clear_tool_inputs?: boolean | string[]
      exclude_tools?: string[]
      clear_at_least?: { type: 'input_tokens'; value: number }
    }
  | {
      type: 'clear_thinking_20251015'
      keep: { type: 'thinking_turns'; value: number } | 'all'
    }
```

---

## 四、关键常量与阈值

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  阈值体系                                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Context Window (模型上下文窗口, 如 200K)                                    │
│  ├── - MAX_OUTPUT_TOKENS_FOR_SUMMARY (20,000)                               │
│  │   = Effective Context Window                                             │
│  │                                                                          │
│  │   Effective Context Window                                               │
│  │   ├── - AUTOCOMPACT_BUFFER_TOKENS (13,000)                               │
│  │   │   = Auto Compact Threshold  ← 超过此值触发自动压缩                    │
│  │   │                                                                      │
│  │   ├── - WARNING_THRESHOLD_BUFFER_TOKENS (20,000)                         │
│  │   │   = Warning Threshold  ← 显示警告                                    │
│  │   │                                                                      │
│  │   ├── - ERROR_THRESHOLD_BUFFER_TOKENS (20,000)                           │
│  │   │   = Error Threshold  ← 显示错误                                      │
│  │   │                                                                      │
│  │   └── - MANUAL_COMPACT_BUFFER_TOKENS (3,000)                             │
│  │       = Blocking Limit  ← 阻止发送，强制手动 /compact                    │
│  │                                                                          │
│  Post-Compact 恢复预算:                                                     │
│  ├── POST_COMPACT_TOKEN_BUDGET = 50,000 (文件恢复总预算)                     │
│  ├── POST_COMPACT_MAX_FILES_TO_RESTORE = 5 (最多恢复文件数)                  │
│  ├── POST_COMPACT_MAX_TOKENS_PER_FILE = 5,000 (单文件 token 上限)           │
│  ├── POST_COMPACT_SKILLS_TOKEN_BUDGET = 25,000 (技能恢复总预算)              │
│  └── POST_COMPACT_MAX_TOKENS_PER_SKILL = 5,000 (单技能 token 上限)          │
│                                                                             │
│  熔断器:                                                                    │
│  └── MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3 (连续失败 3 次后停止重试)       │
│                                                                             │
│  PTL 重试:                                                                  │
│  └── MAX_PTL_RETRIES = 3 (压缩请求本身 prompt-too-long 时的重试次数)         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、触发机制详解


### 5.1 MicroCompact 触发 — 每次 API 调用前

```
query.ts 主循环
    ↓
microcompactMessages(messages, toolUseContext, querySource)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. clearCompactWarningSuppression()  // 重置警告抑制              │
│                                                                  │
│ 2. Time-Based MC 检查 (优先级最高，短路后续路径):                  │
│    evaluateTimeBasedTrigger(messages, querySource)                │
│    ├── 条件: enabled && 主线程 && 距上次 assistant > 60min        │
│    ├── 动作: 清理旧工具结果内容 (直接修改 message content)         │
│    ├── 保留: 最近 keepRecent 个可压缩工具结果                     │
│    └── 原理: 服务端缓存已过期，全量重写不可避免，先瘦身            │
│                                                                  │
│ 3. Cached MC 检查 (仅 ant 用户 + 支持的模型 + 主线程):           │
│    cachedMicrocompactPath(messages, querySource)                  │
│    ├── 注册新工具结果到 CachedMCState                            │
│    ├── 计算需删除的工具 ID (超过 triggerThreshold)                │
│    ├── 生成 cache_edits block (API 层注入)                       │
│    └── 不修改本地消息 — 通过 API cache_reference/cache_edits 实现 │
│                                                                  │
│ 4. 无压缩: 返回原始消息                                          │
└─────────────────────────────────────────────────────────────────┘
```

**可压缩工具集合** (COMPACTABLE_TOOLS):
- `Read` (文件读取)
- `Bash` / `BashTool` (Shell 命令)
- `Grep` / `Glob` (搜索)
- `WebSearch` / `WebFetch` (网络)
- `Edit` / `Write` (文件编辑/写入)

### 5.2 AutoCompact 触发 — token 超阈值

```
query.ts 主循环 (microcompact 之后)
    ↓
autoCompactIfNeeded(messages, toolUseContext, cacheSafeParams, querySource, tracking)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ 前置检查 (任一为 true 则跳过):                                   │
│ ├── DISABLE_COMPACT 环境变量                                     │
│ ├── 熔断器: consecutiveFailures >= 3                             │
│ ├── querySource 是 session_memory / compact / marble_origami     │
│ ├── DISABLE_AUTO_COMPACT 环境变量                                │
│ ├── 用户配置 autoCompactEnabled = false                          │
│ ├── Reactive-only 模式 (tengu_cobalt_raccoon gate)               │
│ └── Context Collapse 模式已启用                                   │
│                                                                  │
│ 阈值计算:                                                        │
│ threshold = getEffectiveContextWindowSize(model)                  │
│           - AUTOCOMPACT_BUFFER_TOKENS (13,000)                   │
│                                                                  │
│ tokenCount = tokenCountWithEstimation(messages) - snipTokensFreed│
│                                                                  │
│ 触发条件: tokenCount >= threshold                                │
└─────────────────────────────────────────────────────────────────┘
    ↓ (触发)
┌─────────────────────────────────────────────────────────────────┐
│ 优先尝试 Session Memory Compact:                                 │
│ trySessionMemoryCompaction(messages, agentId, threshold)         │
│ ├── 条件: tengu_session_memory && tengu_sm_compact 开关均开启    │
│ ├── 等待进行中的 session memory 提取完成                          │
│ ├── 读取已提取的 session memory 内容                              │
│ ├── 计算保留消息范围 (calculateMessagesToKeepIndex)               │
│ └── 成功 → 返回 CompactionResult (无 LLM 调用)                  │
│                                                                  │
│ 回退到 Legacy Compact:                                           │
│ compactConversation(messages, context, ...)                       │
│ ├── 调用 LLM 生成对话摘要                                        │
│ ├── 恢复关键上下文附件                                            │
│ └── 返回 CompactionResult                                        │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 ReactiveCompact 触发 — API 413 错误

```
query.ts 流式响应处理
    ↓
API 返回 prompt_too_long 错误 (被 withhold)
    ↓
tryReactiveCompact({hasAttempted, querySource, aborted, ...})
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ 条件: isReactiveCompactEnabled() && !hasAttempted && !aborted   │
│                                                                  │
│ 从消息尾部逐组剥离 API round groups                              │
│ 直到 token 数降到安全范围                                        │
│ 生成摘要 → 替换消息 → 重试 API 调用                              │
│                                                                  │
│ hasAttemptedReactiveCompact = true (防止循环)                    │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 Manual Compact 触发 — /compact 命令

```
用户输入 /compact [instructions]
    ↓
commands/compact/compact.ts
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. 优先尝试 Session Memory Compact                               │
│ 2. 回退: microcompactMessages() 先瘦身                           │
│ 3. compactConversation() 生成摘要                                │
│ 4. runPostCompactCleanup() 清理缓存                              │
└─────────────────────────────────────────────────────────────────┘

Partial Compact (消息选择器):
    ↓
partialCompactConversation(allMessages, pivotIndex, context, ...)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│ direction = 'from': 摘要 pivotIndex 之后的消息，保留之前的        │
│   → 保留 prompt cache (前缀不变)                                 │
│                                                                  │
│ direction = 'up_to': 摘要 pivotIndex 之前的消息，保留之后的       │
│   → 失去 prompt cache (前缀被替换为摘要)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、核心链路图

### 6.1 完整压缩调用链 (compactConversation)

```
compactConversation(messages, context, cacheSafeParams, ...)
    │
    ├── 1. executePreCompactHooks()
    │       ├── 触发 pre_compact hooks
    │       └── 合并 hook 提供的自定义指令
    │
    ├── 2. 构建摘要请求
    │       ├── getCompactPrompt(customInstructions)
    │       │   ├── NO_TOOLS_PREAMBLE (禁止工具调用)
    │       │   ├── BASE_COMPACT_PROMPT (9 段式摘要模板)
    │       │   └── NO_TOOLS_TRAILER (再次强调禁止工具)
    │       └── createUserMessage({ content: compactPrompt })
    │
    ├── 3. streamCompactSummary() — 核心 API 调用
    │       │
    │       ├── 3a. Fork Path (promptCacheSharingEnabled = true):
    │       │       runForkedAgent({
    │       │         promptMessages: [summaryRequest],
    │       │         cacheSafeParams,        // 复用主对话缓存前缀
    │       │         canUseTool: deny_all,   // 禁止工具调用
    │       │         maxTurns: 1,
    │       │       })
    │       │       ├── 成功 → 返回 AssistantMessage
    │       │       └── 失败 → 回退到 Streaming Path
    │       │
    │       └── 3b. Streaming Path (回退):
    │               queryModelWithStreaming({
    │                 messages: normalize(strip_images(messages + summaryRequest)),
    │                 systemPrompt: "You are a helpful AI assistant...",
    │                 thinkingConfig: { type: 'disabled' },
    │                 tools: [FileReadTool, ToolSearchTool?],
    │                 maxOutputTokens: COMPACT_MAX_OUTPUT_TOKENS,
    │               })
    │               ├── 重试: MAX_COMPACT_STREAMING_RETRIES = 2
    │               └── Keep-alive: 每 30s 发送心跳防止 WebSocket 超时
    │
    ├── 4. PTL 重试循环 (压缩请求本身 prompt-too-long):
    │       for (;;) {
    │         response = streamCompactSummary(...)
    │         if (!prompt_too_long) break
    │         truncateHeadForPTLRetry(messages, response)
    │         // 按 API round groups 从头部丢弃，最多 3 次
    │       }
    │
    ├── 5. 摘要后处理
    │       ├── formatCompactSummary(): 剥离 <analysis> 保留 <summary>
    │       ├── 清理 readFileState 缓存
    │       └── 清理 loadedNestedMemoryPaths
    │
    ├── 6. 恢复上下文附件 (并行)
    │       ├── createPostCompactFileAttachments()
    │       │   ├── 按时间戳排序最近读取的文件
    │       │   ├── 跳过已在 preservedMessages 中的文件
    │       │   ├── 通过 FileReadTool 重新读取 (获取最新内容)
    │       │   └── 受 POST_COMPACT_TOKEN_BUDGET (50K) 限制
    │       │
    │       ├── createAsyncAgentAttachmentsIfNeeded()
    │       │   └── 恢复运行中/已完成的异步 Agent 状态
    │       │
    │       ├── createPlanAttachmentIfNeeded()
    │       │   └── 恢复当前计划文件
    │       │
    │       ├── createPlanModeAttachmentIfNeeded()
    │       │   └── 恢复 plan mode 指令
    │       │
    │       ├── createSkillAttachmentIfNeeded()
    │       │   ├── 按最近使用排序
    │       │   ├── 单技能截断: POST_COMPACT_MAX_TOKENS_PER_SKILL (5K)
    │       │   └── 总预算: POST_COMPACT_SKILLS_TOKEN_BUDGET (25K)
    │       │
    │       └── Delta Attachments (重新注入):
    │           ├── getDeferredToolsDeltaAttachment()
    │           ├── getAgentListingDeltaAttachment()
    │           └── getMcpInstructionsDeltaAttachment()
    │
    ├── 7. processSessionStartHooks('compact')
    │       └── 恢复 CLAUDE.md 等上下文
    │
    ├── 8. 构建结果
    │       ├── createCompactBoundaryMessage() — 压缩边界标记
    │       ├── 记录 preCompactDiscoveredTools (工具搜索状态)
    │       ├── 创建摘要消息 (isCompactSummary: true)
    │       └── buildPostCompactMessages() 组装最终消息序列
    │
    ├── 9. 遥测与状态更新
    │       ├── logEvent('tengu_compact', {...})
    │       ├── notifyCompaction() — 重置缓存命中基线
    │       ├── markPostCompaction() — 标记压缩完成
    │       ├── reAppendSessionMetadata() — 保持 --resume 可见
    │       └── writeSessionTranscriptSegment() — 写入转录
    │
    └── 10. executePostCompactHooks()
            └── 触发 post_compact hooks
```

### 6.2 Session Memory Compact 链路

```
trySessionMemoryCompaction(messages, agentId, autoCompactThreshold)
    │
    ├── 1. shouldUseSessionMemoryCompaction()
    │       └── 检查 tengu_session_memory && tengu_sm_compact 开关
    │
    ├── 2. initSessionMemoryCompactConfig()
    │       └── 从 GrowthBook 加载远程配置 (仅首次)
    │
    ├── 3. waitForSessionMemoryExtraction()
    │       └── 等待后台 session memory 提取完成
    │
    ├── 4. getSessionMemoryContent()
    │       └── 读取已提取的 session memory 文件
    │
    ├── 5. calculateMessagesToKeepIndex(messages, lastSummarizedIndex)
    │       │
    │       ├── 从 lastSummarizedMessageId 之后开始
    │       ├── 向前扩展直到满足:
    │       │   ├── minTokens (10,000) 且 minTextBlockMessages (5)
    │       │   └── 或达到 maxTokens (40,000)
    │       ├── 不越过最后一个 compact boundary
    │       └── adjustIndexToPreserveAPIInvariants()
    │           ├── 保持 tool_use/tool_result 配对完整
    │           └── 保持同 message.id 的 thinking blocks 完整
    │
    ├── 6. 构建 CompactionResult
    │       ├── truncateSessionMemoryForCompact() — 截断过长段落
    │       ├── getCompactUserSummaryMessage() — 格式化摘要
    │       └── annotateBoundaryWithPreservedSegment() — 标注保留段
    │
    └── 7. 阈值检查
            └── postCompactTokenCount >= autoCompactThreshold → 返回 null (回退)
```

### 6.3 MicroCompact Cached Path 链路

```
cachedMicrocompactPath(messages, querySource)
    │
    ├── 1. ensureCachedMCState() — 初始化/获取全局状态
    │
    ├── 2. 收集可压缩工具 ID
    │       collectCompactableToolIds(messages)
    │       └── 遍历 assistant 消息中 COMPACTABLE_TOOLS 的 tool_use blocks
    │
    ├── 3. 注册工具结果
    │       for each user message:
    │         registerToolResult(state, tool_use_id)
    │         registerToolMessage(state, groupIds)
    │
    ├── 4. 计算需删除的工具
    │       getToolResultsToDelete(state)
    │       └── 基于 triggerThreshold / keepRecent 配置
    │
    ├── 5. 生成 cache_edits block
    │       createCacheEditsBlock(state, toolsToDelete)
    │       └── pendingCacheEdits = cacheEdits
    │
    └── 6. 返回 (消息不变，cache_edits 在 API 层注入)
            return { messages, compactionInfo: { pendingCacheEdits } }

    ↓ (API 调用后)

query.ts: 从 API 响应中读取 cache_deleted_input_tokens
    ├── 计算实际删除的 token 数 (delta = current - baseline)
    ├── yield createMicrocompactBoundaryMessage()
    └── pinCacheEdits() — 固定到消息位置以便后续请求重发
```

---

## 七、消息分组策略 (grouping.ts)

```typescript
// groupMessagesByApiRound: 按 API 轮次分组
// 边界条件: assistant message.id 变化 = 新的 API 轮次

Group 0: [user_msg, attachment, ...]           // 初始前言
Group 1: [assistant(id=A), user(tool_results)] // 第一轮 API 调用
Group 2: [assistant(id=B), user(tool_results)] // 第二轮 API 调用
Group 3: [assistant(id=C), ...]                // 第三轮 API 调用
```

**用途**:
- `truncateHeadForPTLRetry()`: 从头部按组丢弃，直到覆盖 tokenGap
- ReactiveCompact: 从尾部按组剥离
- 确保 tool_use/tool_result 配对不被拆分

---

## 八、摘要 Prompt 设计

### 9 段式摘要模板 (BASE_COMPACT_PROMPT)

```
┌─────────────────────────────────────────────────────────────────┐
│  NO_TOOLS_PREAMBLE                                               │
│  "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools."      │
├─────────────────────────────────────────────────────────────────┤
│  <analysis> 草稿区 (最终会被 formatCompactSummary 剥离)          │
│  ├── 按时间顺序分析每条消息                                      │
│  ├── 识别用户意图、技术决策、代码模式                             │
│  └── 交叉验证技术准确性                                          │
├─────────────────────────────────────────────────────────────────┤
│  <summary> 正式摘要 (9 个段落):                                  │
│  1. Primary Request and Intent — 用户请求与意图                   │
│  2. Key Technical Concepts — 关键技术概念                        │
│  3. Files and Code Sections — 文件与代码片段 (含完整代码)         │
│  4. Errors and fixes — 错误与修复 (含用户反馈)                   │
│  5. Problem Solving — 问题解决过程                               │
│  6. All user messages — 所有非工具结果的用户消息                  │
│  7. Pending Tasks — 待完成任务                                   │
│  8. Current Work — 当前工作 (含文件名和代码)                     │
│  9. Optional Next Step — 可选下一步 (含原文引用)                 │
├─────────────────────────────────────────────────────────────────┤
│  NO_TOOLS_TRAILER                                                │
│  "REMINDER: Do NOT call any tools."                              │
└─────────────────────────────────────────────────────────────────┘
```

**Partial Compact 变体**:
- `PARTIAL_COMPACT_PROMPT` (direction='from'): 仅摘要最近部分，早期消息保留
- `PARTIAL_COMPACT_UP_TO_PROMPT` (direction='up_to'): 摘要早期部分，增加 "Context for Continuing Work" 段

---

## 九、Post-Compact 清理 (postCompactCleanup.ts)

```
runPostCompactCleanup(querySource)
    │
    ├── resetMicrocompactState()          // 重置 Cached MC 全局状态
    ├── resetContextCollapse()            // 重置 Context Collapse (仅主线程)
    ├── getUserContext.cache.clear()       // 清理 CLAUDE.md 缓存 (仅主线程)
    ├── resetGetMemoryFilesCache()        // 重置 memory 文件缓存
    ├── clearSystemPromptSections()       // 清理系统提示词段落
    ├── clearClassifierApprovals()        // 清理分类器审批
    ├── clearSpeculativeChecks()          // 清理推测性权限检查
    ├── clearBetaTracingState()           // 清理 tracing 状态
    ├── sweepFileContentCache()           // 清理文件内容缓存 (commit attribution)
    └── clearSessionMessagesCache()       // 清理会话消息缓存
    
    注意: 不清理 sentSkillNames (避免重新注入 ~4K token 的 skill_listing)
    注意: 不清理 invokedSkills (需跨多次压缩保留技能内容)
    注意: 子 Agent 压缩时跳过主线程模块级状态的重置
```

---

## 十、图像与附件处理

### 压缩前预处理

```
stripImagesFromMessages(messages)
    ├── image block → [image] 文本标记
    ├── document block → [document] 文本标记
    └── tool_result 内嵌的 image/document → 同上替换

stripReinjectedAttachments(messages)
    └── 过滤 skill_discovery / skill_listing 附件
        (压缩后会重新注入，避免污染摘要)
```

---

## 十一、错误处理与容错

### 11.1 PTL 重试 (Prompt Too Long)

```
压缩请求本身超出 prompt 限制:
    ↓
truncateHeadForPTLRetry(messages, ptlResponse)
    ├── 解析 tokenGap (从错误响应中提取)
    ├── 按 API round groups 从头部丢弃
    │   ├── 有 tokenGap: 累计丢弃直到覆盖 gap
    │   └── 无 tokenGap: 丢弃 20% 的 groups
    ├── 保留至少 1 个 group (有内容可摘要)
    ├── 如果首条变为 assistant → 前置合成 user 消息
    └── 最多重试 MAX_PTL_RETRIES = 3 次
```

### 11.2 熔断器

```
autoCompactIfNeeded:
    ├── 成功 → consecutiveFailures = 0
    └── 失败 → consecutiveFailures++
        └── >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES (3)
            → 本会话不再尝试自动压缩
            → 日志: "circuit breaker tripped"
```

### 11.3 Compact Warning 状态

```
compactWarningStore (React 外部存储):
    ├── suppressCompactWarning()  — 压缩成功后抑制警告
    ├── clearCompactWarningSuppression() — 新压缩尝试前清除
    └── useCompactWarningSuppression() — React hook 订阅
```

---

## 十二、API 层上下文管理 (apiMicrocompact.ts)

```
getAPIContextManagement(options)
    │
    ├── clear_thinking_20251015 策略:
    │   ├── 条件: hasThinking && !isRedactThinkingActive
    │   ├── 正常: keep: 'all' (保留所有 thinking)
    │   └── 空闲超时: keep: { thinking_turns: 1 } (仅保留最后一轮)
    │
    └── clear_tool_uses_20250919 策略 (仅 ant 用户):
        ├── USE_API_CLEAR_TOOL_RESULTS:
        │   ├── trigger: input_tokens > 180,000
        │   ├── clear_at_least: 180,000 - 40,000 = 140,000 tokens
        │   └── clear_tool_inputs: [Bash, Grep, Glob, Read, WebFetch, WebSearch]
        │
        └── USE_API_CLEAR_TOOL_USES:
            ├── trigger: input_tokens > 180,000
            ├── clear_at_least: 140,000 tokens
            └── exclude_tools: [Edit, Write, NotebookEdit]
```

---

## 十三、文件模块索引

```
src/services/compact/
├── compact.ts                 // 核心: compactConversation, partialCompactConversation
│                              //       CompactionResult, buildPostCompactMessages
│                              //       Post-compact 附件恢复逻辑
├── autoCompact.ts             // 自动压缩: shouldAutoCompact, autoCompactIfNeeded
│                              //           阈值计算, 熔断器, 环境变量覆盖
├── microCompact.ts            // 微压缩: microcompactMessages, Time-Based MC
│                              //         Cached MC 状态管理, token 估算
├── apiMicrocompact.ts         // API 层: getAPIContextManagement
│                              //         clear_tool_uses / clear_thinking 策略
├── sessionMemoryCompact.ts    // Session Memory 压缩: trySessionMemoryCompaction
│                              //         calculateMessagesToKeepIndex
│                              //         adjustIndexToPreserveAPIInvariants
├── grouping.ts                // 消息分组: groupMessagesByApiRound
├── prompt.ts                  // 摘要 Prompt: getCompactPrompt, getPartialCompactPrompt
│                              //              formatCompactSummary
├── postCompactCleanup.ts      // 清理: runPostCompactCleanup
├── compactWarningState.ts     // 警告状态: compactWarningStore
├── compactWarningHook.ts      // React Hook: useCompactWarningSuppression
└── timeBasedMCConfig.ts       // 时间配置: TimeBasedMCConfig, getTimeBasedMCConfig
```

---

## 十四、设计亮点与权衡

1. **Fork Path 缓存复用**: `streamCompactSummary` 优先使用 `runForkedAgent` 复用主对话的 prompt cache 前缀，避免压缩 API 调用产生大量 `cache_creation` 费用。实验数据显示 false path 98% cache miss。

2. **Session Memory 零 LLM 调用**: 当 session memory 已提取时，直接用其内容替代 LLM 摘要，节省一次完整的 API 调用。通过 `calculateMessagesToKeepIndex` 保留足够的原始消息作为上下文。

3. **Cached MC 的缓存保留**: 通过 API 的 `cache_edits` 机制删除工具结果，不修改本地消息内容，从而保留服务端 prompt cache。这是与 Time-Based MC（直接修改内容，破坏缓存）的核心区别。

4. **子 Agent 隔离**: `runPostCompactCleanup` 区分主线程和子 Agent，避免子 Agent 压缩时破坏主线程的模块级状态（如 context collapse store、memory file cache）。

5. **<analysis> 草稿区**: 摘要 prompt 要求模型先在 `<analysis>` 标签中组织思路，再输出 `<summary>`。`formatCompactSummary` 最终剥离 analysis 部分，只保留结构化摘要。这提升了摘要质量但不增加上下文占用。

6. **PTL 自救**: 当压缩请求本身超出 prompt 限制时（CC-1180），通过 `truncateHeadForPTLRetry` 从头部丢弃最旧的 API round groups，最多重试 3 次，避免用户陷入死锁。
