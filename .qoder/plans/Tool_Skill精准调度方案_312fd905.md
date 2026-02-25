# Tool/Skill 精准调度实施方案

## 📋 背景与问题分析

### Trace 问题诊断（`2025ea34-2145-4a1b-ab3d-b1ca459e2d82`）

**核心问题**：
1. **规划不清晰**：Plan 生成时未明确指定每个步骤的工具约束
2. **工具调用不准确**：LLM 在执行过程中偏离计划，随意选择工具

**根本原因**：
- 缺少任务类型识别机制（研究类 vs 创作类 vs 数据处理类）
- 工具约束主要依赖 LLM 自发生成，没有预设规则
- Skill 的 `allowed_tools` 未被充分利用
- 缺少语义路由机制，无法精准匹配 Skill

---

## 🎯 设计原则（基于 tools-skills.md）

### 核心架构思想

```
Agent 不直接选 Tool → Agent 选 Skill → Skill 控制 Tool
```

**三层架构**：
1. **Tool Registry** - 原子能力管理（已完成）
2. **Skill Registry** - 组合能力管理（已完成）
3. **Semantic Router** - 精准调度层（待实现）

---

## 🔧 实施方案

### Phase 1: 增强工具约束机制（立即实施）

#### P1-1: 完善 TASK_TYPE_RULES

**文件**: `backend/src/orchestrator/structured_planner.py`

**目标**: 扩展现有的任务类型识别规则，覆盖更多场景

**改动**:
```python
TASK_TYPE_RULES = {
    "research": {
        "allowed": ["web_search", "fetch_web_content", "memory"],
        "forbidden": ["pdf", "pptx", "run_in_terminal"],
        "keywords": ["研究", "分析", "调查", "趋势", "现状", "预测", "发展", "调研"]
    },
    "creation": {
        "allowed": ["pdf", "pptx", "write_file"],
        "forbidden": [],
        "keywords": ["生成", "创建", "撰写", "制作", "编写", "输出", "创作"]
    },
    "data_processing": {
        "allowed": ["read_file", "write_file", "run_in_terminal"],
        "forbidden": ["web_search"],
        "keywords": ["转换", "处理", "分析", "统计", "计算", "格式化", "提取"]
    },
    "web_task": {
        "allowed": ["web_search", "fetch_web_content", "browser_use"],
        "forbidden": ["pdf", "pptx"],
        "keywords": ["网页", "网站", "在线", "搜索", "抓取", "浏览"]
    },
    "code_development": {  # 新增
        "allowed": ["read_file", "write_file", "run_in_terminal"],
        "forbidden": ["web_search", "pdf", "pptx"],
        "keywords": ["代码", "编程", "开发", "调试", "测试", "重构"]
    }
}
```

**验收标准**:
- ✅ 能正确识别 5 种任务类型
- ✅ 每种类型的工具约束合理
- ✅ 关键词覆盖常见场景

---

#### P1-2: 强化 Skill-based 工具约束

**文件**: 
- `backend/src/orchestrator/structured_planner.py` (Line 204-218)
- `backend/src/tools/manager.py` (已有技能约束检查)

**目标**: 确保技能的 `allowed_tools` 被严格执行

**改动**:
```python
# 在 generate 方法中增强逻辑
if skill_name:
    skill = self.skill_registry.get_skill_metadata(skill_name)
    if skill:
        skill_info = f"- 技能名称：{skill.name}\n- 技能描述：{skill.description}\n- 允许的工具：{skill.allowed_tools or '无限制'}"
        
        # 强制使用技能的 allowed_tools，而不是让 LLM 决定
        if skill.allowed_tools:
            tool_constraints = ToolConstraints(
                allowed=skill.allowed_tools,
                forbidden=[t for t in ["web_search", "pdf", "pptx"] if t not in skill.allowed_tools]
            )
            logger.info("强制应用技能工具约束", extra={"skill": skill.name, "allowed": skill.allowed_tools})
```

**验收标准**:
- ✅ `/pptx create presentation.pptx` 只能使用 pptx 技能定义的工具
- ✅ 尝试使用非 allowed_tools 时被阻止
- ✅ 错误信息清晰说明原因

