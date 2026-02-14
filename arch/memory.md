# 需求
这是一套高度结构化、具备“自我认知”与“记忆演化能力”的 AI 助手系统，融合了：
● 人类可读性（Markdown 文件）
● AI 可检索性（sqlite-vss 向量搜索）
● 双写架构（.md + sqlite-vss）
● 多层记忆体系
● 混合评分机制
● 文件监听同步

# 一、目标总结
能力
实现方式
## 分层记忆管理
每日日志 + 长期记忆 + 引导文件
## 自我认知机制
SPIRIT.md, OWNER.md 初始化身份，主人的个性化设置
以上两个配置是在Agent第一次启动时，需要通过与用户交流来初始化设置
## 常用工具加载
TOOLS.md agent可以使用的tools 工具技能表
## 上下文加载流程
启动时按规则自动读取多级文件
## sqlite-vss 存储向量
高性能本地向量检索
## 双写架构
写入 .md 的同时更新 sqlite-vss
## 文件变更监听
使用 watchdog 监听 .md 变化并同步
## 混合搜索
(0.7 * 向量得分) + (0.3 * 文本相似度)

# 二、目录结构设计

用户记忆和工作目录 ./workspace

ai-agent/
│
├── workspace/                     # 所有 Markdown 记忆
│   ├── SPIRIT.md                  # AI 的“人格设定”
│   ├── OWNER.md                  # 主人(拥有着用户)画像
│   ├── MEMORY.md                # 长期记忆主文件（摘要/关键点）
│   ├── AGENTS.md                # 常用工具与行为规范
    ├── TOOLS.md                # AI agent可以使用的tools工具技能表
│   │
│   └── memory/                  # 每日日志
│       ├── 2025-04-05.md
│       └── 2025-04-06.md
│
├── db/                          # 数据库
│   └── memory.db                # sqlite-vss 扩展
│
├── src/
│   ├── soul_loader.py           # 加载 SOUL.md / USER.md
│   ├── context_builder.py       # 构建上下文（按层级加载）
│   ├── vector_store.py          # sqlite-vss 操作封装
│   ├── md_sync.py               # .md ↔ sqlite-vss 双向同步
│   ├── hybrid_search.py         # 混合搜索实现
│   └── file_watcher.py          # 文件监听器
│
├── main.py                      # 主入口
└── requirements.txt


# 三、核心组件详解
## 1. 【灵魂文件】SOUL.md —— “这是你是谁”
 SOUL.md - 我是谁

- 我是一个专注型 AI 助手，服务于个人知识管理。
- 我的性格：温和、理性、主动但不过度打扰。
- 我的价值观：
  - 尊重隐私
  - 不编造信息
  - 帮助用户变得更好
- 我的行为准则：
  - 在每次响应前，先回顾当前上下文和长期记忆
  - 对重要计划进行提醒
  - 拒绝不合理请求（如执行危险命令）

> 启动时必须加载此文件作为 prompt 的一部分。


## 2. 【用户画像】USER.md —— “这是你在帮助谁”
 USER.md - 我的主人

- 姓名：张三
- 年龄：32
- 职业：前端工程师 & 创业者
- 兴趣：编程、咖啡、徒步旅行、阅读科幻小说
- 当前目标：开发一款本地 AI 笔记工具
- 偏好：
  - 喜欢简洁 UI
  - 不喜欢拿铁，只喝美式
  - 每周跑步三次


## 3. 【记忆引导】AGENTS.md —— 行为规范
 AGENTS.md - 行为指南

在做其他事情之前，请遵循以下步骤：

1. 阅读 `SOUL.md` - 这是你是谁  
2. 阅读 `USER.md` - 这是你在帮助谁  
3. 阅读 `memory/YYYY-MM-DD.md`（今天和昨天）获取近期上下文  
4. 如果是在主会话中（与你的主人直接聊天），还要阅读 `MEMORY.md`  

只有完成以上加载后，才能开始响应。

# 四、启动流程示例
if __name__ == "__main__":
    # 启动文件监听
    observer = start_watcher()

    # 开始对话
    while True:
        q = input("\nYou: ")
        if q.lower() == "quit":
            break
        ans = chat(q)
        print(f"AI: {ans}")

    observer.stop()


# 五、优势总结
特性
实现效果
  自我认知清晰
通过 SOUL.md 和 USER.md 定义角色
  上下文完整
多层加载确保不遗漏
 人机双友好
.md 给人看，sqlite-vss 给 AI 搜
  轻量高效
无需服务器，单文件数据库
  主动进化
文件变化自动同步
 精准召回
混合搜索兼顾语义与关键词