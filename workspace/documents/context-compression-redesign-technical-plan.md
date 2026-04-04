# 上下文压缩重构技术方案

## 1. 文档目标

本文给出一份可以直接在当前仓库中落地的上下文压缩重构方案，目标是解决现有系统在长会话、调研、PRD、多 Agent 协作场景中的以下问题：

- 压缩事件频繁触发，但压缩收益接近 0
- 历史摘要在增量压缩中反复被带回上下文
- 长任务中的事实、证据、结论和对话被混在单一 prose 摘要中
- 上下文越长越不稳定，最终表现为 LLM 第二轮或后续轮次超时

本方案不追求推翻现有会话系统，而是基于当前代码结构做渐进式重构，重点改造：

- [manager.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/manager.py)
- [compressor.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/compressor.py)
- [context_adapter.py](/Users/xuan.lx/Documents/x-agent/backend/src/agent_core/adapters/context_adapter.py)
- [agent_loop.py](/Users/xuan.lx/Documents/x-agent/backend/src/agent_core/agent_loop.py)
- [memory/manager.py](/Users/xuan.lx/Documents/x-agent/backend/src/memory/manager.py)

## 2. 业界参考结论

### 2.1 已验证的优秀策略

调研后可以确认，业界稳定方案不是单一摘要算法，而是多策略组合：

1. 静态前缀缓存
2. 工作记忆保真保留
3. 结构化状态压缩
4. 历史记忆外存化
5. 检索式回填
6. 压缩收益门槛

### 2.2 对当前系统最有价值的参考

1. OpenAI `Compaction`
   核心思想不是把对话写成更短 prose，而是生成“可继续推理的紧凑上下文对象”。

2. Gemini `Context caching`
   核心思想是把大而重复的静态前缀与动态会话状态分离。

3. Anthropic 长上下文建议
   核心思想是把关键状态前置，把问题放在最后，并在长任务里抽取证据而不是依赖整段历史。

4. MemGPT
   核心思想是工作记忆和外部记忆分层，避免历史常驻 prompt。

5. RAG
   核心思想是将旧知识外存，通过检索按需回填，而不是让旧上下文永久驻留。

6. ReSum
   核心思想是对长期任务做 reasoning-state summarization，而不是只做聊天摘要。

### 2.3 本方案采取的原则

- 不再把压缩后的消息列表直接当作下一轮原始输入
- 不再用长 prose 摘要承担全部状态表达责任
- 事实证据与对话摘要分离
- 近期工作集保真，历史通过检索回填
- 所有压缩结果必须接受收益校验

## 3. 现状与根因

### 3.1 当前实现摘要

当前流程是：

1. `AgentLoop` 将当前消息转换为 LLM 格式
2. `ContextAdapter` 调用 `ContextCompressionManager.prepare_context()`
3. `ContextCompressionManager` 从内存或 DB 恢复最近一次 `compressed_messages`
4. 若触发阈值，则执行增量压缩
5. 增量压缩输入为 `cache.compressed_messages + new_messages`
6. `ContextCompressor` 保留第一条 `system`，提取后续摘要，再生成增量摘要
7. 将结果再次写回 `compression_events`

### 3.2 关键缺陷

#### 缺陷 1：错误的压缩输入模型

当前实现把上轮 `compressed_messages` 直接拼到新消息前面继续压缩：

- [manager.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/manager.py:263)

这意味着压缩器处理的不是“原始历史”，而是“已污染的压缩产物 + 新消息”。

#### 缺陷 2：第一条 system 消息被误判

当前压缩器会把第一条 `system` 消息永久保留：

- [compressor.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/compressor.py:85)

在增量压缩场景下，这条第一条 `system` 很可能已经是上轮注入的 `[历史对话摘要]`，并不是真正的原始系统提示。

#### 缺陷 3：摘要只拼接不治理

旧摘要和新摘要仅做字符串拼接：

- [compressor.py](/Users/xuan.lx/Documents/x-agent/backend/src/services/compression/compressor.py:175)

这会导致摘要单调增长，最终摘要本身成为 prompt 的主要负担。

