# Tasks: Agent 语音扩展能力

**Input**: Design documents from `/specs/004-agent-voice-extension/`  
**Prerequisites**: `spec.md`, `plan.md`  
**Tests**: 以后端 `pytest`、前端组件测试、手工链路验证为主  
**Organization**: 按阶段和子系统拆分，便于下次续做

## 当前结论

- [x] 已确认首版采用回合式语音消息
- [x] 已确认 chatbox 为文本/语音双模
- [x] 已确认 TTS 采用可扩展 provider，默认 Edge TTS
- [x] 已确认 ASR 采用可扩展 provider，首批支持 OpenAI + Whisper 兼容接口
- [x] 已确认 GPT-SoVITS 克隆配置按 Agent 绑定
- [x] 已确认 Agent 语音配置入口放在管理后台

## Phase 1: 设计与契约冻结

- [x] 定义语音消息统一数据模型，明确用户音频、转写文本、assistant 语音回复、provider 元数据
- [x] 设计 WebSocket 新消息类型与兼容策略
- [x] 明确消息持久化模型需要新增的字段或关联表
- [x] 明确音频资产 URL 暴露与清理策略
- [x] 明确 Agent 语音配置数据模型和校验规则

## Phase 2: 后端通用语音扩展

- [x] 在 `backend/src/extensions/voice/` 下搭建扩展目录结构
- [x] 增加 TTS provider 抽象、注册器和默认解析逻辑
- [x] 增加 ASR provider 抽象、注册器和默认解析逻辑
- [x] 接入 Edge TTS provider
- [x] 接入 OpenAI TTS provider
- [x] 接入 GPT-SoVITS TTS provider
- [x] 接入 OpenAI ASR provider
- [x] 接入 Whisper 兼容接口 provider
- [x] 增加第三方 provider 预留注册入口
- [x] 增加统一 `VoiceService` 编排入口

## Phase 3: 音频资产与存储

- [x] 设计音频资产元数据模型
- [x] 实现音频上传文件校验
- [x] 实现语音资产落盘与元数据记录
- [x] 实现音频 URL 构建与访问控制
- [ ] 处理临时文件、生成文件和过期文件清理策略

## Phase 4: 网关与聊天协议改造

- [x] 扩展 WebSocket 入站协议以支持语音消息
- [x] 为语音消息补充转写结果事件
- [x] 为 assistant 回复补充语音回复事件或消息元数据
- [x] 将语音消息接入 `AgentBridge` 现有文本聊天主流程
- [ ] 处理 ASR/TTS 失败时的降级与错误透出

## Phase 5: 前端 chatbox 双模

- [x] 扩展前端消息类型定义，支持音频附件和转写结果
- [x] 在 `useAgent` 中处理新的语音 WebSocket 事件
- [x] 在 `AgentChatWindow` 中加入文本/语音模式切换
- [x] 新增录音组件，支持开始录音、停止录音、重录、发送前预览
- [x] 新增音频播放器组件，支持用户语音和 assistant 语音播放
- [x] 调整消息列表和消息项渲染逻辑

## Phase 6: 管理后台配置

- [x] 新增 Agent 语音配置后端接口
- [x] 新增 Agent 语音配置前端表单
- [x] 支持设置默认 TTS / ASR provider
- [x] 支持设置默认 voice / speaker
- [x] 支持配置 GPT-SoVITS 服务地址、参考音频、参考文本
- [x] 支持配置是否默认返回语音

## Phase 7: 测试与验证

- [x] 补 TTS provider registry 单元测试
- [x] 补 ASR provider registry 单元测试
- [x] 补音频资产管理单元测试
- [x] 补 WebSocket 协议转换单元测试
- [x] 补 Agent 语音配置服务测试
- [x] 补前端语音消息渲染和模式切换测试
- [ ] 验证“语音输入 -> ASR -> 聊天 -> TTS -> 语音回复”完整闭环
- [ ] 验证 provider 失败后的降级行为

## 建议下次开工顺序

- [ ] 先实现 `backend/src/extensions/voice/` 的 schema、provider 抽象和 registry
- [ ] 再实现音频资产存储
- [ ] 然后改 WebSocket 协议和 `AgentBridge`
- [ ] 之后改前端 chatbox 双模和播放器
- [ ] 最后补管理后台配置与 GPT-SoVITS 克隆配置

## 备注

- 首版明确不做全双工实时语音
- 不要把聊天语音逻辑继续堆进 `backend/src/extensions/video_pipeline/tts_voice.py`
- 后续可以把视频配音能力迁移为复用新的通用 TTS 层
