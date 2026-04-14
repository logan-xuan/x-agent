# Spec: Agent 语音扩展双路径能力

**Feature Branch**: `004-agent-voice-extension`  
**Date**: 2026-04-14  
**Status**: Approved

## 1. 背景

当前 `extensions/voice` 已经承担了聊天协议层的自动语音处理：

- 用户上传语音时，网关会自动执行 ASR，把结果转成文本进入主对话链路
- assistant 文本回复可以自动生成 TTS 音频并挂回消息
- 前端已经具备语音消息、转写文本、语音回复播放器等渲染能力

但这套能力仍然只有“协议层自动调用”这一条路径，Agent 本身无法把 TTS / ASR 当成可主动调用的能力边界来使用。同时，自动语音回复的触发条件过宽，文本输入在某些配置下也会自动生成音频，不符合当前产品要求。

## 2. 目标

本次改造需要同时满足三件事：

1. **保留协议层自动语音链路**
   - 用户发语音时自动 ASR
   - 仅当“本轮用户输入是语音”时，才允许自动 TTS 回复

2. **把 TTS / ASR 暴露给 Agent**
   - Agent 可以把文字转语音当成内置工具主动调用
   - Agent 可以把音频转文字当成内置工具主动调用

3. **收敛默认交互规则**
   - 用户文本输入默认只返回文本
   - 只有用户明确要求音频版时，Agent 才通过工具主动生成音频回复

## 3. 已确认范围

### 3.1 自动链路

- 保留现有网关层自动语音处理
- 自动 ASR 仍然只在用户发送音频消息时触发
- 自动 TTS 仅在用户本轮输入为音频时触发
- 自动 TTS 仍然受 Agent 级 `reply_enabled` 控制

### 3.2 Agent 主动调用链路

- 新增两个内置工具：
  - `synthesize_speech`
  - `transcribe_audio`
- 工具直接复用 `VoiceService`
- 不再为这两项能力额外设计单独 skill 协议

### 3.3 消息表现

- 自动链路生成的语音回复继续挂载到 assistant 消息的 `audio_reply`
- Agent 通过 `synthesize_speech` 主动生成的音频，也要挂回当前 assistant 消息的 `audio_reply`
- `transcribe_audio` 工具默认返回文本结果和结构化元数据，不强制新增独立消息卡片

## 4. 非目标

本次明确不做：

- 全双工实时通话
- 语音通话级别的打断、抢占、回声消除
- 新增一套独立于工具系统的“语音 skill 协议”
- 在本次改造中重做前端消息卡片样式
- 为所有 provider 设计统一音色枚举协议

## 5. 用户故事

### US1: 语音输入自动处理

作为用户，我发送语音消息后，系统会自动完成转写，并把转写文本交给 Agent 继续处理。

### US2: 语音输入才自动语音回复

作为用户，我用语音发起本轮对话时，如果 Agent 开启自动语音回复，就能收到文本 + 音频；如果我是文本输入，默认只收到文本。

### US3: Agent 主动生成音频

作为用户，当我明确要求“给我语音版/生成音频回复”时，Agent 可以自行调用 TTS 工具并返回可播放音频。

### US4: Agent 主动转写音频

作为用户，当我让 Agent 处理某段音频资产时，Agent 可以主动调用 ASR 工具完成转写，再基于转写结果继续回答。

## 6. 功能需求

### 6.1 自动链路

- **FR-001**: 系统 MUST 保留 `extensions/voice` 作为网关协议层自动语音中间层。
- **FR-002**: 系统 MUST 在用户输入音频消息时自动执行 ASR，并把结果注入后续文本聊天主流程。
- **FR-003**: 系统 MUST 为自动 ASR 产物在消息 metadata 中保留音频资产和转写结果。
- **FR-004**: 系统 MUST 只在 `input_modality=audio` 的回合内考虑自动 TTS 回复。
- **FR-005**: 系统 MUST 在 `input_modality=text` 的回合内默认不做自动 TTS 回复，即使 Agent 开启了默认语音回复。
- **FR-006**: 系统 MUST 在自动 TTS 失败时保底返回文本消息，并向客户端返回结构化错误事件。

