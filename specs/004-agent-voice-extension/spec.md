# Spec: Agent 语音扩展能力

**Feature Branch**: `004-agent-voice-extension`  
**Date**: 2026-04-11  
**Status**: Draft

## 1. 背景

当前项目的 Web Chat 链路是纯文本消息模型：

- 前端 chatbox 只支持文本输入
- WebSocket 协议只支持文本消息和工具事件
- 后端没有通用语音扩展层
- 现有 `backend/src/extensions/video_pipeline/tts_voice.py` 仅服务视频脚本配音场景，不能直接承担聊天语音能力

本特性需要为 Agent 聊天补齐回合式语音消息能力，并把 TTS / ASR 能力收敛为可扩展 provider 架构。

## 2. 目标

构建一套面向 chatbox 的通用语音能力，支持：

- 用户发送语音给 agent
- 后端执行 ASR 语音转文字并进入现有聊天流程
- agent 输出文本后可继续生成语音回复
- chatbox 能展示音频消息、转写结果、语音回复播放器
- TTS 和 ASR 都采用可扩展 provider 架构
- GPT-SoVITS 声音克隆能力按 Agent 维度配置
- 管理后台可配置 Agent 的语音策略

## 3. 已确认范围

### 3.1 交互模式

- 采用“微信语音消息式”的**回合式**交互
- 不做全双工实时通话
- 不做持续收音、实时打断、流式语音回放

### 3.2 Chatbox 模式

- 前端采用**双模可切换**
- 支持 `文本模式 / 语音模式`
- 同一会话协议同时支持文字、音频、转写文本、语音回复

### 3.3 TTS 范围

- TTS 需要支持 provider 扩展
- 首批 provider：
  - Edge TTS（默认）
  - OpenAI TTS API
  - GPT-SoVITS

### 3.4 ASR 范围

- ASR 需要支持 provider 扩展
- 首批 provider：
  - OpenAI ASR
  - Whisper 本地或兼容接口
  - 第三方 provider 预留

### 3.5 音色配置归属

- GPT-SoVITS 声音克隆配置按 **Agent** 维度绑定
- 不按系统全局，不按单个 session 临时切换作为首版主路径

### 3.6 配置入口

- Agent 语音配置通过**管理后台**维护
- 凭证和服务地址仍由后端安全配置承载

## 4. 非目标

本期明确不做：

- 全双工实时语音通话
- 用户边说边上传分片并边转写边推理
- 语音通话级别的打断、抢占、回声消除
- 前端本地离线 ASR / TTS
- 多段音频混音、背景音、语音特效
- 在首版内重构整个聊天存储系统

## 5. 用户故事

### US1: 用户发送语音消息

作为 chatbox 用户，我可以录制一段语音并发送给 agent，系统会保留原始音频并把语音转写为文本供后续推理使用。

### US2: Agent 返回语音回复

作为 chatbox 用户，我在收到 agent 文本回复时，如果当前 Agent 开启语音回复，可以直接播放对应语音。

### US3: 管理员配置 Agent 语音能力

作为管理员，我可以为每个 Agent 配置 ASR/TTS provider、默认音色、GPT-SoVITS 参考音频和语音回复策略。

### US4: 开发者扩展 provider

作为后端开发者，我可以按统一接口增加新的 TTS 或 ASR provider，而不需要修改 chat 协议或业务层主流程。

## 6. 功能需求

### 6.1 后端语音扩展层

- **FR-001**: 系统 MUST 在 `backend/src/extensions/` 下新增通用语音扩展目录，而不是继续把聊天语音逻辑放在视频流水线内。
- **FR-002**: 系统 MUST 为 TTS 定义统一 provider 抽象和 provider 注册机制。
- **FR-003**: 系统 MUST 为 ASR 定义统一 provider 抽象和 provider 注册机制。
- **FR-004**: 系统 MUST 提供默认 TTS provider 解析逻辑，默认使用 Edge TTS。
- **FR-005**: 系统 MUST 支持 OpenAI TTS provider。
- **FR-006**: 系统 MUST 支持 GPT-SoVITS TTS provider。
- **FR-007**: 系统 MUST 支持 OpenAI ASR provider。
- **FR-008**: 系统 MUST 支持 Whisper 兼容接口 provider。
- **FR-009**: 系统 MUST 为第三方 TTS / ASR provider 预留扩展入口。

### 6.2 聊天协议与消息模型

