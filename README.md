# X-Agent2 - 多功能 AI 智能体助手

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue" alt="Python Version">
  <img src="https://img.shields.io/badge/FastAPI-0.104.1-green" alt="FastAPI Version">
  <img src="https://img.shields.io/badge/LangChain-latest-orange" alt="LangChain">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License">
</div>

## 🌟 项目简介

X-Agent2 是一个功能强大的多功能 AI 智能体助手，具备代码编写、自然语言对话、Web 搜索、浏览器自动化、文件系统访问等核心能力。采用模块化架构设计，支持插件扩展和自定义技能开发。

## 🚀 核心功能

### 🧠 智能对话
- 自然语言理解和多轮对话
- 上下文感知和记忆管理
- 个性化交互体验

### 💻 代码能力
- 代码编写和执行
- 代码解释和优化建议
- 多语言支持（Python、JavaScript等）

### 🌐 Web 操作
- 网页搜索和信息提取
- 浏览器自动化操作
- 表单填写和数据抓取

### 📁 文件管理
- 本地文件系统访问
- 文件读写和操作
- 目录管理

### ⚙️ 系统工具
- 命令行执行
- 定时任务管理
- 系统监控

### 🔧 可扩展架构
- 插件化设计
- 自定义技能开发
- MCP 协议支持

## 🏗️ 技术架构

### 架构分层

```
Expression 层 → Gateway 层 → Agent Core 层 → Tools 层 → DBM 层
```

**Expression 表达层**
- Web UI (React + TypeScript)
- 多渠道接入（WebSocket/HTTP）
- 实时日志流

**Gateway 网关层**
- 会话管理
- 消息队列和流控
- 权限控制
- 心跳检测

**Agent Core 核心层**
- LLM 推理引擎
- 任务规划器
- 上下文管理
- 技能路由
- 记忆系统
- 安全守卫

**Tools 工具层**
- 系统工具集
- 用户自定义技能
- 插件化架构

**DBM 数据层**
- 向量数据库 (sqlite-vss)
- 关系数据库 (SQLite)
- 缓存和日志系统

### 技术栈

- **后端**: Python 3.8+, FastAPI
- **AI 框架**: LangChain, OpenAI, Anthropic
- **前端**: React + TypeScript
- **数据库**: SQLite + sqlite-vss
- **消息通信**: WebSocket, HTTP
- **任务调度**: Cron

## 📦 安装部署

### 环境要求

- Python 3.8 或更高版本
- pip 包管理器
- Node.js (前端开发)

### 快速开始

1. **克隆项目**
```bash
git clone git@gitlab.alibaba-inc.com:xuan.lx/x-agent.git
cd x-agent
```

2. **安装依赖**
```bash
# 后端依赖
pip install -r requirements.txt

# 前端依赖（如果需要）
cd frontend
npm install
```

3. **环境配置**
```bash
# 复制环境配置文件
cp .env.example .env

# 编辑配置文件，设置 API 密钥等
vim .env
```

4. **启动服务**
```bash
# 启动后端服务
python src/main.py

# 启动前端（新终端）
cd frontend
npm run dev
```

5. **访问应用**
- 后端 API: http://localhost:8000
- 前端界面: http://localhost:3000
- API 文档: http://localhost:8000/docs

## 🛠️ 配置说明

### 环境变量配置

```bash
# API 密钥配置
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# 数据库配置
DATABASE_URL=sqlite:///./xagent.db

# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=True
```

### 配置文件

- `config/app-config.yaml` - 应用主配置
- `config/providers/` - 模型提供商配置
- `.env` - 环境变量配置

## 📚 API 接口

### 核心接口

**聊天接口**
```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "你好，帮我写一个Python程序",
  "session_id": "unique-session-id",
  "context": {
    "user_preferences": "用户偏好信息"
  }
}
```

**工具执行**
```http
POST /api/v1/tools/execute
Content-Type: application/json

{
  "tool_name": "web-search",
  "parameters": {
    "query": "最新AI技术"
  },
  "session_id": "session-id"
}
```

**任务规划**
```http
POST /api/v1/agents/plan
Content-Type: application/json

{
  "goal": "分析市场趋势并生成报告",
  "context": "金融行业"
}
```

## 🔧 开发指南

### 项目结构

```
x-agent/
├── src/                    # 源代码
│   ├── agent_core/        # Agent 核心模块
│   ├── api/               # API 接口
│   ├── tools/             # 工具模块
│   ├── plugins/           # 插件系统
│   └── main.py           # 入口文件
├── frontend/              # 前端代码
├── tests/                 # 测试代码
├── config/                # 配置文件
├── documents/             # 文档资料
└── workspace/             # 用户工作空间
```

### 开发环境设置

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装开发依赖
pip install -r requirements.txt

# 运行测试
python -m pytest tests/
```

### 添加自定义工具

1. 在 `src/tools/` 目录下创建新工具模块
2. 继承 `BaseTool` 类
3. 实现核心方法
4. 在工具管理器中注册

```python
from src.tools.base_tool import BaseTool

class CustomTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="custom_tool",
            description="自定义工具描述"
        )
    
    def execute(self, **kwargs):
        # 实现工具逻辑
        return {"result": "执行结果"}
```

## 🧪 测试

### 运行测试

```bash
# 运行所有测试
python -m pytest

# 运行单元测试
python -m pytest tests/unit/

# 运行集成测试
python -m pytest tests/integration/

# 生成测试覆盖率报告
python -m pytest --cov=src tests/
```

## 📖 文档

详细的技术文档请参考 `documents/` 目录：

- [架构设计](documents/architecture.md)
- [配置管理](documents/config.md)
- [记忆系统](documents/memory.md)
- [插件开发](documents/Plugin.md)
- [API 接口](documents/api-contract.yaml)

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 贡献流程

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码规范

- 遵循 PEP 8 Python 编码规范
- 使用类型提示
- 编写单元测试
- 保持代码文档化

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- [LangChain](https://github.com/langchain-ai/langchain) - AI 应用开发框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能 Web 框架
- [OpenAI](https://openai.com/) - AI 模型提供商
- [Anthropic](https://www.anthropic.com/) - AI 模型提供商

## 📞 联系方式

- 项目维护者: xuan.lx
- 项目地址: git@gitlab.alibaba-inc.com:xuan.lx/x-agent.git
- 问题反馈: [Issues](https://gitlab.alibaba-inc.com/xuan.lx/x-agent/-/issues)

---

<div align="center">
  <sub> Made with ❤️ by the X-Agent team </sub>
</div>