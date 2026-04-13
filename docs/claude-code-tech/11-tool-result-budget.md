# Claude Code 工具结果预算与控制机制深度分析

## 一、概述

Claude Code 的工具系统面临一个核心挑战：Agent 在自主执行过程中会频繁调用工具（Bash、FileRead、WebSearch、WebFetch、Grep 等），每次调用都会产生可能很大的输出结果。如果不加控制，多次工具调用的累积输出会迅速填满模型的上下文窗口，导致 prompt-too-long 错误或超时。

系统通过三层防线解决这个问题：

1. **工具级限制 (Tool-Level)**: 每个工具在产出结果时自行截断或压缩
2. **结果级持久化 (Result-Level)**: 超过阈值的单个结果写入磁盘，只发送预览
3. **消息级预算 (Message-Level)**: 单条消息内所有工具结果的聚合预算控制

这三层与 Compact 系统（第 10 章）形成完整的上下文管理链路。

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Tool Result Budget Pipeline                          │
│                                                                             │
│  Tool.call()                                                                │
│    ↓                                                                        │
│  Layer 1: 工具内部截断                                                       │
│  ├── BashTool: stdout 截断到 30K chars (getMaxOutputLength)                  │
│  ├── FileReadTool: 内容截断到 25K tokens (validateContentTokens)             │
│  ├── WebFetchTool: Haiku 摘要 + MAX_MARKDOWN_LENGTH                         │
│  └── WebSearchTool: max_uses=8 限制搜索次数                                  │
│    ↓                                                                        │
│  Layer 2: 结果持久化 (processToolResultBlock)                                │
│  ├── 单结果 > maxResultSizeChars → 写入磁盘 + 发送 2KB 预览                  │
│  └── 系统级上限: DEFAULT_MAX_RESULT_SIZE_CHARS = 50K                         │
│    ↓                                                                        │
│  Layer 3: 消息级聚合预算 (enforceToolResultBudget)                           │
│  ├── 单消息所有 tool_result 总和 > 200K chars → 最大的写入磁盘               │
│  └── 跨轮次状态追踪 (ContentReplacementState) 保证 prompt cache 稳定         │
│    ↓                                                                        │
│  → API 调用 (消息已在预算内)                                                 │
│    ↓                                                                        │
│  Layer 4: MicroCompact (跨轮次清理旧工具结果)                                │
│  Layer 5: AutoCompact (全量摘要压缩)                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心数据结构

### 3.1 Tool 接口中的预算字段

```typescript
// src/Tool.ts (简化)
type Tool<Input, Output> = {
  name: string
  maxResultSizeChars: number    // 单结果持久化阈值 (chars)
  // ...
  call(input, context): Promise<{ data: Output }>
  mapToolResultToToolResultBlockParam(output, toolUseID): ToolResultBlockParam
}
```

### 3.2 ContentReplacementState — 跨轮次预算追踪

```typescript
// src/utils/toolResultStorage.ts
type ContentReplacementState = {
  seenIds: Set<string>                    // 已处理过的 tool_use_id (命运已冻结)
  replacements: Map<string, string>       // 被替换的 ID → 替换后的预览字符串
}
```

**设计要点**: 一旦某个 tool_result 被标记为 "seen"，其命运就被冻结——已替换的永远替换（重放缓存的预览），未替换的永远不替换。这保证了 prompt cache 前缀的稳定性。

### 3.3 PersistedToolResult — 磁盘持久化结果

```typescript
type PersistedToolResult = {
  filepath: string        // 磁盘路径: {sessionDir}/tool-results/{toolUseId}.txt
  originalSize: number    // 原始大小
  isJson: boolean         // 是否 JSON 格式
  preview: string         // 前 2KB 预览
  hasMore: boolean        // 是否有更多内容
}
```

---