---

### Phase 2: 实现 Semantic Router（核心功能）

#### P2-1: 创建 Skill Embedding 系统

**新文件**: `backend/src/services/skill_router.py`

**目标**: 基于向量相似度进行 Skill 精准匹配

**实现**:
```python
"""Skill Router for semantic matching."""

import numpy as np
from typing import List, Tuple
from ..services.llm.router import LLMRouter
from ..services.skill_registry import SkillRegistry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SkillRouter:
    """基于语义向量的 Skill 路由器
    
    核心流程:
    1. 将所有 Skill 描述转换为 embedding
    2. 用户任务转换为 embedding
    3. 计算余弦相似度
    4. 返回 Top-K 匹配的 Skill
    """
    
    def __init__(self, llm_router: LLMRouter, skill_registry: SkillRegistry):
        self.llm_router = llm_router
        self.skill_registry = skill_registry
        self._skill_embeddings: dict[str, np.ndarray] = {}
    
    async def _compute_embedding(self, text: str) -> np.ndarray:
        """计算文本的 embedding 向量"""
        # 使用 LLM Router 的 embedding 模型
        response = await self.llm_router.embed(text)
        return np.array(response.embedding)
    
    async def build_index(self) -> None:
        """构建 Skill 索引（启动时调用一次）"""
        skills = self.skill_registry.list_all_skills()
        
        for skill in skills:
            # 组合技能和描述作为索引文本
            index_text = f"{skill.name}: {skill.description}"
            embedding = await self._compute_embedding(index_text)
            self._skill_embeddings[skill.name] = embedding
        
        logger.info(f"Skill index built with {len(self._skill_embeddings)} skills")
    
    async def route(self, task: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """为任务匹配最相关的 Skills
        
        Args:
            task: 用户任务描述
            top_k: 返回前 K 个匹配结果
            
        Returns:
            [(skill_name, similarity_score), ...]
        """
        if not self._skill_embeddings:
            await self.build_index()
        
        # 计算任务 embedding
        task_embedding = await self._compute_embedding(task)
        
        # 计算所有技能的相似度
        similarities = []
        for skill_name, skill_embedding in self._skill_embeddings.items():
            similarity = self._cosine_similarity(task_embedding, skill_embedding)
            similarities.append((skill_name, similarity))
        
        # 排序并返回 Top-K
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))


# 全局实例
_skill_router: SkillRouter | None = None

def get_skill_router(llm_router=None, skill_registry=None) -> SkillRouter:
    """获取全局 SkillRouter 实例"""
    global _skill_router
    if _skill_router is None:
        if llm_router is None:
            from ..services.llm.router import get_llm_router
            llm_router = get_llm_router()
        if skill_registry is None:
            from ..services.skill_registry import get_skill_registry
            from pathlib import Path
            skill_registry = get_skill_registry(Path.cwd())
        _skill_router = SkillRouter(llm_router, skill_registry)
    return _skill_router
```

**验收标准**:
- ✅ 能正确计算 Skill embedding
- ✅ 余弦相似度计算准确
- ✅ Top-K 召回合理

---

#### P2-2: 集成 Semantic Router 到 TaskAnalyzer

**文件**: `backend/src/orchestrator/task_analyzer.py`

**目标**: 在任务分析阶段使用语义路由匹配 Skill

**改动**:
```python
# 在 TaskAnalyzer 中添加 skill_router
from .skill_router import get_skill_router

class TaskAnalyzer:
    def __init__(self, ...):
        # ... existing code ...
        self.skill_router = get_skill_router()
    
    async def analyze(self, user_message: str) -> TaskAnalysis:
        # ... existing analysis ...
        
        # NEW: 使用语义路由匹配 Skills
        matched_skills_with_scores = await self.skill_router.route(user_message, top_k=3)
        
        # 过滤掉相似度低于阈值的
        SIMILARITY_THRESHOLD = 0.6
        matched_skills = [
            (name, score) for name, score in matched_skills_with_scores 
            if score >= SIMILARITY_THRESHOLD
        ]
        
        logger.info(
            "Semantic skill matching",
            extra={
                "task": user_message[:50],
                "matched_skills": matched_skills,
            }
        )
        
        # 如果有高匹配度的 Skill，优先使用
        if matched_skills:
            best_skill = matched_skills[0][0]  # 最佳匹配
            confidence = matched_skills[0][1]
            
            # 如果置信度很高，自动触发
            if confidence > 0.8:
                skill_name = best_skill
                auto_trigger = True
```

