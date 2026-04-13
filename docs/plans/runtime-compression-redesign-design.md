# Runtime 压缩算法改进设计（方案 B）

**日期**：2026-04-07
**范围**：仅改 `runtime`
**目标**：在“压缩率优先”的前提下，建立预算驱动且具备语义护栏的压缩机制，减少重复摘要、状态污染和无效上下文占用，同时避免严重语义丢失。

---

## 1. 背景与问题

当前 runtime 压缩链路已经具备 `microcompact`、`collapse`、`autocompact`、`emergency` 等阶段能力，但整体仍偏向“固定顺序执行的文本压缩流水线”，而不是“面向预算目标的上下文治理器”。这会带来几个问题：

1. **压缩率不可控**
   - 现在更像“触发了就跑阶段”，而不是“为了收敛到某个 token 目标而选择动作并及时停止”。
2. **重复摘要长期污染上下文**
   - 多条 `[collapse summary]`、模板化委托播报、重复状态更新会持续占用预算。
3. **终态不能覆盖过程态**
   - 同一任务可能同时保留 `pending/running/done` 多个阶段的描述，形成状态冲突与冗余。
4. **语义保护边界不够明确**
   - 当前 verifier 已能检查部分结构保留，但还不足以保证“当前目标、未完成事项、关键结论”在高压缩率下仍可用。
5. **emergency 容易退化成常态补丁**
   - 如果前面没有以预算目标驱动收口，最后容易依赖 emergency 兜底。

因此，方案 B 的核心不是再加一个压缩阶段，而是把 runtime 压缩提升为：

> **预算驱动 + 语义护栏 + 唯一状态快照** 的上下文治理机制。

---

## 2. 设计目标

### 2.1 一级目标
- 让 runtime 压缩围绕明确预算目标运行，而不是固定串行跑完所有阶段。
- 优先提升压缩率，减少上下文中低价值、重复、被覆盖的信息。
- 避免严重语义丢失，确保 agent 在压缩后仍知道：
  - 当前目标是什么
  - 还剩哪些未完成事项
  - 已经有哪些关键结论
  - 哪些失败和约束仍然有效

### 2.2 非目标
- 本轮**不改 legacy compression manager**。
- 本轮**不改 agent_core 双轨治理架构**。
- 本轮只聚焦 runtime 内部压缩策略、预算状态机和 verifier 升级。

---

## 3. 核心方案概述

方案 B 由三部分组成：

1. **预算驱动状态机**
   - 根据 `observe_tokens / target_tokens / must_fit_tokens` 决定进入哪一层压缩。
2. **三层压缩动作分工**
   - `microcompact`：局部去噪与重复消除
   - `collapse`：把旧历史收敛为唯一状态快照
   - `autocompact`：围绕预算目标做最终收口
3. **语义护栏与 verifier 扩展**
   - 定义哪些内容不能丢，哪些可以压缩，哪些应该直接淘汰。

### 3.1 当前实现对照（2026-04-08）

基于最新代码，方案 B 已经在 runtime 主链路上落地，当前实现对应关系如下：

1. `backend/src/runtime/context/compression_pipeline.py`
   - 已显式输出 `budget_state`
   - 已按 `microcompact -> collapse -> autocompact -> emergency` 做预算驱动收口
   - 已把 `verifier_result`、`rollback_applied`、`rollback_reason` 作为稳定结果合同返回
2. `backend/src/runtime/context/compression_verifier.py`
   - 已覆盖 objective、artifact refs、state conflict、结论保真与压缩收益等护栏
   - 已支持 `objective_out_of_band` 例外语义
3. `backend/src/gateway/agent_bridge.py`
   - `_runtime_prepare_model_input()` 与 `_runtime_controller_compact()` 已复用同一套 runtime 压缩结果
   - bridge 会继续透传 `compression_operations`、`budget_state` 与 rollback/verifier 元数据
4. `backend/src/runtime/turn/controller.py`
   - `DefaultTurnController._apply_compact_result()` 已消费 compact 后的 messages、artifact refs 与 metadata
