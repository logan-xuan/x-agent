# 长任务编排架构设计

## 1. 背景

当前系统在“长任务执行”和“用户主会话”之间存在耦合问题。

典型场景：

- 用户下发一个长任务，例如调研、PRD 生成、长报告撰写
- 子 agent 或 specialized agent 开始执行
- 用户中途发送“你在处理吗”“还没好吗”“进度如何”
- 这条消息进入了同一个会话上下文
- LLM 将当前轮目标切换为“回复状态”
- 原主任务停止推进，或者本轮不再继续产出

从行为上看，用户感知为：

- 子任务像是“卡住了”
- 明明没报错，但也没继续干活
- 只会回复“还在处理，请稍等”

问题本质不是单次模型超时，而是：

- 长任务执行链与用户主会话共用同一个 session / trace 语义空间
- 状态追问进入主任务上下文后，改变了当前 LLM 调用目标

## 2. 目标

重构后系统要满足：

1. 用户可以随时查询长任务进度
2. 进度查询不会打断主任务
3. 长任务有独立 worker session 持续执行
4. 主会话与 worker 会话分离
5. 进度回复不依赖大模型临时总结
6. 任务完成后自动将结果推送回主会话
7. 任务可以支持取消、补充要求、自动恢复和心跳

## 3. 总体方案

采用四层架构：

1. `Task Registry`
2. `Worker Session`
3. `Status Query Handler`
4. `Completion Push`

设计原则：

- 长任务不是普通聊天消息，而是独立的任务对象
- 长任务必须绑定独立 worker session
- 用户主会话只负责下发任务、查询状态、接收结果
- worker session 只负责推进主任务

## 4. 核心架构

### 4.1 Task Registry

Task Registry 是长任务的唯一事实来源。

它负责：

- 创建任务
- 记录任务状态
- 记录最近进展
- 记录最终结果引用
- 记录恢复次数 / 错误信息 / 心跳时间

建议新增表：

- `agent_tasks`
- `agent_task_events`
- `agent_task_artifacts`
- `agent_task_controls`

### 4.2 Worker Session

每个长任务有独立的 `worker_session_id`。

worker session 负责：

- 持有主任务上下文
- 使用 stateful context 运行
- 累积 `SessionState`
- 累积 `EvidenceLedger`
- 累积 `Artifacts`
- 累积 `EpisodicMemory`

主会话不会把“你在处理吗”这类状态消息送进 worker session。

### 4.3 Status Query Handler

用户问：

- 你在处理吗
- 还没好吗
- 完成了吗
- 当前进度怎样

不再交给 worker LLM 回答。

而是直接读取 `Task Registry`：

- 当前阶段
- 最近心跳时间
- 最近进展摘要
- 已收集 artifact / evidence 数量
- 当前状态

这类回复应该是系统态读取，而不是新启动一轮大型 LLM 汇总。

### 4.4 Completion Push

worker 任务完成后：

- 更新 `task.status = completed`
- 写入 `final_result_ref`
- 向主会话推送最终结果
- 需要时同步带上摘要和 artifact 引用

## 5. 运行流程

### 5.1 创建任务

用户在主会话发起长任务：

- 调研
- 报告生成
- PRD 撰写
- 长分析

系统执行：

1. 识别为长任务
2. 创建 `task_id`
3. 创建 `worker_session_id`
4. 将任务写入 `Task Registry`
5. 主会话立即回复“任务已开始”
6. 后台启动 `TaskRunner`

### 5.2 Worker 执行

`TaskRunner` 负责：

1. 载入 worker session
2. 使用 `AgentInvoker` 驱动目标 agent
3. 运行一轮 `agent_loop`
4. 更新状态 / artifacts / evidence
5. 检查是否完成
6. 如未完成，继续下一轮

worker 的执行是“监督循环”，不是一次性 prompt 后结束。

### 5.3 中途用户查询状态

