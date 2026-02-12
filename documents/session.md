# X-Agent 会话管理系统（Session Management）

## 简介

在现有 .md + sqlite-vss 双写架构的基础上，增加每个会话（Session）的交互记录并同步到 SQLite，不仅能实现：
- ✅ 完整对话追溯
- ✅ 快速按 session 查询历史
- ✅ 支持后续分析（如行为模式、高频问题）
- ✅ 与向量库联动进行混合检索

## ✅ 新增目标

| 功能 | 实现方式 |
|------|----------|
| ✅ 记录每轮 session_id 对话 | 存入 SQLite 表 sessions |
| ✅ 同步存储：用户输入 + AI 输出 | 字段结构化 |
| ✅ 支持查询某 session 所有记录 | 提供查询接口 |
| ✅ 自动关联长期记忆提取结果 | 可用于训练或复盘 |
| ✅ 与 .md 文件双写一致 | 确保数据一致性 |

## 🧩 一、数据库扩展设计（SQLite）

我们在现有的 db/memory.db 中新增一张表：

```sql
-- 创建 sessions 表
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,           -- 会话 ID
    turn_index INTEGER NOT NULL,        -- 轮次索引（第几轮）
    role TEXT NOT NULL,                 -- 'user' 或 'assistant'
    content TEXT NOT NULL,             -- 消息内容
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    metadata JSON,                      -- 扩展字段（可选：token 数、模型名等）

    -- 复合唯一键：防止重复插入
    UNIQUE(session_id, turn_index, role)
);

-- 添加索引提升查询性能
CREATE INDEX IF NOT EXISTS idx_session_id ON sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON sessions(timestamp);
```

💡 这张表将作为"结构化对话日志中心"，便于后续：

## 🔧 二、代码实现（集成到原有系统）

### 1. 【会话管理器】增强版 MemoryManager

```python
# src/md_sync.py → 增强 MemoryManager

import sqlite3
import json
from datetime import datetime
from hashlib import md5

class MemoryManager:
    def __init__(self, db_path="db/memory.db"):
        self.db_path = db_path
        self.vector_db = VectorStore(db_path)  # 已有 sqlite-vss
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata JSON,
                    UNIQUE(session_id, turn_index, role)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON sessions(session_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON sessions(timestamp);")

    # ======================
    # 新增：记录会话交互
    # ======================

    def log_conversation_turn(self, session_id: str, role: str, content: str, metadata: dict = None):
        """记录一轮对话"""
        if role not in ["user", "assistant"]:
            raise ValueError("role must be 'user' or 'assistant'")

        # 获取当前轮次索引
        turn_index = self.get_next_turn_index(session_id, role)

        # 写入 SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, turn_index, role, content, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id, turn_index, role) DO UPDATE SET content=excluded.content
                """,
                (session_id, turn_index, role, content, json.dumps(metadata))
            )
            conn.commit()

        # 同时写入 .md 文件（保持双写一致）
        self._write_to_md_log(session_id, role, content)

        # 如果是 assistant 回复，且包含重要事实，也可触发 long_term_update
        if role == "assistant":
            self._maybe_extract_and_save_long_term(content, session_id)

    def get_next_turn_index(self, session_id: str, role: str) -> int:
        """获取下一个 turn_index（按 role 区分）"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT MAX(turn_index) FROM sessions
                WHERE session_id = ? AND role = ?
            """, (session_id, role))
            result = cur.fetchone()[0]
            return (result or -1) + 1

    def _write_to_md_log(self, session_id: str, role: str, content: str):
        """同步写入 .md 日志文件"""
        path = f"md/sessions/{session_id}.md"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        prefix = "👤" if role == "user" else "🤖"
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{prefix} **{role.title()}**: {content}  \n\n")

    def _maybe_extract_and_save_long_term(self, content: str, session_id: str):
        """简单规则：若回复中含"已记下""提醒"等词，则视为关键记忆"""
        trigger_words = ["已记下", "记住", "提醒", "添加到计划"]
        if any(w in content for w in trigger_words):
            title = f"AI 主动记录 - {datetime.now().strftime('%H:%M')}"
            self.long_term_update(title, content)

    # ======================
    # 查询功能
    # ======================

    def get_session_history(self, session_id: str) -> list:
        """获取完整会话历史"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT role, content, timestamp FROM sessions
                WHERE session_id = ?
                ORDER BY turn_index ASC, role DESC
            """, (session_id,))
            return [{"role": r, "content": c, "timestamp": t} for r, c, t in cur.fetchall()]

    def search_sessions_by_content(self, keyword: str, limit=20) -> list:
        """全文搜索会话内容"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT session_id, role, content, timestamp FROM sessions
                WHERE content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{keyword}%", limit))
            return [dict(zip(["session_id", "role", "content", "timestamp"], row)) for row in cur.fetchall()]
```

