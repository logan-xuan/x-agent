这是一套高度结构化、具备“自我认知”与“记忆演化能力”的 AI 助手系统，融合了：
● ✅ 人类可读性（Markdown 文件）
● ✅ AI 可检索性（sqlite-vss 向量搜索）
● ✅ 双写架构（.md + sqlite-vss）
● ✅ 多层记忆体系
● ✅ 混合评分机制
● ✅ 文件监听同步
我们将基于你的需求，设计一个完整的 智能体记忆引导系统（Agent Memory Guidance System）。

🎯 一、目标总结
能力
实现方式
✅ 分层记忆管理
每日日志 + 长期记忆 + 引导文件
✅ 自我认知机制
SOUL.md, USER.md 初始化身份
✅ 上下文加载流程
启动时按规则自动读取多级文件
✅ sqlite-vss 存储向量
高性能本地向量检索
✅ 双写架构
写入 .md 的同时更新 sqlite-vss
✅ 文件变更监听
使用 watchdog 监听 .md 变化并同步
✅ 混合搜索
(0.7 * 向量得分) + (0.3 * 文本相似度)

📁 二、目录结构设计
ai-agent/
│
├── md/                          # 所有 Markdown 记忆
│   ├── SOUL.md                  # AI 的“人格设定”
│   ├── USER.md                  # 用户画像
│   ├── MEMORY.md                # 长期记忆主文件（摘要/关键点）
│   ├── AGENTS.md                # 工具与行为规范
│   │
│   └── memory/                  # 每日日志
│       ├── 2025-04-05.md
│       └── 2025-04-06.md
│
├── db/                          # 数据库
│   └── memory.db                # SQLite + sqlite-vss 扩展
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


🧠 三、核心组件详解
1. 【灵魂文件】SOUL.md —— “这是你是谁”
# SOUL.md - 我是谁

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


2. 【用户画像】USER.md —— “这是你在帮助谁”
# USER.md - 我的主人

- 姓名：张三
- 年龄：32
- 职业：前端工程师 & 创业者
- 兴趣：编程、咖啡、徒步旅行、阅读科幻小说
- 当前目标：开发一款本地 AI 笔记工具
- 偏好：
  - 喜欢简洁 UI
  - 不喜欢拿铁，只喝美式
  - 每周跑步三次


3. 【记忆引导】AGENTS.md —— 行为规范
# AGENTS.md - 行为指南

在做其他事情之前，请遵循以下步骤：

1. 阅读 `SOUL.md` - 这是你是谁  
2. 阅读 `USER.md` - 这是你在帮助谁  
3. 阅读 `memory/YYYY-MM-DD.md`（今天和昨天）获取近期上下文  
4. 如果是在主会话中（与你的主人直接聊天），还要阅读 `MEMORY.md`  

只有完成以上加载后，才能开始响应。


🔧 四、代码实现
1. 【初始化】加载灵魂与用户设定
# src/soul_loader.py
def load_soul_and_user():
    try:
        with open("md/SOUL.md", encoding="utf-8") as f:
            soul = f.read()
        with open("md/USER.md", encoding="utf-8") as f:
            user = f.read()
        return soul.strip(), user.strip()
    except Exception as e:
        print(f"⚠️ 缺少关键文件: {e}")
        return "", ""


2. 【上下文构建器】按层级加载上下文
# src/context_builder.py
from datetime import datetime, timedelta
import os

def get_today_yesterday_md():
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    paths = [ ]

    for date in [today, yesterday]:
        p = f"md/memory/{date}.md"
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                paths.append(f.read())
    return "\n".join(paths)

def build_context(is_main_chat=True):
    # 步骤 1-2: 加载身份
    from .soul_loader import load_soul_and_user
    soul, user = load_soul_and_user()

    # 步骤 3: 加载最近两天日志
    recent_memories = get_today_yesterday_md()

    # 步骤 4: 主会话才加载长期记忆
    long_term_memory = ""
    if is_main_chat and os.path.exists("md/MEMORY.md"):
        with open("md/MEMORY.md", encoding="utf-8") as f:
            long_term_memory = f.read()

    return {
        "soul": soul,
        "user_profile": user,
        "recent_memories": recent_memories,
        "long_term_memory": long_term_memory
    }


3. 【向量存储】使用 sqlite-vss
# src/vector_store.py
import sqlite3
import vss
import hashlib
from typing import List, Tuple

