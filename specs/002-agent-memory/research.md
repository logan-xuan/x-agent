# Research: AI Agent 记忆系统

**Feature**: 002-agent-memory | **Date**: 2026-02-14

## Research Questions

### RQ-1: 本地向量数据库选型

**Decision**: 使用 sqlite-vss 作为向量存储扩展

**Rationale**:
- 与现有 SQLite 存储无缝集成，无需额外数据库服务
- 支持向量相似度搜索（余弦相似度、欧氏距离）
- 轻量级，适合本地单实例运行
- Python 生态支持良好（sqlite-vss 包）

**Alternatives Considered**:
| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| ChromaDB | 功能丰富，易用 | 需要独立服务，资源占用大 | ❌ 过重 |
| FAISS | 高性能，Meta 出品 | 需要自己管理持久化 | ❌ 集成复杂 |
| Pinecone | 云服务，易扩展 | 需要网络，有费用 | ❌ 不符合本地运行要求 |
| sqlite-vss | 轻量，与 SQLite 集成 | 性能略低于专用向量库 | ✅ 最优选择 |

---

### RQ-2: 本地嵌入模型选型

**Decision**: 使用 sentence-transformers (all-MiniLM-L6-v2)

**Rationale**:
- 轻量级模型（~80MB），适合本地运行
- 中英文双语支持良好
- 384 维向量，平衡性能与精度
- 首次加载后缓存在本地，后续启动快速

**Alternatives Considered**:
| 方案 | 维度 | 大小 | 中文支持 | 结论 |
|------|------|------|----------|------|
| all-MiniLM-L6-v2 | 384 | 80MB | 良好 | ✅ 推荐 |
| paraphrase-multilingual-MiniLM-L12-v2 | 384 | 420MB | 优秀 | ⚠️ 较大 |
| text2vec-chinese | 768 | 400MB | 优秀 | ⚠️ 维度高，存储大 |
| OpenAI embeddings | 1536 | API | 优秀 | ❌ 需要外部 API |

---

### RQ-3: 文件监听与热加载方案

**Decision**: 使用 watchdog 库实现文件变更监听

**Rationale**:
- Python 标准文件监听方案
- 跨平台支持（macOS/Linux/Windows）
- 支持递归监听目录
- 事件驱动，低资源占用

**Implementation Pattern**:
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class MemoryFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.md'):
            # 触发重新加载和向量同步
            pass
```

---

### RQ-4: Markdown 文件格式规范

**Decision**: 采用 frontmatter + content 结构

**Rationale**:
- YAML frontmatter 存储元数据（UUID、时间戳、类型）
- 主体内容为 Markdown 格式，人类可读
- 便于解析和版本控制

**Format Example**:
```markdown
---
id: 550e8400-e29b-41d4-a716-446655440000
type: conversation
created_at: 2026-02-14T10:30:00
updated_at: 2026-02-14T10:30:00
tags: [decision, project]
---

# 用户决定使用 React 作为前端框架

用户在讨论中确认选择 React 而非 Vue，理由是团队更熟悉 React 生态。
```

---

### RQ-5: 混合搜索评分机制

**Decision**: 使用 0.7 * 向量得分 + 0.3 * 文本相似度

**Rationale**:
- 向量搜索捕获语义相似性
- 文本相似度（BM25/TF-IDF）捕获关键词匹配
- 权重分配符合规范要求

**Implementation**:
```python
def hybrid_search(query: str, limit: int = 10) -> list:
    # 1. 向量搜索
    query_embedding = embed(query)
    vector_results = vector_store.search(query_embedding, limit * 2)
    
    # 2. 文本相似度
    text_results = text_search(query, limit * 2)
    
    # 3. 混合评分
    combined = {}
    for item in vector_results:
        combined[item.id] = {'vector_score': item.score, 'text_score': 0}
    for item in text_results:
        if item.id in combined:
            combined[item.id]['text_score'] = item.score
        else:
            combined[item.id] = {'vector_score': 0, 'text_score': item.score}
    
    # 4. 排序
    results = sorted(
        combined.items(),
        key=lambda x: 0.7 * x[1]['vector_score'] + 0.3 * x[1]['text_score'],
        reverse=True
    )
    return results[:limit]
```

---

### RQ-6: 记忆条目类型分类

**Decision**: 定义 4 种记忆类型

| 类型 | 说明 | 触发条件 |
|------|------|----------|
| conversation | 对话记录 | AI 自动识别重要对话 |
| decision | 决策记录 | AI 识别决策关键词 |
| summary | 摘要记录 | 长对话自动提炼 |
| manual | 手动标记 | 用户主动标记 |

**AI 识别关键词**:
- Decision: "决定", "选择", "确认", "确定", "decide", "choose"
- Important: "重要", "关键", "注意", "important", "key", "note"

---

## Technical Decisions Summary

| 领域 | 决策 | 关键参数 |
|------|------|----------|
| 向量存储 | sqlite-vss | 余弦相似度 |
| 嵌入模型 | all-MiniLM-L6-v2 | 384 维向量 |
| 文件监听 | watchdog | 事件驱动 |
| 文件格式 | YAML frontmatter + Markdown | UTF-8 编码 |
| 混合搜索 | 0.7 向量 + 0.3 文本 | BM25 文本相似度 |
| 记忆类型 | 4 种 | conversation/decision/summary/manual |

## Dependencies to Add

```toml
# pyproject.toml
[project.dependencies]
sentence-transformers = ">=2.2.0"
sqlite-vss = ">=0.1.0"
watchdog = ">=3.0.0"
pyyaml = ">=6.0"
python-frontmatter = ">=1.0.0"
```