#### 缺陷 4：固定 retention_count 导致无法回收预算

当前 `retention_count=50`：

- [x-agent.yaml](/Users/xuan.lx/Documents/x-agent/backend/x-agent.yaml:173)

在 52 到 55 条消息规模下，每次只剩 2 到 5 条消息可归档，压缩自然失效。

#### 缺陷 5：没有压缩质量门槛

当前实现会记录压缩事件，但不会验证：

- 是否至少回收了足够 token
- 是否保持关键状态完整
- 是否比上次压缩更优

这会让坏结果写回缓存，继续污染后续请求。

## 4. 目标架构

### 4.1 六层上下文模型

重构后，prompt 组装不再直接依赖压缩消息列表，而由六层组成：

1. `Static Prefix`
2. `Working Set`
3. `Session State`
4. `Evidence Ledger`
5. `Episodic Memory`
6. `Artifact References`

### 4.2 每层职责

#### 4.2.1 Static Prefix

内容：

- 系统提示
- agent 身份与角色
- 工具 schema
- 固定工作流指引

策略：

- 不进入摘要器
- 尽量缓存
- 独立计 token

#### 4.2.2 Working Set

内容：

- 最近 4 到 8 个完整 turn
- 当前未闭合的工具调用链
- 当前用户问题
- 当前轮的中间结果

策略：

- 完全保真
- 不摘要
- 强制靠近 prompt 尾部

#### 4.2.3 Session State

内容：

- 当前目标
- 子任务状态
- 已达成决策
- 用户约束
- 未解决问题
- 当前文件和产物
- 失败记录
- delegate 状态

策略：

- 结构化表达
- 每轮更新
- 控制在固定 token 预算内

#### 4.2.4 Evidence Ledger

内容：

- 调研结论
- 数值事实
- 来源引用
- 可信度
- 更新时间
- 适用任务

策略：

- 与聊天摘要分离
- research / PRD 模式优先注入
- 仅注入与当前目标高度相关的证据

#### 4.2.5 Episodic Memory

内容：

- 历史 turn 折叠成事件卡片
- 历史决策
- 历史失败与修复
- 历史产物引用

策略：

- 外存化到 DB + 向量库
- 按 query 检索回填

#### 4.2.6 Artifact References

内容：

- 长网页正文
- 终端长输出
- 文件内容
- delegate 原始报告

策略：

- 不直接进 prompt
- 只注入短摘要 + `artifact_ref`

## 5. 重构后的请求流程

### 5.1 高层流程

每轮请求变更为：

1. 读取 `Static Prefix`
2. 读取近期原始消息形成 `Working Set`
3. 从 DB 加载 `Session State`
4. 从 `Evidence Ledger` 检索相关证据
5. 从 `Episodic Memory` 检索相关历史事件
6. 动态组装 prompt
7. 如果超预算，再对 `Session State` 和检索结果做裁剪
8. 调用 LLM
9. 根据新消息更新 `Session State`
10. 将退出工作集的历史 turn 写入 `Episodic Memory`
11. 根据工具结果更新 `Evidence Ledger` 或 `Artifact Store`

### 5.2 新的压缩定义

重构后，“压缩”不再表示：

- 把完整聊天历史压成一个摘要消息

而是表示：

- 把历史对话转成结构化状态
- 把老消息移入可检索外存
- 在保真近期工作集的前提下回收预算

## 6. 数据模型设计

### 6.1 新增表：session_context_state

建议新增 SQLAlchemy 模型：

```python
class SessionContextState(Base):
    __tablename__ = "session_context_state"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_goal_json: Mapped[str] = mapped_column(Text, default="{}")
    active_subtasks_json: Mapped[str] = mapped_column(Text, default="[]")
    decisions_json: Mapped[str] = mapped_column(Text, default="[]")
    constraints_json: Mapped[str] = mapped_column(Text, default="[]")
    open_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    delegate_status_json: Mapped[str] = mapped_column(Text, default="[]")
    recent_failures_json: Mapped[str] = mapped_column(Text, default="[]")
    user_preferences_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_text: Mapped[str] = mapped_column(Text, default="")
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
```

