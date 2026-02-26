"""Light planner for X-Agent.

Generates text-based execution plans (not structured DAG) to inject into ReAct prompt.
The plan serves as guidance, allowing LLM to adjust dynamically.
"""

from ..services.llm.router import LLMRouter
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LightPlanner:
    """生成文本计划（非结构化），注入 ReAct Prompt
    
    关键设计：
    - 文本输出：不使用 JSON，降低解析复杂度
    - 工具提示：仅作建议，LLM 可自主决定
    - 动态调整：计划是"软引导"，LLM 可灵活调整
    """
    
    PLAN_PROMPT = """你是一位极简任务规划专家。

【核心原则】
1. YAGNI (You Aren't Gonna Need It): 
   - 每个 step 必须直接贡献于 goal
   - 禁止纯验证步骤（验证应内建到 step 中）
   - If not called, remove it

2. 最短路径:
   - 用最少步骤完成 goal
   - 相似操作必须合并（如连续 write_file）
   - 目标：最小必要步骤数

3. 工具语义清晰:
   - 使用真实工具名：web_search, write_file, run_in_terminal
   - 禁止虚构工具：pdf_create 应描述为 "使用 write_file 创建 Python 脚本生成 PDF"

【输出格式】
严格返回 JSON 数组，每个 step 包含:
{
  "name": "简洁的动作描述",
  "tool": "真实工具名",
  "description": "详细说明，包括如何验证成功"
}

【示例对比】
❌ 错误 Plan (5 步，包含过度验证):
1. web_search: 搜索信息
2. write_file: 整理资料
3. write_file: 撰写文章
4. pdf_create: 生成 PDF
5. list_dir: 验证 PDF 是否生成 ← 过度验证

✅ 正确 Plan (3 步，最短路径):
1. web_search: 搜索"2026 AI 发展趋势"，收集关键信息
2. write_file: 整合搜索结果，撰写研究报告 (MD 格式)
3. write_file + run_in_terminal: 创建 Python 脚本使用 reportlab 生成 PDF，脚本执行成功即验证通过

目标：{goal}
可用工具：{tools}

直接输出计划，不要有其他说明文字。"""

    def __init__(self, llm_router: LLMRouter):
        """初始化轻量计划生成器
        
        Args:
            llm_router: LLM 路由器实例
        """
        self.llm_router = llm_router
    
    async def generate(self, goal: str, tools: list[str]) -> str:
        """生成文本计划
        
        Args:
            goal: 用户目标/任务描述
            tools: 可用工具列表
            
        Returns:
            str: 文本格式的执行计划
        """
        logger.info(
            "Plan generation started",
            extra={
                "goal_length": len(goal),
                "tools_count": len(tools),
            }
        )
        
        # 构建 prompt
        prompt = self.PLAN_PROMPT.format(
            goal=goal,
            tools=", ".join(tools) if tools else "无",
        )
        
        try:
            # 调用 LLM 生成计划
            response = await self.llm_router.chat(
                messages=[{"role": "user", "content": prompt}],
                stream=False,
            )
            
            plan_text = response.content if hasattr(response, 'content') else str(response)
            
            # 清理输出（移除可能的 markdown 标记）
            plan_text = self._clean_plan_output(plan_text)
            
            logger.info(
                "Plan generation completed",
                extra={
                    "plan_length": len(plan_text),
                    "steps_count": plan_text.count("\n") + 1,
                    "plan_preview": plan_text[:100],
                }
            )
            
            return plan_text
            
        except Exception as e:
            logger.warning(
                "Plan generation failed, using fallback",
                extra={
                    "error": str(e),
                    "fallback_used": True,
                }
            )
            # 降级：返回简单的默认计划
            return self._generate_fallback_plan(goal, tools)
    
    def _clean_plan_output(self, plan_text: str) -> str:
        """清理计划输出
        
        移除可能的 markdown 代码块标记等
        """
        # 移除可能的 markdown 代码块
        if plan_text.startswith("```"):
            lines = plan_text.split("\n")
            # 移除第一行和最后一行的 ``` 标记
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            plan_text = "\n".join(lines)
        
        return plan_text.strip()
    
    def _generate_fallback_plan(self, goal: str, tools: list[str]) -> str:
        """生成降级计划
        
        当 LLM 调用失败时，生成一个简单的默认计划
        """
        # 基于目标长度生成简单步骤
        fallback_steps = [
            "1. 分析任务需求",
            "2. 收集必要信息",
            "3. 执行核心操作",
            "4. 验证结果",
        ]
        
        # 如果有工具，添加工具提示
        if tools:
            fallback_steps[1] = f"1. 分析任务需求 (工具: {tools[0] if tools else 'read_file'})"
            if len(tools) > 1:
                fallback_steps[2] = f"2. 执行操作 (工具: {tools[1]})"
        
        return "\n".join(fallback_steps)


# 全局实例
_light_planner: LightPlanner | None = None


def get_light_planner(llm_router: LLMRouter | None = None) -> LightPlanner:
    """获取全局 LightPlanner 实例
    
    Args:
        llm_router: LLM 路由器实例（首次调用时需要）
    """
    global _light_planner
    if _light_planner is None:
        if llm_router is None:
            from ..services.llm.router import get_llm_router
            llm_router = get_llm_router()
        _light_planner = LightPlanner(llm_router)
    return _light_planner
