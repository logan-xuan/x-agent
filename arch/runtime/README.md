# Agent Runtime 总体架构方案

> 目标：先把单任务回合内的结果获取能力做稳定，再把长期多 session / subagent 并行编排做成系统能力。

---

## 1. 文档结构

本目录是新的 runtime 设计入口，不复用旧版架构文档。

- [01-turn-controller.md](./01-turn-controller.md)
  - 单任务循环、预算、收敛、tool 治理
- [02-context-and-compression.md](./02-context-and-compression.md)
  - system prompt build、历史消息、artifact、压缩策略
- [03-session-orchestrator.md](./03-session-orchestrator.md)
  - session 生命周期、lane、route、spawn、announce
- [04-refactor-roadmap.md](./04-refactor-roadmap.md)
  - 结合现有代码结构的分阶段改造顺序
- [05-runtime-interfaces.md](./05-runtime-interfaces.md)
  - Python 模块边界、核心接口、状态对象、协议定义
- [06-config-schema.md](./06-config-schema.md)
  - runtime 配置模型、Pydantic schema、兼容迁移方案
- [07-data-model-and-storage.md](./07-data-model-and-storage.md)
  - transcript、session state、artifact、summary chain 的持久化模型
- [08-execution-sequences.md](./08-execution-sequences.md)
  - 单任务回合、压缩触发、spawn child、announce 回传的执行时序
- [09-implementation-tasks.md](./09-implementation-tasks.md)
  - 按 phase / sprint 拆解的可执行实施任务清单
- [10-test-strategy.md](./10-test-strategy.md)
  - runtime 的单元、集成、时序、回归与性能测试设计

建议阅读顺序：

1. 本文
2. `01-turn-controller.md`
3. `02-context-and-compression.md`
4. `03-session-orchestrator.md`
5. `04-refactor-roadmap.md`
6. `05-runtime-interfaces.md`
7. `06-config-schema.md`
8. `07-data-model-and-storage.md`
9. `08-execution-sequences.md`
10. `09-implementation-tasks.md`
11. `10-test-strategy.md`

---

## 2. 为什么重构

当前系统已经具备以下基础能力：

- `backend/src/agent_core/`：Agent loop、tool executor、middleware、ports/adapters
- `backend/src/conversation/`：context、session、system prompt builder
- `backend/src/services/context/`：session state、artifact、evidence 相关能力
- `backend/src/services/compression/`：压缩管理与 token 统计
- `backend/src/gateway/`：dispatcher、session resolver、agent invoker、message bus
- `backend/src/memory/`：memory manager、md sync、context builder

但这些能力目前仍然偏分散：

- 单任务循环的停止条件、预算、工具治理没有统一 controller
- prompt build、历史消息、压缩、artifact 的边界还不够清晰
- session / route / spawn / announce 还没有被收敛成明确的 orchestrator
- 要做长任务和多 agent，容易把复杂性直接压给主 loop

所以新的架构目标不是推翻现有代码，而是把已有能力重新收敛成三个明确子系统：

1. Turn Controller
2. Context & Compression
3. Session Orchestrator

---

## 3. 总体设计目标

### 3.1 第一优先级

先解决“单个任务回合如何稳定拿结果”：

- 有明确 `maxTurns`
- 有 token / tool / cost / wall time 预算
- 有收益递减检测
- 有 tool result 长度控制
- 有重复调用与重复失败熔断
- 在长任务里仍然保持准确性和稳定性

### 3.2 第二优先级

再解决“长期多 session 如何并行运行”：

- session 生命周期独立
- route 和 lane 独立
- child session 独立上下文和预算
- parent 只接收结构化 child result
- subagent 变成 bounded runtime，而不是 prompt 技巧

---

## 4. 目标总体架构

```text
User / Channel Event
-> Gateway / API Entry
-> Session Orchestrator
-> Turn Controller
   -> Budget Manager
   -> Context Builder
   -> Compression Pipeline
   -> Model Caller
   -> Tool Executor
   -> Assessment Engine
-> Final Answer | Continue | Compact | Spawn Child Session | Archive

Stores:
- Transcript Store
- Session Store
- Artifact Store
- Memory Store
- Telemetry Store
```

### 4.1 三个核心子系统

| 子系统 | 职责 | 核心目标 |
|---|---|---|
| Turn Controller | 单任务回合循环与收敛控制 | 稳定拿结果 |
| Context & Compression | prompt、历史、artifact、压缩 | 控制上下文膨胀 |
| Session Orchestrator | session、route、lane、spawn | 长期并行编排 |

---

## 5. 当前代码到目标架构的映射

### 5.1 Turn Controller 相关

现有基础：

- `backend/src/agent_core/agent_loop.py`
- `backend/src/agent_core/agent.py`
- `backend/src/agent_core/tool_executor.py`
- `backend/src/agent_core/tool_middleware.py`
- `backend/src/services/llm/router.py`
- `backend/src/tools/manager.py`

目标收敛：

- 这些能力应被重构为一个显式的 `TurnController`
- 预算、停止条件、tool policy、assessment 从 loop 中拆出

