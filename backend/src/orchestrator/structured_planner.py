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
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StructuredPlanner:
    """生成结构化计划 v2.0
    
    关键特性：
    - 技能绑定：将计划与具体技能关联
    - 工具约束：白名单/黑名单机制
    - 步骤验证：每个步骤都有验证规则
    - 里程碑检查：关键节点自动验证
    """
    
    SYSTEM_PROMPT = """你是一个结构化任务规划专家。分析用户的目标，生成结构化的执行计划。

## 可用技能信息
{skill_info}

## 可用工具列表
{tools}

## 输出要求
1. 如果用户使用了 /command 格式（如 /pdf），必须：
   - 将该技能名称填入 skill_binding 字段
   - 从技能的 allowed_tools 中提取工具白名单
   - 生成对应的 skill_command
   
2. 每个步骤必须包含：
   - id: 唯一标识（如 step_1, step_2）
   - name: 简洁的中文描述
   - tool: 使用的工具名称
   - expected_output: 预期输出描述

3. 如果可能，为关键步骤添加：
   - skill_command: 具体的 CLI 命令
   - validation: 验证规则

4. 为关键节点定义 milestones

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
    
    async def generate(self, goal: str, skill_name: str | None = None) -> StructuredPlan:
        """生成结构化计划
        
        Args:
            goal: 用户目标/任务描述
            skill_name: 指定的技能名称（如果有）
            
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
        
        # 获取技能信息（如果有）
        skill_info = ""
        tool_constraints = None
        
        if skill_name:
            skill = self.skill_registry.get_skill_metadata(skill_name)
            if skill:
                skill_info = f"- 技能名称：{skill.name}\n- 技能描述：{skill.description}\n- 允许的工具：{skill.allowed_tools or '无限制'}"
                
                # 如果技能指定了 allowed_tools，生成工具约束
                if skill.allowed_tools:
                    tool_constraints = ToolConstraints(
                        allowed=skill.allowed_tools,
                        forbidden=["web_search"] if "run_in_terminal" in skill.allowed_tools else []
                    )
                    logger.info(
                        "Skill-based tool constraints generated",
                        extra={"allowed": skill.allowed_tools}
                    )
        else:
            skill_info = "无特定技能绑定"
        
        # 构建 prompt
        tools_list = list(set(tool_constraints.allowed)) if tool_constraints else ["run_in_terminal", "read_file", "write_file", "web_search"]
        
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
            
            logger.info(
                "Structured plan generation completed",
                extra={
                    "steps_count": len(structured_plan.steps),
                    "milestones_count": len(structured_plan.milestones),
                    "skill_binding": structured_plan.skill_binding,
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
