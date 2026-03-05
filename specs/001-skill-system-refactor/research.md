# Research: Skill 系统重构

**Feature Branch**: `001-skill-system-refactor`  
**Date**: 2026-03-01  
**Status**: Complete

## 研究任务概述

| 研究项 | 决策 | 状态 |
|--------|------|------|
| 向量检索方案 | sqlite-vss | ✅ 决定 |
| Embedding 模型 | M3E-small | ✅ 决定 |
| 混合评分策略 | 语义 0.35 + Schema 0.25 + 策略 0.20 + 延迟 0.10 + 可靠性 0.10 | ✅ 决定 |
| manifest.json Schema | JSON Schema 验证 | ✅ 决定 |

---

## 1. 向量检索方案

### 决策：sqlite-vss

### 备选方案对比

| 方案 | 安装复杂度 | API 简洁性 | 搜索延迟 (50-100文档) | Async 友好 | 持久化 | 推荐度 |
|------|-----------|-----------|---------------------|-----------|--------|-------|
| **sqlite-vss** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 20-50ms | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **首选** |
| hnswlib | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | < 1ms | ⭐⭐⭐ | ⭐⭐⭐ | 备选 |
| faiss | ⭐⭐⭐ | ⭐⭐⭐ | 5-15ms | ⭐⭐ | ⭐⭐ | 不推荐 |
| chromadb | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 100-150ms | ⭐⭐ | ⭐⭐⭐⭐ | 不推荐 |

### 选择理由

1. **架构一致性**: 项目已在 `backend/src/memory/vector_store.py` 成功使用 sqlite-vss
2. **性能充足**: 20-50ms 远低于 200ms 要求
3. **运维成本最低**: 单文件数据库，无额外服务进程
4. **元数据集成**: 向量与元数据一起存储，无需额外映射
5. **智能降级**: 现有实现已有 VSS 不可用时的 Python cosine similarity 降级

### 否决的方案

- **faiss**: 需要自己管理元数据映射，增量更新困难
- **chromadb**: 搜索延迟接近 200ms 上限，性能余量不足
- **hnswlib**: 性能过剩，但需要自己管理持久化和元数据

---

## 2. Embedding 模型

### 决策：M3E-small

### 备选方案对比

| 方案 | 模型大小 | 向量维度 | 内存占用 | CPU 推理速度 | 中文支持 | 英文支持 | 推荐度 |
|------|---------|---------|---------|-------------|---------|---------|-------|
| **M3E-small** | 98 MB | 384 | ~350 MB | 35-60ms | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **首选** |
| BGE-small 双模型 | 211 MB | 512+384 | ~750 MB | 30-50ms | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 备选 |
| sentence-transformers MiniLM-L12 | 420 MB | 384 | ~1.2 GB | 80-120ms | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 不推荐 |
| text2vec | 400-600 MB | 768 | ~1.8 GB | 120-180ms | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 不推荐 |

### 选择理由

1. **性能充足**: 35-60ms 远低于 100ms 要求
2. **内存最低**: 350MB，适合边缘部署
3. **中英双语一体化**: 无需语言检测逻辑，简化实现
4. **技术术语理解**: 对代码/工具描述的理解能力强
5. **轻量启动**: 模型小，启动快速

### 否决的方案

- **sentence-transformers**: 80-120ms 接近 100ms 上限，内存占用较高
- **text2vec**: 英文支持不足，推理速度偏慢
- **BGE 双模型**: 需要实现语言检测，增加复杂度

### 实现建议

```python
# backend/src/services/skill/embedder.py
class SkillEmbedder:
    """技能系统的轻量级 Embedder"""
    
    def __init__(self, model_name: str = "m3e-small"):
        self.model = load_model(model_name)
        self._cache: dict[str, list[float]] = {}
    
    def embed(self, text: str) -> list[float]:
        if text in self._cache:
            return self._cache[text]
        embedding = self.model.encode(text)
        self._cache[text] = embedding
        return embedding
```

---

## 3. 混合评分策略

### 决策：加权综合评分

### 评分维度与权重

