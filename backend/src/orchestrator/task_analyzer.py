"""Task complexity analyzer for X-Agent.

Analyzes user messages to determine if a plan should be injected into ReAct.
Uses hybrid approach: rule-based + LLM-assisted judgment for accuracy.
"""

from dataclasses import dataclass, field
from typing import Literal

from ..config.models import SkillsConfig
from ..services.skill_router import get_skill_router  # NEW: Import semantic router
from ..utils.logger import get_logger

logger = get_logger(__name__)


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
        analysis_method: 分析方法 (rule_based/llm_assisted/hybrid)
    """
    complexity: Literal["simple", "complex"]
    confidence: float
    indicators: list[str] = field(default_factory=list)
    needs_plan: bool = False
    matched_skills: list[dict] = field(default_factory=list)
    recommended_skill: dict | None = None
    analysis_method: str = "rule_based"


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
        # NEW: Action verbs indicating complex tasks
        "action_verbs": ["研究", "分析", "调查", "探索", "评估", "总结", "归纳", "整理", "收集"],
        # NEW: Target objects indicating output generation
        "target_objects": ["文章", "报告", "论文", "文档", "PDF", "PPT", "演示", "表格", "数据"],
        # NEW: Research and creation keywords
        "research_creation": ["深度", "全面", "系统", "详细", "完整", "趋势", "发展", "展望"],
    }
    
    # 复杂度阈值
    COMPLEXITY_THRESHOLD = 0.6
    
    def __init__(self, skills_config: SkillsConfig | None = None, skill_router=None, llm_skill_matcher=None) -> None:
        """初始化任务分析器
        
        Args:
            skills_config: 技能元数据配置（可选）
            skill_router: 语义路由器实例（可选，基于向量相似度）
            llm_skill_matcher: LLM 技能匹配器实例（可选，推荐使用）
        """
        self.skills_config = skills_config
        self.skill_router = skill_router  # 基于向量的语义路由（保留向后兼容）
        
        # P3-0 NEW: Initialize LLM-based skill matcher (preferred method)
        if llm_skill_matcher:
            # Use provided LLM matcher instance
            self.llm_skill_matcher = llm_skill_matcher
            logger.debug("LLM skill matcher initialized with provided instance")
        else:
            # Try to initialize default matcher
            try:
                from .llm_skill_matcher import get_llm_skill_matcher
                self.llm_skill_matcher = get_llm_skill_matcher()
                logger.debug("LLM skill matcher initialized with default instance")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM skill matcher: {e}")
                self.llm_skill_matcher = None
    
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
    
    async def analyze_with_llm(self, user_message: str) -> TaskAnalysis | None:
        """使用 LLM 辅助判断任务复杂度（可选）
        
        Args:
            user_message: 用户消息
            
        Returns:
            TaskAnalysis: LLM 分析结果，如果 LLM 判断失败则返回 None
        """
        try:
            # 🔥 FIX 1: Handle simple greetings without LLM call
            simple_greetings = ["你好", "您好", "hello", "hi", "早上好", "中午好", "晚上好", "再见", "bye"]
            if any(greeting in user_message.lower() for greeting in simple_greetings):
                logger.info("Simple greeting detected, no need for complex analysis")
                return TaskAnalysis(
                    complexity="simple",
                    confidence=0.95,
                    indicators=["simple_greeting"],
                    needs_plan=False,
                    matched_skills=[],
                    recommended_skill=None,
                    analysis_method="rule_based",
                )
            
            # 🔥 FIX 2: Use absolute import instead of relative import
            from src.services.llm.router import get_llm_router
            llm_router = get_llm_router()
            
            # 构建 prompt
            system_prompt = """你是一个任务规划专家。你的任务是判断用户请求是否需要结构化计划（Plan Mode）。

判断标准：
- **需要 Plan**：多步骤任务、研究分析、内容创作、数据处理、使用特定技能（如 PDF/PPT 生成）
- **不需要 Plan**：简单问答、工具确认、状态查询、单步操作