用户在主会话问进度时：

1. 命中 `Status Query Handler`
2. 从 `Task Registry` 读取任务状态
3. 直接构造回复

不进入 worker session。

### 5.4 用户补充新要求

如果用户不是问状态，而是补充任务要求，例如：

- 加上竞品分析
- 不要空话
- 聚焦 C 端

则：

1. 写入 `agent_task_controls`
2. 类型为 `task_update`
3. `TaskRunner` 在 checkpoint 处消费 control queue
4. 注入到 worker session 的 state / constraints 中

### 5.5 完成

完成条件之一满足即可：

- 生成最终 artifact
- `SessionState` 标记 `deliverable_completed`
- `TaskRunner` 检测到明确最终产出

完成后：

1. 更新任务状态为 `completed`
2. 写入 `final_result_ref`
3. 推送结果到主会话

## 6. 数据模型设计

### 6.1 agent_tasks

字段建议：

- `task_id`
- `owner_session_id`
- `worker_session_id`
- `owner_agent_id`
- `worker_agent_id`
- `status`
- `task_mode`
- `primary_goal`
- `user_visible_title`
- `progress_summary`
- `final_result_ref`
- `error_message`
- `started_at`
- `last_heartbeat_at`
- `completed_at`
- `resume_count`
- `metadata_json`

### 6.2 agent_task_events

记录任务生命周期事件：

- `task_created`
- `worker_started`
- `progress_updated`
- `control_applied`
- `resumed`
- `completed`
- `failed`
- `cancelled`
- `stale_detected`

### 6.3 agent_task_artifacts

记录任务级别产物：

- `artifact_id`
- `task_id`
- `kind`
- `title`
- `content_path`
- `preview_text`
- `metadata_json`

### 6.4 agent_task_controls

记录用户对任务的控制命令：

- `control_id`
- `task_id`
- `control_type`
- `payload_json`
- `status`
- `created_at`
- `applied_at`

`control_type` 建议：

- `task_update`
- `cancel`
- `pause`
- `resume`

## 7. 状态机设计

### 7.1 任务状态

`agent_tasks.status`：

- `pending`
- `running`
- `waiting_input`
- `blocked`
- `completed`
- `failed`
- `cancelled`
- `stale`

### 7.2 状态迁移

- `pending -> running`
- `running -> waiting_input`
- `running -> blocked`
- `running -> completed`
- `running -> failed`
- `running -> stale`
- `stale -> running`
- `running -> cancelled`

## 8. TaskRunner 设计

### 8.1 职责

TaskRunner 是后台任务监督器。

职责：

1. 驱动 worker session 执行
2. 更新 `Task Registry`
3. 消费 `task_controls`
4. 进行 watchdog 检查
5. 完成后推送结果

### 8.2 核心循环

伪代码：

```python
while task.status in {"pending", "running"}:
    apply_pending_controls(task)
    update_heartbeat(task)
    response = run_worker_turn(task.worker_session_id)
    update_progress(task, response)

    if task_is_completed(response):
        finalize_task(task)
        push_result_to_owner(task)
        break

    if task_is_waiting_input(response):
        task.status = "waiting_input"
        break
```

### 8.3 自动恢复

当 worker 被状态查询打断、连接中断或异常退出时：

- 如果任务未完成且未取消，则允许自动恢复
- 记录 `resume_count`
- 限制最大自动恢复次数

## 9. 状态查询机制

### 9.1 识别规则

主会话收到消息后先分类：

- 普通聊天
- 长任务创建
- 任务状态查询
- 任务控制更新

状态查询命中关键词示例：

- 你在处理吗
- 还没好吗
- 进度如何
- 完成了吗
- 还在研究吗

### 9.2 回复来源

回复由 `Task Registry` 生成，不走 worker LLM。

字段来源：

- `task.status`
- `task.progress_summary`
- `task.last_heartbeat_at`
- `artifact_count`
- `evidence_count`

