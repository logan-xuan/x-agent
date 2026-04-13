# Claude Code Subagent 系统架构总览

> 本文档是 Claude Code Subagent 系统的顶层架构文档,作为整个 tech/ 目录的导航和总纲。
> 
> **文档版本**: 2.0  
> **最后更新**: 2026-04-09  
> **基于源码**: Claude Code 最新版本

---

## 一、系统定位与核心挑战

### 1.1 系统定位

Claude Code Subagent 系统是一个**多智能体协作框架**,运行在开发者本地环境中,支持:

- **并行执行**: 多个 Agent 同时处理不同任务
- **层级管理**: Leader-Worker 模式的团队组织
- **上下文隔离**: 不同 Agent 之间安全隔离
- **资源控制**: 内存、上下文窗口、工具调用的精细管理

### 1.2 核心技术挑战

| 挑战 | 难度 | 影响范围 | 解决方案 |
|------|------|----------|----------|
| **并发状态管理** | ⭐⭐⭐⭐⭐ | 全局 | 不可变更新 + Fresh State Re-Check |
| **内存泄漏防护** | ⭐⭐⭐⭐ | 任务生命周期 | WeakRef + 回收机制 + 消息上限 |
| **上下文窗口限制** | ⭐⭐⭐⭐⭐ | 所有对话 | 5层压缩策略 + 工具结果预算 |
| **跨进程通信** | ⭐⭐⭐ | 多Agent协作 | 文件邮箱 + 直接调用 + 多层路由 |
| **权限安全隔离** | ⭐⭐⭐⭐ | 团队安全 | 权限继承规则 + Plan审批 |

---

## 二、架构分层模型

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Layer 0: 基础设施层                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  AbortController│  │  AppState       │  │  AsyncLocalStorage          │  │
│  │  链式传播       │  │  集中式状态      │  │  上下文隔离                 │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Layer 1: 任务管理层                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  任务状态机      │  │  任务回收机制    │  │  父子关系管理               │  │
│  │  (01)           │  │  (03)           │  │  (02)                       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Layer 2: 协作通信层                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  多Agent协作     │  │  进程内Teammate │  │  上下文共享                 │  │
│  │  (04)           │  │  (05)           │  │  (08)                       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Layer 3: 安全控制层                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Plan模式审批    │  │  Shutdown协议   │  │  权限系统 ⭐NEW             │  │
│  │  (06)           │  │  (07)           │  │  (规划中)                   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Layer 4: 上下文管理层                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Compact机制     │  │  工具结果预算    │  │  Token 估算 ⭐NEW          │  │
│  │  (10)           │  │  (11)           │  │  (规划中)                   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心设计哲学

### 3.1 分层递进 (Layered Defense)

系统在多个维度采用分层防御策略,确保任一层失效不会导致系统崩溃:

| 维度 | Layer 1 | Layer 2 | Layer 3 | Layer 4 |
|------|---------|---------|---------|---------|
| **任务回收** | 主动回收 | 懒惰 GC | 消息上限 | 宽限期 |
| **上下文压缩** | Micro | Auto | Reactive | Manual |
| **工具预算** | 工具内截断 | 结果持久化 | 消息级预算 | Compact清理 |
| **权限控制** | 工具级 | Session级 | 团队级 | Plan审批 |

### 3.2 用户体验优先 (UX First)

- **30秒宽限期**: 允许用户查看已完成任务
- **retain 机制**: 用户意图优先于自动回收
- **自动恢复**: 发送消息时自动 resume 已停止的 agent
- **智能摘要**: WebFetch 使用 Haiku 摘要而非简单截断

### 3.3 内存安全 (Memory Safety)

- **WeakRef**: 防止 AbortController 循环引用
- **消息上限**: TEAMMATE_MESSAGES_UI_CAP = 50
- **运行时清理**: 终止时清除 selectedAgent、abortController
- **双重 GC**: 主动回收 + 懒惰回收

### 3.4 并发安全 (Concurrency Safety)

- **Fresh State Re-Check**: 防止 TOCTOU 竞态
- **文件锁**: proper-lockfile 确保并发写入安全
- **不可变更新**: 避免副作用,React 最佳实践

---

## 四、文档导航