### 2. 【主流程中使用】记录每次交互

修改 main.py 中的聊天逻辑：

```python
# main.py
def chat(user_input: str, session_id: str = "default"):
    # Step 1: 加载上下文
    ctx = build_context(is_main_chat=True)

    # Step 2: 混合搜索相关记忆
    relevant = hybrid_search(user_input, k=3)
    relevant_text = "\n".join([f"- {r[0]} (score: {r[1]:.3f})" for r in relevant])

    # Step 3: 构造 Prompt 并调用 LLM
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

    # Step 4: 双写记录（新增：同时记录 session 到 SQLite）
    mm = MemoryManager()

    # 记录用户输入
    mm.log_conversation_turn(
        session_id=session_id,
        role="user",
        content=user_input,
        metadata={"source": "webchat"}
    )

    # 记录 AI 输出
    mm.log_conversation_turn(
        session_id=session_id,
        role="assistant",
        content=response,
        metadata={"model": "gpt-3.5-turbo", "tokens": len(response.split())}
    )

    # 同时更新每日日志
    mm.daily_log(f"User: {user_input}")
    mm.daily_log(f"AI: {response}")

    return response
```

## 📊 三、支持的查询能力示例

### ✅ 查看某个会话的全部记录
```python
mm = MemoryManager()
history = mm.get_session_history("sess_abc123")
for msg in history:
    print(f"[{msg['timestamp']}] {msg['role']}: {msg['content'][:50]}...")
```

### ✅ 搜索所有提到"咖啡"的对话
```python
results = mm.search_sessions_by_content("咖啡")
for r in results:
    print(f"{r['session_id']} | {r['role']}: {r['content']}")
```

### ✅ 统计高频问题（可用于优化 prompt）
```python
with sqlite3.connect("db/memory.db") as conn:
    df = pd.read_sql_query("""
        SELECT content, COUNT(*) as cnt FROM sessions
        WHERE role = 'user'
        GROUP BY content
        ORDER BY cnt DESC LIMIT 10
    """, conn)
print(df)
```

## 🗂️ 四、目录结构更新

```
md/
├── sessions/
│   ├── sess_abc123.md      ← 每个 session 的人类可读日志
│   └── sess_xyz456.md
│
db/
└── memory.db               ← 包含：
                             - memories (sqlite-vss)
                             - sessions (新表)
```

实现了：

## ✅ 五、优势总结

| 特性 | 说明 |
|------|------|
| 🔄 双写一致 | .md 和 SQLite 同时更新，互为备份 |
| 🔍 精准回溯 | 可按 session_id 完整还原对话流 |
| 📈 数据分析友好 | 结构化数据支持 SQL 查询、导出、BI 分析 |
| ⚙️ 工程化支撑 | 为未来做 fine-tuning、RAG 复盘、Agent 复盘打基础 |
| 🕵️‍♂️ 审计追踪 | 所有交互可查，满足合规需求 |

## 🚀 六、下一步建议

你可以基于这个系统进一步扩展：

| 功能 | 实现思路 |
|------|----------|
| 📊 会话仪表盘 | 用 Streamlit / Gradio 展示所有 session |
| 🔁 RAG from Session | 将历史优质对话作为 context 注入新会话 |
| 🤖 Agent 复盘机制 | 让 AI 自己回顾"上次是怎么解决这个问题的" |
| 💬 WebChat UI | 显示带时间线的聊天记录，支持翻页 |
| 🔐 权限控制 | 不同用户只能访问自己的 session |

✅ 你现在拥有的是一个完整的"本地 AI 助手记忆中枢"：
```
               +---------------------+
               |     用户提问         |
               +----------+----------+
                          ↓
         +---------------v----------------+
         |  上下文加载引擎                    |
         | • SOUL.md / USER.md            |
         | • daily/*.md                   |
         | • MEMORY.md                    |
         | • session history (SQLite)     |
         +---------------+----------------+
                         ↓
              +----------v----------+
              |   混合搜索 + LLM 响应   |
              +----------+----------+
                         ↓
       +------------------+------------------+
       | 双写持久化                            |
       | • .md 文件（人可读）                   |
       | • SQLite（结构化 + 向量）              |
       +--------------------------------------+
```

## 📦 七、项目交付

是否需要我为你生成完整的项目 ZIP 包？
包含：
● 所有 Python 模块
● 示例 .md 文件
● 初始化数据库脚本
● CLI 测试工具
● requirements.txt

只需告诉我："请生成完整项目模板"，我将一次性交付全部内容，让你可以直接运行。