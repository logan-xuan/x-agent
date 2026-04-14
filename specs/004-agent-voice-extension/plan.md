# Implementation Plan: Agent 语音扩展双路径能力

**Branch**: `004-agent-voice-extension` | **Date**: 2026-04-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-agent-voice-extension/spec.md`

## Summary

在保留现有协议层自动语音处理的基础上，新增 Agent 可主动调用的 `synthesize_speech` / `transcribe_audio` 两个内置工具，并将自动 TTS 的触发条件收敛到“仅当本轮用户输入是语音”这一条规则上。工具链路和自动链路共用 `VoiceService`、音频资产存储和消息 metadata 协议。

## Architecture

### 1. 自动链路

- `backend/src/gateway/endpoints/websocket.py`
  - 音频输入继续走 `_prepare_voice_chat_payload()`
  - 在 metadata 中补充 `input_modality=audio`
  - 自动 TTS 只看 `input_modality=audio` + `reply_enabled`

### 2. Agent 工具链路

- `backend/src/tools/builtin/voice_tools.py`
  - `SynthesizeSpeechTool`
  - `TranscribeAudioTool`
- `backend/src/tools/builtin/__init__.py`
  - 注册两个新工具
- `backend/src/tools/semantic_mapping.py`
  - 暴露工具语义映射

### 3. 共享能力层

- `backend/src/extensions/voice/service.py`
  - 继续作为统一编排入口
- `backend/src/extensions/voice/assets/storage.py`
  - 补充按 `asset_id` 解析资产引用的能力，供工具复用
- `backend/src/gateway/dispatcher.py`
  - 将 envelope metadata 注入请求上下文，供工具读取当前输入音频引用

### 4. 协议协同

- `backend/src/gateway/endpoints/websocket.py`
  - 在收到 `synthesize_speech` 工具结果后缓存其 `audio_reply`
  - 在最终 assistant `message` 事件发送时，把该音频挂到 `audio_reply`
  - 如果同回合也满足自动 TTS 条件，优先使用工具结果

## Delivery Phases

### Phase 1: 契约冻结

输出：

- 更新 `spec.md`
- 更新 `plan.md`
- 更新 `tasks.md`

### Phase 2: 能力补齐

输出：

- 音频资产按 `asset_id` 解析
- 请求上下文保留输入音频 metadata
- Agent 工具实现完成

### Phase 3: 网关收敛

输出：

- 自动 TTS 条件改为仅音频输入
- 工具生成音频可挂回最终 assistant 消息

### Phase 4: 回归验证

输出：

- 工具单测
- WebSocket 协议单测
- 真实语音链路验证

## Risks

### 1. 工具与自动链路重复生成音频

如果不在网关层统一裁决，同一回合可能出现“双份音频回复”。本次需明确“工具结果优先，自动链路兜底”。

### 2. ASR 工具缺少可用音频引用

Agent 默认上下文并不直接看到本地文件路径，因此必须由协议层把当前输入音频 metadata 注入请求上下文，并由资产层提供 `asset_id -> AudioAssetRef` 解析能力。

### 3. 工具结果无法出现在最终消息中

当前前端已经支持 `audio_reply`，但工具结果默认只是 `tool_result`。网关需要在不改 Agent Core 主流程的情况下完成结果提升。

## Verification Strategy

### 后端单测

- `test_voice_websocket_protocol.py`
- `tests/unit/tools/test_voice_tools.py`
- `test_voice_extension.py`

### 回归验证

- 语音输入自动闭环
- 文本输入默认纯文本
- 文本输入显式要求音频时，Agent 可通过工具生成音频

## Simplifications

- 本次不新增前端组件
- 本次不新增独立 skill 协议，先以内置工具完成 Agent 主动调用
- `transcribe_audio` 首版只支持当前请求音频、`asset_id`、本地 `file_path` 三种入口