5. `backend/src/config/models.py`、`backend/src/runtime/context/profile_provider.py`、`backend/src/runtime/service.py`
   - 已维持命名 profile 作为唯一配置入口，并在加载期执行约束校验

这意味着本方案没有停留在“目标态设计”，而是已经和当前 runtime 代码闭环对齐；同时仍然保持 runtime-only scope，没有扩展到 legacy compression manager。

---

## 4. 三层压缩动作分工

这三层不能再都做“泛化压文本”，而必须各自承担不同职责。

### 4.1 microcompact：先清垃圾，不改主叙事

**定位**：最低成本回收 token 的局部瘦身层。  
**目标**：去掉单条消息内部和局部序列中的低价值膨胀内容，但尽量不触碰主语义结构。

#### 主要处理对象
- 重复的 `[collapse summary]` / `[auto-compacted history]` 模板段
- 礼貌话术、emoji、委托流程包装文案
- 同一任务的旧状态行（如 `pending/running` 已被 `done` 覆盖）
- 同签名重复 tool/result
- 超长 tool/result 的低价值长尾文本

#### 允许的动作
- 模板去噪
- 状态覆盖清理
- 重复结果折叠
- 长结果做结构化摘录
- 删除与当前任务无关的 chatter

#### 不允许的动作
- 不删除 objective
- 不删除 unresolved
- 不删除最近关键结论
- 不跨消息重写主任务语义

#### 产出特征
- 尽量不改变整体叙事结构
- 语义损失最小
- 优先回收“显而易见的废 token”

---

### 4.2 collapse：把旧历史收敛成唯一状态快照

**定位**：处理中度压力的历史收敛层。  
**目标**：把多轮旧历史改写成一份当前仍然有效的状态摘要，而不是不断追加新的 summary。

#### 关键原则
- 不再“新增一条 collapse summary”
- 而是维护**唯一一份 collapse state**
- 每次 collapse 都是**重写旧摘要**，不是继续叠加

#### collapse state 中应保留
- 当前 objective
- 当前 unresolved
- 已完成任务的最终结论
- 仍有效的失败 / 约束
- 当前仍被引用的 artifact refs
- 对当前决策仍有价值的少量关键观察

#### 需要删除的内容
- 被终态覆盖的旧状态
- 重复的 objective 描述
- 旧流程播报
- 已经失效的中间过程细节

#### 产出特征
collapse 的产物不再是“历史事件日志”，而是：

> **当前还能继续工作的最小状态表示**

这正是为了解决类似下面的问题：
- 一条 summary 还在说“异步执行中”
- 下一条 summary 已经说“任务完成”
- 两条同时留在上下文里继续占 token

方案 B 下，这种情况会被折叠成一条终态状态快照。

---

### 4.3 autocompact：预算不够时做强收敛，但仍受护栏约束

**定位**：面向预算目标的最终收口层。  
**目标**：在高压力下保证上下文一定能收敛到可接受预算内，但不是无脑截断。

#### 核心原则
- 先明确 `must_fit_tokens`
- 如果当前上下文仍超标
- 按优先级继续压缩
- 每做一步都重算 token
- 一旦达标立即停止

#### 建议压缩顺序
1. 先裁旧 tool 细节
2. 再裁已完成任务的展开叙事，只保留一句结论
3. 再压缩旧失败上下文，只保留“失败原因 + 当前约束”
4. 最后才压最近窗口中可压缩但非核心的内容

#### 不可越过的边界
- 不可删除 P0 级语义
- 不可让 unresolved 变成空泛描述
- 不可把具体结论压成“已处理”“已查询”这种空壳文本

#### 产出特征
- 明确对预算负责
- 有停止条件
- 不再靠“跑完整条固定链路”碰运气

---

## 5. 预算驱动状态机

建议把 runtime 压缩改造成显式状态机，而不是隐式阈值+串行阶段。

### 5.1 状态定义

