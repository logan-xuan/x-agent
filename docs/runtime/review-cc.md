# Runtime 架构审查报告（Claude Code）

## 审查范围

- 基准方案：`arch/runtime/README.md`
- 审查对象：当前分支相对主线的 runtime 相关实现
- 审查目标：
  - 是否符合技术方案
  - 是否开发完整
  - 是否已集成主链路
  - 是否可以完整运行
  - 是否存在 bug 或高风险点
  - 架构是否合理
  - 是否符合低耦合、高内聚
  - 设计模式是否合理

---

## 一、执行摘要

总体结论：**当前实现对 `arch/runtime/README.md` 的落地方向是正确的，整体属于“结构上基本对齐、主链路已有接入、但尚未完全收口”的阶段。**

这批代码已经完成了 runtime 的核心骨架建设，包括：

- `Session Orchestrator`
- `Turn Controller`
- `Context / Compression` 相关配置装配
- `Storage-backed repositories`
- `Gateway adapter / bridge`
- `Child session` 的实际接入路径

但从最终交付标准来看，当前状态仍不能认定为：

- 技术方案已完整实现
- runtime 已彻底接管主链路
- 整体已经“完全可以运行”

核心原因在于：**当前主执行控制器虽然已经接入 runtime 外壳，但实际执行仍明显依赖 legacy bridge 路径，说明新 runtime 更多完成了控制平面搭建，而非完整原生执行闭环。**

### 总评级

**B+（阶段性完成度较高，但不是最终收口版）**

---

## 二、总体验收结论

### 1. 是否符合技术方案

**结论：基本符合，但偏“阶段性实现”，不是 README 所描述的最终态。**

#### 符合项

1. runtime 的核心边界已经建立，具备明确分层：
   - orchestrator
   - controller
   - repositories
   - adapters
   - services
   - types
2. `backend/src/runtime/service.py` 已完成 runtime services 的统一装配，说明并非仅有概念设计。
3. `backend/src/tools/builtin/delegate_task_tool.py` 已将 child session flow 接入真实工具调用链，证明 runtime 不是孤立模块。
4. resume / reconnect / child flow 等能力已有持久化与编排基础。

#### 不符合项

1. 当前主执行控制器并未形成完整原生 runtime planner / executor / assessment 闭环。
2. 主路径执行仍通过 `runtime_legacy_bridge` 过渡，说明新旧执行链路尚未彻底切分。
3. 这与 README 中“runtime 作为主执行体系”的最终目标仍有差距。

#### 判断

- 若按“第一阶段 / 过渡阶段实现”评估：**符合**
- 若按“最终技术方案完全落地”评估：**未完全符合**

---

### 2. 是否开发完整

**结论：不完整。**

#### 依据

1. **runtime turn loop 尚未原生闭环**
   - 当前更接近“新控制平面 + 旧执行平面”的组合。
   - 因此不能认定为完整 runtime 主循环已完成。

2. **child orchestration 能力仍偏保守 / 过渡实现**
   - `child_max_depth` 的语义在运行时被压缩为有限的 0/1 控制，未体现完整多层 child orchestration 能力。

3. **测试覆盖关键模块，但缺少最终主链路证明**
   - 已有 turn controller、resume flow、child flow 的测试证据。
   - 但尚缺足够强的 gateway → runtime → persistence → resume/reconnect 的完整端到端验证。

#### 判断

当前实现已经超出概念验证阶段，但**尚不能定义为“开发完整”**。

---

### 3. 是否已集成主链路

**结论：已集成，但属于“部分接入”，不是“完全接管”。**

#### 已集成的证据

1. gateway / bridge 层已经持有 runtime services 与 runtime turn controller。
2. `run_runtime_turn(...)` 已存在，说明 gateway 层能真实进入 runtime 路径。
3. `delegate_task_tool` 的 child 任务流程已通过 orchestrator + `AgentBridge().run_runtime_turn(...)` 接入 runtime。
4. runtime 已不再只是一个侧边模块，而是进入了真实调用路径。

#### 未完全接管的原因

1. runtime controller 的 planner / executor 实际仍借助 legacy bridge 执行。
2. 因此“runtime 已被主链路调用”与“runtime 已经主导主链路执行”是两回事。

#### 判断

- “是否集成主链路”：**是**
- “是否完成主链路替换”：**否**

---

### 4. 是否完全可以运行

**结论：不能给出“完全可以运行”的判定；更准确的表述是“部分路径可运行”。**

#### 理由

1. 主链路执行仍依赖 legacy bridge，说明 runtime 自身尚未独立完成全链路闭环证明。
2. 部分配置路径存在明显空值 / 配置缺失风险，存在真实运行中断可能。
3. child flow、resume/reconnect、局部控制逻辑看起来具备可运行基础，但这不足以推出“整体完全可运行”。

#### 判断

- 单路径 / 局部流程：**大概率可运行**
- 完整 runtime 最终态：**不能认定完全可运行**

---

### 5. 是否存在 bug 或高风险点

**结论：存在，且至少有 2～3 个实质性风险点。**