- **FR-010**: 系统 MUST 在现有 WebSocket 聊天协议上扩展语音消息事件，而不破坏现有文本消息能力。
- **FR-011**: 系统 MUST 支持用户消息携带音频附件元数据。
- **FR-012**: 系统 MUST 支持服务端返回转写结果事件。
- **FR-013**: 系统 MUST 支持 assistant 消息附带语音回复元数据。
- **FR-014**: 系统 MUST 在历史消息模型中保存文本、原始音频、转写文本、语音回复之间的关系。

### 6.3 Chatbox 交互

- **FR-015**: 前端 MUST 支持文本模式和语音模式切换。
- **FR-016**: 前端 MUST 支持录音、停止录音、发送录音、发送前预览。
- **FR-017**: 前端 MUST 在用户语音消息卡片中展示音频播放器和转写文本。
- **FR-018**: 前端 MUST 在 assistant 回复卡片中展示语音播放器。
- **FR-019**: 如果当前消息没有音频，则前端 MUST 保持现有文本显示行为不变。

### 6.4 Agent 配置管理

- **FR-020**: 系统 MUST 允许在管理后台为 Agent 配置默认 TTS provider。
- **FR-021**: 系统 MUST 允许在管理后台为 Agent 配置默认 ASR provider。
- **FR-022**: 系统 MUST 允许在管理后台为 Agent 配置默认音色或 voice id。
- **FR-023**: 系统 MUST 允许在管理后台为 Agent 配置 GPT-SoVITS 参考音频和参考文本。
- **FR-024**: 系统 MUST 允许在管理后台控制该 Agent 是否默认启用语音回复。

### 6.5 资产与安全

- **FR-025**: 系统 MUST 对上传音频做格式、大小和 MIME 基础校验。
- **FR-026**: 系统 MUST 为生成音频提供可访问但受控的资源 URL。
- **FR-027**: 系统 MUST 记录音频资产的基本元数据，如时长、格式、大小、来源 provider。
- **FR-028**: 系统 MUST 对 provider 调用失败提供可观测错误，并允许降级到“只返回文本”。

## 7. 架构要求

### 7.1 后端分层

建议新增如下边界：

```text
backend/src/extensions/voice/
├── asr/
├── tts/
├── profiles/
├── assets/
└── service.py
```

职责约束：

- `tts/` 只负责文本转语音
- `asr/` 只负责语音转文字
- `profiles/` 只负责 Agent 级语音配置解析
- `assets/` 只负责音频文件持久化与 URL 暴露
- `service.py` 只负责对聊天链路暴露统一编排接口

### 7.2 现有 TTS 代码复用

- `backend/src/extensions/video_pipeline/tts_voice.py` 不应继续作为聊天语音主入口
- 可以在后续改造为复用新通用 TTS 层，避免重复 provider 实现

## 8. 数据与协议建议

### 8.1 用户语音消息

用户发送语音消息后，系统需要保留：

- 原始音频文件引用
- 原始文件元数据
- ASR 结果文本
- 使用的 ASR provider

### 8.2 Assistant 语音回复

assistant 回复需要保留：

- 标准文本内容
- 语音回复文件引用
- 语音文件元数据
- 使用的 TTS provider 和 voice

## 9. 成功标准

- **SC-001**: 用户可以在 chatbox 中录制语音并成功发送，后端能完成 ASR 并进入现有对话流程。
- **SC-002**: assistant 文本回复可在开启语音回复的 Agent 上生成可播放音频。
- **SC-003**: 前端消息列表可正确展示用户语音、转写结果和 assistant 语音播放器。
- **SC-004**: TTS provider 至少支持 Edge、OpenAI、GPT-SoVITS，ASR provider 至少支持 OpenAI、Whisper 兼容接口。
- **SC-005**: 管理后台可以按 Agent 配置语音 provider 和 GPT-SoVITS 克隆素材。
- **SC-006**: 任一语音 provider 调用失败时，系统仍能保底返回文本回复，不使主聊天链路不可用。

## 10. 验证范围

必须覆盖：

- 后端 provider 抽象和 provider 路由单测
- 音频上传 / 资产持久化单测
- 网关语音消息协议单测
- chatbox 双模交互和语音消息渲染测试
- Agent 配置读写测试
- 至少一条从“上传语音 -> ASR -> 聊天 -> TTS -> 返回语音”的集成验证链路