### 9.3 回复示例

示例：

> 还在处理，当前阶段：资料收集中。  
> 最近一次更新：2 分钟前。  
> 已收集 5 条证据、3 个网页内容文件。  
> 下一步：整理结构并撰写报告。

## 10. 自动续跑机制

### 10.1 为什么需要

如果当前系统暂时还没有完整 `TaskRunner` 监督循环，则至少要保证：

- 用户发状态追问
- 系统先回复状态
- 然后后台继续自动恢复主任务

### 10.2 规则

仅在下列条件同时满足时触发：

1. 用户消息是进度查询
2. 当前会话绑定一个仍在运行的 task
3. assistant 回复看起来是状态说明，不是最终结果
4. 距离上次 auto-resume 超过节流阈值

### 10.3 限流

建议：

- 同一任务同一类状态查询 60 秒内只允许 auto-resume 一次
- 同一任务最大并发 runner = 1

## 11. 与现有代码的落点

### 11.1 新增目录

建议新增：

`backend/src/services/tasks/`

文件：

- `task_models.py`
- `task_store.py`
- `task_orchestrator.py`
- `task_runner.py`
- `status_query_handler.py`
- `task_control_queue.py`

### 11.2 现有模块改造点

#### AgentBridge

文件：

- [agent_bridge.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_bridge.py)

职责新增：

- 主会话消息分类
- 长任务创建入口
- 状态查询旁路
- 自动续跑 fallback

#### AgentInvoker

文件：

- [agent_invoker.py](/Users/xuan.lx/Documents/x-agent/backend/src/gateway/agent_invoker.py)

职责保持：

- 继续作为 worker session 后台运行入口

但由 `TaskRunner` 调用，而不是由主会话直接承担全部语义。

#### SessionStateUpdater

文件：

- [session_state_updater.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/context/session_state_updater.py)

职责：

- 继续服务 worker session
- 保留 `primary_goal`
- 区分状态追问与主任务目标

#### ContextAssembler

文件：

- [context_assembler.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/context/context_assembler.py)

职责：

- 继续为 worker session 组装 stateful prompt

#### ToolResultArchiver

文件：

- [tool_result_archiver.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/context/tool_result_archiver.py)

职责：

- 将 `web_search / fetch_web_content` 等高价值结果沉淀成 `EvidenceLedger / Artifact`

## 12. 任务模式建议

### 12.1 interactive_task

特点：

- 用户可以随时查询进度
- 状态查询走旁路
- worker 不停

适合：

- 调研
- 长文档生成
- 多步骤分析

### 12.2 silent_batch

特点：

- 不响应中间状态
- 完成后一次性通知

适合：

- 夜间批处理
- 长时间运行任务

### 12.3 streaming_progress

特点：

- worker 定期上报结构化进度事件
- 用户不需要手动追问

适合：

- 复杂多阶段任务
- 专业研究助手体验

## 13. 风险与控制

### 13.1 重复续跑风险

控制：

- `last_auto_resume_at`
- `resume_count`
- worker 唯一锁

### 13.2 状态查询误判

控制：

- 关键词 + 上下文双重判断
- 如果消息长度长、含新增要求，则进入 `task_update` 而不是 `status_query`

### 13.3 worker 永久卡死

控制：

- watchdog
- stale 检测
- 自动恢复上限
- 失败后主会话明确告警

### 13.4 任务和主会话脱节

控制：

- 主会话必须保存 `task_id`
- 每次状态查询优先按 `owner_session_id` 查任务

## 14. 验收标准

至少满足：

1. 用户连续 10 次发送“你在处理吗”，worker 不停止主任务
2. 状态查询不再触发新的 research LLM 主任务调用
3. `primary_goal` 不会被状态追问覆盖
4. worker 完成后主会话能自动收到结果
5. 同一任务不会出现多个并发 worker
6. 任务卡住后能被标记为 `stale`

