# Runtime Implementation Tasks

> 目标：把新的 runtime 架构方案拆成可执行、可验收、可并行推进的实施任务。

---

## 1. 实施原则

任务拆解遵循以下原则：

- 先稳定单任务回合，再推进上下文与压缩，再推进 session 编排
- 优先抽接口和状态对象，再迁移逻辑
- 每个阶段都可独立验收，不依赖一次性重写
- 能兼容当前代码路径，不做大爆炸替换

### 1.1 状态约定

- `[ ]` 未完成
- `[~]` 进行中
- `[x]` 已完成

约束：

- 每完成一个 task，必须在本文档中更新状态
- 已完成 task 优先补充对应代码入口、测试或提交号，便于下次直接续做
- 当前进行中的 task 只保留一个，避免状态漂移

### 1.2 当前焦点

- `[x] P3-T9`: 已为 `/api/v1/dev/runtime-turn` 补齐超时、阶段诊断和 fallback `output_text`
- `[x] P3-T7`: 已增加 `dev runtime-turn` 调试入口，提交：`c082d75`
- `[x] P3-T8`: 已把 runtime execution 默认桥接到 legacy agent path，提交：`f575531`、`c8aea4c`
- `[x] P3-T11`: 已修复前端 agent WebSocket URL 规范化，`VITE_WS_URL=ws://localhost:8888` 也会正确连接到 `/ws/agent/{session_id}`
- `[x] P3-T10`: 已定位并修复 `LLMRouter.chat` 的预探活阻塞。正常 chat 路径不再额外执行 provider health probe
- `[x] P3-T12`: 已为 `/api/v1/dev/runtime-turn` 增加 `disable_tools` fast mode，`8s` 调试窗口内可稳定返回最终文本
- `[x] P3-T13`: 已为 fast mode 增加 `disable_skills`，进一步压缩首 token 延迟
- `[ ] P3-T14`: 继续压缩 fast mode 首 token 到更短窗口。当前证据：`disable_tools=true` + `disable_skills=true` 下 `8s` 可稳定完成，但 `5s` 预算仍偏紧，首个 `text_chunk` 约在 `4.2s`

---

## 2. 总体阶段

| Phase | 目标 | 对应文档 |
|---|---|---|
| Phase 1 | Turn Controller 收敛 | `01-turn-controller.md` |
| Phase 2 | Context & Compression 收敛 | `02-context-and-compression.md` |
| Phase 3 | Session Orchestrator 收敛 | `03-session-orchestrator.md` |
| Phase 4 | Child Session / Subagent 接入 | `03-session-orchestrator.md` |
| Phase 5 | 数据层与执行链路收口 | `07-data-model-and-storage.md` / `08-execution-sequences.md` |

---

## 3. Phase 1: Turn Controller 收敛

### 3.1 目标

让单任务回合内的结果获取能力先稳定下来。

完成后应具备：

- 显式 `TurnState`
- 显式 `FinishReason`
- 显式 `BudgetManager`
- 初步 `ToolGovernor`
- 初步 `AssessmentEngine`

### 3.2 任务清单

#### [x] P1-T1: 新建 runtime 目录骨架

- 新建：
  - `backend/src/runtime/`
  - `backend/src/runtime/types.py`
  - `backend/src/runtime/turn/`
- 建立基础导出结构

验收：

- import 路径稳定
- 不影响现有运行逻辑

#### [x] P1-T2: 定义共享类型

- 实现：
  - `FinishReason`
  - `TaskFrame`
  - `RouteMeta`
  - `SessionDescriptor`
  - `ArtifactRef`

参考：

- `05-runtime-interfaces.md`

验收：

- 类型定义可被 turn / context / session 三层同时引用

#### [x] P1-T3: 提取 TurnState

- 在 `runtime/turn/state.py` 中定义 `TurnState`
- 从现有：
  - `backend/src/agent_core/agent_loop.py`
  - `backend/src/agent_core/agent.py`
  中梳理出 loop 所需显式状态

验收：

- loop 不再依赖大段隐式局部变量拼接状态

#### [x] P1-T4: 实现 FinishReason 模型

- 在 `runtime/turn/finish_reason.py` 中定义 finish reason
- 将当前散落的结束分支收敛到结构化 reason

验收：

- 所有结束路径都能落成一个 `FinishReason`

#### [x] P1-T5: 实现 BudgetManager v1

- 新建 `runtime/turn/budget.py`
- 实现：
  - turn 限制
  - tool call 总量限制
  - per-tool 限制
  - wall time 限制
- 暂不接入复杂 token / cost 预算推断

验收：

- 回合内可因预算命中而稳定结束

