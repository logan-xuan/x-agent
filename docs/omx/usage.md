# OMX 使用文档

更新时间：2026-04-11

本文面向当前仓库 `/Users/xuan.lx/Documents/x-agent`，用于说明 `oh-my-codex (omx)` 的安装状态、常用命令、推荐工作流，以及在本项目中的实际使用方式。

## 1. 文档目标

`OMX` 是运行在 `Codex CLI` 之上的工作流编排层。它不替代 `Codex`，而是补充以下能力：

- 统一的会话启动方式
- 预装的技能、提示词和 agent 配置
- `deep-interview / ralplan / ralph / team` 这类工作流命令
- `.omx/` 下的状态、计划、日志和协作文件

对当前仓库来说，`OMX` 最有价值的地方不是“更多命令”，而是把需求澄清、方案确认、持续执行、并行协作串成一条稳定的链路。

## 2. 当前环境

当前机器上的关键版本如下：

- `oh-my-codex v0.12.4`
- `codex-cli 0.119.0`
- `Node.js v23.11.0`
- 项目根目录：`/Users/xuan.lx/Documents/x-agent`

当前 `omx doctor` 结果为通过，但有两个已知提醒：

- `omx explore` 依赖 Rust 预编译或本地 `cargo`，当前环境缺失，所以不要把它当成主入口
- 旧目录 `~/.agents/skills` 仍然存在，虽然为空，但可能导致技能列表重复显示

## 3. 安装与校验

如需在新机器上安装，官方主路径如下：

```bash
npm install -g @openai/codex oh-my-codex
omx setup
omx doctor
```

若只想确认当前环境状态，可以直接执行：

```bash
omx --version
omx doctor
omx status
```

## 4. 快速开始

### 4.1 最常用启动方式

在项目目录中启动：

```bash
cd /Users/xuan.lx/Documents/x-agent
omx --high
```

说明：

- `--high` 会把模型推理强度调到高档，适合日常编码与评审
- 这是当前仓库默认推荐的启动方式

### 4.2 强力模式

如果你明确希望绕过审批与沙箱，可以使用：

```bash
omx --madmax --high
```

说明：

- `--madmax` 很激进，只建议在你完全理解风险时使用
- 它会跳过常规审批保护，不适合作为默认模式

### 4.3 在 tmux 中启动

如果你准备使用 `team` 并行团队，建议先进入 `tmux`：

```bash
tmux new -s xagent
cd /Users/xuan.lx/Documents/x-agent
omx --high
```

## 5. 常用命令

### 5.1 状态与诊断

```bash
omx doctor
omx status
omx hud --watch
omx resume
omx session search "team api"
```

用途说明：

- `omx doctor`：检查安装、技能、配置、MCP、状态目录是否正常
- `omx status`：查看 `hud`、`notify-hook`、`tmux-hook` 等当前模式状态
- `omx hud --watch`：每秒刷新一次 HUD 面板，适合在第二个终端观察会话状态
- `omx resume`：恢复之前的交互会话
- `omx session search`：检索本地历史会话

### 5.2 核心工作流命令

```text
$deep-interview
$ralplan
$ralph
$team
```

这些命令的职责边界如下：

- `$deep-interview`：需求还不够清晰时，先澄清目标、边界、非目标、决策权限
- `$ralplan`：在实现之前做共识规划，收敛方案、风险和验证路径
- `$ralph`：一个 owner 持续推进直到验证通过
- `$team`：在 `tmux` 中拉起多个 worker 并行协作，适合大任务

### 5.3 团队运行时命令

```bash
omx team 3:executor "fix failing tests"
omx team status <team-name>
omx team await <team-name> --timeout-ms 30000 --json
omx team resume <team-name>
omx team shutdown <team-name>
```

补充说明：

- `omx team` 现在默认会为 worker 使用独立 worktree
- `--worktree` 已经是兼容性保留参数，不再是主路径
- `team` 更适合“持续运行、共享状态、可恢复”的并行任务，不适合很小的一次性 fanout

