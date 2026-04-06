# 压缩策略问题修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一当前上下文压缩策略的配置、预算计算和入口契约，修复已确认 bug，并让实现与现有测试/配置预期重新一致。

**Architecture:** 以 `ContextCompressionManager` 作为唯一压缩决策中心，统一接收消息、system prompt、tools schema、运行时预算画像等输入；`XAgentContextAdapter` 只负责清洗/组装上下文，不再各自维护隐式预算逻辑。先补齐配置模型与接口契约，再修正预算计算时机、缓存语义和质量门槛，最后补回归测试。

**Tech Stack:** Python 3.11+, Pydantic, pytest, tiktoken, SQLAlchemy, agent_core context adapter

---

## 一、问题清单

### P0：配置模型与运行配置脱节

**现象**
- `backend/x-agent.yaml` 已包含 `max_context_tokens`、`max_tool_message_chars`、`trigger_ratio` 等字段。
- `backend/src/config/models.py` 中 `CompressionConfig` 只定义了 `threshold_rounds`、`threshold_tokens`、`retention_count`。

**影响**
- 配置文件中的大部分压缩预算参数不会进入运行时。
- 测试与实现对 `CompressionConfig` 的理解不一致。
- 运行策略和预期策略已经分叉。

**根因**
- 配置模型没有随压缩策略演进同步更新。

**修复原则**
- 以 `x-agent.yaml` 和现有预算测试为准，补齐 `CompressionConfig` 字段。
- 对字段进行明确分组：静态阈值、硬上限、动态触发、质量门槛、工具输出裁剪、模式选择。

---

### P0：压缩入口接口与测试约定脱节

**现象**
- `backend/src/agent_core/adapters/context_adapter.py` 的 `prepare_context()` 不接受 `tools`。
- adapter 构造器不支持 `context_assembler`。
- 测试已验证 `hybrid` / `stateful` 模式和 tools token 预算。

**影响**
- 当前运行代码无法真正执行“工具 schema 纳入预算”“stateful/hybrid 模式切换”等策略。
- 测试覆盖的是未来设计，线上代码还是旧路径。

**根因**
- adapter / manager / tests 三者未在同一轮重构中完成。

**修复原则**
- 统一 `ContextPort` → `XAgentContextAdapter` → `ContextCompressionManager` 三层签名。
- 明确模式分流：`legacy`、`hybrid`、`stateful`。

---

### P0：预算计算时机错误，漏算后续经验注入

**现象**
- `agent_loop` 先压缩，再拼接 experience prompt。

**影响**
- 压缩阶段认为上下文未超限，但真实发给 LLM 时可能超限。
- 问题只在经验内容较大时暴露，隐蔽性强。

**根因**
- 预算决策点早于完整 prompt 组装点。

**修复原则**
- 把 experience prompt 视为 system prompt 的一部分，在压缩决策前纳入预算。
- 保证“决策时看到的 token 总量”与“实际发送给 LLM 的 token 总量”一致。

---

### P0：触发条件只看新增消息，忽略全局预算

**现象**
- `ContextCompressionManager.prepare_context()` 在有缓存时只看 `new_message_count` / `new_token_count`。
- `total_tokens` 只记录日志，不参与决策。

**影响**
- 历史压缩结果 + system prompt + tools + experience 组合后可能已接近上限，但因为“新增很少”而不再压缩。
- 这是典型的局部阈值替代全局预算。

**根因**
- 当前逻辑把“避免重复压缩”优先级放得高于“保证整体预算安全”。

**修复原则**
- 决策顺序改为：
  1. 先看总预算是否超 trigger/hard cap
  2. 再看新增消息是否值得增量压缩
- 缓存优化只能建立在总预算安全的前提下。

---

### P0：tools schema 成本未纳入预算

**现象**
- 当前 `prepare_context()` 不接收 tools。
- token 预算只统计 messages 和 system prompt。

**影响**
- 无工具时不超限，有工具时瞬间超限。
- 工具越多、schema 越复杂，风险越高。

**根因**
- 压缩模块的输入面不完整。

