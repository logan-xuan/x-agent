"""Structured Planner for X-Agent.

Generates structured plans with skill bindings and tool constraints.
"""

# Use relative imports within the orchestrator package
from .models.plan import (
    StructuredPlan,
    PlanStep,
    Milestone,
    ToolConstraints,
    StepValidation,
)
from ..services.llm.router import LLMRouter
from ..services.skill_registry import SkillRegistry
from ..utils.logger import get_logger

logger = get_logger(__name__)


class StructuredPlanner:
    """生成结构化计划 v2.0
    
    关键特性：
    - 技能绑定：将计划与具体技能关联
    - 工具约束：白名单/黑名单机制
    - 步骤验证：每个步骤都有验证规则
    - 里程碑检查：关键节点自动验证
    """
    
    # 任务类型识别规则
    TASK_TYPE_RULES = {
        "research": {
            "allowed": ["web_search", "fetch_web_content", "memory"],
            "forbidden": ["pdf", "pptx", "run_in_terminal"],
            "keywords": ["研究", "分析", "调查", "趋势", "现状", "预测", "发展", "调研"],
            "required_skills": [],
            "validation": "internal"
        },
        "creation": {
            "keywords": ["生成", "创建", "撰写", "制作", "编写", "输出", "创作"],
            "required_skills": ["write_file"],
            "forbidden": [],
            "validation": "internal",
            "implementation": "根据产物类型选择 pdf/pptx/write_file",
            "default_allowed": ["web_search", "write_file", "run_in_terminal"]  # 🔥 FIX: Add default allowed tools
        },
        "pdf_creation": {
            "keywords": ["pdf", "PDF"],
            "allowed": [
                "run_in_terminal: python create_pdf_from_md.py",
                "write_file"
            ],  # 🔥 只允许增强版脚本
            "forbidden": [],
            "required_skills": ["write_file", "run_in_terminal"],
            "implementation": "Python + reportlab (使用技能脚本 create_pdf_from_md.py)",
            "system_prompt_rule": "pdf_skill_guidelines",
            "skill_scripts": [  # 🔥 NEW: 明确指定技能脚本路径
                "/workspace/x-agent/backend/src/skills/pdf/scripts/create_pdf_from_md.py"
            ]
        },
        "pptx_creation": {
            "keywords": ["ppt", "PPT", "演示文稿", "幻灯片"],
            "allowed": [
                "run_in_terminal: node create_presentation.js",
                "write_file"
            ],  # 🔥 具体技能脚本
            "forbidden": [],
            "required_skills": ["write_file", "run_in_terminal"],
            "implementation": "Node.js + PptxGenJS (使用技能脚本)",
            "system_prompt_rule": "pptx_skill_guidelines",
            "skill_scripts": [  # 🔥 NEW: 明确指定技能脚本路径
                "/workspace/x-agent/backend/src/skills/pptx/scripts/create_presentation.js"
            ]
        },
        "data_processing": {
            "allowed": ["read_file", "write_file", "run_in_terminal"],
            "forbidden": ["web_search"],
            "keywords": ["转换", "处理", "分析", "统计", "计算", "格式化", "提取"],
            "required_skills": [],
            "validation": "automatic"
        },
        "web_task": {
            "allowed": ["web_search", "fetch_web_content", "browser_use"],
            "forbidden": ["pdf", "pptx"],
            "keywords": ["网页", "网站", "在线", "搜索", "抓取", "浏览"],
            "required_skills": [],
            "validation": "internal"
        },
        "code_development": {
            "allowed": ["read_file", "write_file", "run_in_terminal"],
            "forbidden": ["web_search", "pdf", "pptx"],
            "keywords": ["代码", "编程", "开发", "调试", "测试", "重构"],
            "required_skills": [],
            "validation": "automatic"
        }
    }
    
    SYSTEM_PROMPT = """你是一个结构化任务规划专家。分析用户的目标，生成结构化的执行计划。

## 可用技能信息
{skill_info}

## 可用工具列表
{tools}

## ⚠️ 核心原则（必须遵守）

### 1. YAGNI 原则 - 禁止纯验证步骤
- 每个 step 必须直接贡献于 goal
- 禁止独立的验证步骤（如"list_dir: 验证 PDF 是否生成"）
- 验证应内建到 step 中（如"脚本执行成功即验证通过"）
- If not called, remove it

### 2. 最短路径原则
- 用最少步骤完成 goal
- 相似操作必须合并（如连续 write_file 应该合并为一个步骤）
- 目标：最小必要步骤数（通常 3-4 步）

### 3. 工具语义清晰
- 使用真实工具名：web_search, write_file, run_in_terminal
- 禁止虚构工具：pdf_create 应分解为 "write_file + run_in_terminal"
- 明确实现方式：如"Python + reportlab"或"Node.js + PptxGenJS"

### 4. 🔥 技能脚本优先原则（CRITICAL）
- **如果任务绑定了技能（如 pdf skill），必须使用该技能的脚本！**
- **PDF 生成示例**:
  - ✅ 正确：`python create_pdf_from_md.py output.pdf input.md "标题"`
  - ❌ 错误：`python convert_md_to_pdf.py ...`（脚本不存在）或 `python create_simple_pdf.py ...`（已过时）
- **原因**：`create_pdf_from_md.py` 已处理了字体注册、多页支持、自动排版等复杂逻辑
- **检查清单**：
  1. PDF skill → **唯一指定**使用 `create_pdf_from_md.py`
  2. 不要重新发明轮子！

### 5. 🔥🔥🔥 研究 + 创作类任务的特殊规则（CRITICAL FOR MIXED TASKS）
- **适用场景**：任务同时包含“研究/分析”和“生成 PDF/PPT/文档”需求
- **示例**：“深度研究 2026 AI 趋势并生成 PDF 报告”
- **必须遵守的约束**：
  - ✅ **Step 1（信息收集）**: 可以使用 `web_search`，但仅限 **1 次**
  - ✅ **Step 2（内容撰写）**: 使用 `write_file` 整理和撰写完整的 MD 格式报告
  - ✅ **Step 3（格式转换）**: 
    - **使用增强的 PDF 脚本 `create_pdf_from_md.py`**
    - **直接传入 MD 文件路径，脚本会自动读取并转换**
    - **命令格式**: `python create_pdf_from_md.py output.pdf input.md "标题"`
  - ❌ **禁止**: 在 Step 2 及之后继续使用 `web_search`
  - ❌ **禁止**: 在最后一步之前使用 PDF 生成工具
  - ❌ **禁止**: 使用旧版 `create_simple_pdf.py`（仅支持简单文本行）
- **步骤数量**: 严格限制为 **3 步**（除非有特殊需求）
- **PDF 内容要求**: 
  - ✅ **必须包含完整报告内容**（脚本会自动从 MD 文件读取）
  - ✅ **支持多页、章节格式化、自动分页**
  - ✅ **中文字体支持**（PingFang/STHeiti）
- **工具约束建议**: 
  ```json
  {{
    "allowed": ["web_search", "write_file", "run_in_terminal"],
    "forbidden": [],
    "metadata": {{
      "web_search_max_iterations": 1,
      "web_search_allowed_steps": [1],
      "final_step_must_use_skill": true
    }}
  }}
  ```

## 重要规则

1. 必须为每个步骤指定明确的工具
2. 根据任务类型使用对应的工具约束：
   - 研究报告类：只能使用 web_search, fetch_web_content, memory
   - 创作生成类：必须包含 pdf/pptx/write_file 等生成工具
   - 数据处理类：使用 read_file, write_file, run_in_terminal
   - PDF 生成：必须使用 Python + reportlab，禁止 Node.js PDFKit
   - PPT 生成：必须使用 Node.js + PptxGenJS
3. 最后一步通常是生成/输出工具（如 pdf, pptx, write_file）
4. 禁止在早期步骤使用最终生成工具
5. 如果任务需要多步骤研究，限制 web_search 使用次数（建议≤3 次）
6. 验证内建：每个 step 的 expected_output 应包含验证标准

## 输出要求

1. 如果用户使用了 /command 格式（如 /pdf），必须：
   - 将该技能名称填入 skill_binding 字段
   - 从技能的 allowed_tools 中提取工具白名单
   - 生成对应的 skill_command
   
2. 每个步骤必须包含：
   - id: 唯一标识（如 step_1, step_2）
   - name: 简洁的中文描述
   - tool: 使用的工具名称（必须是真实工具）
   - description: 详细说明，包括如何实现和验证
   - expected_output: 预期输出描述

3. 如果可能，为关键步骤添加：
   - skill_command: 具体的 CLI 命令
   - validation: 验证规则

4. 为关键节点定义 milestones

## 示例对比

❌ 错误示例（5 步，包含过度验证）:
{{
  "steps": [
    {{"id": "step_1", "name": "搜索信息", "tool": "web_search"}},
    {{"id": "step_2", "name": "整理资料", "tool": "write_file"}},
    {{"id": "step_3", "name": "撰写文章", "tool": "write_file"}},
    {{"id": "step_4", "name": "生成 PDF", "tool": "pdf_create"}},  // ❌ 虚构工具
    {{"id": "step_5", "name": "验证 PDF", "tool": "list_dir"}}  // ❌ 纯验证
  ]
}}

✅ 正确示例（3 步，最短路径）:
{{
  "version": "2.0",
  "goal": "生成 2026 AI 趋势报告 PDF",
  "skill_binding": null,
  "tool_constraints": {{
    "allowed": ["web_search", "write_file", "run_in_terminal"],
    "forbidden": []
  }},
  "steps": [
    {{
      "id": "step_1",
      "name": "搜索"2026 AI 发展趋势"，收集关键信息",
      "tool": "web_search",
      "description": "使用 web_search 搜索相关信息",
      "expected_output": "获取 5-10 个相关搜索结果"
    }},
    {{
      "id": "step_2",
      "name": "整合搜索结果，撰写研究报告",
      "tool": "write_file",
      "description": "将搜索结果整理为 MD 格式报告",
      "expected_output": "生成 MD 格式的研究报告文件"
    }},
    {{
      "id": "step_3",
      "name": "读取 MD 报告并转换为 PDF（增强版）",
      "tool": "run_in_terminal",
      "description": "**重要**: 使用增强的 PDF 生成脚本 `create_pdf_from_md.py`，该脚本会自动读取 MD 文件内容并生成多页 PDF。命令格式：`python create_pdf_from_md.py {{{{workspace_path}}}}/pdfs/output.pdf {{{{workspace_path}}}}/mds/report.md \"标题\"`。支持中文、自动分页、章节格式化。",
      "expected_output": "PDF 文件成功生成，包含完整的报告内容，中文字符正常显示，自动处理分页和排版",
      "skill_command": "python create_pdf_from_md.py {{{{workspace_path}}}}/pdfs/report.pdf {{{{workspace_path}}}}/mds/report.md \"2026 AI 趋势报告\""
    }}
  ],
  "milestones": [
    {{
      "name": "信息收集完成",
      "after_step": "step_1",
      "check_type": "tool_output"
    }},
    {{
      "name": "报告撰写完成",
      "after_step": "step_2",
      "check_type": "file_exists"
    }},
    {{
      "name": "PDF 生成完成",
      "after_step": "step_3",
      "check_type": "file_exists"
    }}
  ]
}}

## 示例输入
"/pdf convert document.pdf to word"

## 示例输出（JSON 格式）
{{
  "version": "2.0",
  "goal": "将 PDF 文档转换为 Word 格式",
  "skill_binding": "pdf",
  "tool_constraints": {{
    "allowed": ["run_in_terminal", "read_file"],
    "forbidden": ["web_search"]
  }},
  "steps": [
    {{
      "id": "step_1",
      "name": "读取 PDF 文件",
      "tool": "read_file",
      "expected_output": "PDF 文件内容已加载"
    }},
    {{
      "id": "step_2",
      "name": "转换文件格式",
      "skill_command": "pdftotext input.pdf output.docx",
      "tool": "run_in_terminal",
      "expected_output": "Word 格式文件已生成"
    }}
  ],
  "milestones": [
    {{
      "name": "PDF 已读取",
      "after_step": "step_1",
      "check_type": "tool_output"
    }},
    {{
      "name": "转换已完成",
      "after_step": "step_2",
      "check_type": "file_exists"
    }}
  ]
}}

**直接输出 JSON，不要有其他说明文字。**"""

    def __init__(self, llm_router: LLMRouter, skill_registry: SkillRegistry):
        """初始化结构化规划器
        
        Args:
            llm_router: LLM 路由器实例
            skill_registry: 技能注册表实例
        """
        self.llm_router = llm_router
        self.skill_registry = skill_registry
        # 🔥 NEW: SKILL.md 内容缓存（避免重复读取）
        self._skill_md_cache: dict[str, str] = {}
        logger.info("StructuredPlanner initialized with progressive disclosure")
    
    def _extract_skill_guidance(self, skill_name: str, goal: str) -> str:
        """从 SKILL.md 中提取关键指引（渐进式披露）
        
        Args:
            skill_name: 技能名称
            goal: 用户目标
            
        Returns:
            提取的关键指引文本
        """
        import re
        from pathlib import Path
        
        # 检查缓存
        if skill_name in self._skill_md_cache:
            skill_md_content = self._skill_md_cache[skill_name]
        else:
            # 读取 SKILL.md 文件
            try:
                skill_dir = Path(__file__).parent.parent / 'skills' / skill_name
                skill_md_path = skill_dir / 'SKILL.md'
                
                if not skill_md_path.exists():
                    logger.warning(f"SKILL.md not found for skill: {skill_name}")
                    return ""
                
                skill_md_content = skill_md_path.read_text(encoding='utf-8')
                self._skill_md_cache[skill_name] = skill_md_content
                logger.info(
                    f"Loaded SKILL.md for {skill_name} ({len(skill_md_content)} chars)",
                    extra={"skill": skill_name}
                )
            except Exception as e:
                logger.error(f"Failed to read SKILL.md: {e}")
                return ""
        
        # 🔥 动态渐进式披露策略（基于流程图）：
        # 1. Planner 阶段：提供 Skill 名称和描述
        # 2. Router 阶段：提供输入/输出格式和约束
        # 3. Task 执行：提供信例和调用细节（当需要时）
        # 4. Reflection 阶段：补充限制和提示
        
        guidance_parts = []
        
        # === Phase 1: Planner 阶段 - 技能基本信息 ===
        phase1_guidance = self._extract_planner_guidance(skill_md_content, skill_name, goal)
        if phase1_guidance:
            guidance_parts.append(phase1_guidance)
        
        # === Phase 2: Router 阶段 - 输入输出格式和约束 ===
        phase2_guidance = self._extract_router_guidance(skill_md_content, skill_name, goal)
        if phase2_guidance:
            guidance_parts.append(phase2_guidance)
        
        # === Phase 3: Task 执行阶段 - 信例和调用细节 ===
        phase3_guidance = self._extract_task_execution_guidance(skill_md_content, skill_name, goal)
        if phase3_guidance:
            guidance_parts.append(phase3_guidance)
        
        # === Phase 4: Reflection 阶段 - 限制和提示 ===
        phase4_guidance = self._extract_reflection_guidance(skill_md_content, skill_name, goal)
        if phase4_guidance:
            guidance_parts.append(phase4_guidance)
        
        # 记录日志
        if guidance_parts:
            logger.info(
                "Extracted dynamic skill guidance (progressive disclosure)",
                extra={
                    "skill": skill_name,
                    "guidance_length": len("\n".join(guidance_parts)),
                    "phases_count": len([p for p in [phase1_guidance, phase2_guidance, phase3_guidance, phase4_guidance] if p]),
                }
            )
        
        return "\n".join(guidance_parts) if guidance_parts else ""
    
    def _auto_detect_skill_from_keywords(self, goal_lower: str) -> str | None:
        """通用技能自动发现机制（基于 SKILL.md 中的 auto_trigger_keywords）
        
        Args:
            goal_lower: 用户目标（小写）
            
        Returns:
            匹配的技能名称，如果没有匹配则返回 None
        """
        # 🔥 通用逻辑：遍历所有技能，检查它们的 auto_trigger_keywords
        skills = self.skill_registry.list_all_skills()
        
        for skill in skills:
            # 从技能元数据中获取自动触发关键词
            keywords = getattr(skill, 'keywords', []) or []
            
            # 如果没有定义 keywords，使用技能名称和描述作为备选
            if not keywords:
                keywords = [skill.name.lower()]
            
            # 检查是否有任何关键词匹配
            if any(kw.lower() in goal_lower for kw in keywords):
                logger.debug(
                    f"Skill auto-detected via keywords",
                    extra={
                        "skill": skill.name,
                        "matched_keywords": [kw for kw in keywords if kw.lower() in goal_lower],
                    }
                )
                return skill.name
        
        return None
    
    def _extract_planner_guidance(self, skill_md_content: str, skill_name: str, goal: str) -> str:
        """Phase 1: Planner 阶段 - 提供 Skill 名称和描述
        
        从 SKILL.md 中提取技能的基本信息和功能描述。
        """
        import re
        
        # 尝试提取技能概述部分
        overview_patterns = [
            r'^#\s*(.+?)\n',  # 一级标题
            r'^##\s*Overview[\s\S]*?(?=^##|\Z)',  # Overview 章节
            r'^##\s*简介[\s\S]*?(?=^##|\Z)',  # 简介章节
            r'^##\s*Description[\s\S]*?(?=^##|\Z)',  # 描述章节
        ]
        
        for pattern in overview_patterns:
            match = re.search(pattern, skill_md_content, re.MULTILINE | re.IGNORECASE)
            if match:
                content = match.group(0).strip()
                # 限制长度在 300 字符以内
                if len(content) > 300:
                    content = content[:300] + "..."
                return f"\n\n## 📋 技能概述\n{content}"
        
        # 如果没有找到概述，返回简单的技能名称
        return f"\n\n## 📋 技能：{skill_name}"
    
    def _extract_router_guidance(self, skill_md_content: str, skill_name: str, goal: str) -> str:
        """Phase 2: Router 阶段 - 提供输入/输出格式和约束
        
        从 SKILL.md 中提取工具的输入输出格式、允许的工具列表等约束信息。
        """
        import re
        
        guidance_parts = []
        
        # 查找 Usage/Commands/CLI 相关章节
        usage_patterns = [
            (r'^##\s*Usage[\s\S]*?(?=^##|\Z)', "使用方法"),
            (r'^##\s*Commands[\s\S]*?(?=^##|\Z)', "命令"),
            (r'^##\s*CLI[\s\S]*?(?=^##|\Z)', "命令行接口"),
            (r'^##\s*How to use[\s\S]*?(?=^##|\Z)', "如何使用"),
        ]
        
        for pattern, title in usage_patterns:
            match = re.search(pattern, skill_md_content, re.MULTILINE | re.IGNORECASE)
            if match:
                content = match.group(0).strip()
                # 提取关键命令格式（前 500 字符）
                if len(content) > 500:
                    content = content[:500] + "..."
                guidance_parts.append(f"\n\n## 🔧 {title}\n{content}")
                break
        
        # 如果有多个部分，只取第一个匹配的
        if guidance_parts:
            return "\n".join(guidance_parts)
        
        return ""
    
    def _extract_task_execution_guidance(self, skill_md_content: str, skill_name: str, goal: str) -> str:
        """Phase 3: Task 执行阶段 - 提供信例和调用细节
        
        从 SKILL.md 中提取具体的示例、最佳实践和调用细节。
        """
        import re
        
        guidance_parts = []
        
        # 查找 Examples/Examples/Best Practices 相关章节
        example_patterns = [
            (r'^##\s*Examples[\s\S]*?(?=^##|\Z)', "示例"),
            (r'^###\s*Example[\s\S]*?(?=^###|\Z)', "示例"),
            (r'^##\s*Best Practices[\s\S]*?(?=^##|\Z)', "最佳实践"),
        ]
        
        for pattern, title in example_patterns:
            match = re.search(pattern, skill_md_content, re.MULTILINE | re.IGNORECASE)
            if match:
                content = match.group(0).strip()
                # 限制示例长度在 400 字符
                if len(content) > 400:
                    content = content[:400] + "..."
                guidance_parts.append(f"\n\n## 📖 {title}\n{content}")
                break
        
        if guidance_parts:
            return "\n".join(guidance_parts)
        
        return ""
    
    def _extract_reflection_guidance(self, skill_md_content: str, skill_name: str, goal: str) -> str:
        """Phase 4: Reflection 阶段 - 补充限制和提示
        
        从 SKILL.md 中提取注意事项、限制条件、常见错误等反思信息。
        """
        import re
        
        guidance_parts = []
        
        # 查找 Warnings/Caveats/Limitations/Tips 相关章节
        warning_patterns = [
            (r'^##\s*Warnings[\s\S]*?(?=^##|\Z)', "警告"),
            (r'^##\s*Caveats[\s\S]*?(?=^##|\Z)', "注意事项"),
            (r'^##\s*Limitations[\s\S]*?(?=^##|\Z)', "限制"),
            (r'^##\s*Troubleshooting[\s\S]*?(?=^##|\Z)', "故障排除"),
            (r'^##\s*Tips[\s\S]*?(?=^##|\Z)', "提示"),
        ]
        
        for pattern, title in warning_patterns:
            match = re.search(pattern, skill_md_content, re.MULTILINE | re.IGNORECASE)
            if match:
                content = match.group(0).strip()
                # 限制警告信息长度在 300 字符
                if len(content) > 300:
                    content = content[:300] + "..."
                guidance_parts.append(f"\n\n## ⚠️ {title}\n{content}")
                break
        
        if guidance_parts:
            return "\n".join(guidance_parts)
        
        return ""
    
    def _detect_task_type(self, goal: str) -> tuple[str, dict]:
        """检测任务类型并返回对应的工具约束
        
        Args:
            goal: 用户目标/任务描述
            
        Returns:
            tuple[str, dict]: (主任务类型名称，工具约束字典)
        """
        goal_lower = goal.lower()
        
        # 🔥 NEW: 支持多任务类型合并
        matched_types = []
        
        # 遍历任务类型规则，找到所有匹配的类型
        for task_type, rules in self.TASK_TYPE_RULES.items():
            keywords = rules["keywords"]
            match_count = sum(1 for kw in keywords if kw in goal_lower)
            
            # 如果匹配到至少一个关键词，记录该类型
            if match_count > 0:
                allowed = rules.get("allowed", rules.get("default_allowed", ["web_search", "write_file", "run_in_terminal"]))
                forbidden = rules.get("forbidden", [])
                
                matched_types.append({
                    "type": task_type,
                    "allowed": set(allowed),
                    "forbidden": set(forbidden),
                    "priority": len(rules.get("required_skills", [])),  # 有 required_skills 的优先级更高
                })
        
        # 如果没有匹配到任何类型，使用默认值
        if not matched_types:
            logger.info("No specific task type detected, using default constraints")
            return "general", {
                "allowed": ["web_search", "fetch_web_content", "read_file", "write_file", "memory"],
                "forbidden": [],
            }
        
        # 🔥 NEW: 合并多个任务类型的工具约束
        # 策略：
        # 1. 取所有 allowed 的并集
        # 2. 保留明确的 forbidden（即使出现在其他 allowed 中也要保留，这是硬约束）
        # 3. 只有当某个工具在所有类型中都是 forbidden 时，才加入最终 forbidden
        final_allowed = set()
        final_forbidden = set()
        
        # 优先处理有高优先级的类型（如 pdf_creation, pptx_creation）
        matched_types.sort(key=lambda x: x["priority"], reverse=True)
        
        # 收集所有类型的 forbidden 信息
        all_forbidden_tools = {}  # tool -> count (被多少个类型禁止)
        
        for match in matched_types:
            final_allowed.update(match["allowed"])
            # 统计每个工具被禁止的次数
            for tool in match["forbidden"]:
                all_forbidden_tools[tool] = all_forbidden_tools.get(tool, 0) + 1
        
        # 🔥 FIX: 只有当工具在所有匹配的类型中都被禁止时，才加入最终 forbidden
        # 这样可以保留明确的硬约束
        num_matched_types = len(matched_types)
        for tool, count in all_forbidden_tools.items():
            # 如果该工具在所有类型中都被禁止，或者在高优先级类型中被禁止
            if count == num_matched_types or (
                num_matched_types > 1 and 
                all_forbidden_tools.get(tool, 0) >= num_matched_types - 1
            ):
                final_forbidden.add(tool)
        
        # 移除冲突：如果一个工具同时在 allowed 和 forbidden 中，优先 allowed
        final_allowed = final_allowed - final_forbidden
        
        primary_type = matched_types[0]["type"]
        
        logger.info(
            "Task type detected with merged constraints",
            extra={
                "primary_type": primary_type,
                "matched_types": [mt["type"] for mt in matched_types],
                "allowed_tools": list(final_allowed),
                "forbidden_tools": list(final_forbidden),
            }
        )
        
        return primary_type, {
            "allowed": list(final_allowed),
            "forbidden": list(final_forbidden),
        }
    
    async def generate(self, goal: str, skill_name: str | None = None, workspace_path: str | None = None) -> StructuredPlan:
        """生成结构化计划
        
        Args:
            goal: 用户目标/任务描述
            skill_name: 指定的技能名称（如果有）
            workspace_path: 工作目录路径（用于文件路径提示）
            
        Returns:
            StructuredPlan: 结构化计划对象
        """
        logger.info(
            "Structured plan generation started",
            extra={
                "goal_length": len(goal),
                "skill_name": skill_name,
            }
        )
        
        # 🔥 NEW: 检测 PDF 相关关键词，强制绑定 PDF skill
        goal_lower = goal.lower()
        
        # 🔥 CRITICAL FIX: 移除所有硬编码，使用通用的技能自动发现机制
        # 不再针对特定技能写死逻辑，而是通过 SkillMetadata 中的 auto_trigger_keywords
        if not skill_name:
            skill_name = self._auto_detect_skill_from_keywords(goal_lower)
            if skill_name:
                logger.info(
                    "Auto-detected skill from keywords",
                    extra={
                        "goal_preview": goal[:50],
                        "detected_skill": skill_name,
                    }
                )
        
        # 获取技能信息（如果有）
        skill_info = ""
        tool_constraints = None
        
        if skill_name:
            skill = self.skill_registry.get_skill_metadata(skill_name)
            if skill:
                # 🔥 通用处理：从技能元数据中获取所有信息
                skill_info = f"- 技能名称：{skill.name}\n- 技能描述：{skill.description}\n- 允许的工具：{skill.allowed_tools or '无限制'}"
                
                # P1-2 NEW: 强制使用技能的 allowed_tools，而不是让 LLM 决定
                if skill.allowed_tools:
                    # 🔥 通用逻辑：直接使用技能的 allowed_tools，不再特殊处理某个技能
                    allowed_tools = list(skill.allowed_tools)
                    
                    tool_constraints = ToolConstraints(
                        allowed=allowed_tools,
                        forbidden=[t for t in ["web_search", "pdf", "pptx"] if t not in allowed_tools],
                        source="skill",  # ✅ 标记为来自技能
                        priority=5,  # ✅ Skill 约束中等优先级
                    )
                    logger.info(
                        "Applied skill-based tool constraints (generic logic)",
                        extra={
                            "skill": skill.name,
                            "allowed": allowed_tools,
                            "forbidden": tool_constraints.forbidden,
                        }
                    )
        else:
            skill_info = "无特定技能绑定"
            
            # P3-1 NEW: 如果没有指定技能，根据任务类型自动生成工具约束
            task_type, type_constraints = self._detect_task_type(goal)
            if tool_constraints is None and type_constraints:
                tool_constraints = ToolConstraints(
                    allowed=type_constraints["allowed"],
                    forbidden=type_constraints["forbidden"],
                    source="task_type",  # ✅ 标记为来自任务类型检测
                    priority=1,  # ✅ Task Type 约束低优先级
                )
                logger.info(
                    "Task-type-based tool constraints generated",
                    extra={
                        "task_type": task_type,
                        "allowed": type_constraints["allowed"],
                        "forbidden": type_constraints["forbidden"],
                    }
                )
        
        # 🔥 NEW: 收集技能脚本路径（如果有）
        skill_script_paths = []
        if skill_name:
            # 从技能元数据中获取脚本路径
            try:
                from pathlib import Path
                skill_dir = Path(__file__).parent.parent / 'skills' / skill_name / 'scripts'
                if skill_dir.exists():
                    script_files = list(skill_dir.glob('*.py')) + list(skill_dir.glob('*.js'))
                    skill_script_paths = [str(f) for f in script_files]
                    logger.info(
                        "Skill scripts found",
                        extra={
                            "skill": skill_name,
                            "script_count": len(script_files),
                            "scripts": skill_script_paths,
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to get skill scripts: {e}")
        else:
            # 从任务类型规则中获取脚本路径
            task_type, _ = self._detect_task_type(goal)
            if task_type in self.TASK_TYPE_RULES:
                skill_script_paths = self.TASK_TYPE_RULES[task_type].get('skill_scripts', [])
        
        # 🔥🔥🔥 CRITICAL: 渐进式披露 - 从 SKILL.md 中提取关键指引
        skill_md_guidance = ""
        if skill_name:
            skill_md_guidance = self._extract_skill_guidance(skill_name, goal)
            if skill_md_guidance:
                logger.info(
                    "Extracted guidance from SKILL.md (progressive disclosure)",
                    extra={
                        "skill": skill_name,
                        "guidance_length": len(skill_md_guidance),
                    }
                )
        
        # 构建 prompt
        tools_list = list(set(tool_constraints.allowed)) if tool_constraints and tool_constraints.allowed else ["run_in_terminal", "read_file", "write_file", "web_search"]
        
        # 🔥 NEW: 添加技能脚本路径到 skill_info
        if skill_script_paths:
            skill_scripts_str = "\n- 可用脚本：" + "\n  - ".join(skill_script_paths)
            skill_info += f"\n\n## 🔧 技能脚本路径{skill_scripts_str}"
        
        # 🔥🔥🔥 CRITICAL: 添加从 SKILL.md 中提取的指引（渐进式披露）
        if skill_md_guidance:
            skill_info += f"\n\n{skill_md_guidance}"
            logger.info(
                "Added progressive disclosure guidance from SKILL.md",
                extra={
                    "skill": skill_name,
                    "guidance_chars": len(skill_md_guidance),
                }
            )
        
        # 🔥 NEW: 添加工作目录和文件路径指引
        if workspace_path:
            workspace_guidance = f"\n\n## 📁 工作目录配置\n"
            workspace_guidance += f"- **你的工作目录是：** `{workspace_path}`\n"
            workspace_guidance += f"- **所有文件必须保存到工作目录下！**\n"
            workspace_guidance += f"- ✅ 正确示例：`{workspace_path}/pdfs/report.pdf`\n"
            workspace_guidance += f"- ❌ 错误示例：`/tmp/report.pdf` 或其他目录\n"
            
            # 🔥🔥🔥 关键：明确区分脚本路径和输出文件路径
            workspace_guidance += f"\n\n## 🔧 技能脚本路径使用说明\n"
            workspace_guidance += f"- **脚本路径**: 使用 **相对路径** 或 **直接写脚本名**（系统会自动查找）\n"
            workspace_guidance += f"  - ✅ 正确：`python create_pdf_from_md.py ...`（推荐）\n"
            workspace_guidance += f"  - ✅ 也可：`python skills/pdf/scripts/create_pdf_from_md.py ...`\n"
            workspace_guidance += f"  - ❌ 错误：`python /workspace/.../create_pdf_from_md.py`（不要使用绝对路径）\n"
            workspace_guidance += f"- **输出文件路径**: 必须使用完整的 workspace_path\n"
            workspace_guidance += f"  - ✅ 正确：`{workspace_path}/pdfs/output.pdf`\n"
            workspace_guidance += f"  - ❌ 错误：`/tmp/output.pdf` 或 `./output.pdf`\n"
            
            skill_info += workspace_guidance
        
        prompt = self.SYSTEM_PROMPT.format(
            skill_info=skill_info,
            tools=", ".join(tools_list)
        )
        
        # 添加用户目标
        user_prompt = f"用户指令：{goal}\n\n请生成结构化计划（JSON 格式）："
        
        try:
            # 调用 LLM 生成计划
            response = await self.llm_router.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False,
            )
            
            # 解析 LLM 响应为 StructuredPlan
            plan_dict = self._parse_llm_response(response.content)
            structured_plan = self._dict_to_structured_plan(plan_dict, skill_name)
            
            # 如果 LLM 没有返回 tool_constraints，使用我们生成的
            if structured_plan.tool_constraints is None and tool_constraints:
                structured_plan.tool_constraints = tool_constraints
                logger.info(
                    "Applied default tool constraints from task type",
                    extra={"constraints": tool_constraints}
                )
            
            logger.info(
                "Structured plan generation completed",
                extra={
                    "steps_count": len(structured_plan.steps),
                    "milestones_count": len(structured_plan.milestones),
                    "skill_binding": structured_plan.skill_binding,
                    "tool_constraints": structured_plan.tool_constraints,
                }
            )
            
            return structured_plan
            
        except Exception as e:
            logger.warning(
                "Structured plan generation failed, using fallback",
                extra={"error": str(e)}
            )
            # 降级：生成简单的默认计划
            return self._generate_fallback_plan(goal, skill_name, tool_constraints)
    
    def _parse_llm_response(self, content: str) -> dict:
        """解析 LLM 的 JSON 响应"""
        import json
        
        # 清理 markdown 代码块
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON: {e}")
            # 尝试提取 JSON 部分
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise
    
    def _dict_to_structured_plan(self, data: dict, skill_name: str | None) -> StructuredPlan:
        """将字典转换为 StructuredPlan 对象"""
        # 转换 steps
        steps = []
        for step_data in data.get("steps", []):
            validation = None
            if step_data.get("validation"):
                v = step_data["validation"]
                validation = StepValidation(
                    validation_type=v.get("type", "tool_output"),
                    pattern=v.get("pattern"),
                    text=v.get("text"),
                    schema=v.get("schema"),
                )
            
            step = PlanStep(
                id=step_data.get("id", f"step_{len(steps)+1}"),
                name=step_data.get("name", ""),
                description=step_data.get("description"),  # 🔥 ADD: Parse description
                skill_command=step_data.get("skill_command"),
                tool=step_data.get("tool"),
                expected_output=step_data.get("expected_output"),
                validation=validation,
            )
            steps.append(step)
        
        # 转换 milestones
        milestones = []
        for m_data in data.get("milestones", []):
            milestone = Milestone(
                name=m_data.get("name", ""),
                after_step=m_data.get("after_step", ""),
                check_type=m_data.get("check_type", "tool_output"),
                value=m_data.get("value"),
            )
            milestones.append(milestone)
        
        # 转换 tool_constraints
        tc_data = data.get("tool_constraints", {})
        tool_constraints = ToolConstraints(
            allowed=tc_data.get("allowed", []),
            forbidden=tc_data.get("forbidden", []),
            source=tc_data.get("source", "plan"),  # ✅ 默认为 plan，表示来自 Plan 生成
            priority=tc_data.get("priority", 10),  # ✅ Plan 约束默认高优先级
        ) if tc_data else None
        
        return StructuredPlan(
            version=data.get("version", "2.0"),
            goal=data.get("goal", ""),
            skill_binding=data.get("skill_binding") or skill_name,
            tool_constraints=tool_constraints,
            steps=steps,
            milestones=milestones,
            metadata=data.get("metadata", {}),
        )
    
    def _generate_fallback_plan(self, goal: str, skill_name: str | None, tool_constraints: ToolConstraints | None) -> StructuredPlan:
        """生成降级计划（当 LLM 失败时）"""
        steps = [
            PlanStep(id="step_1", name="分析任务需求", tool="read_file", expected_output="理解用户需求"),
            PlanStep(id="step_2", name="收集必要信息", tool="web_search", expected_output="相关信息列表"),
            PlanStep(id="step_3", name="执行核心操作", tool="run_in_terminal", expected_output="操作完成"),
            PlanStep(id="step_4", name="验证结果", tool="read_file", expected_output="验证通过"),
        ]
        
        return StructuredPlan(
            version="2.0",
            goal=goal,
            skill_binding=skill_name,
            tool_constraints=tool_constraints,
            steps=steps,
            milestones=[],
        )


# 全局实例
_structured_planner: StructuredPlanner | None = None


def get_structured_planner(llm_router: LLMRouter | None = None, skill_registry: SkillRegistry | None = None) -> StructuredPlanner:
    """获取全局 StructuredPlanner 实例
    
    Args:
        llm_router: LLM 路由器实例（首次调用时需要）
        skill_registry: 技能注册表实例（首次调用时需要）
    """
    global _structured_planner
    if _structured_planner is None:
        if llm_router is None:
            from ..services.llm.router import get_llm_router
            llm_router = get_llm_router()
        if skill_registry is None:
            from ..services.skill_registry import get_skill_registry
            from pathlib import Path
            skill_registry = get_skill_registry(Path.cwd())
        _structured_planner = StructuredPlanner(llm_router, skill_registry)
    return _structured_planner