#### normal
上下文在安全区内，不压缩，只统计。

行为：
- 计算当前 token
- 记录增长速度
- 记录重复摘要占比、低价值消息占比
- 为后续压缩准备元数据

#### microcompact_requested
进入轻压缩区，但还不需要改写历史结构。

触发条件示例：
- 达到第一档压力阈值
- 或检测到明显重复污染

行为：
- 去噪
- 去重
- 终态覆盖旧状态
- 重算 token

退出条件：
- 达标则回 `normal`
- 否则进 `collapse_requested`

#### collapse_requested
简单去噪已不够，需要把旧历史收敛成唯一状态。

触发条件示例：
- microcompact 后仍超 `target_tokens`
- 历史占比过高
- 已出现摘要套摘要膨胀

行为：
- 生成/重写唯一 collapse state
- 只保留仍有效状态
- 删除过程态和重复态

退出条件：
- 达标则回 `normal`
- 否则进 `autocompact_requested`

#### autocompact_requested
开始强制收口，目标是必须 fit。

触发条件示例：
- collapse 后仍超 `must_fit_tokens`
- 剩余预算低于保留底线
- provider/model 已接近 hard limit

行为：
- 按优先级逐步压缩
- 每步后重算 token
- 达标即停

退出条件：
- 达标回 `normal`
- 多轮仍不达标则进 `emergency`

#### emergency
最后兜底，不应是常态主路径。

触发条件示例：
- autocompact 后仍无法 fit
- provider 明确返回上下文过大
- 恢复态注入后瞬间超限

行为：
- 保留唯一 objective
- 保留 unresolved
- 保留 artifact refs
- 保留必要 tail
- 不允许把旧 collapse summary 原样继续塞回去

---

### 5.2 三条预算线

建议 runtime 内明确区分三条预算线：

#### observe_tokens
- 只观察，不压缩
- 用于统计增长趋势和污染特征

#### target_tokens
- 压缩目标线
- 一旦超过，就尝试用 microcompact / collapse 拉回这条线以下

#### must_fit_tokens
- 硬收口线
- 一旦超过，必须进入 autocompact 直到 fit

#### 价值
三条线可以解决：
- 压得太晚
- 压得太盲
- 压多少才够没有停止准则

---

## 6. 语义护栏

高压缩率前提下，必须先定义哪些语义绝不能丢。

### 6.1 内容分级

#### P0：绝对保留
在任何压缩阶段都不能丢，只能重表达。

包括：
- 当前 objective
- 当前 unresolved
- 最近仍有效的用户约束
- 最近关键失败及失败原因
- 当前仍被引用的 artifact refs
- 最近一次明确支撑当前任务的最终结论

#### P1：强保留，可压缩
可以浓缩，但不能完全消失。

包括：
- 已完成任务的最终结果
- 旧轮次的重要工具观察
- 对当前决策仍有影响的中间结论
- 恢复态中最近仍有效的 summary / snapshot 信息

#### P2：弱保留，预算不足时可淘汰
预算紧张时可压缩到很短，甚至删除。

包括：
- 已完成任务的过程描述
- 旧回合展开推理
- 较早的中间状态播报
- 重复但不完全相同的辅助观察

#### P3：直接可丢弃
本身就不该长期占上下文。

包括：
- 礼貌话术
- emoji
- 模板化委托文案
- “请稍等”“稍后回传”类播报
- 重复的 collapse summary
- 已被终态覆盖的 pending/running 状态
- 完全重复的工具结果
- 与当前任务无关的旧 chatter

---

### 6.2 五条关键护栏

#### 护栏 1：objective 唯一且持续可见
- 最终上下文里必须只有一份当前 objective
- 不允许多个 summary 重复占位
- 不允许 objective 漂移成泛化空话

#### 护栏 2：unresolved 必须可追溯
- 不能只剩“待继续处理”这种模糊描述
- 必须仍能看出具体未完成事项