## 四、关键常量体系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  系统级常量 (src/constants/toolLimits.ts)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DEFAULT_MAX_RESULT_SIZE_CHARS = 50,000                                     │
│    └── 单个工具结果的系统级持久化上限                                         │
│        (工具声明的 maxResultSizeChars 会被 Math.min 到此值)                   │
│                                                                             │
│  MAX_TOOL_RESULT_TOKENS = 100,000                                           │
│  MAX_TOOL_RESULT_BYTES  = 400,000  (= 100K × 4 bytes/token)                │
│    └── 单个工具结果的绝对字节上限                                             │
│                                                                             │
│  MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 200,000                               │
│    └── 单条消息内所有 tool_result 的聚合上限                                  │
│        (可通过 GrowthBook tengu_hawthorn_window 覆盖)                        │
│                                                                             │
│  BYTES_PER_TOKEN = 4                                                        │
│    └── token 估算系数                                                        │
│                                                                             │
│  PREVIEW_SIZE_BYTES = 2,000                                                 │
│    └── 持久化后发送给模型的预览大小                                           │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  工具级常量                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BashTool:                                                                  │
│  ├── maxResultSizeChars = 30,000                                            │
│  ├── BASH_MAX_OUTPUT_DEFAULT = 30,000 (stdout 截断)                          │
│  ├── BASH_MAX_OUTPUT_UPPER_LIMIT = 150,000 (env 覆盖上限)                   │
│  └── MAX_PERSISTED_SIZE = 64 MB (磁盘持久化上限)                             │
│                                                                             │
│  FileReadTool:                                                              │
│  ├── maxResultSizeChars = Infinity (不走持久化，自行限制)                     │
│  ├── DEFAULT_MAX_OUTPUT_TOKENS = 25,000 (token 级截断)                      │
│  └── MAX_OUTPUT_SIZE = 256 KB (文件大小上限)                                 │
│                                                                             │
│  GrepTool:                                                                  │
│  └── maxResultSizeChars = 20,000                                            │
│                                                                             │
│  WebSearchTool:                                                             │
│  ├── maxResultSizeChars = 100,000                                           │
│  └── max_uses = 8 (服务端搜索次数限制)                                       │
│                                                                             │
│  WebFetchTool:                                                              │
│  ├── maxResultSizeChars = 100,000                                           │
│  └── MAX_MARKDOWN_LENGTH (内容截断后由 Haiku 摘要)                           │
│                                                                             │
│  其他工具 (Edit/Write/Glob/MCP/...):                                        │
│  └── maxResultSizeChars = 100,000 (通用默认)                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、Layer 1: 工具内部截断


每个工具在 `call()` 方法内部实现自己的输出大小控制，这是第一道防线。

### 5.1 BashTool — stdout 截断

```
BashTool.call()
    ↓
Shell 执行命令，输出写入临时文件
    ↓
读取 stdout (最多 getMaxOutputLength() = 30K chars)
    ↓
formatOutput(content):
    ├── content.length <= maxOutputLength → 原样返回
    └── content.length > maxOutputLength → 截断 + 追加:
        "[N lines truncated]"
    ↓
如果是图片输出 (base64):
    └── maybeResizeAndDownsampleImageBuffer() → 压缩图片
    ↓
持久化完整输出到 tool-results/{id}.txt (最大 64MB)
    └── 模型可通过 FileRead 读取完整输出
```

### 5.2 FileReadTool — token 级截断

```
FileReadTool.call()
    ↓
stat() 检查文件大小
    ├── > maxSizeBytes (256KB) → 抛出错误，提示用 offset/limit
    └── <= maxSizeBytes → 读取内容
    ↓
validateContentTokens(content, ext, maxTokens=25000):
    ├── roughTokenCountEstimation (快速估算)
    │   └── <= maxTokens/4 → 通过 (快速路径，避免 API 调用)
    ├── countTokensWithAPI (精确计数，需 API 调用)
    │   └── <= maxTokens → 通过
    └── > maxTokens → 抛出 MaxFileReadTokenExceededError
        "File content (N tokens) exceeds maximum (25000).
         Use offset and limit parameters..."
```