说明：

- `summary_text` 不是长 prose 摘要，而是 SessionState 的紧凑文本表现
- `token_estimate` 用于快速预算判断

### 6.2 新增表：episodic_memory_events

```python
class EpisodicMemoryEvent(Base):
    __tablename__ = "episodic_memory_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    source_message_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
```

说明：

- 该表的 `summary + tags` 进入向量检索
- 用于替代“历史摘要常驻 prompt”

### 6.3 新增表：evidence_ledger_entries

```python
class EvidenceLedgerEntry(Base):
    __tablename__ = "evidence_ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    topic: Mapped[str] = mapped_column(String(255), index=True)
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="web")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    freshness_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
```

说明：

- 仅用于 research / PRD / code analysis 等事实密集型任务
- 该表也进入向量检索，但权重高于普通 episodic memory

### 6.4 新增表：artifacts

```python
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content_path: Mapped[str] = mapped_column(Text)
    preview_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
```

说明：

- 长工具输出、大网页正文、delegate 报告写这里
- prompt 只拿 `preview_text + artifact_ref`

## 7. 关键算法设计

### 7.1 Working Set 选择算法

输入：

- 当前 session 最近消息
- 当前是否存在未闭合 tool 调用
- 当前模式 `chat / research / writing / coding`

策略：

1. 默认保留最近 6 个 turn
2. 若存在未闭合 tool 调用，则强制保留其起始 assistant 和对应 tool 结果
3. 若是 `research / writing` 模式，额外保留最近一次“用户最终交付要求”消息
4. 若预算超限，优先裁剪旧 assistant 进度消息

输出：

- 一组精确保真的消息列表

### 7.2 Session State 更新算法

输入：

- 上次 `SessionContextState`
- 本轮新增 user / assistant / tool / delegate 结果

更新规则：

1. 从 user 消息提取 `current_goal / constraints / user_preferences`
2. 从 assistant 规划或结论提取 `active_subtasks / decisions / open_questions`
3. 从 tool 和 delegate 结果提取 `artifact_refs / delegate_status / recent_failures`
4. 将结构化状态重新渲染成紧凑文本
5. 若状态文本超预算，执行状态级再压缩

状态级再压缩规则：

- 保留全部 `current_goal`
- 保留未完成 `active_subtasks`
- 保留最新 10 条 `decisions`
- 保留最新 10 条 `recent_failures`
- `open_questions` 只保留 unresolved
- `artifact_refs` 保留最近和当前任务相关项

### 7.3 Episodic Memory 生成算法

触发时机：

- 某个 turn 退出 `Working Set`
- 某个阶段任务结束
- 某次 delegate 完成

事件卡生成格式：

```json
{
  "event_type": "decision|research|failure|artifact|delegate|user_preference",
  "title": "一句话标题",
  "summary": "2-4 句结构化摘要",
  "tags": ["prd", "research", "delegate", "timeout"],
  "artifact_refs": ["artifact:..."],
  "source_message_ids": ["msg1", "msg2"]
}
```

重要性评分：

- 用户明确要求 +0.3
- 结论型消息 +0.2
- 失败 / 重试 / 修复 +0.2
- 产物生成 +0.2
- 含来源证据 +0.1

### 7.4 Evidence Ledger 生成算法

仅在这些来源触发：

- `web_search`
- `fetch_web_content`
- `delegate_task` 的 research 结果
- 文件解析工具

抽取结构：

```json
{
  "topic": "数字人创业项目",
  "claim": "2025年上半年，抖音/快手AI数字人账号注册量同比增长300%",
  "source_url": "...",
  "source_title": "...",
  "confidence": 0.7,
  "freshness_at": "2026-04-03T..."
}
```

要求：

- 证据条目必须与来源绑定
- 没来源的内容只允许进 `SessionState`，不进 `Evidence Ledger`

### 7.5 检索回填算法

检索 query 由以下部分拼接：

- 当前用户问题
- `current_goal`
- `active_subtasks`
- 当前 agent id / task mode
- 当前已选 artifact refs

检索来源：