#### 护栏 3：终态覆盖非终态
- `done / failed / cancelled` 一旦出现，应覆盖旧的 `pending / running / delegated`
- 压缩后只保留终态结论，不再保留过程播报

#### 护栏 4：保留事务结果，不保留呈现包装
应保留：
- 子任务目标
- 子任务最终结论
- 是否仍未完成

不应保留：
- “任务已成功委托”
- “稍后自动回传”
- 风格化播报文本

#### 护栏 5：工具结果保留证据值，不保留冗长原文
应至少保留：
- 工具名
- 关键发现
- 错误性质
- 必要时的 artifact/ref

例如保留：
- `web_search: 北京今天多云转晴，-1℃~10℃`

而不是：
- 整页网页内容
- 或只留“已查询天气”

---

## 7. verifier 扩展

当前 verifier 已覆盖 objective、unresolved、recent_failures、artifact_refs、role_ordering，方向正确，但仍偏结构性检查。方案 B 建议扩展为“语义保真 + 收益达标”双重校验。

### 7.1 建议新增校验项

#### 1）唯一目标校验
检查：
- 是否只保留一份有效 objective
- 是否存在冲突版本
- 是否被模板摘要重复展开

#### 2）unresolved 可追溯校验
检查：
- 未完成事项是否仍能识别
- 是否被误压成空泛描述
- 是否把未完成项错压成已完成

#### 3）终态覆盖校验
检查：
- 同一 task / subtask 是否同时保留 running 和 done
- 是否保留了已被终态覆盖的旧状态
- 是否存在状态冲突

#### 4）结论保真校验
检查：
- 压缩前后的关键结论是否仍语义对齐
- 不能把“具体结论”压成“已处理”

#### 5）压缩收益校验
检查：
- token gain 是否达到要求
- 是否真正移除了重复污染
- 是否存在“语义损失较大但收益很小”的情况

---

## 8. 回滚策略

当 verifier 不通过时，不能无差别继续压缩，而要根据失败类型回退。

### 8.1 microcompact 失败
说明局部规则误删关键内容。
- 回滚 microcompact
- 放宽局部去噪规则

### 8.2 collapse 失败
说明唯一状态快照没有保住关键语义。
- 回滚到 microcompact 结果
- 重新生成 collapse state
- 收紧摘要模板

### 8.3 autocompact 失败
说明预算目标与语义护栏发生冲突。
- 保留当前最优版本
- 再决定是否进入 emergency

### 8.4 emergency 失败
说明已无法继续安全压缩。
- 停止继续压缩
- 进入 best-effort 最小上下文输出
- 记录为压缩失真风险点

---

## 9. 关键数据结构建议

本轮不要求一次性重构所有模型，但建议在 runtime 内引入以下内部语义结构：

### 9.1 消息级标记
- `message_signature`
  - 用于判断重复 summary / 重复结果
- `state_superseded_by_terminal`
  - 标记某条旧状态是否已被终态覆盖
- `semantic_priority`
  - 对应 P0/P1/P2/P3
- `compressible`
  - 是否允许进入压缩动作

### 9.2 collapse 结果结构
建议引入内部 collapse state，而不是直接拼文本：

```python
{
  "objective": "...",
  "unresolved": [...],
  "finalized_tasks": [...],
  "active_constraints": [...],
  "active_failures": [...],
  "artifact_refs": [...],
  "evidence_summaries": [...],
}
```

然后再由统一 formatter 输出最终摘要文本，避免每次 collapse 直接在自由文本上叠加。

### 9.3 预算控制结构
建议显式区分：
- `observe_tokens`
- `target_tokens`
- `must_fit_tokens`
- `current_tokens`
- `remaining_tokens`
- `pressure_level`

---

## 10. 最终设计结构

这一节把方案 B 收成最终可落地的结构，重点覆盖：
- 组件拆分
- 关键数据结构
- `compression_pipeline.py` 内部改造方式
- 与 `budget.py` / `turn/controller.py` 的衔接

### 10.1 组件拆分