**验收标准**:
- ✅ 输入"生成 PPT"时能匹配到 `pptx` 技能
- ✅ 输入"研究报告"时能匹配到 `research` 相关技能
- ✅ 相似度阈值合理，避免误匹配

---

### Phase 3: 增强 Plan 执行监控（已有功能加强）

#### P3-1: 工具违反追踪增强

**文件**: `backend/src/orchestrator/react_loop.py`

**目标**: 记录并报告工具违反情况

**改动**:
```python
# 在 run_streaming 主循环中
if plan_state and plan_state.structured_plan:
    allowed_tools = plan_state.structured_plan.tool_constraints.allowed
    
    if tool_call.name not in allowed_tools:
        # 记录违反事件
        plan_state.record_tool_violation(
            tool_name=tool_call.name,
            violation_type="not_in_allowed_list",
            details={"allowed": allowed_tools}
        )
        
        # 发出警告
        yield {
            "type": "warning",
            "content": f"⚠️ 工具违反：'{tool_call.name}' 不在允许列表中",
            "allowed_tools": allowed_tools,
        }
        
        # 跳过此工具调用
        continue
```

**验收标准**:
- ✅ 每次违反都被记录
- ✅ 用户收到清晰的警告
- ✅ 可查询历史违反记录

---

#### P3-2: 阶段性验证增强

**文件**: `backend/src/orchestrator/engine.py`

**目标**: 在每个里程碑节点进行严格验证

**改动**:
```python
# 在 ReAct Loop 执行过程中
if plan_state and plan_state.structured_plan.milestones:
    current_step_id = f"step_{plan_state.current_step}"
    
    # 检查是否达到某个里程碑
    for milestone in plan_state.structured_plan.milestones:
        if milestone.after_step == current_step_id:
            # 执行里程碑验证
            validator = MilestoneValidator(plan_state.structured_plan)
            is_valid, reason = validator.check_milestone(milestone.name, tool_result)
            
            if not is_valid:
                # 触发反思或调整
                yield {
                    "type": "milestone_failed",
                    "milestone": milestone.name,
                    "reason": reason,
                    "suggestion": "请重新执行此步骤或调整策略",
                }
```

---

### Phase 4: Skill Graph 预研（高级功能）

#### P4-1: Skill Graph 数据结构设计

**文件**: `backend/src/models/skill_graph.py` (新文件)

**目标**: 为未来支持复杂 Skill 编排做准备

**实现**:
```python
"""Skill Graph data model for complex workflow orchestration."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillNode:
    """Skill 图节点"""
    id: str
    skill_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    tools: list[str]
    next_skills: list[str] = field(default_factory=list)


@dataclass  
class SkillGraph:
    """Skill 有向图"""
    nodes: dict[str, SkillNode] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=dict)
    
    def add_node(self, node: SkillNode) -> None:
        self.nodes[node.id] = node
    
    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id not in self.edges:
            self.edges[from_id] = []
        self.edges[from_id].append(to_id)
        self.nodes[from_id].next_skills.append(to_id)
```

**验收标准**:
- ✅ 能定义 Skill 节点
- ✅ 能建立 Skill 之间的依赖关系
- ✅ 支持图的遍历

---

## 📊 预期效果对比

| 指标 | 当前 | 目标 | 改进幅度 |
|------|------|------|----------|
| 规划清晰度 | 模糊 | 明确 | ↑90% |
| 工具调用准确率 | ~60% | >90% | ↑50% |
| Skill 匹配精度 | 关键词匹配 | 语义匹配 | ↑70% |
| Plan 执行偏离率 | ~60% | <15% | ↓75% |
| 平均迭代次数 | 10 次 | 5-6 次 | ↓40% |