## 15. 实施顺序

建议按以下顺序落地：

1. 新增 `Task Registry` 数据模型和 store
2. 新增 `TaskRunner`
3. 新增 `Status Query Handler`
4. `AgentBridge` 加消息分类分流
5. 主会话长任务改走 `spawn_task`
6. worker session 跑 stateful 主链
7. 自动完成推送与 cancel/update 控制
8. 最后再做 UI 展示优化

## 16. 时间预算、任务级 SLA 与 Watchdog

### 16.1 当前问题

当前系统只有步骤级 timeout，没有任务级 timeout。

表现为：

- 单次 LLM 调用会在 provider timeout + retry 上限处失败
- delegate_task 会在 wait timeout 处返回“后台继续”
- 终端工具会在工具级 timeout 处中止
- 但系统没有“整个长任务最多允许运行多久”的统一约束

结果就是：

- 任务整体没有明确 SLA
- 某一步超时后，系统不知道应不应该恢复、降级还是失败
- 用户主观感受是“卡住了”

### 16.2 目标

重构后应有两层时间控制：

1. **步骤级 timeout**
2. **任务级 SLA**

并配套：

3. **watchdog**
4. **heartbeat**
5. **自动恢复**

### 16.3 步骤级 timeout

每个 stage 都应有自己的 timeout 预算。

建议：

- `task_intake`: 10s
- `evidence_collect`: 120s
- `evidence_normalize`: 60s
- `outline_generate`: 60s
- `section_draft`: 90s / section
- `section_review`: 60s / section
- `document_assemble`: 60s
- `render_publish`: 60s

说明：

- `evidence_collect` 通常最慢，因为包含多个工具调用
- `section_draft` 必须按 section 单独限时，不能整个报告共享一个大 timeout
- `render_publish` 不应使用大模型超长调用，优先用已有 artifact 合并

### 16.4 任务级 SLA

每个 task 需要有统一 SLA。

建议按任务类型分档：

- `interactive_task`: 15 分钟
- `deep_research`: 30 分钟
- `heavy_batch`: 60 分钟

可在 `agent_tasks` 中增加：

- `sla_seconds`
- `deadline_at`

### 16.5 Heartbeat

worker session 和 TaskRunner 都应更新 heartbeat。

建议：

- worker 每完成一个 stage、每生成一个 section、每次 evidence 批次写入后更新 heartbeat
- `last_heartbeat_at` 写在 `agent_tasks`

heartbeat 更新粒度建议：

- 最长间隔不超过 30 秒

### 16.6 Watchdog

新增 watchdog 检查：

- 如果 `now - last_heartbeat_at > stale_threshold`
- 且任务状态仍是 `running`

则标记：

- `status = stale`

并触发：

- 自动恢复
- 或主会话提醒

建议阈值：

- `stale_threshold = max(stage_timeout * 1.5, 60s)`

### 16.7 自动恢复

自动恢复必须有上限。

建议：

- 每个 stage 最多恢复 2 次
- 每个 task 总恢复次数最多 5 次

恢复策略：

1. 若当前 stage 有 checkpoint，则从最近 checkpoint 恢复
2. 若无 checkpoint，但已有部分 artifact，则只补未完成部分
3. 若连续两次都卡在同一 stage，则将 task 标记为 `failed` 或 `waiting_input`

### 16.8 降级策略

当某个 stage repeatedly timeout 时，系统应自动降级。

示例：

#### `section_draft`

- 超时一次：减少 evidence 注入量
- 超时两次：将 section 再拆成更小子段

#### `document_assemble`

- 超时一次：先输出 markdown artifact
- 超时两次：跳过 HTML 渲染，先推送 markdown 结果

### 16.9 状态机补充

任务状态补充以下含义：

- `stale`: 长时间无 heartbeat，需要恢复
- `blocked`: 外部资源缺失或工具失败，无法继续
- `failed`: 超过恢复上限

