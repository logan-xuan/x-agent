# Runtime 重构路线图

> 目标：结合当前代码结构，按可落地、可回滚的顺序完成 runtime 架构升级。

---

## 1. 总体策略

不做 big bang 重写，采用四阶段收敛：

1. 先稳定单任务回合
2. 再统一上下文与压缩
3. 再收敛 session / route / lane
4. 最后开放 bounded subagent

原则：

- 每阶段都要保持外部 API 基本兼容
- 每阶段都能单独验收
- 每阶段都先抽接口，再迁移实现

---

## 2. 当前代码基线

### 2.1 回合执行

- `backend/src/agent_core/agent_loop.py`
- `backend/src/agent_core/agent.py`
- `backend/src/agent_core/tool_executor.py`
- `backend/src/tools/manager.py`
- `backend/src/services/llm/router.py`

### 2.2 上下文与压缩

- `backend/src/conversation/system_prompt_builder.py`
- `backend/src/conversation/context_loader.py`
- `backend/src/services/context/`
- `backend/src/services/compression/`
- `backend/src/memory/manager.py`

### 2.3 session 与 gateway

- `backend/src/gateway/dispatcher.py`
- `backend/src/gateway/agent_invoker.py`
- `backend/src/gateway/session_resolver.py`
- `backend/src/conversation/session.py`
- `backend/src/api/v1/sessions.py`

---

## 3. Phase 1: Turn Controller 收敛

### 3.1 目标

在不改变 session 和 gateway 语义的前提下，先把单任务回合稳定下来。

### 3.2 交付物

- `TurnState`
- `BudgetManager`
- `ToolGovernor`
- `AssessmentEngine`
- `FinishReason`

### 3.3 建议动作

1. 从 `agent_loop.py` 提取显式状态对象
2. 将预算判断从 loop 分支中抽成 `BudgetManager`
3. 将 tool 次数和重复签名治理抽成 `ToolGovernor`
4. 先接入只读 `AssessmentEngine`
5. 再逐步把“是否继续”权力迁移到 controller

### 3.4 验收

- loop 有显式状态对象
- 有统一 finish reason
- 可以识别收益递减
- 可以在预算逼近时稳定收尾

---

## 4. Phase 2: Context & Compression 收敛

### 4.1 目标

把历史、prompt、artifact、compression 变成统一运行时能力。

### 4.2 交付物

- `SystemPromptBuilderV2`
- `ContextBuilder`
- `ArtifactStore`
- `CompressionProfile`
- `CompressionPipeline`
- `CompressionVerifier`

### 4.3 建议动作

1. 从 `system_prompt_builder.py` 抽三层 prompt build
2. 从 `conversation/session.py` 拆出 active history view
3. 用 `ArtifactStore` 吸收大工具输出
4. 将 `services/compression/` 收敛成 pipeline
5. 把 `memory/manager.py` 中与压缩前归档相关逻辑接入 `memory_flush`

### 4.4 验收

- active context 与 raw transcript 分离
- 大结果不再长期保留在 active context
- 压缩逻辑不再分散在多个入口
- 有 emergency compression 和 post-check

---

## 5. Phase 3: Session Orchestrator 收敛

### 5.1 目标

把 session、route、lane、announce 从 gateway 分支逻辑中收敛成控制平面。

### 5.2 交付物

- `Session`
- `RouteMeta`
- `SessionStore`
- `LaneScheduler`
- `RouteResolver`
- `SessionOrchestrator`

### 5.3 建议动作

1. 从 `conversation/session.py` 中抽离会话模型
2. 从 `gateway/session_resolver.py` 抽离 route 解析
3. 从 `gateway/dispatcher.py` 与 `agent_invoker.py` 抽离统一 orchestrator
4. 为 lane 添加显式并发和排队策略
5. 把 `api/v1/sessions.py` 接到新的 session store

### 5.4 验收

- session 生命周期显式化
- route 与 lane 独立存在
- gateway 调度入口简化
- child session 能被控制平面管理

---

## 6. Phase 4: Bounded Subagent

### 6.1 目标

在前 3 个阶段稳定后，再开放 child session / subagent。

### 6.2 交付物

- `SpawnPacket`
- `ChildResult`
- `SpawnManager`
- `AnnouncementManager`

### 6.3 建议动作

1. 定义 child session 的输入输出协议
2. 限制 child session 默认 budget
3. 限制 child 默认 prompt mode 为 `minimal`
4. 限制 child 默认不暴露 session tools
5. 限制 child 默认不能继续 spawn

### 6.4 验收

- child session 真正独立
- parent 只接收结构化结果
- announce 协议稳定
- 不会把主上下文拖爆

---

## 7. 推荐实施顺序

### Sprint 1

- `TurnState`
- `BudgetManager`
- `FinishReason`

### Sprint 2

- `ToolGovernor`
- `AssessmentEngine`
- loop 收敛

### Sprint 3

- `SystemPromptBuilderV2`
- `ContextBuilder`
- `ArtifactStore`

### Sprint 4

- `CompressionProfile`
- `CompressionPipeline`
- `CompressionVerifier`

### Sprint 5

- `Session`
- `RouteMeta`
- `SessionStore`
- `LaneScheduler`

### Sprint 6

- `SessionOrchestrator`
- `SpawnPacket`
- `ChildResult`
- `AnnouncementManager`

---

## 8. 风险与控制

### 风险 1：loop 重构过早影响线上行为

控制方式：

- 先抽状态对象和 manager，不立即改流程
- 逐步把分支迁入 controller

### 风险 2：压缩改动破坏历史语义

控制方式：

- 引入 post-check
- 保留 raw transcript
- 压缩失败时允许 rollback

### 风险 3：session 与 gateway 改造过大

控制方式：

- 先抽 store 和 resolver
- 最后才替换 orchestrator 主入口

### 风险 4：subagent 过早开放导致系统复杂度激增

控制方式：

- 必须在前 3 阶段完成后再开放
- 默认 depth=1
- 默认 child 不可继续 spawn

---

## 9. 最终验收标准

全部阶段完成后，应满足：

- 单任务回合有显式收敛控制
- 上下文有统一构建与压缩管道
- session 有明确控制平面
- child session 通过结构化协议接入
- 主线程不再承担所有原始搜索/工具轨迹

这时 runtime 才真正从“一个会调用模型和工具的循环”升级为“一个可长期运行、可并行扩展的 agent 系统”。