**关键设计**: FileReadTool 的 `maxResultSizeChars = Infinity`，意味着它不走 Layer 2 的持久化路径。原因是将 FileRead 的输出持久化到文件，然后模型再用 FileRead 读取该文件，会形成循环。FileReadTool 通过自己的 token 级截断自行保证输出大小。

### 5.3 WebSearchTool — 服务端搜索次数限制

```
WebSearchTool.call()
    ↓
构建 server-side tool schema:
    { type: 'web_search_20250305', max_uses: 8 }
    ↓
queryModelWithStreaming() — 模型自主决定搜索几次 (最多 8 次)
    ↓
收集所有 content blocks:
    ├── server_tool_use → 搜索请求
    ├── web_search_tool_result → 搜索结果 (title + url)
    └── text → 模型的文字总结
    ↓
makeOutputFromSearchResponse() → 格式化输出
    ↓
mapToolResultToToolResultBlockParam():
    格式化为 "Web search results for query: ..."
    包含链接 JSON + 文字总结
```

**关键设计**: WebSearch 是服务端工具，搜索结果由 Anthropic API 服务端生成。`max_uses: 8` 硬编码限制了单次调用最多执行 8 次搜索，从源头控制了输出量。输出格式只包含 title + url（不含网页全文），天然较小。

### 5.4 WebFetchTool — Haiku 摘要

```
WebFetchTool.call()
    ↓
getURLMarkdownContent(url) → 获取网页 Markdown
    ↓
applyPromptToMarkdown(prompt, content):
    ├── 使用 Haiku (小模型) 对网页内容进行摘要
    ├── 根据用户 prompt 提取相关信息
    └── 输出是摘要后的文本 (远小于原始网页)
    ↓
如果是预审批 URL + Markdown + < MAX_MARKDOWN_LENGTH:
    └── 直接返回原始内容 (跳过摘要)
```

**关键设计**: WebFetch 不是简单截断，而是用小模型（Haiku）对网页内容做智能摘要。这保证了即使原始网页很大，返回给主模型的结果也是精炼的。

---

## 六、Layer 2: 结果级持久化

当工具的输出通过了 Layer 1 的内部截断后，进入 `processToolResultBlock` 进行第二层检查。

### 6.1 持久化阈值计算

```
getPersistenceThreshold(toolName, declaredMaxResultSizeChars):
    │
    ├── declaredMaxResultSizeChars = Infinity → 返回 Infinity (不持久化)
    │   └── 仅 FileReadTool 使用此值
    │
    ├── GrowthBook 覆盖 (tengu_satin_quoll):
    │   └── overrides[toolName] 存在且 > 0 → 使用覆盖值
    │
    └── 默认: Math.min(declaredMaxResultSizeChars, DEFAULT_MAX_RESULT_SIZE_CHARS)
        └── 即 Math.min(工具声明值, 50,000)
```

### 6.2 持久化流程

```
maybePersistLargeToolResult(toolResultBlock, toolName, threshold)
    │
    ├── 空内容检查:
    │   └── 空 → 注入 "(toolName completed with no output)"
    │       (防止模型因空 tool_result 触发 \n\nHuman: 停止序列)
    │
    ├── 图片内容 → 跳过 (图片需原样发送给 Claude)
    │
    ├── contentSize(content) <= threshold → 返回原始 block
    │
    └── contentSize(content) > threshold:
        ├── persistToolResult(content, toolUseId)
        │   ├── 写入 {sessionDir}/tool-results/{toolUseId}.txt
        │   ├── 使用 flag='wx' 避免重复写入 (幂等)
        │   └── 生成 2KB 预览 (在换行符处截断)
        │
        └── buildLargeToolResultMessage(result):
            "<persisted-output>
             Output too large (N KB). Full output saved to: /path/to/file
             Preview (first 2 KB):
             {preview content}
             ...
             </persisted-output>"
```

### 6.3 各工具的有效持久化阈值

