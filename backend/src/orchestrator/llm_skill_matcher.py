"""LLM-based skill matcher for semantic understanding.

使用 LLM 进行语义理解的技能匹配器。
相比向量相似度，LLM 能更好地理解任务意图和技能适用性。

核心优势:
1. 真正的语义理解，而非表面相似性
2. 可以考虑技能的实际能力和限制
3. 支持复杂的多技能组合推荐
4. 动态读取注册的元数据，无需硬编码
"""

from typing import List, Tuple, Optional
import json
from pathlib import Path

from ..services.skill_registry import SkillRegistry, get_skill_registry
from ..services.llm.router import LLMRouter
from ..main import get_llm_router
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LLMSkillMatcher:
    """基于 LLM 的智能技能匹配器
    
    使用 LLM 理解任务描述，从已注册的技能中选择最相关的技能。
    """
    
    # ✅ FIX: Add constants for cache management
    MAX_CACHE_SIZE = 1000
    CACHE_TTL_SECONDS = 3600  # 1 hour
    
    def __init__(self, skill_registry: SkillRegistry, llm_router: LLMRouter | None = None):
        """初始化 LLM 技能匹配器
        
        Args:
            skill_registry: 技能注册表实例
            llm_router: LLM 路由器实例（可选，默认使用全局实例）
        """
        self.skill_registry = skill_registry
        self.llm_router = llm_router or get_llm_router()
        # ✅ FIX: Use OrderedDict for LRU cache
        from collections import OrderedDict
        self._cache: OrderedDict = OrderedDict()
        self._cache_timestamps: dict[str, float] = {}
        
        logger.info(
            "LLMSkillMatcher initialized",
            extra={
                "skill_count": len(skill_registry.list_all_skills()) if skill_registry else 0,
                "max_cache_size": self.MAX_CACHE_SIZE,
            }
        )
    
    def _build_available_skills_prompt(self) -> str:
        """动态构建可用技能列表 prompt
        
        Returns:
            格式化的技能列表字符串
        """
        if not self.skill_registry:
            return "无可用技能"
        
        skills = self.skill_registry.list_all_skills()
        if not skills:
            return "无可用技能"
        
        # 按优先级排序（数字越小优先级越高）
        sorted_skills = sorted(skills, key=lambda s: s.priority if hasattr(s, 'priority') else 999)
        
        skill_lines = []
        for skill in sorted_skills:
            name = skill.name
            description = skill.description or "无描述"
            
            # 添加关键词信息（如果有）
            keywords_info = ""
            if hasattr(skill, 'keywords') and skill.keywords:
                keywords_str = ", ".join(skill.keywords[:5])  # 最多显示 5 个关键词
                keywords_info = f" (关键词：{keywords_str})"
            
            # 添加自动触发信息
            auto_trigger_info = ""
            if hasattr(skill, 'auto_trigger') and skill.auto_trigger:
                auto_trigger_info = " [可自动触发]"
            
            skill_lines.append(f"- **{name}**: {description}{keywords_info}{auto_trigger_info}")
        
        return "\n".join(skill_lines)
    
    def _sanitize_input(self, text: str, max_length: int = 2000) -> str:
        """清理输入，防止 prompt 注入
        
        Args:
            text: 需要清理的文本
            max_length: 最大长度限制
            
        Returns:
            清理后的文本
        """
        import re
        
        # 限制长度
        text = text[:max_length]
        
        # 移除可能的危险标记（prompt injection patterns）
        dangerous_patterns = [
            r'ignore.*previous.*instructions?',
            r'disregard.*previous.*instructions?',
            r'system.*override',
            r'admin.*command',
            r'bypass.*safety',
            r'act.*as.*assistant',
        ]
        
        for pattern in dangerous_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        return text.strip()
    
    async def match_skills(self, task: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """为任务匹配最相关的技能
        
        Args:
            task: 用户任务描述
            top_k: 返回前 K 个匹配结果（默认 3 个）
            
        Returns:
            [(skill_name, confidence_score), ...] 
            按置信度降序排列的列表，分数范围 0-1
        """
        import time
        start_time = time.time()
        cache_hit = False
        fallback_used = False
        
        # ✅ FIX: Include skill list hash in cache key to avoid stale results
        import hashlib
        skills_hash = hashlib.md5(
            ''.join(s.name for s in self.skill_registry.list_all_skills()).encode()
        ).hexdigest()[:8]
        cache_key = f"{task}_{top_k}_{skills_hash}"
        
        if cache_key in self._cache:
            logger.debug("Using cached skill matches")
            cache_hit = True
            
            # ✅ FIX: Check cache TTL
            import time
            cache_age = time.time() - self._cache_timestamps.get(cache_key, 0)
            if cache_age > self.CACHE_TTL_SECONDS:
                logger.debug(f"Cache entry expired (age={cache_age:.1f}s), removing")
                del self._cache[cache_key]
                del self._cache_timestamps[cache_key]
                return await self.match_skills(task, top_k)  # Recursively call again
            
            return self._cache[cache_key]
        
        try:
            # ✅ FIX: Sanitize input to prevent prompt injection
            task = self._sanitize_input(task)
            
            # 构建动态技能列表
            available_skills_prompt = self._build_available_skills_prompt()
            
            # ✅ FIX: Handle empty skills list early
            if not available_skills_prompt or available_skills_prompt == "无可用技能":
                logger.warning("No skills available for matching, returning empty result")
                return []
            
            # 构建 prompt
            system_prompt = """你是一个智能技能匹配助手。分析用户的任务描述，从可用技能列表中选择最相关的技能。

## 匹配规则

1. **语义理解优先**：不要只看关键词匹配，要理解任务的真实意图
2. **考虑技能能力**：只推荐真正能完成该任务的技能
3. **多技能组合**：如果任务需要多个技能配合，可以都推荐
4. **置信度评分**：
   - 0.9-1.0: 完美匹配，技能的核心功能就是做这个
   - 0.7-0.9: 高度相关，技能可以很好地完成任务
   - 0.5-0.7: 中等相关，技能可以部分参与
   - 0.3-0.5: 弱相关，技能可能有帮助但不是必需
   - <0.3: 不推荐

## 输出格式

严格输出 JSON 格式：
```json
[
  {"skill_name": "pdf", "confidence": 0.95, "reason": "简短说明理由"},
  {"skill_name": "write_file", "confidence": 0.8, "reason": "需要编写文件"}
]
```

如果没有匹配的技能，输出空数组：[]"""

            user_prompt = f"""任务描述：{task}

可用技能列表：
{available_skills_prompt}

请分析任务并推荐最相关的技能（最多 {top_k} 个）："""

            # 调用 LLM
            response = await self.llm_router.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                stream=False,
            )
            
            # 解析响应
            result = self._parse_llm_response(response.content, top_k)
            
            # 缓存结果
            self._cache[cache_key] = result
            self._cache_timestamps[cache_key] = time.time()
            
            # ✅ FIX: Enforce cache size limit (LRU eviction)
            if len(self._cache) > self.MAX_CACHE_SIZE:
                # Remove oldest entry
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)
                self._cache_timestamps.pop(oldest_key, None)
            
            elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
            logger.info(
                "LLM-based skill matching completed successfully",
                extra={
                    "task": task[:50],
                    "matched_skills": result,
                    "elapsed_time_ms": int(elapsed_time),
                    "cache_hit": cache_hit,
                    "cache_size": len(self._cache),
                }
            )
            
            return result
            
        except asyncio.TimeoutError as e:
            elapsed_time = (time.time() - start_time) * 1000
            fallback_used = True
            logger.warning(
                "LLM skill matching timeout, falling back to keyword matching",
                extra={
                    "timeout_duration_ms": int(elapsed_time),
                    "task_preview": task[:100],
                }
            )
            return self._fallback_keyword_matching(task, top_k)
            
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            fallback_used = True
            logger.error(
                "LLM skill matching failed",
                extra={
                    "error_type": type(e).__name__,
                    "error_msg": str(e)[:200],
                    "task_preview": task[:100],
                    "elapsed_time_ms": int(elapsed_time),
                },
                exc_info=True
            )
            return self._fallback_keyword_matching(task, top_k)
    
    def _parse_llm_response(self, content: str, top_k: int) -> List[Tuple[str, float]]:
        """解析 LLM 响应
        
        Args:
            content: LLM 返回的内容
            top_k: 最多返回的数量
            
        Returns:
            技能匹配列表
        """
        try:
            # 尝试提取 JSON
            import re
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析
                json_str = content.strip()
            
            data = json.loads(json_str)
            
            # 转换为 (skill_name, confidence) 格式
            result = []
            for item in data:
                skill_name = item.get("skill_name", "")
                confidence = float(item.get("confidence", 0))
                
                if skill_name:
                    result.append((skill_name, confidence))
            
            # 按置信度排序
            result.sort(key=lambda x: x[1], reverse=True)
            
            # 截取 top_k
            return result[:top_k]
            
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return []
    
    def _fallback_keyword_matching(self, task: str, top_k: int) -> List[Tuple[str, float]]:
        """降级方案：关键词匹配（当 LLM 失败时使用）
        
        Args:
            task: 用户任务描述
            top_k: 最多返回的数量
            
        Returns:
            技能匹配列表
        """
        task_lower = task.lower()
        matches = []
        
        skills = self.skill_registry.list_all_skills()
        for skill in skills:
            score = 0
            
            # 技能名称匹配
            if skill.name.lower() in task_lower:
                score += 0.5
            
            # 描述匹配
            if skill.description and any(kw.lower() in task_lower for kw in skill.description.lower()):
                score += 0.3
            
            # 关键词匹配
            if hasattr(skill, 'keywords') and skill.keywords:
                keyword_matches = sum(1 for kw in skill.keywords if kw.lower() in task_lower)
                score += keyword_matches * 0.1
            
            if score > 0:
                matches.append((skill.name, min(score, 1.0)))
        
        # 排序并返回
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:top_k]
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.debug("LLMSkillMatcher cache cleared")


# 全局单例
_llm_skill_matcher: Optional[LLMSkillMatcher] = None


def get_llm_skill_matcher(
    skill_registry: SkillRegistry | None = None,
    llm_router: LLMRouter | None = None
) -> LLMSkillMatcher:
    """获取全局 LLMSkillMatcher 实例
    
    Args:
        skill_registry: 技能注册表实例（首次调用时需要）
        llm_router: LLM 路由器实例（可选）
        
    Returns:
        LLMSkillMatcher 单例实例
    """
    global _llm_skill_matcher
    if _llm_skill_matcher is None:
        if skill_registry is None:
            # ✅ FIX: Use default workspace path instead of cwd()
            from ..config.manager import ConfigManager
            try:
                config = ConfigManager().config
                workspace_path = Path(config.workspace.path)
                skill_registry = get_skill_registry(workspace_path)
            except Exception as e:
                logger.warning(f"Failed to load workspace config, using cwd: {e}")
                skill_registry = get_skill_registry(Path.cwd())
        _llm_skill_matcher = LLMSkillMatcher(skill_registry, llm_router)
    return _llm_skill_matcher
