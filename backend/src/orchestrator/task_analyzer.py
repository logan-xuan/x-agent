"""Task complexity analyzer for X-Agent.

Analyzes user messages to determine if a plan should be injected into ReAct.
Uses pure rule matching (no LLM calls) for fast decision making.
"""

from dataclasses import dataclass, field
from typing import Literal

from ..config.models import SkillsConfig


@dataclass
class TaskAnalysis:
    """任务分析结果
    
    Attributes:
        complexity: 任务复杂度 (simple/complex)
        confidence: 复杂度置信度 (0.0-1.0)
        indicators: 复杂度指标列表
        needs_plan: 是否需要注入计划
        matched_skills: 匹配到的技能列表（基于关键词）
        recommended_skill: 推荐使用的技能（如果有高匹配度）
    """
    complexity: Literal["simple", "complex"]
    confidence: float
    indicators: list[str] = field(default_factory=list)
    needs_plan: bool = False
    matched_skills: list[dict] = field(default_factory=list)
    recommended_skill: dict | None = None


class TaskAnalyzer:
    """分析任务复杂度，决定是否需要计划引导
    
    使用纯规则匹配（无 LLM 调用），快速判断任务是否需要注入计划。
    
    复杂度判断依据：
    1. 多步骤关键词：先、然后、接着、最后、步骤、流程等
    2. 条件判断关键词：如果、当、判断、检查、确认等
    3. 迭代关键词：所有、每个、批量、遍历、循环等
    4. 不确定性关键词：可能、或者、不确定、试试等
    5. 范围关键词：重构、迁移、搭建、实现、设计等
    6. 消息长度：超过 200 字符
    7. 句子数量：超过 3 个句子
    8. 技能关键词：匹配注册的技能关键词
    """
    
    # 复杂度指标（规则快速匹配）
    COMPLEXITY_INDICATORS = {
        "multi_step": ["先", "然后", "接着", "最后", "步骤", "流程", "第一步", "第二步", "第三步"],
        "conditional": ["如果", "当", "判断", "检查", "确认", "验证", "否则"],
        "iteration": ["所有", "每个", "批量", "遍历", "循环", "全部", "逐个"],
        "uncertainty": ["可能", "或者", "不确定", "试试", "尝试", "也许"],
        "scope": ["重构", "迁移", "搭建", "实现", "设计", "构建", "开发"],
    }
    
    # 复杂度阈值
    COMPLEXITY_THRESHOLD = 0.6
    
    def __init__(self, skills_config: SkillsConfig | None = None) -> None:
        """初始化任务分析器
        
        Args:
            skills_config: 技能元数据配置（可选）
        """
        self.skills_config = skills_config
    
    @staticmethod
    def parse_skill_command(user_message: str) -> tuple[str, str]:
        """解析 /command 格式的命令，提取技能名称和参数
        
        Args:
            user_message: 用户消息
            
        Returns:
            (skill_name, arguments) 元组
            - 如果不是 /command 格式，返回 ("", user_message)
            - 如果是 /command 格式，返回 (技能名，参数)
            
        Examples:
            >>> parse_skill_command("/pptx create test.pptx")
            ('pptx', 'create test.pptx')
            
            >>> parse_skill_command("/pdf")
            ('pdf', '')
            
            >>> parse_skill_command("Hello")
            ('', 'Hello')
        """
        if not user_message.startswith('/'):
            return "", user_message
        
        # 移除开头的 / 并分割
        parts = user_message[1:].split(' ', 1)
        skill_name = parts[0].strip()
        arguments = parts[1].strip() if len(parts) > 1 else ""
        
        return skill_name, arguments
    
    def analyze(self, user_message: str) -> TaskAnalysis:
        """分析任务复杂度
        
        Args:
            user_message: 用户消息内容
            
        Returns:
            TaskAnalysis: 分析结果
        """
        if not user_message:
            return TaskAnalysis(
                complexity="simple",
                confidence=0.0,
                indicators=[],
                needs_plan=False,
                matched_skills=[],
                recommended_skill=None,
            )
        
        # ===== 关键修复：检测 /command 格式的技能调用 =====
        # 当用户直接使用 /command 调用技能时，强制触发 Plan Mode
        skill_name, arguments = self.parse_skill_command(user_message)
        if skill_name:
            # 用户明确调用了技能命令，这通常是复杂任务
            # Fix: matched_skills must be list of dicts, not list of strings
            return TaskAnalysis(
                complexity="complex",
                confidence=0.8,
                indicators=[f"skill_command_detected: {skill_name}"],
                needs_plan=True,
                matched_skills=[{"name": skill_name}],  # Fix: Wrap in dict
                recommended_skill={"name": skill_name, "arguments": arguments},
            )
        
        score = 0.0
        indicators = []
        
        # 关键词匹配
        for category, keywords in self.COMPLEXITY_INDICATORS.items():
            matches = [kw for kw in keywords if kw in user_message]
            if matches:
                score += len(matches) * 0.2
                indicators.append(f"{category}: {matches}")
        
        # 长度辅助判断
        if len(user_message) > 200:
            score += 0.3
        
        # 句子数量辅助判断
        sentence_count = user_message.count("。") + user_message.count("；") + user_message.count("？")
        if sentence_count > 3:
            score += 0.2
        
        # 技能关键词匹配（新增功能）
        matched_skills = []
        recommended_skill = None
        
        if self.skills_config and self.skills_config.registered:
            matched = self.skills_config.match_skills_by_keywords(user_message)
            
            for skill in matched:
                skill_info = {
                    "name": skill.name,
                    "description": skill.description,
                    "priority": skill.priority,
                    "auto_trigger": skill.auto_trigger,
                }
                matched_skills.append(skill_info)
                
                # 如果是最优先的自动触发技能，设为推荐技能
                if skill.auto_trigger and recommended_skill is None:
                    recommended_skill = skill_info
                    # 提高复杂度评分（有明确技能匹配的任务更可能需要计划）
                    score += 0.3
                    indicators.append(f"skill_matched: {skill.name}")
        
        # 限制置信度在 0-1 范围
        confidence = min(score, 1.0)
        
        # 判断是否需要计划
        needs_plan = confidence > self.COMPLEXITY_THRESHOLD
        
        # 如果匹配到高优先级技能，降低计划阈值（技能相关任务通常更复杂）
        if recommended_skill and recommended_skill.get("priority", 999) <= 3:
            needs_plan = needs_plan or confidence > 0.4
        
        return TaskAnalysis(
            complexity="complex" if needs_plan else "simple",
            confidence=confidence,
            indicators=indicators,
            needs_plan=needs_plan,
            matched_skills=matched_skills,
            recommended_skill=recommended_skill,
        )


# 全局实例
_task_analyzer: TaskAnalyzer | None = None


def get_task_analyzer() -> TaskAnalyzer:
    """获取全局 TaskAnalyzer 实例"""
    global _task_analyzer
    if _task_analyzer is None:
        _task_analyzer = TaskAnalyzer()
    return _task_analyzer
