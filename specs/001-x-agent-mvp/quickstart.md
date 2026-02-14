# Quick Start Guide: X-Agent MVP

**Feature**: X-Agent MVP  
**Created**: 2026-02-14  
**Related**: [spec.md](./spec.md), [plan.md](./plan.md)

## 环境要求

- Python 3.11+
- Node.js 18+
- pnpm (推荐) 或 npm
- Git

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd x-agent
```

### 2. 安装后端依赖

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. 安装前端依赖

```bash
cd ../frontend
pnpm install  # 或 npm install
```

### 4. 配置

复制配置文件模板并编辑：

```bash
cp backend/x-agent.yaml.example backend/x-agent.yaml
```

编辑 `backend/x-agent.yaml`：

```yaml
# X-Agent 配置文件
# 所有配置集中管理，无需环境变量

models:
  # 主模型配置
  - name: primary
    provider: openai
    base_url: https://api.openai.com/v1
    api_key: sk-your-openai-key-here
    model_id: gpt-3.5-turbo
    is_primary: true
    timeout: 30.0
    max_retries: 2
  
  # 备用模型配置 (阿里云百炼)
  - name: backup-bailian
    provider: bailian
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-your-bailian-key-here
    model_id: qwen-turbo
    is_primary: false
    timeout: 45.0
    max_retries: 3
    priority: 1  # 备用模型优先级，数值越小优先级越高
  
  # 备用模型配置 (其他 OpenAI 兼容提供商)
  - name: backup-custom
    provider: custom
    base_url: https://your-custom-api.com/v1
    api_key: sk-your-custom-key-here
    model_id: your-model-id
    is_primary: false
    timeout: 60.0
    priority: 2

server:
  host: 0.0.0.0
  port: 8000
  cors_origins:
    - http://localhost:5173
  reload: false  # 开发模式设为 true

logging:
  level: INFO
  format: json
  file: logs/x-agent.log
  max_size: 10MB
  backup_count: 5
  console: true
```

**配置说明**:
- 所有配置集中在 `x-agent.yaml`，无需环境变量
- 支持多模型配置，一主多备自动故障转移
- 厂商无关设计，支持任意 OpenAI 兼容 API
- 配置文件变更自动检测（热重载）

## 启动服务

### 方式一：一键启动（推荐）

```bash
./start.sh
```

启动脚本将：
- 自动检查并安装依赖
- 启动后端服务 (http://localhost:8000)
- 启动前端服务 (http://localhost:5173)
- 按 Ctrl+C 可优雅关闭所有服务

### 方式二：分别启动（开发模式）

**终端 1 - 启动后端：**

```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
python -m src.main
```

后端服务将启动在 http://localhost:8000

**终端 2 - 启动前端：**

```bash
cd frontend
yarn dev  # 或 npm run dev
```

前端开发服务器将启动在 http://localhost:5173

### 方式三：单独启动各服务

```bash
# 仅启动后端
./start-backend.sh

# 仅启动前端
./start-frontend.sh
```

## 验证安装

### 1. 健康检查

```bash
curl http://localhost:8000/api/v1/health
```

预期响应：

```json
{
  "success": true,
  "timestamp": "2026-02-14T10:00:00Z",
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "uptime": 3600
  }
}
```

### 2. Web 界面

打开浏览器访问 http://localhost:5173

你应该看到：
- 聊天窗口界面
- 输入框和发送按钮
- 空的消息历史区域

### 3. 发送测试消息

1. 在输入框中输入 "你好"
2. 点击发送按钮或按 Enter
3. 观察 AI 回复是否以流式方式显示

## 常见问题

### Q: 后端启动失败，提示端口被占用

**A**: 修改 `x-agent.yaml` 中的 `server.port` 为其他端口（如 8001），同时更新前端 `.env` 中的 API 地址。

### Q: 前端无法连接到后端

**A**: 检查：
1. 后端服务是否正常运行
2. `x-agent.yaml` 中的 `cors_origins` 是否包含前端地址
3. 浏览器开发者工具中的网络请求错误

### Q: AI 回复显示 "服务不可用"

**A**: 检查：
1. API Key 是否正确配置
2. 模型提供商服务是否正常
3. 后端日志中的详细错误信息
4. 备用模型是否配置正确（主模型故障时会自动切换）

### Q: 如何修改配置后无需重启服务

**A**: X-Agent 支持配置文件热重载：
1. 修改 `x-agent.yaml` 文件
2. 保存后系统会自动检测变更
3. 新的配置将在下一次请求时生效
4. 查看日志确认配置已重新加载

### Q: 如何添加新的模型提供商

**A**: 支持任意 OpenAI 兼容的 API：
1. 在 `models` 列表中添加新配置
2. `provider` 设为 `custom`
3. 填写正确的 `base_url` 和 `api_key`
4. 无需修改代码，配置即可生效

### Q: 一主多备如何工作

**A**: 
1. 系统优先使用标记 `is_primary: true` 的模型
2. 主模型故障时（超时或错误），自动切换到备用模型
3. 备用模型按 `priority` 数值从小到大依次尝试
4. 所有模型都不可用时返回错误

### Q: 配置文件中的敏感信息如何保护

**A**: 
1. API Key 在内存中加密存储（SecretStr）
2. 日志中自动脱敏，不显示完整 Key
3. 建议设置文件权限：`chmod 600 x-agent.yaml`
4. 不要将配置文件提交到 Git

### Q: 如何查看日志

**A**: 

```bash
# 实时查看日志
tail -f backend/logs/x-agent.log

# 或使用 jq 格式化 JSON 日志
tail -f backend/logs/x-agent.log | jq
```

## 开发工作流

### 运行测试

**后端测试：**

```bash
cd backend
pytest
```

**前端测试：**

```bash
cd frontend
pnpm test
```

### 代码检查

**后端：**

```bash
cd backend
ruff check .
ruff format .
mypy src/
```

**前端：**

```bash
cd frontend
pnpm lint
pnpm type-check
```

## 下一步

- 阅读 [API 文档](./contracts/openapi.yaml)
- 查看 [数据模型](./data-model.md)
- 了解 [实现计划](./plan.md)