1. `Evidence Ledger`
2. `Episodic Memory`
3. 现有 `MemoryManager` 长期记忆

排序规则：

`final_score = semantic_score * 0.55 + recency_score * 0.2 + importance_score * 0.15 + source_match_score * 0.1`

### 7.6 压缩收益门槛

本次压缩结果只有满足下列条件才写回缓存：

1. 净回收至少 1000 tokens
2. 或压缩率至少 15%
3. 且关键字段无缺失：
   - `current_goal`
   - unresolved `open_questions`
   - in-flight `delegate_status`
   - 相关 `artifact_refs`

否则：

- 丢弃本次压缩结果
- 记录 `compression_quality_failed`
- 不写 DB 缓存

## 8. Prompt 组装策略

### 8.1 最终 prompt 顺序

最终发送给模型的内容顺序必须统一：

1. `Static Prefix`
2. `Session State`
3. `Evidence Ledger` 摘要块
4. 检索回来的 `Episodic Memory`
5. `Working Set`
6. 当前用户问题

原因：

- 把状态和证据提前
- 把问题放在最后，减少 Lost-in-the-Middle 风险

### 8.2 不同模式的预算

#### 普通对话模式

- 总目标预算：18k 到 22k
- `Session State`：800 到 1200
- 检索结果：1000 到 2000
- `Working Set`：3000 到 5000

#### 调研模式

- 总目标预算：22k 到 26k
- `Session State`：1000 到 1500
- `Evidence Ledger`：1500 到 2500
- `Episodic Memory`：1500 到 2500
- `Working Set`：3500 到 6000

#### 文档写作模式

- 总目标预算：20k 到 24k
- `Session State`：1000 到 1500
- `Artifact References`：1000 到 2500
- `Working Set`：3000 到 5000

### 8.3 裁剪优先级

预算不足时的裁剪顺序：

1. 去掉低重要度 episodic memory
2. 去掉低可信度 evidence
3. 合并 session state 中较老 decisions
4. 去掉冗余 assistant 进度消息
5. 最后才压缩 working set

## 9. 模块改造方案

### 9.1 保留的现有模块

以下模块保留并复用：

- `MemoryManager`
- `VectorStore`
- `HybridSearch`
- `AgentLoop`
- `LLMRouter`

### 9.2 需要新增的模块

建议新增：

- `backend/src/services/context/session_state_store.py`
- `backend/src/services/context/episodic_memory_store.py`
- `backend/src/services/context/evidence_ledger_store.py`
- `backend/src/services/context/artifact_store.py`
- `backend/src/services/context/context_assembler.py`
- `backend/src/services/context/session_state_updater.py`
- `backend/src/services/context/mode_detector.py`
- `backend/src/services/context/compression_quality.py`

### 9.3 现有模块职责调整

#### manager.py

从“压缩消息列表管理器”改为“预算与编排管理器”：

- 保留触发与预算计算
- 删除对 `compressed_messages` 的直接恢复依赖
- 改为协同 `ContextAssembler`

#### compressor.py

从“消息摘要器”改为“状态压缩器”：

- 输入不再是完整消息列表
- 输入改为 `SessionState`
- 输出为受预算控制的状态文本

#### context_adapter.py

保留预算解析职责，但改为：

- 先构建 `ContextBuildRequest`
- 再调用 `ContextAssembler.build()`

#### agent_loop.py

当前在调用 LLM 前只调用 `prepare_context`。

重构后改为：

1. 获取 current messages
2. 推断 mode
3. 构建 `ContextBuildRequest`
4. 获取 `PreparedContextBundle`
5. 调用模型
6. LLM 返回后调用 `SessionStateUpdater`

## 10. 与现有记忆系统的整合

### 10.1 复用 MemoryManager

当前 [memory/manager.py](/Users/xuan.lx/Documents/x-agent/backend/src/memory/manager.py) 已具备：

- 压缩前提取重要信息
- 长期记忆写入
- 混合检索
- 向量同步

改造策略：

- `archive_before_compression()` 不再承担“主上下文压缩”职责
- 改为专注长期偏好、决策和用户身份类信息
- `Episodic Memory` 和 `Evidence Ledger` 作为新的检索层补充到现有 `MemoryManager`

