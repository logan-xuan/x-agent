"""Light planner for X-Agent.

Generates text-based execution plans (not structured DAG) to inject into ReAct prompt.
The plan serves as guidance, allowing LLM to adjust dynamically.
"""

from ..services.llm.router import LLMRouter
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LightPlanner:
    """生成文本计划（非结构化），注入 ReAct Prompt
    
    关键设计：
    - 文本输出：不使用 JSON，降低解析复杂度
    - 工具提示：仅作建议，LLM 可自主决定
    - 动态调整：计划是"软引导"，LLM 可灵活调整
    """
    
    PLAN_PROMPT = """你是一个任务规划助手。分析用户的目标，生成简洁的执行计划。

目标：{goal}
可用工具：{tools}

要求：
1. 输出 3-7 个步骤，每步一行
2. 使用简洁的中文描述
3. 标注每步建议使用的工具（如果有）
4. 不要输出 JSON，直接输出文本列表

输出格式：
1. [步骤描述] (工具: xxx)
2. [步骤描述] (工具: xxx)
...

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