### 5.4 Ralph 模式命令

```bash
omx ralph "Fix flaky notify-hook tests"
omx ralph --prd "Ship release checklist automation"
omx ralph --no-deslop "Refactor state hydration"
```

说明：

- `omx ralph` 是“持续干到完成”的入口
- `--prd` 会在 `.omx/` 中初始化更完整的计划与进度工件
- `--no-deslop` 会跳过最后一轮 `ai-slop-cleaner`

## 6. 推荐工作流

### 6.1 小任务

适合单文件、小修复、明确目标的情况：

```bash
omx --high
```

会话中直接描述任务，或者显式进入 Ralph：

```text
$ralph "修复 backend/src/runtime/context/compression_verifier.py 的回滚判断"
```

### 6.2 中等任务

适合跨几个模块，但范围已基本可控的任务：

```text
$deep-interview --quick "重构 runtime compression pipeline，拆开预算决策与语义裁剪"
$ralplan --interactive "基于澄清后的需求规划实现路径和测试策略"
$ralph "按已批准方案执行并完成验证"
```

### 6.3 大任务

适合跨 `runtime/context`、`runtime/turn`、`gateway`、`tests` 的任务：

```text
$deep-interview --standard "澄清 runtime compression redesign 的边界、非目标、验证标准"
$ralplan --interactive --deliberate "产出跨模块的实现计划、风险列表和回归方案"
$team 3:executor "按批准方案并行推进实现、测试和验证"
```

推荐理解方式：

- `deep-interview` 解决“做什么”和“不要做什么”
- `ralplan` 解决“怎么做最稳”
- `ralph` 解决“一个 owner 持续推进到完成”
- `team` 解决“需要并行拆 lane 的时候怎么跑”

## 7. 当前仓库的推荐用法

当前仓库是一个 Python/FastAPI 项目，且 `AGENTS.md` 已经给出了清晰的单测与代码风格约束，因此在本仓库内更推荐下面这套模板。

### 7.1 Runtime Compression 重构模板

```text
$deep-interview --quick "重构 runtime compression redesign，明确 scope、non-goals、回滚策略和验证标准"
$ralplan --interactive --deliberate "基于澄清后的规格，为 backend runtime compression redesign 生成执行计划和验证路径"
$team 3:executor "按已批准计划执行 runtime compression redesign，并以 pytest + ruff 作为完成门槛"
```

### 7.2 Ralph 验证门槛模板

在当前仓库内，建议直接把验证命令写进 prompt，让 Ralph 明确完成标准：

```text
$ralph "实现 runtime compression redesign，完成后必须执行：
cd backend &&
pytest --no-cov tests/unit/test_runtime_compression_pipeline.py -q &&
pytest --no-cov tests/unit/test_runtime_compression_verifier.py -q &&
pytest --no-cov tests/unit/test_runtime_gateway_adapter.py -q &&
pytest --no-cov tests/unit/test_runtime_turn_controller.py -q &&
pytest --no-cov tests/unit/test_runtime_compression_profiles.py -q &&
ruff check src"
```

### 7.3 HUD 观察模板

先在一个终端启动 OMX：

```bash
cd /Users/xuan.lx/Documents/x-agent
omx --high
```

再在第二个终端里查看 HUD：

```bash
cd /Users/xuan.lx/Documents/x-agent
omx hud --watch
```

如果当前没有活跃会话，`omx status` 往往会显示 `hud: inactive`。这不是故障，只是说明当前没有运行中的 OMX 模式。

## 8. 常见场景建议与详细案例

这一节不只回答“什么时候用哪个命令”，还回答“为什么这样选”。对当前仓库来说，真正有价值的是减少模式切换失误，避免把简单任务复杂化，或者把复杂任务过早压进单线程执行。

### 8.1 案例一：单文件、小范围、目标明确的修复

典型场景：

- 某个单测失败，定位已经明确
- 只会改一个或两个文件
- 不需要先澄清需求，也不需要并行拆分