| 工具 | 声明值 | 有效阈值 | 说明 |
|------|--------|---------|------|
| FileReadTool | Infinity | Infinity | 不持久化，自行 token 截断 |
| GrepTool | 20,000 | 20,000 | 搜索结果较小 |
| BashTool | 30,000 | 30,000 | stdout 已在 Layer 1 截断 |
| WebSearchTool | 100,000 | 50,000 | 被系统上限 clamp |
| WebFetchTool | 100,000 | 50,000 | 被系统上限 clamp |
| MCPTool | 100,000 | 50,000 | 被系统上限 clamp |
| 其他工具 | 100,000 | 50,000 | 被系统上限 clamp |

---

## 七、Layer 3: 消息级聚合预算

Layer 2 控制单个工具结果的大小，但当模型并行调用多个工具时（如同时 Grep 5 个文件），单条消息内的 tool_result 总量可能爆炸。Layer 3 解决这个问题。

### 7.1 触发位置

```
query.ts 主循环 (每次 API 调用前):
    ↓
applyToolResultBudget(messagesForQuery, state, writeToTranscript, skipToolNames)
    ↓
enforceToolResultBudget(messages, state, skipToolNames)
```

### 7.2 预算执行流程

```
enforceToolResultBudget(messages, state, skipToolNames)
    │
    ├── 1. collectCandidatesByMessage(messages)
    │       按 API 级用户消息分组 (模拟 normalizeMessagesForAPI 的合并行为)
    │       ├── 连续 user 消息合并为一组 (Bedrock 兼容)
    │       ├── assistant 消息创建新组边界
    │       └── progress/attachment/system 不创建边界
    │
    ├── 2. 对每个消息组:
    │       partitionByPriorDecision(candidates, state)
    │       ├── mustReapply: 之前已替换 → 重放缓存的预览 (零 I/O)
    │       ├── frozen: 之前已见但未替换 → 不可替换 (保护 cache)
    │       └── fresh: 首次出现 → 可参与预算决策
    │
    ├── 3. 预算检查 (仅对 fresh 候选):
    │       limit = getPerMessageBudgetLimit()  // 默认 200K chars
    │       frozenSize + freshSize > limit?
    │       ├── Yes → selectFreshToReplace(fresh, frozenSize, limit)
    │       │         按大小降序排列，从最大的开始替换
    │       │         直到 frozenSize + remainingFreshSize <= limit
    │       └── No → 全部标记为 seen，不替换
    │
    ├── 4. 持久化选中的候选:
    │       await Promise.all(toPersist.map(buildReplacement))
    │       ├── persistToolResult() → 写入磁盘
    │       ├── state.seenIds.add(id)
    │       ├── state.replacements.set(id, previewContent)
    │       └── 记录 ContentReplacementRecord (写入 transcript)
    │
    └── 5. replaceToolResultContents(messages, replacementMap)
            返回替换后的消息数组
```

### 7.3 Prompt Cache 稳定性保证

```
┌─────────────────────────────────────────────────────────────────┐
│  Turn 1: 模型调用 Grep(A), Grep(B), Grep(C)                     │
│  ├── A: 80K chars, B: 60K chars, C: 90K chars                   │
│  ├── 总计: 230K > 200K 预算                                      │
│  ├── 选择替换: C(90K) → 预览(2K)                                 │
│  ├── state.seenIds = {A, B, C}                                   │
│  └── state.replacements = {C → preview}                          │
│                                                                  │
│  Turn 2: 模型继续对话                                             │
│  ├── A: frozen (80K, 不替换 — 模型已见过完整内容)                 │
│  ├── B: frozen (60K, 不替换)                                     │
│  ├── C: mustReapply → 重放缓存的 preview (字节相同)              │
│  └── prompt cache 前缀完全一致 ✓                                 │
│                                                                  │
│  Turn 3: 模型调用 Grep(D)                                        │
│  ├── D: 150K chars (fresh)                                       │
│  ├── 这是新消息，独立评估: 150K < 200K → 不替换                  │
│  └── state.seenIds = {A, B, C, D}                                │
└─────────────────────────────────────────────────────────────────┘
```