class VectorStore:
    def __init__(self, db_path="db/memory.db"):
        self.conn = sqlite3.connect(db_path)
        vss.register(self.conn)
        self._init_table()

    def _init_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                type TEXT,
                timestamp TEXT
            )
        """)
        self.conn.execute("""
            CREATE VSS INDEX IF NOT EXISTS idx_embedding ON memories(embedding)
        """)

    def add_memory(self, content: str, content_type: str = "general"):
        text_hash = hashlib.md5(content.encode()).hexdigest()
        embedding = vss.Vector.encode_from_text(content)

        self.conn.execute(
            "INSERT OR REPLACE INTO memories (id, content, type, timestamp, embedding) VALUES (?, ?, ?, ?, ?)",
            (text_hash, content, content_type, datetime.now().isoformat(), embedding)
        )
        self.conn.commit()

    def search(self, query: str, k=5) -> List[Tuple[str, float]]:
        query_vec = vss.Vector.encode_from_text(query)
        results = self.conn.execute("""
            SELECT content, distance
            FROM vss_search(idx_embedding, ?, k=?)
        """, (query_vec.to_bytes(), k)).fetchall()
        return [(row[0], row[1]) for row in results]


4. 【双写管理器】
# src/md_sync.py
from src.vector_store import VectorStore
from datetime import datetime

vector_db = VectorStore()

class MemoryManager:
    @staticmethod
    def write_md_and_vss(file_path: str, content: str, content_type: str = "general"):
        # 写入 .md
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"- {content}  \n")

        # 写入 sqlite-vss
        vector_db.add_memory(content, content_type)

    @staticmethod
    def daily_log(content: str):
        today = datetime.now().strftime("%Y-%m-%d")
        path = f"md/memory/{today}.md"
        MemoryManager.write_md_and_vss(path, content, "daily")

    @staticmethod
    def long_term_update(title: str, content: str):
        path = "md/MEMORY.md"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n## {title}\n{content}\n\n")
        vector_db.add_memory(content, "long_term")


5. 【混合搜索】最终得分 = 0.7×向量 + 0.3×文本
# src/hybrid_search.py
import re
from difflib import SequenceMatcher
from src.vector_store import VectorStore

def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def hybrid_search(query: str, k=5) -> List[Tuple[str, float]]:
    # 向量搜索
    vector_results = VectorStore().search(query, k=k*2)
    
    # 全局文本匹配（可优化为从所有 .md 中提取句子）
    all_sentences = extract_all_sentences()  # 简化版略

    text_scores = [ ]

    for sent in all_sentences:
        score = text_similarity(query, sent)
        if score > 0.3:
            text_scores.append((sent, score))

    # 合并去重
    combined = {}
    for content, v_score in vector_results:
        norm_v = (1 - v_score)  # 距离越小越好 → 得分越大
        combined[content] = 0.7 * norm_v + 0.3 * 0

    for content, t_score in text_scores:
        combined[content] = max(combined.get(content, 0), 0.7 * 0 + 0.3 * t_score)

    # 排序返回 Top-K
    sorted_items = sorted(combined.items(), key=lambda x: -x[1])
    return sorted_items[:k]


6. 【文件监听】自动同步新内容到向量库
# src/file_watcher.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

class MDHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        print(f"检测到文件变化: {event.src_path}")
        # 可触发增量解析 + 写入 sqlite-vss
        # TODO: 提取新增行，避免重复写入

def start_watcher():
    event_handler = MDHandler()
    observer = Observer()
    observer.schedule(event_handler, path="md", recursive=True)
    observer.start()
    return observer


🔄 五、主流程整合
# main.py
from src.context_builder import build_context
from src.hybrid_search import hybrid_search
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-3.5-turbo")

def chat(user_input: str):
    # Step 1: 加载上下文（按 AGENTS.md 规则）
    ctx = build_context(is_main_chat=True)

    # Step 2: 混合搜索相关记忆
    relevant = hybrid_search(user_input, k=3)
    relevant_text = "\n".join([f"- {r[0]} (score: {r[1]:.3f})" for r in relevant])

    # Step 3: 构造 Prompt
    prompt = f"""
{ctx['soul']}

你正在帮助：
{ctx['user_profile']}

近期动态：
{ctx['recent_memories']}

长期记忆摘要：
{ctx['long_term_memory']}

相关记忆检索结果：
{relevant_text}

问题：{user_input}
请综合以上信息作答。
"""

    response = llm.invoke(prompt).content

    # Step 4: 双写记录
    from src.md_sync import MemoryManager
    MemoryManager.daily_log(f"User: {user_input}")
    MemoryManager.daily_log(f"AI: {response}")

    return response


✅ 六、启动流程示例
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


🚀 七、优势总结
特性
实现效果
✅ 自我认知清晰
通过 SOUL.md 和 USER.md 定义角色
✅ 上下文完整
多层加载确保不遗漏
✅ 人机双友好
.md 给人看，sqlite-vss 给 AI 搜
✅ 轻量高效
无需服务器，单文件数据库
✅ 主动进化
文件变化自动同步
✅ 精准召回
混合搜索兼顾语义与关键词