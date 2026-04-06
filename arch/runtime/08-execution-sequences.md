# Runtime Execution Sequences 详细方案

> 范围：关键运行时流程的时序与执行顺序，包括单任务回合、压缩触发、child session spawn、announce 回传，以及与当前 gateway/agent 调用链的映射。

---

## 1. 目标

这份文档解决的是“系统具体怎么跑”。

重点不是模块定义，而是：

- 入口事件进入后，调用链如何流动
- 哪些步骤在 controller
- 哪些步骤在 context/compression
- 哪些步骤在 orchestrator

---

## 2. 当前调用链基线

当前有两个典型入口：

### 2.1 用户入口

相关代码：

- [dispatcher.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/dispatcher.py)
- [agent_bridge.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_bridge.py)

大致链路：

```text
GatewayDispatcher.dispatch()
-> resolve agent
-> build context identity
-> ensure session
-> AgentBridge.create_agent()
-> AgentBridge.load_session_history()
-> agent loop
-> persist messages
-> push to client
```

### 2.2 系统触发入口

相关代码：

- [agent_invoker.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_invoker.py)

大致链路：

```text
AgentInvoker.invoke()
-> resolve session
-> build internal context
-> ensure session
-> create agent
-> load history
-> run agent loop
-> push / queue outbound
```

目标架构不是改变这两个入口的外部语义，而是让它们统一收口到：

- `SessionOrchestrator`
- `TurnController`
- `ContextRuntime`

---

## 3. 序列一：普通用户消息 -> 单任务回合

### 3.1 目标时序

```text
Gateway Event
-> SessionOrchestrator.resolveOrCreate()
-> LaneScheduler.enqueue(main)
-> ContextBuilder.build()
-> CompressionPipeline.run()
-> TurnController.run()
   -> BudgetManager.evaluate()
   -> ModelInvoker.plan()
   -> ToolGovernor.validate()
   -> ToolExecutor.execute()
   -> AssessmentEngine.assess()
-> SessionStateSnapshot.persist()
-> Transcript persist
-> Gateway response
```

### 3.2 详细步骤

1. Gateway 收到消息
2. RouteResolver 解析 route
3. SessionOrchestrator 解析或创建 `SessionDescriptor`
4. 将任务放入 lane
5. ContextBuilder 生成：
   - system prompt
   - active history
   - active artifact refs
6. CompressionPipeline 预压缩
7. TurnController 开始循环
8. 每轮执行：
   - budget check
   - model call
   - tool governance
   - tool execution
   - assessment
9. 输出最终结果
10. 持久化 transcript 和 state snapshot
11. 返回给 gateway 端点

### 3.3 伪代码

```python
async def handle_user_event(event: GatewayEvent) -> None:
    session = await orchestrator.resolve_or_create(event)

    async def run():
        context_result = await context_builder.build(...)
        compressed = await compression_pipeline.run(...)
        turn_result = await turn_controller.run(...)

        await transcript_repo.append(...)
        await state_snapshot_repo.save(...)
        await gateway_adapter.emit(turn_result)

    await lane_scheduler.enqueue(session.lane, run)
```

---

## 4. 序列二：单任务回合内部循环

### 4.1 目标时序

```text
bootstrap
-> budget check
-> plan
-> govern tool usage
-> execute tools / model
-> observe result
-> assess progress
-> decide continue / finish / compact / spawn / abort
```

### 4.2 各组件职责

| 步骤 | 组件 |
|---|---|
| budget check | `BudgetManager` |
| plan | `ModelInvoker` |
| govern | `ToolGovernor` |
| execute | `ToolExecutor` |
| assess | `AssessmentEngine` |
| decide | `TurnController` |

### 4.3 关键分支

#### continue

- 更新 `TurnState`
- 保留 active context
- 下一轮前再做 budget + compression check

#### finish

- 生成结构化 `TurnResult`
- 带上 `FinishReason`

#### compact

- 调用 `CompressionPipeline`
- 重建 active context
- 再回到下一轮

#### spawn

- 不直接在 controller 里创建 child session
- 只返回 `SpawnPacket`
- 由 `SessionOrchestrator` 接手

---

## 5. 序列三：压缩触发

### 5.1 正常压缩时序

```text
ContextBuilder.build()
-> estimate tokens
-> CompressionPipeline.run()
   -> persist stage
   -> aggregate budget stage
   -> ttl prune stage
   -> microcompact stage
   -> collapse stage
   -> autocompact stage
   -> memory flush stage
-> CompressionVerifier.verify()
-> commit compressed active view
```

### 5.2 何时触发

- 每次模型调用前
- 工具执行后，若新增大结果且估计会推高上下文
- session resume 时，若历史过长

### 5.3 Emergency Compression 时序

