# Runtime Test Strategy

> 目标：为新的 runtime 架构提供一套可落地的测试设计，覆盖单任务回合、上下文与压缩、session 编排、child session，以及关键失败路径的回归保护。

---

## 1. 范围

本测试策略覆盖以下子系统：

- `TurnController`
- `BudgetManager`
- `ToolGovernor`
- `AssessmentEngine`
- `ContextBuilder`
- `CompressionPipeline`
- `CompressionVerifier`
- `SessionOrchestrator`
- `LaneScheduler`
- `SpawnManager`
- `AnnouncementManager`

不直接覆盖：

- 第三方模型供应商的真实稳定性
- 外部渠道平台自身的可用性
- 非本仓库维护的外部工具行为

这些内容应通过 stub / fake / mock 或专项联调验证。

---

## 2. 与现有测试结构对齐

当前后端测试主要在：

- `backend/tests/unit`
- `backend/tests/integration`

已有相关测试基础包括：

- [test_runtime_budget_controls.py](/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_runtime_budget_controls.py)
- [test_compressor.py](/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_compressor.py)
- [test_context_builder.py](/Users/xuan.lx/Documents/x-agent/backend/tests/unit/test_context_builder.py)
- [test_context_flow.py](/Users/xuan.lx/Documents/x-agent/backend/tests/integration/test_context_flow.py)

建议保持当前组织方式，不额外引入复杂目录树。

推荐新增测试文件命名：

- `backend/tests/unit/test_runtime_turn_controller.py`
- `backend/tests/unit/test_runtime_budget_manager.py`
- `backend/tests/unit/test_runtime_tool_governor.py`
- `backend/tests/unit/test_runtime_assessment_engine.py`
- `backend/tests/unit/test_runtime_context_builder.py`
- `backend/tests/unit/test_runtime_compression_pipeline.py`
- `backend/tests/unit/test_runtime_compression_verifier.py`
- `backend/tests/unit/test_runtime_session_orchestrator.py`
- `backend/tests/unit/test_runtime_lane_scheduler.py`
- `backend/tests/unit/test_runtime_spawn_manager.py`
- `backend/tests/unit/test_runtime_announcement_manager.py`
- `backend/tests/integration/test_runtime_turn_flow.py`
- `backend/tests/integration/test_runtime_compression_flow.py`
- `backend/tests/integration/test_runtime_session_flow.py`
- `backend/tests/integration/test_runtime_child_session_flow.py`
- `backend/tests/integration/test_runtime_resume_flow.py`

---

## 3. 测试分层

### 3.1 单元测试

目标：

- 验证单个模块的纯逻辑
- 覆盖边界条件、异常分支、回退逻辑
- 不依赖数据库、网络、真实模型

特点：

- 使用 fake / mock
- 运行快
- 精准定位逻辑错误

### 3.2 集成测试

目标：

- 验证多个 runtime 模块串联后是否符合预期
- 覆盖 session、context、compression、controller 联动行为

特点：

- 可用 sqlite / 临时目录 / fake provider
- 允许触发真实 repository / adapter
- 不依赖真实外部 API

### 3.3 时序测试

目标：

- 验证关键执行顺序没有错位
- 验证压缩、spawn、announce、resume 等跨模块流程

建议归入 `integration`，不单独再建新目录。

### 3.4 回归测试

目标：

- 保护历史上容易出错的行为
- 针对具体 bug 建立最小 reproducer

建议：

- 仍放在 `unit` 或 `integration`
- 文件名上保留问题语义，不必强行新建 `regression/`

### 3.5 性能与稳定性测试

目标：

- 验证长上下文、长工具输出、连续多轮不会明显退化
- 验证压缩前后 token、延迟、状态一致性

建议初期：

- 先不进入常规 CI 阻塞项
- 可放在 `backend/scripts/` 或后续独立 `tests/perf`

---

## 4. 测试环境策略

### 4.1 推荐依赖替身

| 依赖 | 替身策略 |
|---|---|
| LLM provider | fake provider / stub stream |
| Tool manager | fake tool set |
| Artifact store | 临时目录 / in-memory store |
| Session store | sqlite in-memory 或 fake repository |
| Gateway route | stub route resolver |
| Outbound delivery | fake announcement sink |

### 4.2 推荐 fixture

建议增加基础 fixture：

- `temp_workspace`
- `fake_runtime_config`
- `fake_session_descriptor`
- `fake_task_frame`
- `fake_artifact_store`
- `fake_session_store`
- `fake_llm_router`
- `fake_tool_executor`

这些 fixture 可以逐步沉淀到：

- `backend/tests/conversation/conftest.py`
- 或新增 `backend/tests/conftest.py`

---