### 7.4 skipToolNames 机制

```typescript
// query.ts
const skipToolNames = new Set(
  toolUseContext.options.tools
    .filter(t => !Number.isFinite(t.maxResultSizeChars))
    .map(t => t.name),
)
```

`maxResultSizeChars = Infinity` 的工具（目前仅 FileReadTool）被排除在消息级预算之外。这些工具已通过自己的 token 级截断保证了输出大小，且将其输出持久化到文件再让模型用 FileRead 读取会形成循环。

---

## 八、WebSearch 防爆机制详解

WebSearch 是最容易导致 token 爆满的工具之一，系统通过多层机制防护：

```
┌─────────────────────────────────────────────────────────────────┐
│  防线 1: 服务端搜索次数限制                                       │
│  max_uses: 8 — 单次 WebSearch 调用最多执行 8 次搜索              │
│  (硬编码在 makeToolSchema 中)                                    │
│                                                                  │
│  防线 2: 输出格式精简                                             │
│  搜索结果只包含 title + url (不含网页全文)                        │
│  模型的文字总结也是精炼的                                         │
│                                                                  │
│  防线 3: 结果持久化                                               │
│  有效阈值 = min(100K, 50K) = 50K chars                           │
│  超过 50K → 写入磁盘 + 2KB 预览                                  │
│                                                                  │
│  防线 4: 消息级预算                                               │
│  如果同一轮有多个 WebSearch 并行                                  │
│  总量 > 200K → 最大的被替换为预览                                 │
│                                                                  │
│  防线 5: MicroCompact                                             │
│  旧的 WebSearch 结果在后续轮次被清理                              │
│  (WebSearch 在 COMPACTABLE_TOOLS 集合中)                         │
│                                                                  │
│  防线 6: AutoCompact                                              │
│  token 总量超阈值 → 全量摘要压缩                                  │
└─────────────────────────────────────────────────────────────────┘
```

WebFetch 的防护类似，但多了一层 Haiku 摘要：

```
WebFetch 防爆:
    ├── Haiku 摘要: 原始网页 → 精炼摘要 (大幅缩小)
    ├── 结果持久化: > 50K → 磁盘 + 预览
    ├── 消息级预算: 聚合控制
    └── MicroCompact: 旧结果清理
```

---

## 九、工具执行编排与并发控制

### 9.1 并发分区策略

```
toolOrchestration.ts:
partitionToolCalls(toolUseMessages, context)
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  isConcurrencySafe = true (只读工具):                            │
│  ├── FileRead, Grep, Glob, WebSearch, WebFetch, LSP             │
│  └── 并发执行 (max = 10, 可通过 env 覆盖)                       │
│                                                                  │
│  isConcurrencySafe = false (写入工具):                           │
│  ├── Bash, FileEdit, FileWrite, NotebookEdit                    │
│  └── 串行执行                                                    │
│                                                                  │
│  分区规则:                                                       │
│  连续的只读工具 → 合并为一个并发批次                              │
│  遇到写入工具 → 单独一个串行批次                                  │
│  [Read, Grep, Grep] → 并发批次                                   │
│  [Bash] → 串行批次                                               │
│  [Read, Read] → 并发批次                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 并发执行的预算影响

并发执行 N 个只读工具时，它们的 tool_result 会被合并到同一条 user 消息中。这正是 Layer 3 消息级预算存在的原因：

```
模型请求: [Grep(A), Grep(B), Grep(C), Grep(D), Grep(E)]
    ↓ 并发执行
5 个 tool_result 合并到 1 条 user 消息
    ↓
enforceToolResultBudget 检查这条消息:
    总量 = 40K + 35K + 50K + 45K + 30K = 200K
    ├── <= 200K 预算 → 全部保留
    └── 如果某个结果更大导致超预算 → 最大的被替换
```

---

## 十、完整调用链路图

```
模型返回 tool_use blocks
    ↓