#### RuntimeCompressionCoordinator
**职责**：压缩总调度器。  
作为 runtime 压缩主入口，负责：
- 接收 `CompressionContext`
- 计算预算状态
- 选择进入 `microcompact / collapse / autocompact / emergency`
- 串联 verifier 与 rollback
- 输出最终 `CompressionResult`

说明：可以继续沿用 `DefaultCompressionPipeline` 作为外部类名，但内部应转为 coordinator 风格，而不是固定阶段流水线。

#### CompressionBudgetPolicy
**职责**：只回答“当前应该压到哪一层”。

负责：
- 根据 `current_tokens`
- 对比 `observe_tokens / target_tokens / must_fit_tokens`
- 结合重复污染程度、历史占比、overflow 风险
- 输出当前压缩状态和下一步动作计划

说明：它只做决策，不直接修改消息。

#### CompressionSemanticClassifier
**职责**：给消息打语义标签。

负责：
- 识别消息是否属于 objective / unresolved / final result / process update / chatter / summary
- 标注 `P0/P1/P2/P3`
- 生成 `message_signature`
- 识别状态是否已被终态覆盖
- 识别重复 summary / 重复结果 / 重复播报

说明：这是方案 B 语义护栏的基础层。

#### MicrocompactReducer
**职责**：局部去噪和重复清理。

只做：
- 去模板
- 去 emoji / 礼貌包装
- 去重复 summary
- 去已被终态覆盖的过程态
- 长结果结构化摘录
- 重复结果折叠

说明：它不负责生成历史摘要。

#### CollapseStateBuilder
**职责**：把旧历史收敛成唯一状态快照。

负责从旧历史中抽取：
- objective
- unresolved
- finalized_tasks
- active_constraints
- active_failures
- artifact_refs
- evidence_summaries

说明：collapse 结果先生成内部状态对象，再交给 formatter 输出文本；不再直接叠加自由文本 summary。

#### AutocompactReducer
**职责**：围绕 `must_fit_tokens` 做最终收口。

负责：
- 计算还差多少 token
- 按优先级逐步裁剪 P2/P1 内容
- 每一步后重算 token
- 达标立即停止
- 无法达标时进入 emergency

说明：它是预算闭环，不是再做一轮泛化摘要。

#### CompressionVerifier
**职责**：验证压缩后仍能继续工作。

除现有结构校验外，还应覆盖：
- objective 唯一性
- unresolved 可追溯性
- 终态覆盖冲突
- 关键结论保真
- 压缩收益是否达标

#### CompressionFormatter
**职责**：把内部结构输出成最终消息文本。

负责：
- 将 `collapse_state` 渲染为统一摘要模板
- 确保 objective 只出现一次
- 确保 unresolved 简洁但具体
- 统一最终摘要格式

说明：避免各 reducer 自己拼自由文本，导致格式漂移和重复污染。

### 10.2 关键数据结构

#### `AnalyzedMessage`

```python
@dataclass
class AnalyzedMessage:
    raw: dict[str, Any]
    index: int
    role: str
    content: str

    semantic_priority: str  # P0 | P1 | P2 | P3
    message_kind: str       # objective | unresolved | result | failure | status | chatter | summary
    message_signature: str | None = None

    task_id: str | None = None
    state_label: str | None = None  # pending | running | done | failed | cancelled
    superseded_by_terminal: bool = False

    compressible: bool = True
    droppable: bool = False
```

作用：
- 为后续 reducer 提供统一分析输入
- 避免每层反复猜测消息含义

#### `CollapseState`

```python
@dataclass
class CollapseState:
    objective: str
    unresolved: list[str]
    finalized_tasks: list[str]
    active_constraints: list[str]
    active_failures: list[str]
    artifact_refs: list[str]
    evidence_summaries: list[str]
```

作用：
- collapse 结果先结构化，再格式化为唯一 summary
- 解决“摘要套摘要”问题

#### `CompressionBudgetState`