### 4.1 基础层文档

| 文档 | 主题 | 状态 | 核心内容 |
|------|------|------|----------|
| [01-task-state-machine](01-task-state-machine.md) | 任务状态机 | ✅ 已深度分析 | 状态定义、转换函数、TOCTOU防护、引用相等优化 |
| [02-parent-child-management](02-parent-child-management.md) | 父子关系管理 | ✅ 已深度分析 | AbortController链、WeakRef内存安全、身份解析 |
| [03-task-eviction](03-task-eviction.md) | 任务回收机制 | ✅ 已深度分析 | 宽限期、retain机制、双重GC、消息上限 |

**📊 统计数据**:
- 技术挑战点: 12+
- 设计亮点: 18+
- 改进建议: 15+
- 源码引用: 50+

### 4.2 协作层文档

| 文档 | 主题 | 状态 | 核心内容 |
|------|------|------|----------|
| [04-multi-agent-collaboration](04-multi-agent-collaboration.md) | 多Agent协作 | ✅ 已深度分析 | TeamCreateTool、SendMessageTool、文件邮箱、消息路由 |
| [05-in-process-teammate](05-in-process-teammate.md) | 进程内Teammate | ⚠️ 需补充 | AsyncLocalStorage、独立AbortController、轻量级协作 |
| [08-context-sharing](08-context-sharing.md) | 上下文共享 | ⚠️ 需补充 | Fork Context、工具继承、权限继承、缓存共享 |

**📊 统计数据**:
- 技术挑战点: 8+
- 设计亮点: 12+
- 改进建议: 10+
- 源码引用: 35+

### 4.3 安全层文档

| 文档 | 主题 | 状态 | 核心内容 |
|------|------|------|----------|
| [06-plan-mode-approval](06-plan-mode-approval.md) | Plan模式审批 | ⚠️ 需补充 | Plan创建、审批流程、权限继承 |
| [07-shutdown-protocol](07-shutdown-protocol.md) | Shutdown协议 | ⚠️ 需补充 | 协商式关闭、requestId关联、后端感知 |

**🔧 改进计划**: 
- 合并 06+07 为统一的安全控制文档
- 补充权限系统深度分析
- 添加安全审计追踪机制

### 4.4 上下文管理层文档

| 文档 | 主题 | 状态 | 核心内容 |
|------|------|------|----------|
| [10-compact-mechanism](10-compact-mechanism.md) | Compact压缩机制 | ✅ 已深度分析 | 5层压缩、Prompt Cache、Session Memory、Fork Path |
| [11-tool-result-budget](11-tool-result-budget.md) | 工具结果预算 | ✅ 已深度分析 | 三层防线、ContentReplacementState、Prompt Cache稳定 |

**📊 统计数据**:
- 技术挑战点: 10+
- 设计亮点: 20+
- 改进建议: 15+
- 源码引用: 60+

### 4.5 综合分析文档

| 文档 | 主题 | 状态 | 核心内容 |
|------|------|------|----------|
| [09-architecture-overview](09-architecture-overview.md) | 架构总览 | ⚠️ 需重构 | 系统架构图、设计原则总结 |
| [16-core-systems-deep-dive](16-core-systems-deep-dive.md) | 核心系统深度分析 | ✅ 已完成 | 11个系统的技术挑战、设计亮点、改进建议 |

---

## 五、文档重构计划

### 5.1 立即执行 (Phase 1)

#### 任务 1: 补充 05-in-process-teammate
**问题**: 当前只有 76 行,内容过于简略  
**计划**:
- 补充 AsyncLocalStorage 工作原理
- 添加独立 AbortController 设计分析
- 对比进程外 teammate 的详细差异
- 添加并发模型和故障隔离分析
- 预估补充后: 500+ 行

#### 任务 2: 补充 06-plan-mode-approval
**问题**: 当前只有 82 行,缺少源码级分析  
**计划**:
- 添加 Plan 模式触发条件详解
- 补充审批流程时序图
- 分析权限继承的优先级规则
- 添加安全审计追踪机制
- 预估补充后: 400+ 行