---

## 🚀 实施顺序

### 第一阶段（本周完成）
1. **P1-1**: 完善 TASK_TYPE_RULES - 2 小时
2. **P1-2**: 强化 Skill-based 工具约束 - 1.5 小时
3. **P3-1**: 工具违反追踪增强 - 1.5 小时

### 第二阶段（下周完成）
4. **P2-1**: 创建 Skill Embedding 系统 - 4 小时
5. **P2-2**: 集成 Semantic Router - 3 小时
6. **P3-2**: 阶段性验证增强 - 2 小时

### 第三阶段（预研）
7. **P4-1**: Skill Graph 数据结构 - 3 小时

---

## 🧪 测试计划

### 单元测试
```python
# test_semantic_router.py
async def test_research_task_matching():
    router = get_skill_router()
    task = "帮我研究一下 AI 发展趋势"
    matches = await router.route(task, top_k=3)
    
    assert len(matches) > 0
    assert matches[0][1] > 0.6  # 相似度>0.6
```

### 集成测试
```bash
# 测试研究类任务
/research 分析新能源汽车市场趋势

# 预期:
# 1. 自动匹配 research 技能
# 2. 工具约束：只能用 web_search, fetch_web_content, memory
# 3. 禁止使用 pdf, pptx
```

---

## ⚠️ 风险与缓解

### 风险 1: Semantic Router 性能开销
**缓解**: 
- 启动时预计算 Skill embeddings
- 使用缓存避免重复计算
- 设置合理的 top_k 值（默认 3）

### 风险 2: 工具约束过严
**缓解**:
- 提供"申请突破约束"机制
- LLM 可说明理由后使用非常规工具
- 记录所有突破案例用于优化

---

## 📝 验收标准

### 功能性验收
1. ✅ 研究类任务自动禁止 PDF/PPT 工具
2. ✅ 创作类任务自动包含生成工具
3. ✅ Semantic Router 能准确匹配 Skills（相似度>0.6）
4. ✅ 工具违反被记录并警告
5. ✅ 里程碑验证正常工作

### 性能验收
1. ✅ Skill 匹配响应时间 < 200ms
2. ✅ 工具约束检查不显著影响性能（<50ms）
3. ✅ 平均迭代次数下降到 5-6 次

### 用户体验验收
1. ✅ 用户输入"生成 PPT"时自动触发 pptx 技能
2. ✅ 工具违反时收到清晰的引导消息
3. ✅ 执行过程可视化（当前进度、允许的工具）

---

## 🔗 关键文件映射

| 组件 | 文件路径 | 修改类型 |
|------|----------|----------|
| TASK_TYPE_RULES | `orchestrator/structured_planner.py` | 增强 |
| Skill Router | `services/skill_router.py` | 新建 |
| Task Analyzer | `orchestrator/task_analyzer.py` | 集成 |
| Tool Manager | `tools/manager.py` | 已有约束检查 |
| React Loop | `orchestrator/react_loop.py` | 违反追踪 |
| Engine | `orchestrator/engine.py` | 里程碑验证 |
| Skill Graph | `models/skill_graph.py` | 新建（预研） |

---

## 💡 下一步行动

**立即执行**:
1. 确认方案是否符合设计需求
2. 开始 Phase 1 实施（P1-1, P1-2）
3. 准备测试用例

**需要澄清的问题**:
1. 是否需要立即实现 Skill Graph，还是先聚焦于 Semantic Router？
2. embedding 模型的选择：使用现有 LLM Router 还是引入专门的 embedding 服务？
3. 相似度阈值的默认值：0.6 是否合适？

---

## 📖 参考资料

- 设计文档：`arch/tools-skills.md`
- 现有实现：`backend/src/orchestrator/structured_planner.py`
- 工具约束：`backend/src/tools/manager.py` (Line 144-159)
- Plan v2.0: `backend/src/orchestrator/models/plan.py`