```python
@dataclass
class CompressionBudgetState:
    current_tokens: int
    observe_tokens: int
    target_tokens: int
    must_fit_tokens: int
    remaining_tokens: int

    pressure_level: str     # normal | yellow | orange | red
    repeated_summary_ratio: float
    history_share_ratio: float
    overflow_risk: bool
```

作用：
- 决定当前是观察、轻压缩、历史收敛还是强收口
- 让预算语义集中，而不是散落在 profile 阈值中

#### `CompressionActionPlan`

```python
@dataclass
class CompressionActionPlan:
    phase: str  # microcompact | collapse | autocompact | emergency
    reason: str
    target_tokens: int
    must_preserve: list[str]
    allowed_drop_priorities: list[str]
```

作用：
- 显式表示“为什么进入这一层、目标压到哪、哪些不能动”
- 便于 trace、debug 和单测

#### `CompressionVerificationReport`

```python
@dataclass
class CompressionVerificationReport:
    ok: bool
    preserved: dict[str, bool]
    token_gain: int
    duplicate_reduction: int
    reasons: list[str]
```

作用：
- 明确说明是哪里失败了
- 量化压缩收益与重复消除效果

### 10.3 `compression_pipeline.py` 内部改造

核心思想：从“固定流水线”改成“先分析，再决策，再动作，再验证”的闭环。

#### 当前问题
当前链路大致是：

```python
persist
-> aggregate_budget
-> ttl_prune
-> microcompact
-> collapse
-> autocompact
-> verifier
```

问题：
- 顺序固定
- 每次都可能走完整条链
- 不是按预算缺口选择动作
- collapse 仍偏向文本式追加
- autocompact 不是严格的预算收口器

#### 改造后的主流程

```python
async def run(self, ctx: CompressionContext) -> CompressionResult:
    working = self._normalize_messages(ctx)
    analyzed = self.semantic_classifier.analyze(working, ctx)
    budget = self.budget_policy.evaluate(analyzed, ctx)

    working, artifacts = await self._persist_large_results_if_needed(ctx, analyzed)

    while True:
        analyzed = self.semantic_classifier.analyze(working, ctx)
        budget = self.budget_policy.evaluate(analyzed, ctx)

        if budget.pressure_level == "normal" and budget.current_tokens <= budget.target_tokens:
            break

        plan = self.budget_policy.plan_next_action(analyzed, budget, ctx)

        if plan.phase == "microcompact":
            candidate = self.microcompact_reducer.apply(analyzed, ctx, plan)
        elif plan.phase == "collapse":
            collapse_state = self.collapse_builder.build(analyzed, ctx, plan)
            candidate = self.formatter.render_collapse_state(collapse_state, analyzed, ctx)
        elif plan.phase == "autocompact":
            candidate = self.autocompact_reducer.apply(analyzed, ctx, plan)
        elif plan.phase == "emergency":
            return await self.run_emergency(ctx)

        report = self.verifier.verify(...)
        if report.ok:
            working = candidate
        else:
            working = self._rollback_or_relax(working, candidate, report, plan, ctx)

        if self._fit_budget(working, ctx, budget):
            break

    return self._build_result(...)
```

#### 子阶段重定义

##### `_normalize_messages`
负责：
- 统一 role/content
- 提取 tool_name / task_id / status hint
- 标准化 collapse summary 标记
- 预识别重复模板块

##### `_persist_large_results_if_needed`
继续保留 artifact 持久化，但语义上应被定义为：
- 证据外移
- 不是压缩主策略本身

persist 后应重新分析消息优先级，而不是直接进入下游阶段。

##### `semantic_classifier.analyze`
每轮动作前重新分析：
- P0/P1/P2/P3 分级
- 状态覆盖关系
- 重复消息与重复摘要
- 可合并证据块

##### `budget_policy.plan_next_action`
这是新核心。它只回答：
- 当前缺口多大
- 主要问题是重复污染、历史膨胀还是硬预算超限
- 下一步应进入哪一层