推荐做法：

```text
omx --high
$ralph "修复 runtime compression verifier 的回滚判断，并执行对应单测验证"
```

为什么这样选：

- 这种任务的核心矛盾不是“方案不清楚”，而是“尽快做完并验证”
- `deep-interview` 会增加前置澄清成本，但对明确 bug 收益不大
- `team` 需要 tmux、lane 拆分和状态协调，任务太小时成本高于收益
- 用 `ralph` 可以把“修复 + 验证”绑成单一完成链路，避免只改代码不跑测试

适用信号：

- 你已经知道要改哪个函数或文件
- 成功标准可以直接写成测试命令或 lint 命令
- 任务预计不需要跨很多模块来回讨论

### 8.2 案例二：需求模糊、用户明确说“不要假设”

典型场景：

- 用户只说“把 runtime compression redesign 做好”
- 你不确定边界、非目标、可自动决策项
- 用户强调“先别乱做”“不要假设”

推荐做法：

```text
$deep-interview --quick "澄清 runtime compression redesign 的目标、边界、非目标、回滚策略和验证标准"
$ralplan --interactive "基于澄清后的结论规划实现路径和测试策略"
```

为什么这样选：

- 这类任务的风险不在执行速度，而在一开始就做错方向
- `deep-interview` 负责把“要做什么、不要做什么、谁拍板”先说清楚
- `ralplan` 把口头澄清转成实现顺序、验证策略和风险控制，避免进入实现后再返工
- 如果直接进 `ralph`，往往会把未确认的假设偷偷带入实现

适用信号：

- prompt 里大量出现“先分析”“先澄清”“不要默认”
- 你无法一句话说清楚验收标准
- 同一任务可能有多种互斥方案，但用户还没表态

### 8.3 案例三：跨模块改造，但强耦合，优先单 owner 推进

典型场景：

- 会改 `runtime/context`、`runtime/turn`、`gateway`，但改动强依赖先后顺序
- 例如要先收口接口，再改调用方，再补测试
- 可以预计中间会不断调整方案

推荐做法：

```text
$deep-interview --quick "明确跨模块改造的 scope、兼容边界和验证标准"
$ralplan --interactive --deliberate "为跨 runtime/gateway 的改造生成顺序化计划"
$ralph "按已批准计划顺序实施，并以 pytest + ruff 作为完成门槛"
```

为什么这样选：

- 虽然是大任务，但不代表必须并行
- 如果文件之间高度耦合，多个 worker 同时写容易制造冲突和回滚成本
- `ralph` 更适合“一个 owner 顺序推进、多次验证、持续收敛”的任务
- 这里的关键是降低上下文切换和合并复杂度，而不是盲目追求并行吞吐

适用信号：

- 每一步都依赖上一步的接口或类型变更
- 你很难把写权限切成互不冲突的 2 到 4 份
- 实现路径偏线性，而不是天然扇出

### 8.4 案例四：可以拆 lane 的大任务，优先 `team`

典型场景：

- 任务明确，计划也已经批准
- 可以拆成多个相对独立的 lane
- 需要较长执行时间，并且希望支持中断恢复

推荐做法：

```text
$deep-interview --standard "澄清大任务边界、非目标和完成定义"
$ralplan --interactive --deliberate "生成可并行执行的 lane 划分、风险和验证计划"
$team 3:executor "按批准方案并行推进实现、测试和验证"
```

如果拿当前仓库举例，比较合理的 lane 可能是：

- lane 1：`runtime/context` 与压缩策略核心实现
- lane 2：`gateway` / `runtime/turn` 适配与调用链调整
- lane 3：单测补齐、回归验证、ruff 检查与结果汇总

为什么这样选：

- `team` 的价值不只是“多几个 agent”，而是有 tmux、邮箱、共享状态、可恢复运行时
- 当 lane 能清晰切开时，并行确实能缩短总耗时
- 测试和验证可以与实现并行，而不是所有代码写完后再集中补
- 对跨多个目录、执行时间较长的任务，`team` 的恢复能力明显优于临时 fanout