**修复原则**
- 增加 `tools` 参数。
- 使用 `TokenCounter.count_tool_definitions()` 或等价实现纳入总预算。
- 若 `TokenCounter` 尚未实现该方法，先补实现与测试。

---

### P1：从 DB 恢复缓存时，summary 语义不纯

**现象**
- `_load_cache_from_db()` 直接把摘要 system message 的完整 `content` 放进 `cache.summary`。
- 正常压缩路径返回的是摘要正文，DB 恢复路径返回的是“带 marker 和尾提示的整段消息”。

**影响**
- `PreparedContext.summary` 的语义不稳定。
- 上层展示、日志、调试输出会混入包装文本。

**根因**
- manager 侧重复实现了摘要抽取逻辑，但未和 compressor 共享同一规则。

**修复原则**
- 统一用一个“摘要消息 <-> 纯摘要文本”转换函数。
- manager 不应自行维护另一套解析规则。

---

### P1：压缩没有质量门槛，可能压了也没收益

**现象**
- `_compress_context()` 压完后直接接受结果。
- 测试里已体现 `compression_quality_gate_enabled` / `min_compression_ratio` / `min_token_savings` 的需求。

**影响**
- 摘要调用增加耗时和信息失真，但实际只节省极少 token。
- 对低收益压缩没有回退机制。

**根因**
- 旧版实现只关心“能不能压”，不关心“值不值得压”。

**修复原则**
- 加质量门槛：节省比例和绝对节省 token 任一不达标则回退原文。
- 回退时不记录 compression event。

---

### P1：`retention_count` 以消息条数为单位，语义不稳定

**现象**
- 当前保留区按“消息条数”切分。
- 工具调用会扩展为多条消息，导致同样的 `retention_count` 在不同会话中语义差异很大。

**影响**
- “保留 50 条”并不等于“保留最近 25 轮”。
- 多工具会话下，最近对话上下文可能比预期短很多。

**根因**
- 实现使用简单切片而非轮次/预算驱动保留。

**修复原则**
- 短期先保持按消息条数，但补注释和测试，明确它是 message-based retention。
- 中期可演进为“按轮次 + token 上限双约束”的保留策略。

---

### P2：tool 边界保护只保证协议合法，不保证语义完整

**现象**
- `_find_safe_split_point()` 只避免让保留区开头从 `tool` 消息开始。

**影响**
- 可以避免 API 400，但不能保证一组完整的 tool 交互语义都还在保留区。

**根因**
- 当前算法只处理最低限度的结构约束。

**修复原则**
- 短期不做复杂重写，只补针对 assistant/tool/assistant 组合的回归测试。
- 后续如继续演进，再改成“按完整 tool transaction 保留”。

---

## 二、修复方案设计

### 方案目标

把当前策略收敛成一条清晰链路：

1. 完整组装预算输入（messages + system prompt + experience + tools）
2. 根据 mode 选择上下文构建方式（legacy / hybrid / stateful）
3. 由 `ContextCompressionManager` 统一做预算判断
4. 压缩后执行质量门槛校验
5. 安全写入压缩事件与缓存

---

### 方案 A：统一配置模型（必须先做）

**修改文件**
- `backend/src/config/models.py`
- `backend/x-agent.yaml`
- `backend/tests/unit/test_runtime_budget_controls.py`

**新增/补齐字段建议**
- `mode: Literal["legacy", "hybrid", "stateful"] = "legacy"`
- `max_context_tokens: int`
- `max_tool_message_chars: int`
- `trigger_ratio: float`
- `output_reserve_ratio: float`
- `min_output_reserve_tokens: int`
- `safety_margin_ratio: float`
- `min_safety_margin_tokens: int`
- `compression_quality_gate_enabled: bool = False`
- `min_compression_ratio: float = 0.0`
- `min_token_savings: int = 0`

**设计要求**
- 给出默认值和上下界约束。
- 增加 validator，避免明显非法组合。
- 让 YAML、Pydantic、测试三者一致。

---

### 方案 B：统一上下文入口契约（高优先级）