```text
model returns prompt_too_long / context_overflow
-> CompressionPipeline.run_emergency()
-> fallback summary if needed
-> rebuild active context
-> retry current turn
-> if still fails: reset session / best effort stop
```

---

## 6. 序列四：系统触发 / cron / webhook

### 6.1 目标时序

```text
External Trigger
-> SessionOrchestrator.resolveOrCreate()
-> LaneScheduler.enqueue(cron or followup)
-> ContextBuilder.build(minimal or normal)
-> TurnController.run()
-> Transcript / state snapshot persist
-> AnnouncementManager or outbound delivery
```

### 6.2 与用户入口的差异

- route 通常为内部 route
- prompt mode 可以更小
- 输出可能走 outbound queue，而不是 websocket 实时推送

### 6.3 对应现有代码

当前对应入口主要在：

- [agent_invoker.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_invoker.py)

未来应收敛到 `SessionOrchestrator`，而不是由 invoker 自己拼完整链路。

---

## 7. 序列五：spawn child session

### 7.1 目标时序

```text
Parent TurnController
-> returns SpawnPacket
-> SessionOrchestrator.spawnChild()
-> SessionStore.create(child)
-> LaneScheduler.enqueue(subagent)
-> ContextBuilder.build(prompt_mode=minimal)
-> TurnController.run(child)
-> child result persisted
-> AnnouncementManager.enqueue(child result)
```

### 7.2 关键原则

- parent 不直接运行 child loop
- child 不共享 parent active context
- child 只拿 `SpawnPacket`
- child 默认不能再继续 spawn

### 7.3 SpawnPacket 内容

- objective
- deliverable
- constraints
- parent summary
- selected artifacts
- tool allowlist
- budget profile
- timeout

---

## 8. 序列六：child 完成 -> announce 回传

### 8.1 目标时序

```text
Child Turn completes
-> ChildResult generated
-> AnnouncementManager.build()
-> RouteResolver picks parent route
-> if parent idle: deliver immediately
-> if parent busy: enqueue announce
-> parent receives structured child result
```

### 8.2 父线程接回内容

父线程只接收：

- status
- summary
- unresolved
- artifact refs
- usage / duration

绝不能回灌 child 原始 transcript。

---

## 9. 序列七：session archive

### 9.1 目标时序

```text
Session becomes idle
-> LifecycleManager evaluates archive policy
-> if child and expired: archive
-> if main and inactive long enough: compact or archive
-> SessionRecord status update
-> active_transcript closed
-> summary chain retained
```

### 9.2 child session 默认策略

- child 完成后短时间内保留
- 到达 `child_auto_archive_ms` 后 archive
- transcript 仍可审计
- active state 不再参与调度

---

## 10. 序列八：resume / reconnect

### 10.1 目标时序

```text
Reconnect or resume request
-> SessionOrchestrator.load(session_key)
-> StateSnapshotRepository.get_latest()
-> SummaryRepository.get_latest_chain()
-> TranscriptRepository.get_recent_entries()
-> ContextBuilder.rebuild_active_view()
-> continue normal turn flow
```

### 10.2 关键原则

- resume 依赖 `SessionStateSnapshot`
- 不应从全量 transcript 重新推断所有 runtime 状态

---

## 11. 异常时序

### 11.1 Tool breaker

```text
same tool signature repeats
-> ToolGovernor marks repeated pattern
-> AssessmentEngine lowers novelty
-> TurnController stops with diminishing_returns / breaker
```

### 11.2 Compression invariant failure

```text
CompressionPipeline.run()
-> CompressionVerifier fails
-> rollback
-> emergency compression
-> if still fails: reset session / best effort finish
```

### 11.3 Session route failure

```text
AnnouncementManager.build()
-> RouteResolver fails
-> enqueue pending outbound
-> retry later or mark undelivered
```

---

## 12. 与现有代码的改造落点

### 12.1 用户入口

当前：

- `gateway/dispatcher.py`
- `gateway/agent_bridge.py`

目标：

- dispatcher 只做 envelope 入口
- orchestrator 接手 session + lane + turn 调度

### 12.2 系统触发入口

当前：

- `gateway/agent_invoker.py`

目标：

- invoker 只做 source adaptation
- orchestrator 接手实际执行链路

### 12.3 session 历史与压缩

当前：

- `conversation/session.py`
- `services/compression/`

目标：

- `ContextBuilder + CompressionPipeline + StateSnapshotRepository`

---

## 13. 验收标准

时序设计完成后，应满足：

- 用户入口、系统入口、child session 入口有统一目标链路
- 关键状态转换有明确归属
- spawn、announce、archive、resume 都有显式序列
- 能直接指导后续 controller/orchestrator 的实现顺序

如果时序不先明确，模块边界即使定义了，落地时仍然会回到“谁方便谁就做”的耦合状态。