### 10.2 检索统一入口

建议在 `MemoryManager` 新增两个接口：

```python
async def search_episodic_events(self, query: str, session_id: str, limit: int = 8) -> list[dict]:
    ...

async def search_evidence_ledger(self, query: str, session_id: str, limit: int = 8) -> list[dict]:
    ...
```

再由 `ContextAssembler` 统一调用：

```python
async def retrieve_context_fragments(request: ContextBuildRequest) -> RetrievedContext:
    ...
```

## 11. 可观测性与验收指标

### 11.1 新增日志事件

新增事件类型：

- `context_build_start`
- `context_build_end`
- `session_state_updated`
- `episodic_event_created`
- `evidence_ledger_entry_created`
- `compression_quality_passed`
- `compression_quality_failed`
- `context_budget_overflow`
- `retrieval_injected`

### 11.2 每轮必须记录的指标

- 原始总 token
- static prefix token
- session state token
- evidence token
- episodic memory token
- working set token
- 最终 prompt token
- 净回收 token
- 压缩率
- 检索注入条数
- 压缩是否通过质量门槛

### 11.3 验收指标

#### P0 指标

- 长会话场景下，压缩后净回收 token 中位数 >= 20%
- `compression_quality_failed` 占比 < 10%
- research / PRD 场景中，第二轮超时率下降 60% 以上
- 重复摘要常驻问题归零

#### P1 指标

- 同等任务质量不下降
- Evidence 引用完整度提升
- Delegate 任务状态恢复准确率提升

## 12. 灰度与迁移方案

### 12.1 Phase 1: 加结构，不换默认路径

目标：

- 引入新表
- 引入 `SessionStateStore`
- 记录状态，但仍沿用旧压缩路径

收益：

- 低风险
- 可先观察结构化状态质量

### 12.2 Phase 2: 新旧双写

目标：

- 旧 `compression_events` 继续写
- 新 `SessionState / Episodic / Evidence` 同时写

收益：

- 可以对比新旧方案的 token 预算和效果

### 12.3 Phase 3: 新路径只读灰度

目标：

- 对部分 session 开启 `ContextAssembler`
- 但保留旧方案回退开关

灰度开关建议：

```yaml
context_engine:
  mode: legacy|hybrid|stateful
  enable_session_state: true
  enable_evidence_ledger: true
  enable_episodic_memory: true
  compression_quality_gate: true
```

### 12.4 Phase 4: 切换默认

目标：

- `stateful` 变默认
- 旧 `compressed_messages` 恢复逻辑下线

## 13. 实施顺序

### 第 1 周

- 新增 DB 表和 SQLAlchemy 模型
- 新增 `SessionStateStore`
- 新增 `ContextBuildRequest / PreparedContextBundle`
- 新增日志指标

### 第 2 周

- 实现 `SessionStateUpdater`
- 实现 `EpisodicMemoryStore`
- 实现 `EvidenceLedgerStore`
- 接入工具结果和 delegate 结果结构化写入

### 第 3 周

- 实现 `ContextAssembler`
- 实现模式识别
- 实现 prompt 组装和预算裁剪

### 第 4 周

- 实现压缩质量门槛
- 完成灰度开关
- 回归测试长会话、调研、PRD、多 Agent 协作

## 14. 关键接口草案

### 14.1 ContextBuildRequest

```python
@dataclass
class ContextBuildRequest:
    session_id: str
    agent_id: str
    mode: str
    system_prompt: str
    tools: list[dict]
    current_messages: list[dict]
    max_prompt_tokens: int
    reserved_output_tokens: int
```

### 14.2 PreparedContextBundle

```python
@dataclass
class PreparedContextBundle:
    messages: list[dict]
    session_state_text: str
    evidence_entries: list[dict]
    episodic_entries: list[dict]
    artifact_refs: list[dict]
    token_breakdown: dict[str, int]
    used_fallback: bool = False
```

### 14.3 SessionStateUpdater