请只返回 JSON 格式：
```json
{
  "needs_plan": true/false,
  "complexity": "simple"/"complex",
  "confidence": 0.0-1.0,
  "reason": "简短说明理由"
}
```"""
            
            user_prompt = f"用户请求：{user_message}\n\n请判断是否需要结构化计划："
            
            # 调用 LLM
            response = await llm_router.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False,
            )
            
            # 解析响应
            import json
            content = response.content.strip()
            
            # 尝试提取 JSON
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '{' in content and '}' in content:
                start = content.find('{')
                end = content.rfind('}') + 1
                json_str = content[start:end]
            else:
                logger.warning(f"LLM response not in JSON format: {content[:100]}")
                return None
            
            result = json.loads(json_str)
            
            needs_plan = result.get('needs_plan', False)
            complexity = result.get('complexity', 'simple' if not needs_plan else 'complex')
            confidence = float(result.get('confidence', 0.5))
            reason = result.get('reason', '')
            
            logger.info(
                "LLM-assisted task analysis completed",
                extra={
                    "needs_plan": needs_plan,
                    "complexity": complexity,
                    "confidence": confidence,
                    "reason": reason[:100] if reason else '',
                }
            )
            
            return TaskAnalysis(
                complexity=complexity,
                confidence=confidence,
                indicators=[f"llm_reason: {reason}"],
                needs_plan=needs_plan,
                matched_skills=[],
                recommended_skill=None,
                analysis_method="llm_assisted",
            )
            
        except Exception as e:
            logger.warning(f"LLM-assisted analysis failed: {e}")
            return None
    
    @staticmethod
    def extract_skill_name(user_message: str, available_skills: list[str] | None = None) -> tuple[str, str]:
        """从用户消息中提取技能名称（支持有/和无/的情况）
        
        Args:
            user_message: 用户消息
            available_skills: 可用技能列表（可选），用于精确匹配
            
        Returns:
            (skill_name, remaining_message) 元组
            - 如果匹配到技能，返回 (技能名，剩余消息)
            - 如果没有匹配，返回 ("", user_message)
            
        Examples:
            >>> extract_skill_name("/pdf convert file.pdf")
            ('pdf', 'convert file.pdf')
            
            >>> extract_skill_name("pptx create presentation")
            ('pptx', 'create presentation')
        """
        # 先尝试 /command 格式
        skill_name, remaining = TaskAnalyzer.parse_skill_command(user_message)
        if skill_name:
            return skill_name, remaining
        
        # NEW: 尝试模糊匹配 - 检查消息中是否包含技能名（不只在开头）
        if available_skills:
            message_lower = user_message.lower()
            
            # 策略 1: 检查是否以某个技能名开头（原有逻辑）
            words = user_message.split()
            if words:
                first_word = words[0].lower()
                for skill in available_skills:
                    if skill.lower() == first_word:
                        remaining_msg = ' '.join(words[1:]) if len(words) > 1 else ""
                        return skill, remaining_msg
            
            # NEW 策略 2: 检查消息中是否包含技能名（更灵活）
            # 例如："生成 pdf"中包含"pdf"
            for skill in available_skills:
                skill_lower = skill.lower()
                if skill_lower in message_lower:
                    # 找到技能名在消息中的位置
                    skill_pos = message_lower.find(skill_lower)
                    
                    # 提取技能名前后的内容
                    before = user_message[:skill_pos].strip()
                    after = user_message[skill_pos + len(skill):].strip()
                    
                    # 如果技能名前面是动词（如"生成"、"创建"），也认为是技能调用
                    action_verbs = ["生成", "创建", "制作", "做", "写", "画", "转换", "处理"]
                    if any(verb in before for verb in action_verbs) or not before:
                        # 返回技能名和剩余内容作为参数
                        remaining_msg = f"{before} {after}".strip() if before or after else ""
                        return skill, remaining_msg
        
        return "", user_message
    
    async def analyze(self, user_message: str) -> TaskAnalysis:
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
        
        # 🔥 NEW: 检测工具确认上下文，避免误判
        # 如果消息包含"[用户已确认执行高危命令]"，说明是工具确认后的继续执行
        # 这种情况下不应该重新进行任务分析，而是保持原有的计划状态
        if "[用户已确认执行高危命令]" in user_message:
            logger.info(
                "Tool confirmation context detected, skipping complexity analysis",
                extra={"message_preview": user_message[:100]}
            )
            
            # 🔥 NEW: 即使是在工具确认上下文中，也要检查是否有 PDF 等复杂需求
            pdf_keywords = ["pdf", "PDF", "生成 pdf", "创建 pdf", "pdf 报告"]
            has_pdf_need = any(kw in user_message for kw in pdf_keywords)
            
            if has_pdf_need:
                logger.info(
                    "PDF requirement detected in tool confirmation context",
                    extra={"matched_pdf_keywords": [kw for kw in pdf_keywords if kw in user_message]}
                )
                return TaskAnalysis(
                    complexity="complex",
                    confidence=0.85,
                    indicators=["tool_confirmation_context_with_pdf_need"],
                    needs_plan=True,  # 🔥 需要 Plan Mode
                    matched_skills=[],
                    recommended_skill=None,
                )
            
            # 否则确实是简单任务（只是继续执行已确认的命令）
            return TaskAnalysis(
                complexity="simple",
                confidence=0.9,  # 高置信度这是确认上下文
                indicators=["tool_confirmation_context"],
                needs_plan=False,  # 不应该重新生成计划，应该继续执行原有计划
                matched_skills=[],
                recommended_skill=None,
            )
        
        # ===== P1: /command 格式强制 Plan Mode =====
        skill_name, arguments = self.parse_skill_command(user_message)
        if skill_name:
            # 用户明确调用了技能命令，这通常是复杂任务
            # Fix: matched_skills must be list of dicts, not list of strings
            return TaskAnalysis(
                complexity="complex",
                confidence=1.0,
                indicators=[f"skill_name_detected: {skill_name}"],
                needs_plan=True,  # Always need plan when skill is explicitly invoked
                matched_skills=[{"name": skill_name}],
                recommended_skill={"name": skill_name, "arguments": arguments},
                analysis_method="rule_based",
            )
        
        # ===== P2: LLM 辅助判断（混合模式）=====
        # 先尝试使用 LLM 判断，如果 LLM 判断置信度高则直接采用
        llm_analysis = await self.analyze_with_llm(user_message)
        if llm_analysis and llm_analysis.confidence >= 0.8:
            # LLM 判断置信度高，直接采用
            logger.info(
                "Using LLM-assisted analysis (high confidence)",
                extra={
                    "confidence": llm_analysis.confidence,
                    "needs_plan": llm_analysis.needs_plan,
                }
            )
            return llm_analysis
        
        # ===== P3: 规则匹配（fallback）=====
        # 如果 LLM 判断失败或置信度低，使用规则匹配
        logger.debug(
            "Falling back to rule-based analysis",
            extra={
                "llm_confidence": llm_analysis.confidence if llm_analysis else None,
            }
        )
        
        # ===== 新增：支持无斜杠的技能名称匹配 =====
        # 即使用户没有输入 /，只要消息以技能名开头，也识别为技能调用
        if self.skills_config and self.skills_config.registered:
            available_skills = [skill.name for skill in self.skills_config.registered]
            extracted_skill, remaining_msg = self.extract_skill_name(user_message, available_skills)
            
            if extracted_skill:
                logger.info(
                    "Skill name detected without slash prefix",
                    extra={
                        "skill_name": extracted_skill,
                        "original_message": user_message,
                        "remaining_message": remaining_msg,
                    }
                )
                
                # Check if this is a high-confidence skill match
                # If skill appears with action verbs or at the beginning, confidence is higher
                confidence = 0.8
                skill_lower = extracted_skill.lower()
                message_lower = user_message.lower()
                
                # Higher confidence scenarios
                if (message_lower.startswith(skill_lower) or
                    any(verb in user_message[:user_message.lower().find(skill_lower)] 
                        for verb in ["生成", "创建", "制作", "写", "画"])):
                    confidence = 0.95
                
                return TaskAnalysis(
                    complexity="complex",
                    confidence=confidence,
                    indicators=[f"skill_name_detected: {extracted_skill}"],
                    needs_plan=True,  # Always need plan when skill is explicitly invoked
                    matched_skills=[{"name": extracted_skill}],
                    recommended_skill={"name": extracted_skill, "arguments": remaining_msg},
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
        
        # 技能关键词匹配（原有逻辑）+ P2-2 NEW: 语义路由增强 + P3-0 NEW: LLM 智能匹配
        matched_skills = []
        recommended_skill = None
        
        if self.skills_config and self.skills_config.registered:
            # Step 1: 原有的关键词匹配
            keyword_matched = self.skills_config.match_skills_by_keywords(user_message)
            
        # P3-0 NEW: Step 2 - 优先使用 LLM 进行智能匹配（最准确）
            llm_matches = []
            if self.llm_skill_matcher:
                try:
                    # ✅ FIX: Use await directly in async context
                    llm_matches = await self.llm_skill_matcher.match_skills(user_message, top_k=3)
                    logger.info(
                        "LLM-based skill matching completed",
                        extra={
                            "task": user_message[:50],
                            "llm_matches": llm_matches,
                        }
                    )
                except Exception as e:
                    logger.warning(f"LLM skill matching failed: {e}")
                    llm_matches = []
            
            # P2-2 NEW: Step 3 - 使用语义路由匹配 Skills（降级方案）
            semantic_matches = []
            if self.skill_router and not llm_matches:  # LLM 失败时才使用
                try:
                    semantic_matches = self.skill_router.route(user_message, top_k=3)
                    logger.info(
                        "Semantic skill matching completed (fallback)",
                        extra={
                            "task": user_message[:50],
                            "semantic_matches": semantic_matches,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Semantic routing failed: {e}")
            
            # Step 4: 合并匹配结果（优先级：LLM > 语义 > 关键词）
            seen_skills = set()
            all_matched = []
            
            # 优先添加 LLM 匹配的结果（最准确）
            for skill_name, score in llm_matches:
                if score >= 0.6 and skill_name not in seen_skills:  # 置信度阈值 0.6
                    skill = self.skills_config.get_skill_by_name(skill_name)
                    if skill:
                        skill_info = {
                            "name": skill.name,
                            "description": skill.description,
                            "priority": skill.priority,
                            "auto_trigger": skill.auto_trigger,
                            "match_score": score,  # LLM 置信度
                            "match_type": "llm",  # 标记为 LLM 匹配
                        }
                        all_matched.append(skill_info)
                        seen_skills.add(skill_name)
                        
                        # 高置信度匹配（>0.8）自动推荐
                        if score > 0.8 and recommended_skill is None:
                            recommended_skill = skill_info
                            score += 0.3  # 提高复杂度评分
                            indicators.append(f"llm_skill_matched: {skill.name} (confidence: {score:.2f})")
            
            # 其次添加语义匹配的结果
            for skill_name, score in semantic_matches:
                if score >= 0.6 and skill_name not in seen_skills:
                    skill = self.skills_config.get_skill_by_name(skill_name)
                    if skill:
                        skill_info = {
                            "name": skill.name,
                            "description": skill.description,
                            "priority": skill.priority,
                            "auto_trigger": skill.auto_trigger,
                            "match_score": score,
                            "match_type": "semantic",  # 标记为语义匹配
                        }
                        all_matched.append(skill_info)
                        seen_skills.add(skill_name)
                        
                        # 高置信度匹配（>0.8）自动推荐
                        if score > 0.8 and recommended_skill is None:
                            recommended_skill = skill_info
                            score += 0.3
                            indicators.append(f"semantic_skill_matched: {skill.name} (score: {score:.2f})")
            
            # 最后添加关键词匹配的结果
            for skill in keyword_matched:
                if skill.name not in seen_skills:
                    skill_info = {
                        "name": skill.name,
                        "description": skill.description,
                        "priority": skill.priority,
                        "auto_trigger": skill.auto_trigger,
                        "match_type": "keyword",  # 标记为关键词匹配
                    }
                    all_matched.append(skill_info)
                    seen_skills.add(skill.name)
                    
                    # 如果是自动触发技能，设为推荐
                    if skill.auto_trigger and recommended_skill is None:
                        recommended_skill = skill_info
                        score += 0.3
                        indicators.append(f"keyword_skill_matched: {skill.name}")
            
            matched_skills = all_matched
        
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