### 5.2 Context & Compression 相关

现有基础：

- `backend/src/conversation/system_prompt_builder.py`
- `backend/src/conversation/context_loader.py`
- `backend/src/conversation/session.py`
- `backend/src/services/context/`
- `backend/src/services/compression/`
- `backend/src/memory/manager.py`

目标收敛：

- 统一 `ContextBuilder`
- 统一 `ArtifactStore`
- 统一 `CompressionPipeline`
- 统一 active history / summary chain / raw transcript 视图

### 5.3 Session Orchestrator 相关

现有基础：

- `backend/src/gateway/dispatcher.py`
- `backend/src/gateway/agent_invoker.py`
- `backend/src/gateway/session_resolver.py`
- `backend/src/gateway/message_bus.py`
- `backend/src/api/v1/sessions.py`
- `backend/src/conversation/identity.py`

目标收敛：

- 统一 `SessionOrchestrator`
- 统一 session lifecycle
- 统一 lane 调度
- 统一 spawn / announce / route

---

## 6. 设计原则

### 6.1 controller 决策高于模型建议

- 模型可以建议下一步做什么
- runtime 决定是否继续、是否压缩、是否结束、是否 spawn

### 6.2 原始大结果不上主上下文

- 网页正文、搜索结果集、长命令输出、超长 tool result 进入 artifact store
- 主上下文只保留 preview、summary、artifact ref

### 6.3 历史不是原始数组，而是多层视图

- raw transcript
- summary chain
- active history
- model input

### 6.4 子任务默认隔离

- 独立 session
- 独立 transcript
- 独立 budget
- 独立 prompt mode
- parent 只拿结构化结果

### 6.5 先做单任务稳定，再开放多 agent

如果主 loop 还不能稳定收敛，过早开放 session_spawn 只会把混乱并行化。

---

## 7. 推荐模块边界

### 7.1 第一层：单任务回合

- `TurnController`
- `BudgetManager`
- `AssessmentEngine`
- `ToolGovernor`
- `ModelInvoker`

详见 [01-turn-controller.md](./01-turn-controller.md)

### 7.2 第二层：上下文与压缩

- `SystemPromptBuilderV2`
- `ContextBuilder`
- `HistoryViewBuilder`
- `ArtifactStore`
- `CompressionPipeline`

详见 [02-context-and-compression.md](./02-context-and-compression.md)

### 7.3 第三层：session 与并行编排

- `SessionOrchestrator`
- `SessionStore`
- `LaneScheduler`
- `RouteResolver`
- `SpawnManager`
- `AnnouncementManager`

详见 [03-session-orchestrator.md](./03-session-orchestrator.md)

### 7.4 第四层：接口与配置

- `RuntimeInterfaces`
- `RuntimeConfig`
- `BudgetProfile`
- `CompressionProfile`
- `SessionProfile`

详见 [05-runtime-interfaces.md](./05-runtime-interfaces.md) 和 [06-config-schema.md](./06-config-schema.md)

### 7.5 第五层：数据与时序

- `StorageModels`
- `SessionStateSnapshot`
- `SummaryChain`
- `ExecutionSequences`

详见 [07-data-model-and-storage.md](./07-data-model-and-storage.md) 和 [08-execution-sequences.md](./08-execution-sequences.md)

---

## 8. 改造策略

这次重构应采用“分层收敛，不做 big bang”的方式。

### Phase 1

先把单任务 loop 收敛成 `TurnController`：

- 不改变外部 API
- 不先动 session / gateway 语义
- 优先让回合内预算、tool 次数、停止条件变得稳定

### Phase 2

再把上下文和压缩收敛成统一 pipeline：

- prompt build
- active history
- artifact refs
- compression profile
- emergency compression

### Phase 3

最后再引入 `SessionOrchestrator`：

- session lifecycle
- lane
- route
- child session
- announce

详见 [04-refactor-roadmap.md](./04-refactor-roadmap.md)

---

## 9. 最终交付形态

最终应该形成一套稳定的 runtime：

- 单任务回合由 `TurnController` 有界驱动
- 上下文由 `ContextBuilder + CompressionPipeline` 统一管理
- 长期多会话由 `SessionOrchestrator` 统一调度

这样才能同时满足：

- 单任务拿结果的能力
- 长期多 session 并行能力
- 可维护、可演进、可调参的系统形态

## 10.工作流程要求
1、你将拥有所有权限 每写一个phase 完成code review和测试验证后 自动通过git提交工作区的代码。 
2、提交完代码后，继续严格按照计划和设计进行下一步工作，每个小功能要按照测试要求进行测试验证和codereview，如此循环。
3、当达到可以小范围端到端测试验证时，你需要通过mcp 调用 chrome devtool 进行端到端的测试。
4、为了确保专业性，code review 和测试验证需要启用专门的subagent 身份如执行这项工作，各subagent 将执行结构回传各main agent，再决策做下一步工作。
5、始终尊崇arch/runtime/README.md 指导，查阅相关tasks和设计方案文档，不偏离设计和任务主线。