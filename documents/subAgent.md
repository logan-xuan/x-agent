
# 需求目标
按需启动：subagent 默认不开启，避免资源浪费  
精准投喂：为每个子代理定制最小化 Prompt，提升识别精度、降低 token 消耗
基于显式指令触发 + 职责隔离 + 精准 Prompt 注入


# 一、整体架构图
                     [用户输入]
                          ↓
           是否以 `/subagent` 开头？
                   ↓             ↓
                是               否
                 ↓               ↓
     解析 role: /subagent coder    → 主 Agent 处理
                 ↓
       [检查权限 & 是否已注册] 
                 ↓
      [加载该 subagent 的专属 Prompt]
                 ↓
   [仅传递必要上下文（压缩后+过滤）]
                 ↓
        [启动 subagent 实例]
                 ↓
      [执行任务 → 流式返回结果]
                 ↓
         [完成后自动关闭或休眠]


# 二、核心设计原则
原则
说明
 默认关闭
所有 subagent 初始状态为 inactive
 显式唤醒
必须使用 /subagent <role> 触发
  职责单一
每个 subagent 只做一件事，如 coder, researcher
 Prompt 隔离
不共享主 Prompt，只注入自身角色说明
 上下文精简
只传相关记忆，避免信息过载
 可配置生命周期
支持“临时”或“持久”模式

# 三、SubAgent 注册机制（roles.json）
// config/subagents.json
[
  {
    "role": "coder",
    "name": "代码助手",
    "description": "专注于编写和审查代码",
    "prompt": "你是一个专业的 Python 开发者。请根据需求生成简洁、可运行的代码，无需解释。",
    "allowed_channels": ["webchat", "terminal"],
    "auto_shutdown_after_seconds": 300,
    "enable_by_default": false
  },
  {
    "role": "researcher",
    "name": "研究专家",
    "description": "擅长信息检索与知识整合",
    "prompt": "你是一个严谨的研究员，请从可靠来源中提取事实，并用第三人称总结。",
    "tools": ["web-search", "file-read"],
    "enable_by_default": false
  },
  {
    "role": "reviewer",
    "name": "质量审查员",
    "description": "负责代码/文案的质量检查",
    "prompt": "你是一个挑剔但公正的审查员，请指出逻辑漏洞、风格问题和潜在风险。",
    "require_context": true,
    "enable_by_default": false
  }
]

 所有 subagent 默认禁用，必须通过命令显式启用。

# 四、显式命令语法
用户输入格式：
/subagent coder
写一个 Python 函数，计算斐波那契数列第 n 项。

/subagent researcher --persist
查找最近三年关于 AI 伦理的主要学术观点。

/subagent off

支持参数：
● --persist：保持激活状态
● --timeout=60：自定义存活时间
● off：关闭当前 subagent


# 五、Prompt 投喂策略对比
场景
传统方式
本方案
输入 token 数
~1800
~400
内容组成
SOUL.md + USER.md + 完整历史
仅角色 Prompt + 过滤后上下文
上下文相关性
低（信息混杂）
高（按角色过滤）
响应准确率
中
高
成本
高
降低 70%+

# 六、优势总结
特性
效果
 按需启用
不占用资源，不影响主流程
  精准角色定位
每个 subagent 只懂自己的事
 最小 Prompt 投喂
大幅节省 token
 上下文感知
仍能获取关键记忆
 自动回收
非持久模式超时关闭
 安全可控
无法绕过权限调用工具

# 七、典型使用场景
场景
示例
 编程辅助
/subagent coder → 写算法、修 Bug
  知识研究
/subagent researcher → 查资料、写综述
 文案润色
/subagent reviewer → 审查邮件、报告
 项目规划
/subagent planner → 拆解任务、制定路线图