#### 任务 3: 补充 07-shutdown-protocol
**问题**: 当前只有 90 行,缺少实际案例  
**计划**:
- 添加协商式关闭的源码分析
- 补充超时和强制关闭机制
- 分析不同 backend 的关闭策略
- 添加批量关闭的设计方案
- 预估补充后: 350+ 行

#### 任务 4: 补充 08-context-sharing
**问题**: 当前只有 91 行,缺少上下文传递细节  
**计划**:
- 添加 forkContextMessages 的完整链路
- 补充工具继承规则的源码分析
- 分析权限继承的优先级决策树
- 添加 ReadFileState 共享机制
- 预估补充后: 500+ 行

### 5.2 短期优化 (Phase 2)

#### 任务 5: 合并 06+07 为统一文档
**新文档**: `06-security-control.md`  
**内容**:
- Plan 模式审批
- Shutdown 协议
- 权限系统 (新增)
- 安全审计追踪 (新增)

**收益**: 
- 减少文档碎片
- 统一安全控制视角
- 补充权限深度分析

#### 任务 6: 重构 09-architecture-overview
**计划**:
- 更新为本文档 (00-architecture-overview.md)
- 添加完整的分层架构模型
- 补充核心设计哲学
- 作为导航和总纲

### 5.3 长期规划 (Phase 3)

#### 新文档 1: 权限系统深度分析
**文件名**: `13-permission-system.md`  
**内容**:
- 权限模式 (plan/default/auto/acceptEdits)
- 权限继承规则
- 权限审批流程
- 权限审计追踪
- 预估: 600+ 行

#### 新文档 2: Token 估算与上下文窗口
**文件名**: `14-token-estimation.md`  
**内容**:
- Token 估算算法
- 上下文窗口管理
- 模型差异分析
- 预算动态调整
- 预估: 450+ 行

#### 新文档 3: MCP 集成与工具扩展
**文件名**: `15-mcp-integration.md`  
**内容**:
- MCP 协议概述
- 工具注册与发现
- MCP 客户端管理
- 工具继承与隔离
- 预估: 500+ 行

---

## 六、系统关键路径分析

### 6.1 任务创建路径

```
User Input
    ↓
AgentTool.call()
    ↓
registerAsyncAgent()
    ├── 创建 AbortController (父子链或独立)
    ├── 初始化输出文件符号链接
    ├── 构建 TaskState
    ├── 注册清理回调
    └── registerTask() → AppState.tasks
    ↓
Agent 开始执行
```

**涉及文档**: 01, 02, 04

### 6.2 任务完成路径

```
Agent 执行完成
    ↓
completeAgentTask()
    ├── 更新 status → 'completed'
    ├── 清除运行时引用
    ├── 设置 evictAfter (如果 retain=false)
    └── evictTaskOutput()
    ↓
enqueueAgentNotification()
    ├── notified = true
    └── 发送 UI 通知
    ↓
pollTasks() → generateTaskAttachments()
    ├── 检查回收条件
    └── 加入 evictedTaskIds
    ↓
applyTaskOffsetsAndEvictions()
    ├── Fresh State Re-Check
    └── 从 AppState.tasks 删除
```

**涉及文档**: 01, 03

### 6.3 上下文压缩路径

```
对话轮次增加
    ↓
MicroCompact (每次 API 调用前)
    ├── Time-Based MC (空闲超时)
    └── Cached MC (cache_edits)
    ↓
AutoCompact (token 超阈值)
    ├── Session Memory Compact (零 LLM 调用)
    └── Legacy Compact (LLM 摘要)
    ↓
ReactiveCompact (API 413 错误)
    └── 紧急压缩
    ↓
Manual Compact (/compact 命令)
    └── 用户主动触发
```

**涉及文档**: 10, 11

---

## 七、性能数据与基准

### 7.1 内存性能

| 场景 | 指标 | 数据 | 来源 |
|------|------|------|------|
| **单 Agent 内存** | RSS/agent | ~20MB (500+ 轮次) | BQ 分析第 9 轮 |
| **并发突发** | RSS/agent | ~125MB (swarm 突发) | BQ 分析第 9 轮 |
| **Whale 会话** | 峰值内存 | 36.8GB (292 agents) | 会话 9a990de8 |
| **消息上限** | TEAMMATE_MESSAGES_UI_CAP | 50 条 | 优化后 |