输出动作只允许是：
- `microcompact`
- `collapse`
- `autocompact`
- `emergency`

##### `collapse_builder + formatter`
旧历史先被收敛成 `CollapseState`，再由 formatter 渲染。

关键约束：
- 最终上下文只允许一份有效 objective
- unresolved 必须具体
- 已完成任务只保留终态结论
- 不重复保留过程播报

##### `autocompact_reducer.apply`
必须具备预算闭环：
- 先计算 token 缺口
- 再决定裁剪哪些 P2/P1 内容
- 每一步后重算 token
- 达标立即停止

这里不再采用“一次性大摘要替换全部历史”的做法，以降低语义塌陷风险。

##### `run_emergency()`
继续保留，但正式纳入状态机末级。

要求：
- 只保留一份 objective
- 只保留 unresolved
- 只保留 artifact refs
- 只保留必要 tail
- 不允许重新拼回旧 collapse summary

### 10.4 与 `budget.py` 的衔接

#### 当前职责保留
`DefaultBudgetManager.evaluate()` 仍负责：
- 是否 `continue`
- 是否 `compact`
- 是否 `stop`

这一层不需要接管具体压缩逻辑。

#### 建议增强
建议 `BudgetDecision.compact(...)` 附带更明确的运行意图，例如：

```python
BudgetDecision.compact(
    reason="compact_trigger_tokens reached",
    finish_reason=None,
    details={
        "pressure_level": "orange",
        "target_tokens": 24000,
        "must_fit_tokens": 28000,
        "overflow_risk": False,
    }
)
```

这样 runtime compression 能直接知道：
- 当前是轻压缩还是强收口
- 本轮目标预算是多少
- 离硬边界还有多远

#### 边界说明
- `budget.py` 决定：**是否必须启动压缩，以及压缩压力等级**
- `compression_pipeline.py` 决定：**具体如何压**

### 10.5 与 `turn/controller.py` 的衔接

#### 当前情况
controller 当前通过 `CompactFn` 抽象挂载压缩：

```python
CompactFn = Callable[[TurnState, str], Awaitable[TurnState]]
```

这层解耦是合理的，建议保留。

#### 建议增强
controller 不需要知道 reducer 细节，但建议知道“这次 compact 属于哪一档”。可将 compact reason 收敛成：
- `budget_microcompact`
- `budget_collapse`
- `budget_autocompact`
- `overflow_emergency`
- `assessment_compact`

好处：
- trace 更清晰
- 单测更容易写
- 失败时更容易差异化处理

#### controller 与 compression 的边界
controller 负责：
- 控制回合循环
- 接 budget 决策
- 触发 compact hook
- 处理 compact 后继续/停止逻辑

compression pipeline 负责：
- 消息分析
- 预算收口
- 唯一状态快照生成
- 语义校验与回滚

也就是说，controller 仍是 orchestration 层，不应重新承担压缩语义逻辑。

#### 推荐交互方式

controller 侧：

```python
if budget_decision.action == "compact":
    state = await self.compact_fn(
        state,
        budget_decision.reason or "budget_compact"
    )
```

`compact_fn` 内部：
- 从 `state` 提取 messages / artifact / task_frame / metadata
- 构造 `CompressionContext`
- 调用新的 runtime compression coordinator
- 将结果写回 `state.messages / active_artifact_refs / metadata`

建议补充回写的 metadata：
- `last_compaction_phase`
- `last_compaction_token_gain`
- `last_duplicate_reduction`
- `last_compaction_reason`
- `compaction_count`

### 10.6 最终整体数据流

#### 正常路径
1. `budget.py` 发现进入压缩区
2. `turn/controller.py` 触发 `compact_fn`
3. `compression_pipeline.py`：
   - 标准化消息
   - 语义分类
   - 预算评估
   - 选择 `microcompact / collapse / autocompact`
   - verifier 校验
   - 必要时 rollback
4. 压缩结果写回 `TurnState`
5. controller 继续后续 turn

