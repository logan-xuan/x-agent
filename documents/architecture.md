# 项目目标
要开发一个具备以下能力的 多功能 Agent 智能体跟人助理：
● 编写代码
● 自然语言聊天（对话）
● 扩展技能（如制作 PPT、处理文档，预留workspace文件夹由用户自定义扩展skill）
● Web 搜索
● chrome浏览器自动化操作
● 执行本地 CLI 命令（能本地操作）
● 访问本地文件系统
● Cron 定时任务管理
这样的智能体属于“通用 AI Agent”范畴，类似 Openclaw 等。下面我将从 编程语言选择 和 技术架构设计 两个维度为你详细规划。
# 技术架构
## 技术栈
采用模块化 + 插件式架构，便于扩展功能（skills）
前后端分离架构（TypeScript + Python），后端（Python FastAPI）

## 架构分层
Expression（表达）->Gateway（网关接入）->Agent Core（智能体核心）-> tools（工具库和执行）->DBM（databese数据库存储和管理）
### Expression 表达层
#### 用户界面
● Web UI (React + TS)  webchat  WebSocket / REST API  可以进行文字、图片、文件的方式进行沟通
● 实时日志流 
● 设置入口：大模型切换设置，skill，plugin、mcp、channel配置
#### Channel 消息渠道扩展
可以接入飞书、钉钉、微信消息渠道，能力与webchat一致用于与agent继续沟通的渠道。
### Gateway 网关接入层
承上启下，接收上层消息传递至Agent。
session 管理、消息队列流控、权限控制、日志统一、分类收集。
http或WebSocket通信链路管理。
心跳检测：主要检查agent与表达层的链接状态，确保agent在执行长任务活跃状态检测
### Agent Core 控制中心
LLM 推理引擎
Context engineering  (上下文工程管理：select subAgent、 压缩、外部记忆存储)
Task Planner（任务规划）
Skill Router（技能路由)
Memory System（记忆系统）
Security Guard（安全守卫）
Tools 工具执行层

1、系统级的tools和plugin，模块化可插拔，后续可迭代。
2、客户自定义技能存放在项目根目录 workspace

| - Cron 定时任务管理 |

| - Web Search |
| - Code Interpreter |
| - File System Access |
| - Command Executor |
| - Office Automation |
| - Custom Plugins... |

### DBM 数据存储与管理
● Vector DB: sqlite-vss 
● SQLite: 历史记录  
● Cache & Logs
● MarkDown 文件存储用户日志记忆

## 特别技术设计
### 配置文件
一个灵活、通用、可扩展的 AI Agent 配置体系，支持多模型接入、插件化架构、通信通道管理与环境适配。
config.md
### 上下文工程
不是把所有历史塞给 LLM，而是只传递最精准、最关键的上下文
ConversationCompression.md
同时增加每个会话session的交互记录，同步到sqlite，便于后续查询
session.md

### 记忆系统
具备“自我认知”与“记忆演化能力”的 AI 助手系统
memory.md

### 心跳机制
—— 构建一个高可用、可监控、用户友好的长任务执行系统
适用于：RAG 检索、代码生成与运行、多步规划、文件处理等耗时操作。
Heartbeat.md
### 插件设计
目标：让开发者像安装 App 一样为 AI Agent 添加新能力，无需修改主代码。

Plugin.md
### 命令执行模块
允许大模型（LLM）在默认情况下，安全地执行用户自定义的 kill 操作及常见 CLI 命令，如：并特别说明：kill 是指 类似 Anthropic 定义的安全 kill 技能 —— 即：仅限于当前用户权限下终止自身启动的进程或开发服务。
command.md

### Agent执行引擎
构建一个支持 LLM + Tools + MCP + SubAgent 协同工作的智能执行中枢
目标：让 AI Agent 不再是“单打独斗”，而是成为一个会调用工具、能分解任务、可协调子代理的智能指挥官。
agentCore.md

### X-Agent SubAgent 执行引擎设计（v2.0）
subAgent默认不开启，由显性命令/subagent 开启，而且应该根据自身应用职责 精准投喂Prompt以减少token，识别更精准
按需启动：subagent 默认不开启，避免资源浪费  
精准投喂：为每个子代理定制最小化 Prompt，提升识别精度、降低 token 消耗
subAgent.md

### Cron 定时任务管理
现在我们来设计 Cron 定时任务管理，当用户提到某个时间计划提醒做某事，创建一个cron任务，到点执行任务。
Corn.md


