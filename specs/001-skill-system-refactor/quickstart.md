# Quick Start: Skill 系统重构

**Feature Branch**: `001-skill-system-refactor`  
**Date**: 2026-03-01

## 概述

本文档提供 Skill 系统重构的快速入门指南，帮助开发者理解新系统的核心概念和使用方式。

---

## 核心概念

### 1. 技能清单 (SkillManifest)

每个技能由 `manifest.json` 定义，包含完整的元数据：

```json
{
  "skill_id": "pptx",
  "name": "PPT 演示文稿工具",
  "version": "2.0.0",
  "description": "创建和编辑 PowerPoint 演示文稿",
  "tags": ["document", "presentation"],
  "domains": ["document", "creative"],
  "risk_level": "medium",
  "approval_mode": "auto",
  "supports_dry_run": true
}
```

### 2. 技能来源优先级

| 来源 | 优先级 | 路径 |
|------|--------|------|
| USER | 最高 | `~/.x-agent/workspace/skills/` |
| SYSTEM | 次之 | `backend/src/skills/` |

同名技能 USER 覆盖 SYSTEM。

### 3. 技能发现流程

```
用户输入 → 语义检索 → 混合评分 → 约束过滤 → SkillCard 输出
```

---

## 快速开始

### 创建新技能

1. **创建技能目录**

```bash
mkdir -p ~/.x-agent/workspace/skills/my-skill
```

2. **创建 manifest.json**

```json
{
  "skill_id": "my-skill",
  "name": "我的技能",
  "version": "1.0.0",
  "description": "这是我的自定义技能",
  "tags": ["custom"],
  "auto_trigger": true,
  "risk_level": "low"
}
```

3. **创建 SKILL.md（可选，人类可读）**

```markdown
---
name: my-skill
description: "这是我的自定义技能"
keywords: [自定义, 测试]
---

# 我的技能

## 使用方法

...
```

4. **刷新技能缓存**

```bash
curl -X POST http://localhost:8000/api/v1/skills/cache/clear
```

### 发现技能

```python
import httpx

async def discover_skills(user_input: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/skills/discover",
            json={
                "user_input": user_input,
                "top_k": 5
            }
        )
        return response.json()

# 示例
skills = await discover_skills("帮我做一个演示文稿")
for skill in skills["skills"]:
    print(f"{skill['emoji']} {skill['name']} - {skill['relevance_score']:.2f}")
```

### 执行技能

```python
async def execute_skill(skill_id: str, params: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8000/api/v1/skills/{skill_id}/execute",
            json={
                "session_id": "test-session",
                "params": params,
                "dry_run": False
            }
        )
        return response.json()

# 示例
result = await execute_skill("pptx", {"action": "create", "filename": "demo.pptx"})
print(result)
```

---

## 组件使用

### ManifestParser

```python
from src.services.skill.manifest_parser import ManifestParser

parser = ManifestParser()
manifest = parser.parse(Path("skills/pptx/manifest.json"))
print(manifest.skill_id)  # pptx
```

### SkillRegistry

```python
from src.services.skill.registry import SkillRegistry

registry = SkillRegistry(workspace_path=Path("~/.x-agent/workspace"))
skills = registry.list_all_skills()
for skill in skills:
    print(f"{skill.name} ({skill.source})")
```

### SkillDiscovery

```python
from src.services.skill.discovery import SkillDiscovery
from src.services.skill.registry import SkillRegistry
from src.services.skill.indexer import SkillIndexer

registry = SkillRegistry(workspace_path)
indexer = SkillIndexer(registry)
discovery = SkillDiscovery(registry, indexer)

context = SkillSearchContext(
    user_input="帮我做一个演示文稿",
    available_params={},
    user_permissions=["read", "write"],
)

cards = await discovery.discover(context, top_k=5)
for card in cards:
    print(f"{card.name}: {card.relevance_score:.2f}")
```

### SkillExecutor

```python
from src.services.skill.executor import SkillExecutor

executor = SkillExecutor()

context = SkillExecutionContext(
    session_id="test",
    user_input="创建 PPT",
    params={"action": "create"},
    dry_run=True,  # 预演模式
)

result = await executor.execute(manifest, context)
if result.success:
    print(f"预演成功: {result.output}")
else:
    print(f"预演失败: {result.error}")
```

---

## 配置

### x-agent.yaml

```yaml
workspace:
  path: ~/.x-agent/workspace
  skills_dir: skills  # 相对于 workspace.path

skills:
  cache_ttl_seconds: 300  # 缓存过期时间
  watch_enabled: false    # 是否监听文件变化
  embedding:
    model: m3e-small      # 嵌入模型
    cache_enabled: true   # 嵌入缓存
```

---

## 目录结构

### 技能目录

```
skill/
├── manifest.json     # 必需：技能清单
├── SKILL.md          # 可选：人类可读指南
├── schemas/          # 可选：输入输出 Schema
│   ├── input.json
│   └── output.json
├── scripts/          # 可选：执行脚本
├── references/       # 可选：参考文档
└── assets/           # 可选：资源文件
```

### 源代码

```
backend/src/services/skill/
├── __init__.py
├── manifest_parser.py   # Manifest 解析器
├── registry.py          # 技能注册表
├── indexer.py           # 向量索引
├── discovery.py         # 发现服务
├── scorer.py            # 混合评分
└── executor.py          # 渐进执行
```

---

## 常见问题

### Q: 如何覆盖系统内置技能？

在用户技能目录创建同名技能，USER 来源优先级更高会自动覆盖。

### Q: 如何调试技能发现？

```python
# 获取详细的评分分解
card = cards[0]
print(f"语义得分: {card.score_breakdown['semantic']:.2f}")
print(f"Schema填充: {card.score_breakdown['schema_fit']:.2f}")
print(f"策略得分: {card.score_breakdown['policy']:.2f}")
```

### Q: 如何实现高风险技能的确认流程？

```json
{
  "skill_id": "delete-files",
  "risk_level": "high",
  "approval_mode": "confirm",
  "supports_dry_run": true
}
```

系统会自动在执行前要求用户确认。

### Q: 如何回滚失败的操作？

```python
# 检查是否支持回滚
if result.rollback_available:
    rollback_result = await executor.rollback(manifest, result.rollback_data)
```

---

## 下一步

1. 阅读 [data-model.md](./data-model.md) 了解完整数据模型
2. 查看 [contracts/skill-api.yaml](./contracts/skill-api.yaml) 了解 API 契约
3. 运行 `/speckit.tasks` 生成实现任务列表
