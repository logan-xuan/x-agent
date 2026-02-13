# x-agent2 QWEN 模型配置指南

## 配置摘要

我们已成功为x-agent2配置了阿里云通义千问（QWEN）大模型，以下是详细配置信息：

## 1. 配置文件修改

### config/app-config.yaml
```yaml
models:
  primary: "qwen-max"              # 主要模型：通义千问MAX版
  fallback: "qwen-plus"           # 备用模型：通义千问PLUS版
  providers:
    - qwen                        # 支持QWEN提供商
    - openai                      # 保留原有提供商
```

### .env 环境变量
```env
# Qwen Configuration
QWEN_API_KEY=sk-b9cc4741b6c0418f974288e79eef08d9
QWEN_BASE_URL=https://dashscope.aliyuncs.com/api/v1
```

## 2. 代码修改

### src/agent_core/llm_engine/service.py
- 添加了对QWEN模型的支持
- 添加了ChatTongyi导入和初始化逻辑
- 更新了primary和fallback客户端初始化方法
- 更新了配置验证方法

### src/main.py
- 添加了对app-config.yaml配置文件的读取
- 修改了LLM服务初始化逻辑以使用配置文件中的模型设置

## 3. 依赖安装

安装了以下必要依赖：
- `langchain-community` - 提供ChatTongyi客户端
- `dashscope` - 阿里云通义千问SDK

## 4. 验证结果

- ✓ 配置文件成功更新
- ✓ 代码支持QWEN模型
- ✓ API端点显示正确的model_used: qwen-max
- ✓ 环境变量已正确设置

## 5. 使用说明

启动服务时，系统将使用QWEN模型作为主要模型，配置如下：
- 主要模型：qwen-max（通义千问MAX版）
- 备用模型：qwen-plus（通义千问PLUS版）
- API密钥：已配置
- 基础URL：https://dashscope.aliyuncs.com/api/v1

## 6. 故障排除

如果遇到"Agent is not available due to compatibility issues."消息：
1. 确认QWEN_API_KEY有效
2. 检查网络连接是否可达https://dashscope.aliyuncs.com/api/v1
3. 确认账户余额充足（如适用）

要切换回其他模型，只需修改config/app-config.yaml中的primary和fallback模型名称。