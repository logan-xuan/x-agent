# Tasks: Agent 语音扩展双路径能力

**Input**: Design documents from `/specs/004-agent-voice-extension/`  
**Prerequisites**: `spec.md`, `plan.md`  
**Tests**: 以后端 `pytest`、真实 WebSocket 语音链路验证为主

## Phase 1: 文档冻结

- [x] 更新规格文档，确认“自动链路 + agent 工具链路”双路径
- [x] 更新实现计划，明确能力边界、消息归并规则和验证策略
- [x] 更新任务分解，作为 OMX 执行清单

## Phase 2: 共享基础设施

- [x] 为 `AudioAssetStore` 增加 `asset_id -> AudioAssetRef` 解析能力
- [x] 在 `GatewayDispatcher` 构建请求上下文时保留 envelope metadata
- [x] 约定当前请求语音输入的 metadata 结构，供工具默认读取

## Phase 3: Agent 工具

- [x] 新增 `synthesize_speech` 内置工具
- [x] 新增 `transcribe_audio` 内置工具
- [x] 在内置工具注册表中暴露两个工具
- [x] 更新工具语义映射，确保工具系统可见

## Phase 4: 自动链路收敛

- [x] 在语音输入预处理时写入 `input_modality=audio`
- [x] 收紧自动 TTS 触发条件，只允许音频输入回合触发
- [x] 保留自动 TTS 失败时的文本降级和错误事件

## Phase 5: 工具结果并入消息协议

- [x] 在 WebSocket 事件发送阶段识别 `synthesize_speech` 工具结果
- [x] 将工具生成的音频资产挂入最终 assistant 消息 `audio_reply`
- [x] 若同时存在自动 TTS 候选，优先采用工具结果

## Phase 6: 测试与验证

- [x] 更新 `test_voice_websocket_protocol.py`
- [x] 新增 `tests/unit/tools/test_voice_tools.py`
- [x] 更新语音扩展相关测试，删除与新规则冲突的旧断言
- [x] 跑通后端语音相关测试集
- [x] 真实验证：
  - [x] 语音输入自动闭环
  - [x] 文本输入默认纯文本
  - [x] 文本输入显式请求音频时，Agent 通过工具生成音频