| 维度 | 权重 | 说明 |
|------|------|------|
| **语义相似度** | 0.35 | 用户输入与技能描述的向量余弦相似度 |
| **Schema 填充度** | 0.25 | 上下文已知参数对技能必需参数的覆盖率 |
| **策略得分** | 0.20 | 风险等级、权限检查、审批模式的综合惩罚 |
| **延迟得分** | 0.10 | 预估执行延迟与预算的匹配度 |
| **可靠性得分** | 0.10 | 历史执行成功率 |

### 评分公式

```
总分 = 0.35 × 语义相似度 
     + 0.25 × Schema填充度 
     + 0.20 × 策略得分 
     + 0.10 × 延迟得分 
     + 0.10 × 可靠性得分
```

### 策略得分惩罚规则

| 风险等级 | 惩罚 |
|---------|------|
| LOW | 0.0 |
| MEDIUM | -0.1 |
| HIGH | -0.3 |
| CRITICAL | -0.5 |

| 审批模式 | 惩罚 |
|---------|------|
| AUTO | 0.0 |
| CONFIRM | -0.1 |
| APPROVAL | -0.3 |
| MANUAL | -0.5 |

---

## 4. manifest.json Schema 设计

### 决策：JSON Schema 验证

### 必需字段

```json
{
  "skill_id": "string (kebab-case)",
  "name": "string (显示名称)",
  "version": "string (semver)",
  "description": "string (简短描述)"
}
```

### 完整 Schema

参考设计方案中的 SkillManifest 定义，包含：

1. **Identity**: skill_id, name, version, vendor, signature
2. **Capability**: description, description_detail, tags, domains, examples
3. **IO Contract**: input_schema, output_schema, error_schema
4. **Execution**: endpoint, callable, timeout_ms, max_retries, idempotency
5. **Constraints**: preconditions, postconditions, invariants, os, requires_bins, requires_env
6. **Risk & Policy**: risk_level, data_access, side_effect, approval_mode, auto_trigger
7. **Observability**: telemetry, trace_fields, redaction_rules
8. **Progressive Execution**: stages, supports_dry_run, supports_rollback

### 验证实现

```python
import jsonschema

class ManifestParser:
    def __init__(self, schema_path: Path | None = None):
        self._schema = self._load_schema(schema_path)
    
    def validate(self, manifest: dict) -> bool:
        jsonschema.validate(manifest, self._schema)
        return True
```

---

## 5. 组件化架构决策

### 组件依赖关系

```
Agent Core (不依赖任何实现)
    │
    ▼
SkillPort (Protocol 接口定义)
    │
    ▼
┌─────────────────────────────────────────┐
│           独立组件层                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │Manifest │ │Registry │ │Discovery│   │
│  │ Parser  │ │         │ │         │   │
│  └─────────┘ └─────────┘ └─────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ Scorer  │ │Executor │ │ Indexer │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
    │
    ▼
SkillAdapter (组合各组件，实现 SkillPort)
```

### 组件职责

| 组件 | 职责 | 依赖 |
|------|------|------|
| ManifestParser | 解析 manifest.json | 无 |
| SkillRegistry | 技能注册与存储 | ManifestParser |
| SkillIndexer | 向量索引构建 | Registry, Embedder |
| SkillDiscovery | 检索与召回 | Registry, Indexer |
| SkillScorer | 混合打分 | 无 |
| SkillExecutor | 执行与阶段管理 | 无 |
| SkillAdapter | 组合与适配 | 以上所有 |

---

## 6. 迁移策略

### 现有代码影响

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `models/skill.py` | 重构 | 统一为 SkillManifest |
| `agent_core/ports/skill_port.py` | 扩展 | 添加新的数据结构 |
| `services/skill_registry.py` | 迁移 | 移至 skill/registry.py |
| `services/skill_parser.py` | 保留 | 兼容 SKILL.md 解析 |

### 向后兼容

1. **SKILL.md 兼容**: 保留现有解析器，支持 SKILL.md YAML frontmatter
2. **manifest.json 优先**: 如果 manifest.json 存在，优先使用
3. **渐进迁移**: 现有技能可逐步添加 manifest.json

---

## 结论

所有研究项已完成决策，无需进一步澄清。可以进入 Phase 1 设计阶段。