### 16.10 用户可见策略

用户不需要看到复杂的 timeout 细节，但需要看到：

- 当前阶段
- 最近更新时间
- 任务是否仍在推进
- 是否已自动恢复
- 是否因超时进入降级输出

### 16.11 建议新增字段

在 `agent_tasks` 中新增：

- `sla_seconds`
- `deadline_at`
- `stale_threshold_seconds`
- `last_heartbeat_at`
- `resume_count`
- `last_stage_timeout_at`

在 `agent_task_stages` 中新增：

- `timeout_seconds`
- `stale_threshold_seconds`
- `attempt_count`

### 16.12 验收标准

必须满足：

1. 单个 stage timeout 不会导致整个任务直接消失
2. 长任务超出步骤级 timeout 后会进入 `stale` 或自动恢复
3. 超过任务 SLA 后，任务状态明确，不再无限后台悬挂
4. 主会话可查询当前任务是否已进入降级或恢复

## 17. 结论

不要再让“你在处理吗”进入长任务 worker 的主上下文。

正确方案是：

- 主会话负责任务入口和状态查询
- worker session 负责真实任务推进
- 状态查询旁路
- 完成后推送结果

这比“回复完状态后再自动续跑一次”的补丁方案更稳，也更接近真正可规模化的长任务架构。

## 18. 需求澄清协议设计

### 17.1 问题

长任务执行过程中，经常会遇到信息不足场景，例如：

- 用户没有明确目标用户
- 没有明确输出格式（HTML / Markdown / PDF）
- 没有明确范围边界（C 端 / B 端 / 国内 / 海外）
- 没有明确优先级（先出提纲还是直接写完整版）

如果 worker session 直接向用户发问，会带来三个问题：

1. worker 会话与主会话重新耦合
2. 用户回复会污染 worker 主任务上下文
3. 系统重新回到“一个 session 既执行任务又处理聊天”的错误模式

因此，worker 可以提出澄清需求，但不能直接和用户对话。

### 17.2 设计原则

澄清协议必须满足：

1. worker 只负责提出“缺什么信息”
2. owner session 负责把问题展示给用户
3. 用户回答通过 control queue 回流给 worker
4. worker 恢复时读取结构化答案，不直接读取用户聊天消息

### 17.3 核心对象

建议新增：

- `agent_task_clarifications`

字段建议：

- `clarification_id`
- `task_id`
- `worker_session_id`
- `question`
- `reason`
- `required_fields_json`
- `status`
- `asked_at`
- `answered_at`
- `answer_payload_json`
- `metadata_json`

`status` 建议：

- `pending`
- `asked`
- `answered`
- `expired`
- `cancelled`

### 17.4 流程

标准流程如下：

1. worker 执行到某阶段时发现缺少关键输入
2. worker 不直接回复用户，而是创建 `clarification_request`
3. `TaskRunner` 将任务状态改为 `waiting_input`
4. owner session 收到系统生成的澄清问题
5. 用户回复后，系统将其写入 `clarification_answer` 或 `task_update`
6. `TaskRunner` 消费这条回答，将结构化结果注入 worker state
7. worker 恢复执行

### 17.5 owner / worker 会话边界

#### owner session 负责

- 展示任务开始
- 展示当前进度
- 展示澄清问题
- 接收用户补充回答
- 展示最终结果

#### worker session 负责

- 推进主任务
- 维护 `SessionState`
- 维护 `EvidenceLedger`
- 维护 `Artifacts`
- 提出 clarification request
- 消费 clarification answer

### 17.6 为什么不会混淆

不会混淆的前提是：

1. 用户对澄清问题的回答不直接进入 worker message history
2. 用户回答只进入 `task_control_queue`
3. worker 恢复时只读取结构化 answer payload

也就是说：

- owner session 和 worker session 不共享聊天消息
- 只共享 `task_id / control / clarification / artifact refs`