toolOrchestration.runTools()
    ├── partitionToolCalls() → 分区
    ├── runToolsConcurrently() / runToolsSerially()
    │   ↓
    │   toolExecution.runToolUse()
    │       ↓
    │       tool.call(input, context)          ← Layer 1: 工具内部截断
    │       ↓
    │       processToolResultBlock(tool, result, id)
    │           ↓
    │           tool.mapToolResultToToolResultBlockParam()
    │           ↓
    │           maybePersistLargeToolResult()   ← Layer 2: 结果持久化
    │               ├── size <= threshold → 原样返回
    │               └── size > threshold → 写磁盘 + 预览
    │       ↓
    │       yield UserMessage(tool_result)
    ↓
query.ts 主循环 (下一次 API 调用前):
    ↓
applyToolResultBudget(messages, state)         ← Layer 3: 消息级预算
    ├── enforceToolResultBudget()
    │   ├── 分组 → 分区 → 预算检查
    │   └── 超预算 → 最大的写磁盘 + 替换
    ↓
microcompactMessages(messages)                  ← Layer 4: 微压缩
    ├── Time-Based MC: 清理旧工具结果
    └── Cached MC: cache_edits 删除旧结果
    ↓
autoCompactIfNeeded(messages)                   ← Layer 5: 自动压缩
    ├── Session Memory Compact
    └── Legacy Compact (LLM 摘要)
    ↓
API 调用 (上下文已在安全范围内)
```

---

## 十一、GrowthBook 远程配置

| Flag | 作用 | 默认值 |
|------|------|--------|
| `tengu_satin_quoll` | 工具级持久化阈值覆盖 (tool_name → chars) | `{}` |
| `tengu_hawthorn_window` | 消息级聚合预算上限 | `200,000` |
| `tengu_hawthorn_steeple` | 消息级预算功能开关 | `false` |
| `tengu_amber_wren` | FileRead 限制覆盖 (maxTokens, maxSizeBytes) | `{}` |

---

## 十二、文件模块索引

```
src/constants/toolLimits.ts          // 系统级常量定义
src/utils/toolResultStorage.ts       // 核心: 持久化 + 消息级预算
src/utils/shell/outputLimits.ts      // Bash stdout 截断限制
src/services/tools/toolOrchestration.ts  // 工具并发编排
src/services/tools/toolExecution.ts  // 工具执行 + processToolResultBlock
src/tools/FileReadTool/limits.ts     // FileRead 限制配置
src/tools/BashTool/utils.ts          // Bash 输出格式化/截断
src/tools/WebSearchTool/WebSearchTool.ts  // WebSearch 服务端工具
src/tools/WebFetchTool/WebFetchTool.ts    // WebFetch + Haiku 摘要
```

---

## 十三、设计亮点与权衡

1. **三层递进防线**: 工具内部截断 → 单结果持久化 → 消息级聚合预算，每层独立工作，任一层失效不会导致系统崩溃。

2. **Prompt Cache 稳定性**: `ContentReplacementState` 的 "一旦 seen 命运冻结" 设计，保证了跨轮次的 prompt 前缀字节相同，最大化 API prompt cache 命中率。

3. **FileRead 的特殊处理**: `maxResultSizeChars = Infinity` 跳过持久化，避免 "持久化到文件 → FileRead 读取 → 再持久化" 的循环。FileRead 通过自己的 token 级截断（25K tokens）自行保证。

4. **WebSearch 的服务端限制**: `max_uses: 8` 在 API 服务端执行，客户端无法绕过。输出格式只含 title + url，天然精简。

5. **WebFetch 的智能摘要**: 不是简单截断，而是用 Haiku 小模型对网页内容做语义摘要，保留了信息密度。

6. **空结果注入**: 空 tool_result 会被注入 `"(toolName completed with no output)"`，防止某些模型因空内容触发停止序列。

7. **并发与预算的协同**: 并发执行的工具结果合并到同一消息，消息级预算正好覆盖这个场景，防止 N 个并行工具各自在阈值内但总量爆炸。