```python
class SessionStateUpdater:
    async def update_after_turn(
        self,
        session_id: str,
        agent_id: str,
        new_messages: list[dict],
        tool_results: list[dict],
        delegate_results: list[dict],
    ) -> None:
        ...
```

## 15. 风险与应对

### 风险 1：结构化状态提取不稳定

应对：

- 第一阶段双写，不切流量
- 为关键字段设置必填校验
- 失败时回退到最近一次可用状态

### 风险 2：检索带来幻觉式拼接

应对：

- Evidence 必须带 source
- Episodic event 带 source_message_ids
- 注入 prompt 时明确标注“检索片段”

### 风险 3：新增表和逻辑过多，复杂度上升

应对：

- 明确模块边界
- 先引入 `SessionState` 和质量门槛，再逐步加 `Evidence Ledger`

### 风险 4：状态文本过于结构化，模型表达变差

应对：

- `SessionState` 控制为“结构化 + 少量自然语言”
- 近期工作集保真，不牺牲当前推理上下文

## 16. 结论

当前系统的问题不是“摘要模型不够强”，而是上下文工程架构不适合长任务。

最优解不是继续优化现有的“摘要拼接 + 固定 retention + 缓存恢复”，而是切换到：

- 静态前缀缓存
- 近期工作集保真
- 结构化 SessionState
- Episodic Memory 外存
- Evidence Ledger 外存
- 检索式回填
- 压缩质量门槛

这套方案与当前仓库兼容，能直接复用现有：

- `MemoryManager`
- `VectorStore`
- `HybridSearch`
- `AgentLoop`
- `LLMRouter`

并且可以通过双写和灰度逐步上线。

## 17. 参考资料

1. OpenAI Compaction Guide  
   https://developers.openai.com/api/docs/guides/compaction

2. Gemini API Context Caching  
   https://ai.google.dev/gemini-api/docs/caching/

3. Anthropic Long Context Tips  
   https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips

4. MemGPT: Towards LLMs as Operating Systems  
   https://arxiv.org/abs/2310.08560

5. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks  
   https://nlp.cs.ucl.ac.uk/publications/2020-05-retrieval-augmented-generation-for-knowledge-intensive-nlp-tasks/

6. Lost in the Middle: How Language Models Use Long Contexts  
   https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long

7. ReSum: Unlocking Long-Horizon Search Intelligence via Context Summarization  
   https://likuanppd.github.io/publications/ReSum

## 18. 静态 Prompt 文件兼容与迁移

### 18.1 目标

本节专门回答一个关键问题：

> 重构上下文压缩方案后，原有系统依赖的 `AGENTS.md / IDENTITY.md / OWNER.md / SPIRIT.md / TOOLS.md / BOOTSTRAP.md / HEARTBEAT.md / MEMORY.md` 是否还继续参与 prompt 构造，加载逻辑是否需要调整？

结论：

1. `AGENTS.md / SPIRIT.md / TOOLS.md / IDENTITY.md / OWNER.md / HEARTBEAT.md` 继续参与 prompt 构造
2. 它们应从“动态上下文材料”升级为“静态前缀（Static Prefix）”
3. `BOOTSTRAP.md` 保持独立特殊逻辑
4. `MEMORY.md` 不应再与上述静态文件一起常驻 system prompt
5. 原有加载链路保留，但职责要重新划分

### 18.2 当前系统中的两条加载链

当前静态 md 文件同时走两条链：

#### 链路 A：SystemPromptBuilder 原文注入

在 [system_prompt_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/system_prompt_builder.py:37) 中，
文件按以下顺序加载并直接拼到 `Project Context`：

