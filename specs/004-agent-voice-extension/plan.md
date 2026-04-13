# Implementation Plan: Agent 语音扩展能力

**Branch**: `004-agent-voice-extension` | **Date**: 2026-04-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-agent-voice-extension/spec.md`

## Summary

在现有纯文本 Web Chat 架构上扩展一套面向聊天场景的通用语音能力层。后端新增 `voice` 扩展目录，统一承载 TTS / ASR provider、Agent 语音配置与音频资产管理；前端把 chatbox 扩展为文本/语音双模，并升级消息模型和 WebSocket 协议以承载“语音消息、转写文本、语音回复”。

## Confirmed Scope

- 回合式语音消息，不做全双工实时语音
- chatbox 双模切换
- TTS provider：Edge / OpenAI / GPT-SoVITS
- ASR provider：OpenAI / Whisper 兼容接口 / 第三方预留
- GPT-SoVITS 声音克隆按 Agent 配置
- 管理后台提供 Agent 语音配置入口

## Out Of Scope

- 实时通话
- 打断、抢占、流式语音回放
- 离线端侧 ASR/TTS
- 背景音与高级音频编辑

## Architecture

### 1. 后端

新增语音扩展主边界：

```text
backend/src/extensions/voice/
├── __init__.py
├── service.py
├── schemas.py
├── assets/
│   ├── __init__.py
│   ├── models.py
│   ├── storage.py
│   └── url_builder.py
├── asr/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── openai_asr.py
│   └── whisper_compatible.py
├── tts/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   ├── edge_tts.py
│   ├── openai_tts.py
│   └── gpt_sovits.py
└── profiles/
    ├── __init__.py
    ├── models.py
    ├── repository.py
    └── service.py
```

接入点：

- `backend/src/gateway/endpoints/websocket.py`
- `backend/src/gateway/agent_bridge.py`
- `backend/src/api/v1/assets.py` 或新增语音资产路由
- `backend/src/conversation/dao/models.py` 或相邻消息持久化模型
- 管理后台配置接口对应的后端 API

### 2. 前端

主要改动边界：

```text
frontend/src/
├── components/agent/
│   ├── AgentChatWindow.tsx
│   ├── AgentMessageList.tsx
│   ├── AgentMessageItem.tsx
│   ├── VoiceRecorder.tsx
│   └── AudioMessagePlayer.tsx
├── hooks/
│   └── useAgent.ts
├── services/
│   ├── api.ts
│   └── websocket.ts
└── types/
    └── index.ts
```

### 3. 管理后台

需要新增 Agent 语音配置表单：

- ASR provider
- TTS provider
- 默认 voice / speaker
- GPT-SoVITS 服务地址、参考音频、参考文本
- 是否默认语音回复

## Delivery Phases

### Phase 1: 契约与数据模型

目标：

- 固定语音消息的数据结构
- 确定 WebSocket 新事件类型
- 明确消息持久化模型和资产元数据

输出：

- 语音扩展 schema
- 前后端统一字段命名
- Agent 语音配置模型

### Phase 2: 后端语音扩展层

目标：

- 抽象 TTS / ASR provider
- 接通 provider registry
- 打通语音资产存储和 URL 输出

输出：

- 统一 `VoiceService`
- `TTSProvider` / `ASRProvider` 抽象
- Edge / OpenAI / GPT-SoVITS / Whisper 兼容实现

### Phase 3: 网关与消息协议

目标：

- 扩展 WebSocket 协议
- 让用户语音输入进入现有聊天链路
- 让 assistant 文本回复后可附带语音资产

输出：

- 新消息类型与事件转换
- 用户语音消息入站处理
- assistant 语音回复出站处理

### Phase 4: 前端 chatbox 双模交互

目标：

- 加入录音和音频播放组件
- 扩展消息渲染和前端状态机

输出：

- 文本/语音模式切换
- 用户语音消息卡片
- assistant 语音播放卡片

### Phase 5: 管理后台配置

目标：

- 让 Agent 语音能力可配置

输出：

- Agent 语音配置表单
- 配置查询与保存 API
- GPT-SoVITS 相关配置项

### Phase 6: 验证与收口

目标：

- 跑通关键测试和集成链路
- 确保 provider 失败可降级

输出：

- 单元测试
- 前端交互验证
- 端到端语音闭环验证

## Risks

### 1. 协议膨胀风险

当前 WebSocket 协议偏轻量，新增语音事件后需要控制字段命名与兼容路径，避免把历史文本链路打碎。

### 2. 资产持久化风险

音频文件的落盘位置、URL 暴露方式、生命周期清理策略如果不先收敛，后续会形成脏数据和孤儿文件。

### 3. Provider 行为差异风险

OpenAI、Edge、GPT-SoVITS、Whisper 兼容接口在入参、输出格式、错误语义上差异较大，需要统一错误模型和超时策略。

### 4. GPT-SoVITS 配置复杂度

参考音频、参考文本、服务地址、speaker 映射等配置可能产生大量无效组合，需要在 Agent 配置层做校验。

## Verification Strategy

### 后端

- `pytest` 覆盖 provider registry、音频资产管理、消息协议转换、Agent 配置服务
- 跑一条“语音输入 -> ASR -> 文本回复 -> TTS”的集成链路

### 前端

- 组件测试覆盖模式切换、录音状态、播放器渲染
- 手工验证发送语音消息和播放 assistant 语音回复

### 降级

- TTS 失败时必须仍返回文本消息
- ASR 失败时必须返回清晰错误，不得造成 WebSocket 卡死

## Recommended Execution Order

1. 先补 `voice` 扩展层数据结构和 provider 抽象
2. 再升级网关协议和消息存储
3. 然后做前端 chatbox 双模
4. 最后补管理后台配置与 GPT-SoVITS 素材管理
5. 收尾阶段统一做回归测试和降级验证