#### [x] P1-T6: 实现 ToolGovernor v1

- 新建 `runtime/turn/tool_governor.py`
- 实现：
  - `ToolCallSignature`
  - 重复签名检测
  - per-tool 调用次数限制
  - 工具默认 timeout 和 max parallel 约束读取

验收：

- 能识别并阻止明显重复的工具调用

#### [x] P1-T7: 实现 AssessmentEngine v1

- 新建 `runtime/turn/assessment.py`
- 实现：
  - `unresolvedCount`
  - `noveltyScore`
  - `repeatedPatternScore`
  - `controllerDecision`

验收：

- 能对连续重复调用和无进展回合做出结构化判断

#### [x] P1-T8: 实现 TurnController 外壳

- 新建 `runtime/turn/controller.py`
- 初版只做 orchestration：
  - budget check
  - plan
  - tool execution
  - assessment
  - finish

验收：

- 不替换现有入口，只能被测试或 adapter 调用

#### [x] P1-T9: 编写 AgentCoreAdapter

- 新建 `runtime/adapters/agent_core_adapter.py`
- 将现有 `agent_core` loop 输入输出映射到新 `TurnController`

验收：

- 可在不改 gateway 对外行为的情况下试运行新 controller

### 3.3 Phase 1 验收标准

- `runtime/turn/` 基础模块存在
- `TurnState` 已引入
- `FinishReason` 全覆盖
- 有基础预算和重复调用控制
- 新 controller 可通过 adapter 接入

---

## 4. Phase 2: Context & Compression 收敛

### 4.1 目标

把上下文构建与压缩从当前分散状态收敛成统一运行时能力。

### 4.2 任务清单

#### [x] P2-T1: 实现 SystemPromptBuilderV2

- 新建 `runtime/context/builder.py`
- 收敛：
  - 稳定前缀
  - 半稳定层
  - 动态尾部
- 兼容现有：
  - `conversation/system_prompt_builder.py`

验收：

- 支持 `full / minimal / none`

#### [x] P2-T2: 实现 HistoryViewBuilder

- 新建 `runtime/context/history_view.py`
- 明确定义：
  - raw transcript
  - summary chain
  - active history view

验收：

- active history 不再等于完整 message 历史

#### [x] P2-T3: 实现 ArtifactStore 接口

- 新建 `runtime/context/artifact_store.py`
- 先用当前 `services/context/` 能力做 adapter
- 支持：
  - put
  - get
  - preview
  - dedupe

验收：

- 大工具输出可以稳定外置

#### [ ] P2-T4: 定义 CompressionProfile

- 读取 `runtime.compression_profiles`
- 建立 provider
- 校验默认 profile 和字段约束

验收：

- 压缩参数不再散落在代码里

#### [x] P2-T5: 实现 CompressionPipeline v1

- 新建 `runtime/context/compression_pipeline.py`
- 实现阶段：
  - persist
  - aggregate budget
  - ttl prune
  - microcompact
  - collapse
  - autocompact
  - memory flush

验收：

- 有统一的 pipeline 入口

#### [x] P2-T6: 实现 CompressionVerifier

- 新建 `runtime/context/compression_verifier.py`
- 校验：
  - objective
  - unresolved
  - recent failures
  - artifact refs
  - role ordering

验收：

- 压缩后不再仅靠人工检查正确性

#### [ ] P2-T7: 接入 emergency compression

- 为 `prompt_too_long / context_overflow` 定义统一 fallback
- 接入：
  - rollback
  - fallback summary
  - emergency compact

验收：

- 压缩失败不会在同一坏上下文里无限重试

### 4.3 Phase 2 验收标准

- prompt build 分层明确
- active history 与 raw transcript 分离
- 大输出进入 artifact store
- compression pipeline 独立可测
- 有 verifier 和 emergency fallback

---

## 5. Phase 3: Session Orchestrator 收敛

### 5.1 目标

让 session / route / lane 从 gateway 分支逻辑中收口成控制平面。

### 5.2 任务清单

#### [x] P3-T1: 定义 SessionDescriptor 与 RouteMeta

- 在 `runtime/types.py` 补齐 session 相关共享类型

验收：

- session、route 不再只依赖现有 DAO 模型语义

#### [x] P3-T2: 实现 SessionStore 接口

- 新建 `runtime/session/store.py`
- 兼容现有：
  - `models/session.py`
  - `conversation/session.py`

验收：

- 通过 repository 访问 session

#### [x] P3-T3: 实现 RouteResolver

- 新建 `runtime/session/route_resolver.py`
- 将 route 解析从 gateway 入口分离

验收：