- `AGENTS.md`
- `SPIRIT.md`
- `TOOLS.md`
- `IDENTITY.md`
- `OWNER.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `MEMORY.md`

随后在 [system_prompt_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/system_prompt_builder.py:557)
中整体拼接成 system prompt 末尾的 `Project Context`。

#### 链路 B：ContextBuilder 结构化解析

在 [context_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/memory/context_builder.py:77) 中，
又会把其中部分文件解析为结构化对象：

- `SPIRIT.md`
- `IDENTITY.md`
- `OWNER.md`
- `TOOLS.md`
- `memory/*.md`
- `MEMORY.md`

因此当前系统存在一个重要现实：

- 静态文件既以 raw 形式注入 prompt
- 又以结构化形式进入内存上下文

这本身并非错误，但在新架构中必须重新归类，否则会继续导致 token 重复消耗。

### 18.3 新架构中的文件归类

#### 18.3.1 保留在 Static Prefix 的文件

以下文件继续由 `SystemPromptBuilder` 负责读取，并保留在 system prompt 中：

- `AGENTS.md`
- `SPIRIT.md`
- `TOOLS.md`
- `IDENTITY.md`
- `OWNER.md`
- `HEARTBEAT.md`

这些文件的共同特征是：

- 变化频率低
- 定义 agent 身份、人格、边界、工具使用规则
- 与当前某一轮对话内容无直接时效耦合

因此它们应该被视为静态前缀，而不是动态上下文。

#### 18.3.2 保持特殊逻辑的文件

- `BOOTSTRAP.md`

该文件继续只在“未出生 / 未初始化”模式下生效，保留现有的最高优先级引导逻辑：

- [system_prompt_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/system_prompt_builder.py:440)

此逻辑不应与普通压缩、记忆检索、SessionState 混用。

#### 18.3.3 从 Static Prefix 中移出的文件

- `MEMORY.md`
- `memory/*.md`

这两类文件不再继续和 `AGENTS.md` 一起作为 `Project Context` 常驻在 system prompt 中。

改造后它们的职责如下：

- `MEMORY.md`：长期偏好 / 身份 / 经验类检索源
- `memory/*.md`：episodic memory 的原始素材来源

### 18.4 对现有实现的具体调整

#### 18.4.1 SystemPromptBuilder 调整

建议将当前 `BOOTSTRAP_FILE_ORDER` 拆分为三类：

```python
STATIC_PREFIX_FILE_ORDER = [
    "AGENTS.md",
    "SPIRIT.md",
    "TOOLS.md",
    "IDENTITY.md",
    "OWNER.md",
    "HEARTBEAT.md",
]

BOOTSTRAP_ONLY_FILE = ["BOOTSTRAP.md"]

DYNAMIC_MEMORY_FILES = [
    "MEMORY.md",
]
```

目标：

1. `Project Context` 只拼装 `STATIC_PREFIX_FILE_ORDER`
2. `BOOTSTRAP.md` 继续独立逻辑
3. `MEMORY.md` 从 `SystemPromptBuilder` 常驻拼装中移出

#### 18.4.2 ContextBuilder 调整

`ContextBuilder` 的结构化解析职责保留，但其产物在新架构中的用途要变化：

- `SPIRIT.md / OWNER.md / IDENTITY.md / TOOLS.md`
  仍用于结构化字段构造与热更新
- `MEMORY.md`
  不再默认进入 prompt 文本，而是进入检索与状态更新流程

也就是说：

- `ContextBuilder` 继续读取这些文件
- 但“读取”不再等于“常驻 prompt 注入”

#### 18.4.3 ContextLoader 调整

当前 [context_loader.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/context_loader.py:102)
已经有 shared context 下排除 `MEMORY.md` 的逻辑，这个方向是正确的。

在新架构中应保留并加强：

- `MAIN` 会话：允许 `MEMORY.md` 参与检索
- `SHARED` 会话：禁止 `MEMORY.md` 参与检索与注入

### 18.5 各文件在新架构中的职责矩阵

| 文件 | 现状 | 新架构角色 | 是否常驻 system prompt | 是否参与压缩 | 是否参与检索 |
|------|------|------------|------------------------|--------------|--------------|
| `AGENTS.md` | raw 注入 | Static Prefix | 是 | 否 | 否 |
| `SPIRIT.md` | raw + 结构化 | Static Prefix + Identity Metadata | 是 | 否 | 否 |
| `TOOLS.md` | raw + 结构化 | Static Prefix + Tool Metadata | 是 | 否 | 否 |
| `IDENTITY.md` | raw + 结构化 | Static Prefix + Identity Metadata | 是 | 否 | 否 |
| `OWNER.md` | raw + 结构化 | Static Prefix + User Metadata | 是 | 否 | 否 |
| `HEARTBEAT.md` | raw 注入 | Static Prefix | 是 | 否 | 否 |
| `BOOTSTRAP.md` | 特殊 raw 注入 | Bootstrap Instruction | 初始化阶段是 | 否 | 否 |
| `MEMORY.md` | raw + 结构化 | Long-term Memory Source | 否 | 否 | 是 |
| `memory/*.md` | 结构化日志 | Episodic Raw Source | 否 | 否 | 是 |

### 18.6 为什么必须把 MEMORY.md 移出静态前缀

`MEMORY.md` 和 `AGENTS.md` 这类文件本质不同：

1. 它不是静态规则，而是持续增长的动态历史
2. 它天然适合检索，不适合常驻
3. 它与当前用户任务的相关性是稀疏的，不应每轮全量注入
4. 当前 `SystemPromptBuilder` 只做字符截断，不做语义筛选

如果继续让 `MEMORY.md` 常驻 system prompt，会带来：

- token 浪费
- 老记忆抢占工作集预算
- 与 `SessionState / Episodic Memory` 重复表达

因此，`MEMORY.md` 应从“静态前缀文本”转换成“长期记忆检索源”。

### 18.7 对静态文件解析器的兼容性修复

这是一个必须纳入方案的补充项。

当前 `IDENTITY.md` 解析在两个位置都偏向英文模板字段：

- [system_prompt_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/conversation/system_prompt_builder.py:182)
- [context_builder.py](/Users/xuan.lx/Documents/x-agent/backend/src/memory/context_builder.py:179)

而现有工作区里的很多 `IDENTITY.md / OWNER.md / SPIRIT.md` 是中文格式，例如：

- `姓名`
- `存在形式`
- `气质风格`
- `标志性emoji`

这会导致一个现实问题：

- 当前系统真正“理解”这些文件，很多时候依赖的是 raw 注入
- 结构化解析结果可能为空或不完整

在新架构中，因为 `SessionState`、`Identity Metadata`、`User Metadata` 会更多依赖结构化字段，
所以必须同步补强解析器：

#### 建议改造

1. 为 `IDENTITY.md` 解析器增加中英文字段别名：
   - `Name / 姓名`
   - `Creature / 存在形式`
   - `Vibe / 气质风格`
   - `Emoji / 标志性emoji`

2. 为 `OWNER.md` 和 `SPIRIT.md` 的解析器增加中英文字段兼容

3. 对常见 Markdown 样式统一支持：
   - `**字段:** 值`
   - `**字段**: 值`
   - `## 标题 + 下一行正文`
   - 列表项格式

### 18.8 静态前缀缓存建议

静态文件虽然不参与压缩，但应该参与缓存。

建议增加 `StaticPrefixCache`：

```python
@dataclass
class StaticPrefixCache:
    workspace_path: str
    content_hash: str
    rendered_prompt: str
    token_count: int
    updated_at: datetime
```

缓存失效条件：

- `AGENTS.md / SPIRIT.md / TOOLS.md / IDENTITY.md / OWNER.md / HEARTBEAT.md` 任一文件变更
- `BOOTSTRAP.md` 状态切换
- agent workspace 切换

这样可以避免每次请求都重新拼接全部静态文件。

### 18.9 最终迁移原则

本方案对静态 md 文件的处理原则总结如下：

1. 保留静态身份文件的优先级和语义
2. 保留 `SystemPromptBuilder` 作为静态前缀构建器
3. 保留 `BOOTSTRAP.md` 特殊初始化逻辑
4. 将 `MEMORY.md` 从静态前缀中剥离，进入检索体系
5. 强化 `IDENTITY.md / OWNER.md / SPIRIT.md` 的结构化解析兼容性
6. 引入静态前缀缓存，而不是让这些文件进入压缩器

换句话说：

- `AGENTS.md / IDENTITY.md` 这些文件不是要被削弱
- 而是要从“被动参与长上下文膨胀”升级为“稳定、缓存、不可压缩的静态前缀”