**修改文件**
- `backend/src/agent_core/ports/context_port.py`
- `backend/src/agent_core/adapters/context_adapter.py`
- `backend/src/services/compression/manager.py`
- `backend/src/agent_core/agent_loop.py`

**目标签名**
- `prepare_context(session_id, messages, system_prompt="", tools=None)`

**职责划分**
- `agent_loop`：先组装完整 `system_prompt`（包括 experience prompt），再调用 `prepare_context()`。
- `XAgentContextAdapter`：
  - 清洗消息
  - 裁剪超大 tool message
  - hybrid/stateful 模式下调用 assembler
  - 把 tools 和最终 system prompt 传给 manager
- `ContextCompressionManager`：
  - 做预算决策
  - 做压缩
  - 做质量门槛判断
  - 做缓存/落库

**关键原则**
- 不允许“发给 LLM 的内容”和“预算决策时看到的内容”不一致。

---

### 方案 C：重构压缩触发逻辑为“全局预算优先”

**修改文件**
- `backend/src/services/compression/manager.py`
- `backend/src/services/compression/token_counter.py`
- `backend/tests/unit/test_runtime_budget_controls.py`

**建议决策顺序**
1. 计算：
   - message tokens
   - system prompt tokens
   - tools schema tokens
   - 组合 total prompt tokens
2. 解析预算画像：
   - 优先运行时 profile
   - 否则回退静态 config
3. 触发规则：
   - 若 `total_prompt_tokens >= hard_context_limit`：强制压缩
   - 若 `total_prompt_tokens >= trigger_tokens`：优先压缩
   - 若未达总预算阈值，再用 `new_message_count/new_token_count` 作为增量压缩信号

**设计结果**
- 缓存优化保留，但不能覆盖硬预算判断。
- 真正解决“新增少但总体已超”的问题。

---

### 方案 D：补上 tool schema 与 tool output 两类预算控制

**修改文件**
- `backend/src/services/compression/token_counter.py`
- `backend/src/agent_core/adapters/context_adapter.py`
- `backend/tests/unit/test_runtime_budget_controls.py`

**两类处理**
1. **tool schema**：纳入发送前总预算
2. **tool output message**：在 adapter 层按 `max_tool_message_chars` 截断

**截断策略**
- 只截断 `role == "tool"` 的 content
- 尾部追加统一提示，例如 `...[tool output truncated]`
- 保留 `tool_call_id`

**理由**
- schema 控总预算
- output 控单条消息爆炸
- 这两个问题不能混为一谈

---

### 方案 E：统一摘要编码/解码规则

**修改文件**
- `backend/src/services/compression/compressor.py`
- `backend/src/services/compression/manager.py`
- `backend/tests/unit/test_compressor.py`

**重构建议**
在 `ContextCompressor` 内集中提供：
- `build_summary_message(summary: str) -> dict`
- `extract_summary_text(message: dict) -> str`
- `is_summary_message(message: dict) -> bool`

**收益**
- manager 不再自己猜摘要格式。
- DB 恢复缓存和在线压缩返回同一语义。
- marker 变更时不需要多处同步。

---

### 方案 F：增加压缩质量门槛

**修改文件**
- `backend/src/services/compression/manager.py`
- `backend/tests/unit/test_runtime_budget_controls.py`

**策略**
- 压缩后计算：
  - `token_savings = original - compressed`
  - `compression_ratio = token_savings / original`
- 若质量门槛开启且：
  - `token_savings < min_token_savings` 或
  - `compression_ratio < min_compression_ratio`
- 则返回原始消息，不写 compression event，不更新缓存。

**注意**
- 强制压缩场景下可考虑允许“质量门槛失效”，否则硬上限场景会无路可走。
- 建议把“强制压缩”和“收益压缩”分开处理。

---

## 三、实施顺序

### 阶段 1：收敛契约
1. 扩展 `CompressionConfig`
2. 更新 `ContextPort.prepare_context()` 签名
3. 更新 `XAgentContextAdapter.prepare_context()` 签名
4. 更新 `ContextCompressionManager.prepare_context()` 签名
5. 更新 `agent_loop` 调用点，先拼完 experience prompt 再压缩