详见下文“问题分级清单”。

---

### 6. 架构是否合理

**结论：整体合理，方向正确，但当前属于过渡架构，执行链路耦合尚未完全切干净。**

#### 架构优点

1. 分层清楚，职责边界明确。
2. 控制平面与存储平面已抽象出来。
3. repositories / adapters / orchestrator 的角色划分合理。
4. child flow 通过 orchestrator 管理，而不是在工具层拼接复杂状态。

#### 架构不足

1. controller 与 legacy bridge 的实际运行耦合仍然偏强。
2. 局部配置 / 策略存在硬编码与语义压缩。
3. 新架构在代码结构上已拆分清晰，但运行时仍存在过渡性混合路径。

---

### 7. 是否符合低耦合、高内聚

**结论：模块结构层面基本达到，但运行链路层面仍未完全达标。**

#### 正面评价

- service / orchestrator / repositories / adapters / types 的拆分体现出较好的高内聚。
- runtime 相关能力被聚合在自身边界内，没有明显被散落到业务工具各处。

#### 保留意见

- 运行时最核心的执行路径仍受 legacy bridge 影响，说明系统在“运行态耦合”上尚未完全收敛。
- 因此目前更适合表述为：**结构上低耦合，运行上仍存在关键耦合点。**

---

### 8. 设计模式是否合理

**结论：总体良好。**

合理之处：

- orchestrator 模式适合 session 生命周期管理
- repository 模式适合 runtime persistence 抽象
- adapter 模式适合新旧链路过渡期兼容
- service composition 适合 runtime profile / policy / orchestration 装配

不足之处：

- 当前模式组合更像“合理的迁移架构”，而非“最终态纯 runtime 架构”
- 设计是正确的，但执行闭环尚未完全从 legacy 侧抽离

---

## 三、问题分级清单

---

## Critical（必须修）

### Critical-1：child budget profile 存在空值风险，可能导致运行时异常

#### 位置

- `backend/src/tools/builtin/delegate_task_tool.py`

#### 问题描述

当前 child task 流程中直接写死：

- `budget_profile="child-default"`

随后又通过：

- `runtime_services.turn_profiles.get(child_request.session.budget_profile)`

获取 profile，并继续直接访问属性（如 `max_wall_time_ms`）。

如果配置中不存在 `child-default`，或者 profile 名称与配置不一致，则 `.get(...)` 返回 `None`，后续直接访问属性会触发异常。

#### 影响

- child task delegation 可能在运行期直接失败
- 该问题属于真实可触发风险，而非代码风格问题
- 会削弱 runtime child flow 的稳定性

#### 要求

必须至少满足以下之一：

1. 明确保证 `child-default` 在配置层始终存在，并有启动时校验
2. 在代码层增加显式兜底逻辑
3. 在缺失时返回清晰、可观测、可定位的错误，而不是空指针式失败

#### 验收标准

- 缺失 profile 时不能崩溃
- 能返回明确错误或安全回退
- 有对应测试覆盖缺失场景

---

### Critical-2：runtime 已接主链路，但尚未真正完成主链路执行接管

#### 位置

- `backend/src/gateway/agent_bridge.py`

#### 问题描述

当前 runtime controller 虽然已接入网关主路径，但 planner / executor 实际仍通过 `runtime_legacy_bridge` 进入执行路径。

这意味着：

- 从控制平面看，runtime 已经进了主链路
- 从执行平面看，核心执行仍依赖 legacy 路径

#### 影响

- 容易在架构认知上造成“已完成 runtime 主链路替换”的误判
- 排查故障时会出现“看起来在 runtime，实际问题在 legacy 路径”的调试分裂
- 会延缓 runtime 真正收口

#### 要求

必须明确回答并落实其一：

1. **若这是过渡方案**：
   - 在实现与文档中明确标注当前属于过渡态
   - 明确说明 legacy bridge 的存在是阶段性安排
   - 定义退出条件

2. **若目标是最终态**：
   - 继续去除 controller 对 legacy bridge 的关键执行依赖
   - 形成原生 runtime planner / executor / assessment 闭环

#### 验收标准

- 可以清楚说明：runtime 当前到底是“控制壳”还是“完整执行链路”
- 文档、代码、测试口径一致

---

### Critical-3：缺少足够强的主链路集成验证，无法证明 runtime 方案整体已跑通

#### 问题描述

虽然已有部分单测 / 集成测试覆盖 turn controller、child flow、resume flow，但当前仍缺少能够直接证明如下链路的完整集成验证：

- gateway entry
- runtime prepare turn
- runtime execute
- persistence / transcript / snapshot
- resume / reconnect（如适用）

#### 影响

- 只能证明“模块能工作”，不能证明“主链路能工作”
- 不足以支撑“完全可运行”的结论

#### 要求

至少补一条完整主链路集成测试，用于证明 runtime 在真实入口路径上的可用性。

#### 验收标准

- 能证明从入口到运行到状态持久化的完整链路可用
- 测试结果能支撑对外宣称“主链路已接入并可运行”