- route 解析可独立测试

#### [x] P3-T4: 实现 LaneScheduler

- 新建 `runtime/session/lane_scheduler.py`
- 支持：
  - `main`
  - `followup`
  - `subagent`
  - `cron`
  - `background_tool`

验收：

- lane 有独立并发和深度统计

#### [x] P3-T5: 实现 SessionOrchestrator v1

- 新建 `runtime/session/orchestrator.py`
- 实现：
  - resolve or create session
  - enqueue turn
  - archive session

验收：

- gateway 可以通过 adapter 调到 orchestrator

#### [x] P3-T6: 编写 GatewayAdapter

- 新建 `runtime/adapters/gateway_adapter.py`
- 将：
  - `gateway/dispatcher.py`
  - `gateway/agent_invoker.py`
  - `gateway/agent_bridge.py`
  的调用收束到 orchestrator

验收：

- 新旧入口可并行存在

#### [x] P3-T7: 增加 runtime-turn 调试入口

- 新增：
  - `backend/src/api/v1/dev.py`
  - `backend/tests/unit/test_dev_runtime_turn_api.py`
- 对应提交：
  - `c082d75`

验收：

- `/api/v1/dev/runtime-turn` 可在不替换默认 chat path 的前提下调试 runtime bridge

#### [x] P3-T8: runtime execution 接通 legacy agent path

- 调整：
  - `gateway/agent_bridge.py`
  - `gateway/dispatcher.py`
  - `gateway/agent_invoker.py`
  - `tests/unit/test_runtime_gateway_adapter.py`
- 对应提交：
  - `f575531`
  - `c8aea4c`

验收：

- `run_runtime_turn()` 默认不再落回 no-op controller
- `dev runtime-turn` 会进入真实 legacy agent 执行链路

#### [x] P3-T9: 补齐 runtime-turn 超时与阶段诊断

- 目标：
  - 为 legacy bridge 增加 wall-time timeout
  - 将执行阶段、事件计数、最后进度写入返回 metadata 与日志
  - 用本地 smoke test 定位真实挂点

- 已完成：
  - `backend/src/gateway/agent_bridge.py`
  - `backend/src/api/v1/dev.py`
  - `backend/tests/unit/test_runtime_gateway_adapter.py`
  - `backend/tests/unit/test_dev_runtime_turn_api.py`
  - 本地验证：
    - `python -m pytest --override-ini addopts='' tests/unit/test_runtime_gateway_adapter.py tests/unit/test_dev_runtime_turn_api.py`
    - `curl -X POST http://localhost:8888/api/v1/dev/runtime-turn ... runtime_timeout_ms=5000`
  - 当前观测结论：
    - 请求会在超时内稳定返回
    - 返回中包含 `runtime_diagnostics`
    - 当前挂点位于 `agent_start` 之后、首个 `text_chunk` 之前

验收：

- 超时场景不再无限挂起
- 返回值能区分卡在建 agent、读历史还是事件流消费
- 可据此继续定位上游 LLM / 外部依赖阻塞

#### [x] P3-T10: 排查上游 LLM provider 首 token 阻塞

- 目标：
  - 结合 `runtime_diagnostics` 与 `x-agent.log`
  - 确认是 provider 连接错误、首 token 延迟，还是流式配置问题
  - 视结果决定是修 provider 配置、补重试策略，还是在 debug path 上增加更细粒度 LLM 阶段日志

- 已完成：
  - `backend/src/services/llm/router.py`
  - `backend/tests/unit/test_llm_router.py`
  - 关键修复：
    - 显式 `router.health_check()` 仍保留真实 provider probe
    - 正常 `router.chat()` 不再在调用前额外执行 provider `health_check()`
    - 若存在近期失败的健康检查缓存，chat 路径会跳过该 provider
  - 验证：
    - `python -m pytest --override-ini addopts='' tests/unit/test_llm_router.py tests/unit/test_runtime_gateway_adapter.py tests/unit/test_dev_runtime_turn_api.py`
    - `curl -X POST http://localhost:8888/api/v1/dev/runtime-turn ... runtime_timeout_ms=15000`
  - 当前观测结论：
    - 修复前：请求常卡在 `agent_start` 之后、首个 `text_chunk` 之前
    - 修复后：`15s` 请求已能拿到首个文本和多次工具调用，说明首 token 阻塞已解除
    - `x-agent.log` 显示 `LLMRouter.chat` 首次模型调用约 `9.6s`，后续一轮约 `3.2s`
    - 现阶段主要耗时已转移到 agent 正常生成和工具执行，而不是 preflight health probe

验收：