### 7.2 上下文性能

| 场景 | 指标 | 数据 | 说明 |
|------|------|------|------|
| **AutoCompact 阈值** | 有效窗口 - 13K | ~187K (200K 窗口) | AUTOCOMPACT_BUFFER_TOKENS |
| **Session Memory** | 零 LLM 调用 | 节省完整 API | 当 session memory 已提取 |
| **Fork Path 缓存** | cache miss 率 | 98% | 需优化缓存策略 |
| **工具预算** | 单消息上限 | 200K chars | 可 GrowthBook 覆盖 |

### 7.3 通信性能

| 场景 | 指标 | 数据 | 说明 |
|------|------|------|------|
| **文件邮箱** | 并发锁重试 | 10 次, 5-100ms | proper-lockfile |
| **消息路由** | 查找复杂度 | O(1) | agentNameRegistry |
| **进程内通信** | 延迟 | < 1ms | 直接函数调用 |
| **进程外通信** | 延迟 | ~100ms | 文件轮询 |

---

## 八、关键文件索引

### 8.1 核心框架

| 文件 | 作用 | 关联文档 |
|------|------|----------|
| `src/utils/task/framework.ts` | 任务状态机核心 | 01, 03 |
| `src/Task.ts` | TaskStateBase 定义 | 01 |
| `src/utils/abortController.ts` | AbortController 链 | 02, 05 |
| `src/utils/teammateContext.ts` | AsyncLocalStorage | 05, 08 |

### 8.2 协作工具

| 文件 | 作用 | 关联文档 |
|------|------|----------|
| `src/tools/TeamCreateTool/` | 团队创建 | 04 |
| `src/tools/SendMessageTool/` | 消息传递 | 04, 06, 07 |
| `src/utils/teammateMailbox.ts` | 文件邮箱 | 04, 07 |
| `src/utils/agentId.ts` | Agent ID 格式化 | 02, 04 |

### 8.3 上下文管理

| 文件 | 作用 | 关联文档 |
|------|------|----------|
| `src/services/compact/compact.ts` | 核心压缩逻辑 | 10 |
| `src/services/compact/autoCompact.ts` | 自动压缩 | 10 |
| `src/services/compact/microCompact.ts` | 微压缩 | 10 |
| `src/utils/toolResultStorage.ts` | 工具结果预算 | 11 |
| `src/constants/toolLimits.ts` | 预算常量 | 11 |

### 8.4 权限与安全

| 文件 | 作用 | 关联文档 |
|------|------|----------|
| `src/utils/permissions/` | 权限管理 | 06, 13(规划) |
| `src/tools/AgentTool/` | Agent 工具 | 08 |
| `src/QueryEngine.ts` | 查询引擎 | 08, 10, 11 |

---

## 九、设计决策记录

### 9.1 核心决策

| 决策点 | 选择 | 原因 | 文档 |
|--------|------|------|------|
| **状态更新模式** | 不可变更新 | React 最佳实践,避免副作用 | 01 |
| **回收策略** | 宽限期 + 轮询 | 平衡精确度和复杂度 | 03 |
| **AbortController** | WeakRef 双向引用 | 完全避免内存泄漏 | 02 |
| **通信机制** | 文件邮箱 + 直接调用 | 跨进程兼容 + 高性能 | 04 |
| **上下文隔离** | AsyncLocalStorage | 干净的并发模型 | 05 |
| **压缩策略** | 5层分层 | 从轻量到重量级兜底 | 10 |
| **预算控制** | 三层递进防线 | 任一层失效不崩溃 | 11 |

### 9.2 权衡分析

| 权衡点 | 方案 A | 方案 B | 选择 | 原因 |
|--------|--------|--------|------|------|
| **回收触发** | setTimeout 精确 | 轮询检查 | 轮询 | 减少定时器管理复杂度 |
| **Teammate 隔离** | Worker Threads | 共享进程 | 共享进程 | 轻量级,毫秒级创建 |
| **消息路由** | inotify 监听 | 轮询文件 | 轮询 | 跨平台兼容 |
| **压缩方式** | 增量摘要 | 全量摘要 | 全量 | 实现简单,质量可控 |

---

## 十、学习路径