### 17.7 澄清回复的两种实现

#### 方式 A：自由文本澄清

示例：

> 当前任务需要补充以下信息：  
> 1. 目标用户是谁？  
> 2. 输出是 HTML 还是 Markdown？  
> 3. 是否聚焦 C 端？

优点：

- 灵活
- 易实现

缺点：

- 结构化程度弱
- 后续解析成本高

#### 方式 B：表单化澄清

对固定任务类型（调研、PRD、长报告）优先推荐。

字段例如：

- `audience`
- `output_format`
- `depth`
- `scope`
- `deadline`
- `must_include`

优点：

- 结构化强
- 可直接写入 `SessionState.constraints / task_inputs`

缺点：

- 前端需要配合表单展示

### 17.8 推荐实现

建议采用：

- 首版：自由文本澄清
- 第二版：高频任务切换到表单化澄清

## 19. 对现有 agent_core loop 的影响与边界

### 18.1 结论

`agent_core loop` 仍然保留，但职责必须收缩。

它不再是“长任务生命周期管理器”，而是：

- 单次 worker 执行回合引擎

### 18.2 保留不变的能力

这些能力依然成立且应继续复用：

1. 单次 LLM 调用
2. 工具调用与结果回填
3. turn 级事件流
4. assistant / tool / message 事件序列
5. `SessionState` 的本轮更新

也就是说，`agent_loop` 的事件流模型本身不需要推翻。

### 18.3 必须改变的认知

以前容易默认：

- 一个长任务 = 一次 `agent_loop`

新架构中必须改成：

- 一个长任务 = 多次 `agent_loop` + `TaskRunner` + `Stage Orchestrator`

### 18.4 agent_core loop 负责什么

`agent_core loop` 负责：

1. 在 worker session 中执行当前回合
2. 调用工具
3. 产出消息与事件
4. 写回当前回合状态
5. 将工具结果沉淀到 `EvidenceLedger / Artifact`

### 18.5 agent_core loop 不负责什么

以下职责不应塞进 loop：

1. 长任务创建
2. `task_id` 生命周期管理
3. owner / worker session 路由
4. 状态查询旁路
5. 澄清请求转发
6. 自动续跑调度
7. watchdog
8. stage 切换
9. 最终完成判定

这些职责属于 orchestration 层。

### 18.6 关键语义修正

#### `AgentEndEvent != task completed`

这点必须明确：

- `AgentEndEvent` 只表示本次 worker 回合结束
- 不表示整个长任务结束

长任务是否完成，应由 `TaskRunner` 根据：

- stage 状态
- artifact 完整性
- final_result_ref
- control queue

综合判断。

#### `pending_messages / follow_up` 的边界

当前 loop 里已有：

- `pending_messages`
- follow-up 概念

这些可以保留，但它们只适合：

- 本轮局部 steering
- 当前 worker 内部临时补消息

不适合承担：

- 长任务的全局自动续跑
- 用户状态查询恢复

### 18.7 推荐的三层分工

#### 执行层

由 `agent_core loop` 负责：

- 单轮执行
- 工具调用
- 本轮状态更新

#### 状态层

由 stateful context 负责：

- `SessionState`
- `EvidenceLedger`
- `Artifacts`
- `EpisodicMemory`

#### 编排层

由任务系统负责：

- `TaskRunner`
- `TaskRegistry`
- `StatusHandler`
- `Clarification Protocol`
- `Completion Push`

### 18.8 最小改造建议

如果从现有代码迁移，建议只对 loop 做以下增强：

1. 继续在每轮结束后更新 `SessionState`
2. 继续默认归档高价值工具结果
3. 将 `AgentEndEvent` 视为“本轮结束”，不是“任务完成”
4. 为 `TaskRunner` 暴露必要的内部执行信号

而不要把整个任务编排逻辑塞回 loop。