- 能明确指出阻塞责任点属于 runtime 内部还是上游 provider
- 如果是本地代码问题，有对应修复与回归测试
- 如果是外部依赖问题，有稳定复现方式和明确规避策略

#### [x] P3-T12: 收口 runtime-turn 长路径超时

- 目标：
  - 让 `/api/v1/dev/runtime-turn` 在调试场景下更快返回稳定 `output_text`
  - 区分“桥接是否打通”和“agent 是否继续进入多轮工具链”
  - 评估是否需要增加 debug fast profile，例如限制工具、最小化上下文、或缩短 agent loop

- 已完成：
  - `backend/src/api/v1/dev.py`
  - `backend/src/gateway/agent_bridge.py`
  - `backend/tests/unit/test_runtime_gateway_adapter.py`
  - `backend/tests/unit/test_dev_runtime_turn_api.py`
  - 关键修复：
    - debug endpoint 新增 `disable_tools`
    - legacy bridge 在 `runtime_disable_tools=True` 时创建无工具 agent config
    - fast mode 下跳过 `ToolManager` / tool middleware 初始化
  - 验证：
    - `python -m pytest --override-ini addopts='' tests/unit/test_llm_router.py tests/unit/test_runtime_gateway_adapter.py tests/unit/test_dev_runtime_turn_api.py`
    - `curl -X POST http://localhost:8888/api/v1/dev/runtime-turn ... disable_tools=true runtime_timeout_ms=8000`
  - 当前观测结论：
    - `disable_tools=false` 时，`15s` 请求会进入多轮工具链并可能超时
    - `disable_tools=true` 时，`8s` 请求已能稳定返回最终文本
    - `disable_tools=true` 且 `5s` 时仍有一定概率超时，首个 `text_chunk` 约 `4.8s`

验收：

- 调试入口可在更短时间窗口内稳定返回有意义的文本
- 不影响默认 WebSocket / 聊天主路径
- 对应行为有明确 metadata 开关和回归测试

#### [x] P3-T13: 继续压缩 fast mode 首 token 延迟

- 目标：
  - 将 `disable_tools=true` 场景下的首个 `text_chunk` 再提前
  - 继续排查 skill 初始化、prompt 构建、以及 provider 首 chunk 之间的耗时分布
  - 评估是否需要进一步提供 `disable_skills` / `minimal_context` 等 debug 开关

- 已完成：
  - `backend/src/api/v1/dev.py`
  - `backend/src/gateway/agent_bridge.py`
  - `backend/tests/unit/test_dev_runtime_turn_api.py`
  - `backend/tests/unit/test_runtime_gateway_adapter.py`
  - 关键修复：
    - debug endpoint 新增 `disable_skills`
    - `disable_tools=true` 时默认同时注入 `runtime_disable_skills=true`
    - legacy bridge 在 debug fast mode 下跳过 skill prompt 注入
  - 验证：
    - `python -m pytest --override-ini addopts='' tests/unit/test_llm_router.py tests/unit/test_runtime_gateway_adapter.py tests/unit/test_dev_runtime_turn_api.py`
    - `curl -X POST http://localhost:8888/api/v1/dev/runtime-turn ... disable_tools=true runtime_timeout_ms=8000`
  - 当前观测结论：
    - 首个 `text_chunk` 由约 `4.8s` 下降到约 `4.2s`
    - `disable_tools=true` + `disable_skills=true` 下，`8s` 请求可稳定返回 final output_text
    - `5s` 预算仍偏紧，主要瓶颈已集中到模型首 chunk 和基础 prompt/context 装配

验收：

- `disable_tools=true` 场景在更短超时窗口内也能稳定拿到文本
- 不影响默认 agent 行为和主聊天路径

#### [ ] P3-T14: 继续压缩 fast mode 首 token 到更短窗口

- 目标：
  - 进一步缩短 `disable_tools=true` + `disable_skills=true` 下的首 token 时间
  - 评估是否要继续引入 `minimal_context` / `skip_history_load` / `minimal_system_prompt` 等 debug-only 开关
  - 保持默认聊天路径完全不受影响

验收：

- fast mode 在更短超时窗口内也能稳定拿到文本
- 新开关边界清晰，有回归测试和 e2e 验证

#### [x] P3-T11: 修复前端 agent WebSocket 路径拼接

- 背景：
  - 浏览器报错连接到 `ws://localhost:8888/agent/{session_id}`
  - 后端实际端点为 `/ws/agent/{session_id}`