---

## Important（建议尽快修）

### Important-1：child depth 的配置语义与实际运行语义不一致

#### 位置

- `backend/src/runtime/service.py`

#### 问题描述

`child_max_depth` 看起来表达的是 child 层级能力，但在运行时策略里被压缩为近似 0 / 1 的 `max_spawns` 控制。

#### 影响

- 配置表达能力与运行能力不一致
- 容易让维护者误以为系统支持更完整的多层 child orchestration
- 后续扩展时会造成认知偏差

#### 建议

二选一：

1. 将配置语义收缩为当前真实能力
2. 将运行时实现补齐到与配置语义一致

#### 期望结果

配置含义、运行行为、测试验证三者一致。

---

### Important-2：child profile 名称硬编码，降低配置演进弹性

#### 位置

- `backend/src/tools/builtin/delegate_task_tool.py`

#### 问题描述

当前直接在工具层硬编码：

- `child-default`

#### 影响

- 配置变更时容易产生隐式断裂
- runtime policy 的统一管理被绕过
- 工具层对配置命名产生不必要耦合

#### 建议

- 从 runtime defaults、session profile 或统一 policy 提供器中获取 child budget profile
- 避免工具层直接绑定 profile 字符串

---

### Important-3：runtime 与 legacy 的边界说明不足

#### 问题描述

从代码组织上看，runtime 已经具备完整结构；但从执行路径上看，系统仍是新旧混合。

这种状态如果没有明确文档说明，会让后续维护者误以为：

- runtime 已经 fully own main path
- legacy 路径已不重要
- 当前实现已经达到最终态

#### 建议

在 `arch/runtime/README.md` 或相关实现说明中补充：

- 哪些模块是最终态模块
- 哪些模块是兼容桥接模块
- 当前阶段的退出条件是什么
- 何时视为完成 legacy bridge 移除

#### 价值

- 降低维护成本
- 降低架构认知偏差
- 提升后续评审一致性

---

## Minor（可后续优化）

### Minor-1：进一步强化 runtime / child flow 的可观测性

#### 建议重点

增加以下关键节点的结构化日志或可观测字段：

- child turn 创建
- child profile 解析
- runtime controller 决策结果
- legacy bridge fallback / bridge execution
- child complete / archive 结果

#### 价值

后续排查“到底卡在 runtime 还是 legacy”会更高效。

---

### Minor-2：补足 architecture guard tests

#### 建议增加的测试类型

- 配置缺失时的失败测试
- child profile fallback 测试
- legacy bridge 开启 / 关闭下的行为差异测试
- runtime persistence 下 resume / reconnect 一致性测试

#### 价值

防止架构性假设在后续迭代中被破坏。

---

## 四、优点与已达成项

### 1. runtime 核心骨架已经成型

包括：

- services 装配
- session orchestration
- persistence abstraction
- adapters
- controller shell
- child flow 接入

这说明当前分支不是“只做了文档映射”，而是已经进入可运行工程阶段。

### 2. 分层设计总体健康

- 运行时相关代码没有明显散落到业务层各处
- 关键职责已被归位到各自模块
- repository / adapter / orchestrator 的组合是合理的

### 3. child flow 已进入真实工具路径

这点非常关键。它说明 runtime 不只是未来规划，而是已接入实际功能链路。

### 4. 有意识地保留兼容桥接

虽然 legacy bridge 仍是当前关键依赖，但从工程迁移角度看，这是一种可以理解的过渡策略。问题不在于过渡本身，而在于当前缺少足够明确的“过渡态边界说明”和“退出条件”。

---

## 五、合并建议

### 场景 A：如果这是“runtime 第一阶段 / 过渡版本”PR

**建议：有条件合并。**

前提是至少先处理以下项：

1. 修复 child budget profile 空值风险
2. 明确 runtime 与 legacy 的实际关系与边界
3. 补足最关键的主链路验证或明确其未完成状态

### 场景 B：如果这是“runtime 已完成主链路替换”的 PR

**建议：不按该结论合并。**

原因是：

- 当前还不能证明 runtime 已完整接管执行主链路
- 也还不能证明整体完全可运行
- 文档目标与执行现实之间仍存在差距

---

## 六、最终结论

### 最终判断

当前分支对 `arch/runtime/README.md` 的实现应定义为：

> **结构上基本对齐，主链路已有接入，但整体仍未完全收口。**

### 最终分项结论

- **是否符合技术方案**：基本符合，但偏阶段实现，不是最终态
- **是否开发完整**：不完整
- **是否集成主链路**：已集成，但未完全接管
- **是否完全可以运行**：不能下此结论，只能认为部分路径可运行
- **是否存在 bug**：存在明确风险点
- **架构是否合理**：合理，方向正确
- **是否低耦合高内聚**：模块结构较好，但执行链路仍受 legacy 耦合影响
- **设计模式是否良好**：总体良好，尤其是 orchestrator / repository / adapter 的分层思路

### 一句话结论

**这是一个完成度较高的 runtime 过渡版本，不是最终收口版本。**