### 阶段 2：修预算
6. `TokenCounter` 增加 tools schema 计数能力
7. manager 改成“总预算优先，增量阈值次之”
8. adapter 增加 tool output 截断

### 阶段 3：修缓存与摘要语义
9. 抽出摘要消息编解码辅助函数
10. 修复 `_load_cache_from_db()` 返回纯摘要文本
11. 为 DB 恢复路径补测试

### 阶段 4：补质量门槛
12. manager 加 quality gate
13. 增加“低收益压缩回退”测试
14. 明确强制压缩场景是否绕过 gate

### 阶段 5：回归验证
15. 跑 `test_compressor.py`
16. 跑 `test_runtime_budget_controls.py`
17. 跑相关 adapter / agent loop 测试
18. 检查 `x-agent.yaml` 能正常加载

---

## 四、测试设计

### 必测用例

**配置与契约**
- `CompressionConfig` 能加载 YAML 中所有字段
- `prepare_context(..., tools=...)` 全链路签名一致

**预算控制**
- 总 token 超 hard cap 时，即使新增消息很少也会触发压缩
- tool schema 把总预算推过阈值时触发压缩
- experience prompt 计入预算

**adapter 行为**
- tool message 超长时被裁断
- `hybrid` 模式会先调用 assembler 再进 manager
- `stateful` 模式直接走 assembler，不走 legacy manager

**缓存/摘要**
- 在线压缩返回的 `summary` 与 DB 恢复缓存后的 `summary` 语义一致
- old summary 不会被再次摘要化

**质量门槛**
- 压缩收益不足时回退原消息
- 强制压缩时 quality gate 行为符合设计

**结构正确性**
- tool_calls/tool 消息不会被切裂到非法结构

---

## 五、风险与取舍

### 风险 1：一次改动面较大
涉及 config、adapter、manager、agent loop、tests 多处联动。

**控制方式**
- 先统一签名和配置，再改算法。
- 每一步先补测试再改代码。

### 风险 2：stateful/hybrid 逻辑可能未完全落地
测试已经表达了方向，但源码里可能还有未接入的 assembler 依赖。

**控制方式**
- 若短期目标是修线上压缩 bug，可先完整修复 legacy + budget path。
- hybrid/stateful 如依赖未成熟，可先补接口兼容和 guard，避免半实现。

### 风险 3：质量门槛与硬上限冲突
若总预算已超上限，quality gate 不能简单回退原文。

**控制方式**
- 引入“forced compression”分支，强制压缩不经过收益否决。

---

## 六、建议的落地策略

### 最小可用修复（推荐先做）
先修这 5 项：
1. 补齐 `CompressionConfig`
2. `prepare_context` 支持 `tools`
3. experience prompt 前移到压缩判断之前
4. 总预算优先于新增预算
5. tool schema / tool output 预算控制

这样可以先解决最危险的线上问题：**预算误判和接口漂移**。

### 第二阶段再做
6. DB 缓存摘要语义统一
7. quality gate
8. retention 策略优化
9. 更完整的 tool transaction 保留

---

## 七、建议修改文件清单

**核心代码**
- `backend/src/config/models.py`
- `backend/src/agent_core/ports/context_port.py`
- `backend/src/agent_core/adapters/context_adapter.py`
- `backend/src/agent_core/agent_loop.py`
- `backend/src/services/compression/manager.py`
- `backend/src/services/compression/compressor.py`
- `backend/src/services/compression/token_counter.py`
- `backend/x-agent.yaml`

**测试**
- `backend/tests/unit/test_compressor.py`
- `backend/tests/unit/test_runtime_budget_controls.py`
- 可能补：adapter/agent loop 相关测试文件

---

## 八、完成标准

满足以下条件才算修复完成：

1. `CompressionConfig` 与 YAML 字段一致
2. 压缩预算包含 messages + system prompt + experience + tools schema
3. 总预算超限时一定触发压缩，不会被“新增消息少”绕过
4. adapter 能裁断超长 tool 输出
5. DB 恢复缓存后 `summary` 语义一致
6. 低收益压缩可回退（若启用 gate）
7. 现有预算控制测试通过，且新增回归测试通过