## 5. TurnController 测试设计

### 5.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_turn_controller.py`

核心用例：

1. 正常完成
   - 给定有限轮内可完成任务
   - 应返回 `kind="final"`
   - 应带上正确 `FinishReason`
2. 达到 `maxTurns`
   - 达到阈值后停止
   - 不继续进入下一轮
3. 达到 `maxToolCalls`
   - budget 命中后停止
4. 达到 `maxWallTimeMs`
   - budget 命中后停止
5. assessment 判定为 `continue`
   - 正常进入下一轮
6. assessment 判定为 `compact`
   - 应调用 `CompressionPipeline`
7. assessment 判定为 `spawn`
   - 不直接执行 child loop
   - 返回 `SpawnPacket`
8. assessment 判定为 `abort`
   - 返回 `controller_abort`
9. 工具重复签名过多
   - 进入 breaker / diminishing returns
10. 连续失败簇重复
   - 正确停止而不是无限重试

### 5.2 断言重点

- turn 计数正确
- `FinishReason` 正确
- `SpawnPacket` 是否被返回
- 压缩调用是否发生
- 不会在无进展时无限循环

---

## 6. BudgetManager 测试设计

### 6.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_budget_manager.py`

核心用例：

1. 未达预算 -> `ok`
2. 命中 `maxTurns` -> `stop`
3. 命中 `maxToolCalls` -> `stop`
4. 命中 per-tool 限额 -> `stop`
5. 命中 wall time -> `stop`
6. token 进入 compact trigger -> `compact`
7. token 进入 hard stop -> `stop`
8. 预算边界值刚好命中时的判定

### 6.2 回归点

- 不要出现 `<` / `<=` 边界错误
- 不要出现多个预算同时命中时 reason 不稳定

---

## 7. ToolGovernor 测试设计

### 7.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_tool_governor.py`

核心用例：

1. 工具调用签名规范化
2. 相同参数签名重复识别
3. 相同工具不同参数不应误判重复
4. per-tool `max_uses_per_turn` 生效
5. tool timeout 约束能被读取
6. subagent 禁用工具时正确拒绝
7. 高风险工具 cost weight 读取正确

### 7.2 断言重点

- 签名 hash 稳定
- 重复调用限制精确
- policy 读取优先级正确

---

## 8. AssessmentEngine 测试设计

### 8.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_assessment_engine.py`

核心用例：

1. unresolved 下降 -> `continue`
2. novelty 持续下降 -> `finish`
3. 重复签名调用过多 -> `finish`
4. 连续失败簇重复 -> `finish`
5. assessment 返回 `compact`
6. assessment 返回 `spawn`

### 8.2 回归点

- 收益递减规则不要过于激进，导致过早结束
- 也不要太宽松，导致循环发散

---

## 9. ContextBuilder 测试设计

### 9.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_context_builder.py`

核心用例：

1. `full` prompt mode
2. `minimal` prompt mode
3. `none` prompt mode
4. 稳定前缀与动态尾部拼装顺序正确
5. active history 与 raw transcript 分离
6. artifact refs 注入正确
7. budget 信息注入正确

### 9.2 集成测试用例

建议文件：

- `backend/tests/integration/test_runtime_turn_flow.py`

核心用例：

1. 从 session state + summary chain + recent transcript 重建 active view
2. resume 时不需要重放全量 transcript

---

## 10. CompressionPipeline 测试设计

### 10.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_compression_pipeline.py`
- `backend/tests/unit/test_runtime_compression_verifier.py`

核心用例：

1. single result persist
2. aggregate result budget
3. TTL prune
4. microcompact
5. collapse
6. autocompact
7. memory flush
8. `minCompressionGainTokens` 生效
9. verifier 通过时提交
10. verifier 失败时 rollback
11. emergency compression fallback summary

### 10.2 必测边界

1. 图像 / 二进制结果跳过 prune
2. 最近 assistant tail 被保护
3. `P0/P1` 信息未丢失
4. 压缩后 token 确实下降
5. 压缩失败时不会无限重试

### 10.3 集成测试用例

建议文件：

- `backend/tests/integration/test_runtime_compression_flow.py`

核心用例：

1. 长工具输出进入 artifact store
2. 构建 active view 时只保留 preview
3. prompt too long -> emergency compression -> retry

---

## 11. SessionOrchestrator 测试设计

### 11.1 单元测试用例

建议文件：

- `backend/tests/unit/test_runtime_session_orchestrator.py`
- `backend/tests/unit/test_runtime_lane_scheduler.py`

核心用例：

1. resolve existing session
2. create new session
3. session lifecycle 状态更新
4. lane enqueue / depth 统计
5. archive 行为
6. child session create