### 10.1 新手入门

1. 阅读 [09-architecture-overview](09-architecture-overview.md) 了解系统全景
2. 阅读 [01-task-state-machine](01-task-state-machine.md) 理解任务生命周期
3. 阅读 [04-multi-agent-collaboration](04-multi-agent-collaboration.md) 了解协作机制

### 10.2 深入理解

4. 阅读 [02-parent-child-management](02-parent-child-management.md) 学习内存安全
5. 阅读 [10-compact-mechanism](10-compact-mechanism.md) 学习上下文管理
6. 阅读 [11-tool-result-budget](11-tool-result-budget.md) 学习预算控制

### 10.3 专家级

7. 阅读 [16-core-systems-deep-dive](16-core-systems-deep-dive.md) 深度分析
8. 研究源码实现,理解设计权衡
9. 参与改进计划,贡献优化方案

---

## 十一、术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| 任务状态机 | Task State Machine | 管理任务生命周期的状态转换系统 |
| AbortController | AbortController | JavaScript 标准的中止信号机制 |
| 弱引用 | WeakRef | 不阻止垃圾回收的引用 |
| TOCTOU | Time-of-Check to Time-of-Use | 检查和使用之间的竞态条件 |
| 宽限期 | Grace Period | 任务完成后的保留时间 |
| 进程内 | In-Process | 运行在同一 Node.js 进程内 |
| 进程外 | Out-of-Process | 运行在独立进程 (tmux/iTerm2) |
| 上下文压缩 | Context Compaction | 压缩对话历史以节省 token |
| 工具结果预算 | Tool Result Budget | 控制工具输出大小的机制 |
| Prompt Cache | Prompt Cache | Anthropic API 的缓存机制 |

---

## 十二、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-04-09 | 初始版本,创建架构总览 |
| 2.0 | 2026-04-09 | 重构为导航文档,添加重构计划 |

---

## 附录 A: 文档统计

| 文档 | 行数 | 图表数 | 代码片段 | 完成度 |
|------|------|--------|----------|--------|
| 01-task-state-machine | 862 | 3 | 15 | 100% |
| 02-parent-child-management | 669 | 4 | 12 | 100% |
| 03-task-eviction | 607 | 3 | 10 | 100% |
| 04-multi-agent-collaboration | 526 | 5 | 8 | 100% |
| 05-in-process-teammate | 76 | 0 | 0 | 30% |
| 06-plan-mode-approval | 82 | 0 | 2 | 30% |
| 07-shutdown-protocol | 90 | 0 | 3 | 30% |
| 08-context-sharing | 91 | 0 | 2 | 30% |
| 09-architecture-overview | 179 | 5 | 0 | 60% |
| 10-compact-mechanism | 706 | 12 | 20 | 100% |
| 11-tool-result-budget | 559 | 8 | 18 | 100% |
| 16-core-systems-deep-dive | 741 | 0 | 25 | 100% |

**总计**: 5,188 行, 40 张图表, 115 个代码片段

---

## 附录 B: 快速参考

### 关键常量

```typescript
// 任务管理
POLL_INTERVAL_MS = 1000              // 轮询间隔
PANEL_GRACE_MS = 30_000              // 宽限期
TEAMMATE_MESSAGES_UI_CAP = 50        // 消息上限

// 上下文压缩
AUTOCOMPACT_BUFFER_TOKENS = 13_000   // 自动压缩缓冲
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3  // 熔断器
MAX_PTL_RETRIES = 3                  // PTL 重试次数

// 工具预算
DEFAULT_MAX_RESULT_SIZE_CHARS = 50_000    // 单结果持久化上限
MAX_TOOL_RESULT_TOKENS = 100_000          // 单结果绝对上限
MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 200_000  // 消息级预算
```

### 核心文件

```
src/utils/task/framework.ts          # 任务状态机
src/utils/abortController.ts         # AbortController 链
src/services/compact/compact.ts      # Compact 压缩
src/utils/toolResultStorage.ts       # 工具结果预算
src/tools/SendMessageTool/           # 消息传递
```

---

**文档维护者**: AI 深度分析  
**反馈渠道**: 请提交 Issue 或 PR  
**更新频率**: 随源码更新同步