#### 高压路径
1. budget 或 provider overflow 表明必须强收口
2. controller 触发 compact
3. pipeline 进入：
   - `autocompact`
   - 不够再 `emergency`
4. 输出最小可工作上下文
5. controller 再决定继续还是 best-effort finish

### 10.7 推荐代码改造边界

#### 必改
- `backend/src/runtime/context/compression_pipeline.py`
- `backend/src/runtime/context/compression_verifier.py`

#### 建议改
- `backend/src/runtime/turn/budget.py`
- `backend/src/runtime/turn/controller.py`

#### 暂不改
- legacy `ContextCompressionManager`
- `agent_core` 双轨上下文治理

### 10.8 一句话总结

最终方案不是“在 pipeline 里继续堆规则”，而是：

> **BudgetPolicy 决定压缩层级，SemanticClassifier 识别高低价值语义，Microcompact/Collapse/Autocompact 分层处理，Verifier 保证语义不塌，Controller 只负责调度。**

---

## 11. 预期收益

### 11.1 压缩率提升
- 清除大量重复模板、状态播报、包装文本
- 把多条 summary 压成唯一状态快照
- 把过程态改成终态结论

### 11.2 语义损失更可控
- 通过 P0/P1/P2/P3 分级明确边界
- 通过 verifier 防止压成空壳摘要
- 通过 rollback 避免错误压缩持续放大

### 11.3 budget 行为可解释
可以更明确回答：
- 这轮为什么压缩
- 压缩压到了哪一档
- 为什么在这一层停止
- 为什么进入 emergency

### 11.4 减少 emergency 常态化
前面通过预算闭环逐层收口后，emergency 将真正变成最后兜底，而不是主路径补丁。

---

## 12. 风险与注意事项

### 12.1 风险：过度依赖规则化分级
如果 P0/P1/P2/P3 分类不准，可能会误删对当前任务有价值的信息。

**缓解**：
- 先对已知高价值字段做保守保留
- 通过 verifier 和回滚逐步收紧

### 12.2 风险：collapse state 生成过度摘要化
如果 collapse state 太抽象，agent 可能失去具体操作抓手。

**缓解**：
- unresolved 必须具体可追溯
- 关键结论必须保留实体信息
- 失败上下文至少保留失败原因和约束

### 12.3 风险：为追求压缩率而牺牲恢复能力
在 resumed 场景下，如果只剩抽象摘要，后续恢复质量会下降。

**缓解**：
- 恢复态中的 summary/snapshot 按 P1 处理
- artifact refs 必须保留

---

## 13. 推荐实施顺序

建议按低风险顺序推进：

### 第 1 阶段：先做去重与终态覆盖
- 增加 `message_signature`
- 增加终态覆盖逻辑
- 消除重复 summary / 重复状态播报

### 第 2 阶段：引入预算状态机
- 明确 `observe_tokens / target_tokens / must_fit_tokens`
- 压缩从“固定阶段串行”改为“按目标选择动作”

### 第 3 阶段：collapse 改成唯一状态快照
- 从“追加摘要”改为“重写唯一 collapse state”

### 第 4 阶段：扩展 verifier 与 rollback
- 增加终态冲突检查
- 增加结论保真与收益评估

### 第 5 阶段：收敛 emergency
- 让 emergency 成为正式末级，而不是散落 fallback

---

## 14. 最终结论

方案 B 的本质不是“让 runtime 压得更狠”，而是：

> **把 runtime 压缩从固定流水线升级为预算驱动的上下文治理器。**

它相对当前实现的核心提升在于：
- 不再让重复摘要持续堆积
- 不再让过程态和终态同时污染上下文
- 不再只有“触发了就压”，而是围绕预算目标收敛
- 不再只看结构没坏，而是明确保护任务语义

如果落地得当，这套方案能够同时满足：
- **压缩率优先**
- **只改 runtime**
- **避免语义丢失太严重**

这也是当前约束下最均衡、最可落地的改进方向。