- 已完成：
  - `frontend/src/hooks/useAgent.ts`
  - 新增 `normalizeWsBaseUrl()`，将缺少 `/ws` 的 `VITE_WS_URL` 规范化
  - 验证：
    - `npm run type-check`
    - `npm run build`
    - 浏览器实际连接已变为 `ws://localhost:5177/ws/agent/{session_id}`
    - 后端日志显示 `WebSocket /ws/agent/... [accepted]`

验收：

- 前端不再错误连接 `/agent/{session_id}`
- 通过 Vite 代理或直接配置 `VITE_WS_URL` 都能连接到正确端点

### 5.3 Phase 3 验收标准

- session 生命周期显式化
- route 与 lane 独立
- gateway 入口不再直接拼接完整执行链

---

## 6. Phase 4: Child Session / Subagent 接入

### 6.1 目标

在前三阶段稳定后，再开放 bounded child session。

### 6.2 任务清单

#### [x] P4-T1: 定义 SpawnPacket 与 ChildResult

- 放入 `runtime/types.py`
- 对齐：
  - child objective
  - parent summary
  - selected artifacts
  - budget profile

验收：

- child session 输入输出结构化

#### [x] P4-T2: 实现 SpawnManager

- 新建 `runtime/session/spawn_manager.py`
- 实现：
  - child session create
  - child route attach
  - child budget / prompt mode 设定

验收：

- child session 创建逻辑统一，不在 controller/gateway 中散落

#### [x] P4-T3: 实现 AnnouncementManager

- 新建 `runtime/session/announcement_manager.py`
- 处理：
  - child result -> parent route
  - parent busy 时排队
  - announce payload 构造

验收：

- child 结束后的回传协议稳定

#### [ ] P4-T4: child session 限制落地

- 默认 `minimal prompt`
- 默认 `max_spawns = 0`
- 默认不暴露 session tools
- 默认自动 archive

验收：

- child session 不会把复杂度继续向下扩散

### 6.3 Phase 4 验收标准

- child session 真正独立
- parent 不回灌 child 原始历史
- announce 与 archive 都有统一管理

---

## 7. Phase 5: 数据层与执行链路收口

### 7.1 目标

补齐存储与时序层，使 runtime 能长期稳定运行。

### 7.2 任务清单

#### [ ] P5-T1: 定义仓储层接口

- `SessionRepository`
- `TranscriptRepository`
- `SummaryRepository`
- `ArtifactRepository`
- `StateSnapshotRepository`

验收：

- runtime 逻辑不再直接依赖 ORM model

#### [ ] P5-T2: 新增状态快照与摘要链存储

- 新增：
  - `session_state_snapshots`
  - `summary_records`
  - `artifact_records`

验收：

- resume 可以依赖状态快照，而不是从全量 transcript 重新推导

#### [ ] P5-T3: 统一压缩 telemetry

- 将 `compression_events` 定位为 telemetry / audit
- 记录：
  - 阶段
  - tokens before/after
  - affected entries
  - fallback used

验收：

- 压缩调参具备数据支撑

#### [ ] P5-T4: 完成执行链路对齐

- 对齐：
  - 用户入口
  - 系统触发入口
  - child session 入口
  - resume / reconnect

验收：

- 所有关键入口都统一走 orchestrator + controller + context runtime

---

## 8. Sprint 建议

### Sprint 1

- P1-T1 ~ P1-T4

### Sprint 2

- P1-T5 ~ P1-T9

### Sprint 3

- P2-T1 ~ P2-T4

### Sprint 4

- P2-T5 ~ P2-T7

### Sprint 5

- P3-T1 ~ P3-T4

### Sprint 6

- P3-T5 ~ P3-T6

### Sprint 7

- P4-T1 ~ P4-T4

### Sprint 8

- P5-T1 ~ P5-T4

---

## 9. 建议的首批代码落点

如果现在立刻进入实现，建议先做以下文件：

- `backend/src/runtime/__init__.py`
- `backend/src/runtime/types.py`
- `backend/src/runtime/turn/state.py`
- `backend/src/runtime/turn/finish_reason.py`
- `backend/src/runtime/turn/budget.py`
- `backend/src/runtime/adapters/agent_core_adapter.py`

原因：

- 这些改动最容易局部落地
- 能最快验证新 runtime 的骨架是否合理
- 不会过早卷入 session / storage / gateway 大范围改造

---

## 10. Definition Of Done

整个 runtime 改造完成的标准：

- 有统一的 `TurnController`
- 有统一的 `ContextBuilder + CompressionPipeline`
- 有统一的 `SessionOrchestrator`
- 有独立 runtime 配置树
- 有独立数据与仓储模型
- child session 走结构化协议
- 所有关键入口都接入新 runtime

在这之前，不应认为多 agent 架构已经真正稳定。