适用信号：

- 能明确写出每个 lane 的文件边界或职责边界
- 不同 worker 之间只需要轻量协调，而不是频繁改同一批文件
- 任务完成定义已经足够清楚，可以交给 worker 按 lane 执行

### 8.5 案例五：长任务的监控、恢复和二次进入

典型场景：

- 任务已经跑起来了，但你想从另一个终端盯状态
- shell 断开过，需要恢复会话
- `team` 已启动，需要查看当前 worker 状态

推荐做法：

```bash
cd /Users/xuan.lx/Documents/x-agent
omx status
omx hud --watch
omx resume
omx team status <team-name>
omx team await <team-name> --timeout-ms 30000 --json
```

为什么这样选：

- `hud --watch` 适合做观察，不适合拿来判断“是否启动成功”
- `status` 先告诉你当前有没有活跃模式，避免把 `hud: inactive` 误判成故障
- `resume` 解决的是交互会话恢复，不是团队 worker 恢复
- `team status / await / resume` 解决的是团队运行时视角的问题

适用信号：

- 你已经有会话或 team 在跑
- 你关心的是“现在到哪一步了”，不是“重新规划怎么做”
- 你需要把监控和执行分离到不同终端

### 8.6 什么时候只用 `omx --high`

满足下面任一条件时，可以直接进入正常会话：

- 任务目标明确
- 文件或函数范围明确
- 不需要先做大范围需求澄清
- 不需要 tmux 并行 worker

### 8.7 什么时候优先用 `deep-interview`

满足下面任一条件时，先澄清再规划更稳：

- 用户目标模糊
- 需求边界不清楚
- 不确定哪些内容应明确排除
- 不确定哪些决策可以自动做、哪些必须先确认

### 8.8 什么时候优先用 `team`

满足下面任一条件时，`team` 明显优于单线程 Ralph：

- 任务可以拆成 2 到 4 条独立 lane
- 需要持续 tmux worker
- 需要共享状态、邮箱、恢复能力
- 任务预计会跨多个模块和较长执行时间

### 8.9 什么时候暂时不要依赖 `explore`

当前机器上，`omx doctor` 已提示 `Explore Harness` 缺少可用 Rust 预构建或本地 `cargo`。因此：

- 可以继续正常使用 `deep-interview / ralplan / ralph / team`
- 不要把 `omx explore` 作为主入口
- 若确实要用 `explore`，先补齐 Rust/cargo 或配置 `OMX_EXPLORE_BIN`

## 9. 常见问题

### 9.1 `omx hud --watch` 没有内容

先检查：

```bash
omx status
```

如果显示 `hud: inactive`，说明当前没有活跃会话。先启动一个 OMX 会话，再打开 HUD。

### 9.2 `team` 启不来

优先检查：

```bash
tmux -V
echo $TMUX
omx doctor --team
```

若不在 `tmux` 中，`team` 的使用体验通常会很差，甚至无法满足预期。

### 9.3 技能列表出现重复项

当前机器保留了一个空的旧目录 `~/.agents/skills`。如果 Codex 出现重复技能项，可以移走或归档这个目录。

## 10. 推荐的最小实践

如果你不想记太多命令，只记这一套就够了：

```bash
cd /Users/xuan.lx/Documents/x-agent
omx --high
```

进入会话后按任务规模选择：

```text
$deep-interview --quick "澄清需求"
$ralplan --interactive "收敛方案"
$ralph "执行到验证通过"
$team 3:executor "并行执行"
```

## 11. 资料来源

本文整理基于以下信息：

- 官方仓库 README：`https://github.com/Yeachan-Heo/oh-my-codex`
- 本机命令帮助：`omx --help`
- 本机子命令帮助：`omx team --help`、`omx ralph --help`、`omx session --help`、`omx hud --help`
- 本机安装健康检查：`omx doctor`