### 6.2 Agent 工具链路

- **FR-007**: 系统 MUST 暴露 `synthesize_speech` 作为内置工具给 Agent 调用。
- **FR-008**: `synthesize_speech` MUST 复用 `VoiceService.synthesize()`，并支持可选 `provider`、`voice` 参数。
- **FR-009**: `synthesize_speech` MUST 返回结构化音频资产元数据，并允许协议层把该结果挂载到当前 assistant 消息的 `audio_reply`。
- **FR-010**: 系统 MUST 暴露 `transcribe_audio` 作为内置工具给 Agent 调用。
- **FR-011**: `transcribe_audio` MUST 复用 `VoiceService.transcribe()`，并支持转写当前请求音频、历史音频资产或显式文件路径。
- **FR-012**: `transcribe_audio` MUST 返回转写文本、语言和输入音频元数据，供后续 LLM 继续推理。

### 6.3 工具与协议协同

- **FR-013**: 网关 MUST 能识别 `synthesize_speech` 的工具结果，并把音频资产元数据提升为最终 assistant 消息的 `audio_reply`。
- **FR-014**: 若同一回合中同时存在“工具主动生成音频”和“自动语音回复”候选，系统 MUST 优先采用工具生成的音频结果，避免重复合成。
- **FR-015**: 当前请求上下文 MUST 向工具暴露本轮输入音频的可解析引用，以便 `transcribe_audio` 在无显式参数时处理当前语音输入。

## 7. 架构要求

### 7.1 责任边界

- `extensions/voice/`
  - 继续只承载能力层：provider、资产、编排、文本重写
- `tools/builtin/`
  - 新增语音工具入口，直接复用 `VoiceService`
- `gateway/endpoints/websocket.py`
  - 负责自动链路触发条件
  - 负责把语音工具结果合并进最终消息协议
- `gateway/dispatcher.py`
  - 请求上下文中透传本轮语音输入 metadata，供工具默认解析

### 7.2 不做的边界

- 不把 TTS / ASR 逻辑写进 Agent prompt 模板
- 不在工具层重复实现 provider 逻辑
- 不为自动链路和工具链路维护两套音频资产格式

## 8. 数据与协议约束

### 8.1 请求级 metadata

语音输入进入主链路后，metadata 至少需要保留：

- `input_modality=audio`
- `audio.asset_id`
- `audio.public_url`
- `audio.playback_url`
- `transcript.text`
- `transcript.provider`

### 8.2 工具结果 metadata

`synthesize_speech` 成功后，其工具结果 metadata 至少需要保留：

- `audio_reply.asset_id`
- `audio_reply.public_url`
- `audio_reply.playback_url`
- `audio_reply.provider`
- `audio_reply.voice`

## 9. 成功标准

- **SC-001**: 语音输入仍可走通“上传语音 -> 自动 ASR -> 聊天 -> 自动语音回复”闭环。
- **SC-002**: 文本输入默认只返回文本，不再因 `reply_enabled` 自动生成音频。
- **SC-003**: 用户明确要求音频版时，Agent 可以通过 `synthesize_speech` 主动生成并返回可播放音频。
- **SC-004**: `transcribe_audio` 工具可以处理当前请求音频或显式音频资产，并把转写结果返回给 Agent。
- **SC-005**: 自动链路和工具链路共用同一套 provider / asset / metadata 结构，不产生重复实现。

## 10. 验证范围

必须覆盖：

- 自动语音回复只在音频输入下触发的单测
- `synthesize_speech` 工具注册、执行、结果元数据单测
- `transcribe_audio` 工具注册、执行、默认上下文解析单测
- 网关将工具生成的音频挂回最终 assistant 消息的单测
- 至少一条真实链路验证：
  - 语音输入自动闭环
  - 文本输入通过工具生成音频回复