### 11.2 集成测试用例

建议文件：

- `backend/tests/integration/test_runtime_session_flow.py`

核心用例：

1. Gateway event -> session resolved -> turn enqueued
2. 系统触发入口复用相同 orchestrator
3. session archive 后不再进入 active 调度

---

## 12. Child Session / Subagent 测试设计

### 12.1 集成测试用例

建议文件：

- `backend/tests/integration/test_runtime_child_session_flow.py`

核心用例：

1. `TurnController` 返回 `SpawnPacket`
2. `SessionOrchestrator` 创建 child session
3. child session 使用 `minimal` prompt
4. child session 使用 child budget profile
5. child session 默认 `max_spawns = 0`
6. child 完成后生成 `ChildResult`
7. parent 只收到结构化 child result
8. child transcript 不会回灌 parent active context

### 12.2 AnnouncementManager 测试

建议文件：

- `backend/tests/unit/test_runtime_announcement_manager.py`

核心用例：

1. 正常 announce
2. parent busy -> queue announce
3. route 丢失 -> fallback queue / retry
4. announce payload 包含 status、summary、artifact refs、usage

---

## 13. Resume / Reconnect 测试设计

### 13.1 集成测试用例

建议文件：

- `backend/tests/integration/test_runtime_resume_flow.py`

核心用例：

1. session reconnect 能恢复 route
2. 能从 `SessionStateSnapshot` 恢复 task frame
3. 能从 summary chain + recent transcript 重建 active view
4. resume 后继续下一轮而不是从头开始

---

## 14. 数据层测试设计

### 14.1 单元测试

建议文件：

- `backend/tests/unit/test_runtime_session_repository.py`
- `backend/tests/unit/test_runtime_summary_repository.py`
- `backend/tests/unit/test_runtime_artifact_repository.py`
- `backend/tests/unit/test_runtime_state_snapshot_repository.py`

核心用例：

1. session record create/get/patch
2. summary chain append/query
3. artifact put/get/dedupe
4. state snapshot save/load latest

### 14.2 集成测试

核心用例：

1. turn 完成后 transcript 和 snapshot 同时落库
2. compaction 后 summary record 与 compression event 同步写入

---

## 15. 回归测试清单

以下问题应建立回归用例：

1. tool result 被截断后丢失关键信息
2. 压缩后 role ordering 损坏
3. budget 命中后仍然继续下一轮
4. 相同工具调用无限重试
5. child transcript 被错误回灌到 parent
6. parent busy 时 child announce 丢失
7. resume 时从全量 transcript 重建过慢或状态错误
8. emergency compression 后仍重复 compact 死循环

---

## 16. 性能与稳定性测试

### 16.1 建议初期不进阻塞 CI

建议先做脚本级或 nightly：

- 长历史 1000+ entries 构建 active view
- 大工具输出 1MB+ artifact persist
- 连续 20 轮 turn controller 压力测试
- 10 个 child session 排队 / announce 测试

### 16.2 关键指标

- active view build latency
- compression latency
- tokens before / after compression
- session enqueue wait time
- child announce delivery latency

---

## 17. Mock / Fake 策略

### 17.1 推荐优先级

优先使用：

1. fake repository
2. fake llm provider
3. fake tool executor
4. sqlite in-memory
5. 临时目录 artifact store

尽量避免：

- 大量 patch 私有函数
- 直接 mock 整个 controller 主流程

原则是优先测真实模块边界，而不是 mock 掉一切。

---

## 18. CI 建议

### 18.1 PR 阻塞项

- unit tests
- 关键 integration tests
- 回归测试

### 18.2 非阻塞项

- 长时性能测试
- 大上下文压力测试
- 多 child session 并发测试

---

## 19. 推荐落地顺序

### 第一批

- `test_runtime_budget_manager.py`
- `test_runtime_turn_controller.py`
- `test_runtime_tool_governor.py`
- `test_runtime_assessment_engine.py`

### 第二批

- `test_runtime_context_builder.py`
- `test_runtime_compression_pipeline.py`
- `test_runtime_compression_verifier.py`
- `test_runtime_compression_flow.py`

### 第三批

- `test_runtime_session_orchestrator.py`
- `test_runtime_lane_scheduler.py`
- `test_runtime_session_flow.py`
- `test_runtime_child_session_flow.py`
- `test_runtime_resume_flow.py`

---

## 20. 验收标准

测试策略补齐后，应满足：

- 新 runtime 每个子系统都有明确测试层级
- 文件命名与现有 `backend/tests` 结构一致
- 核心失败路径都有回归点
- 可以直接指导后续代码实现时同步补测试

如果没有这一层，runtime 实现很快会再次回到“先写功能，后补保护”的状态。
