# 配置管理体系设计文档

## 概述
配置管理体系是一个灵活、通用、可扩展的 AI Agent 配置系统，支持多模型接入、插件化架构、通信通道管理与环境适配。

## 目标
实现方式
 统一模型配置
抽象 provider/baseUrl/apiKey/modelId，不依赖厂商
 即插即用切换模型
改配置即可从 OpenAI 切换到 Qwen、GLM 或本地 Ollama
 安全密钥管理
支持 ${VAR} 注入环境变量
 插件系统支持
可启用/禁用插件，自动发现目录
 多通信通道
WebSocket / HTTP / CLI 等
 网关服务控制
端口、CORS、限流等
 多环境支持
dev / prod 配置覆盖机制
结构清晰易读
yaml 格式 + 模块化组织
