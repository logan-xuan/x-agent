"""SkillDiscovery - 智能技能发现与推荐。

组合多种召回策略:
1. 基于嵌入的语义搜索
2. 关键词匹配
3. 标签/领域过滤

返回按相关性排序的 SkillCard 列表，附带匹配原因说明。
"""

from typing import Any

from ...models.skill import (
    SkillManifest,
    SkillSearchContext,
    SkillCard,
    SkillScore,
    SkillSource,
)
from ...utils.logger import get_logger
from .registry import SkillRegistry
from .embedder import SkillEmbedder, get_embedder
from .scorer import SkillScorer

logger = get_logger(__name__)


class SkillDiscovery:
    """智能技能发现服务。
    
    结合语义搜索、关键词匹配和过滤策略，
    为用户查询找到最相关的技能。
    
    示例:
        discovery = SkillDiscovery(registry, embedder, scorer)
        context = SkillSearchContext(user_input="转换为 pdf")
        results = discovery.discover(context, top_k=5)
        
        for card in results:
            print(f"{card.skill_id}: {card.relevance_score:.2f}")
    """
    
    # 结果最低分数阈值
    MIN_SCORE_THRESHOLD = 0.1
    
    # 关键词匹配加成
    KEYWORD_BOOST = 0.15
    TAG_BOOST = 0.10
    
    def __init__(
        self,
        registry: SkillRegistry,
        embedder: SkillEmbedder | None = None,
        scorer: SkillScorer | None = None,
    ) -> None:
        """初始化发现服务。
        
        Args:
            registry: 技能注册表，用于列出技能
            embedder: 语义搜索用嵌入器（可选）
            scorer: 相关性评分器（可选）
        """
        self.registry = registry
        self.embedder = embedder or get_embedder()
        self.scorer = scorer or SkillScorer()
        
        # 技能嵌入缓存
        self._skill_embeddings: dict[str, list[float]] = {}
    
    def discover(
        self,
        context: SkillSearchContext,
        top_k: int = 10,
        domains: list[str] | None = None,
        min_score: float | None = None,
    ) -> list[SkillCard]:
        """发现与用户查询相关的技能。
        
        Args:
            context: 包含用户输入的搜索上下文
            top_k: 最大返回结果数
            domains: 按领域过滤（可选）
            min_score: 最低相关性分数（可选）
            
        Returns:
            按相关性排序的 SkillCard 列表
        """
        min_score = min_score or self.MIN_SCORE_THRESHOLD
        
        # 从注册表获取所有技能
        all_skills = self.registry.list_skills()
        
        if not all_skills:
            logger.debug("注册表中未找到技能")
            return []
        
        # 生成查询嵌入向量
        query_embedding = self.embedder.embed(context.user_input).embedding
        
        # 对每个技能评分
        scored_skills: list[tuple[SkillManifest, SkillScore, list[str]]] = []
        
        for skill in all_skills:
            # 应用领域过滤
            if domains and not self._matches_domain(skill, domains):
                continue
            
            # 获取技能嵌入向量
            skill_embedding = self._get_skill_embedding(skill)
            
            # 计算语义相似度
            semantic_sim = self.embedder.cosine_similarity(
                query_embedding, skill_embedding
            )
            
            # 检查关键词/标签匹配
            match_reasons = []
            keyword_boost = 0.0
            
            # 关键词匹配
            keyword_matches = self._match_keywords(context.user_input, skill)
            if keyword_matches:
                keyword_boost += self.KEYWORD_BOOST
                match_reasons.append(f"keyword match: {', '.join(keyword_matches)}")
            
            # 标签匹配
            tag_matches = self._match_tags(context.user_input, skill)
            if tag_matches:
                keyword_boost += self.TAG_BOOST
                match_reasons.append(f"tag match: {', '.join(tag_matches)}")
            
            # 计算含加成的分数
            boosted_similarity = min(1.0, semantic_sim + keyword_boost)
            
            score = self.scorer.score(
                manifest=skill,
                context=context,
                semantic_similarity=boosted_similarity,
            )
            
            # 高语义相似度时添加匹配原因
            if semantic_sim > 0.5 and not keyword_matches:
                match_reasons.append(f"semantic match ({semantic_sim:.0%})")
            
            if score.total >= min_score:
                scored_skills.append((skill, score, match_reasons))
        
        # 按分数排序
        scored_skills.sort(key=lambda x: x[1].total, reverse=True)
        
        # 取前 top_k 个
        top_skills = scored_skills[:top_k]
        
        # 转换为 SkillCard
        results = []
        for skill, score, reasons in top_skills:
            card = self._create_skill_card(skill, score, context, reasons)
            results.append(card)
        
        logger.debug(
            f"为查询发现了 {len(results)} 个技能",
            extra={
                "query": context.user_input[:50],
                "results": [r.skill_id for r in results],
            }
        )
        
        return results
    
    def _get_skill_embedding(self, skill: SkillManifest) -> list[float]:
        """获取或生成技能的嵌入向量。"""
        if skill.skill_id in self._skill_embeddings:
            return self._skill_embeddings[skill.skill_id]
        
        # 构建能力描述文本
        capability_text = self._build_capability_text(skill)
        
        # 生成嵌入向量
        result = self.embedder.embed(capability_text)
        self._skill_embeddings[skill.skill_id] = result.embedding
        
        return result.embedding
    
    def _build_capability_text(self, skill: SkillManifest) -> str:
        """构建用于嵌入的能力描述文本。"""
        parts = [
            skill.name,
            skill.description,
        ]
        
        if skill.description_detail:
            parts.append(skill.description_detail)
        
        if skill.examples:
            parts.extend(skill.examples[:3])
        
        if skill.keywords:
            parts.append(" ".join(skill.keywords))
        
        return " ".join(parts)
    
    def _match_keywords(
        self,
        query: str,
        skill: SkillManifest,
    ) -> list[str]:
        """查找查询与技能之间的关键词匹配。"""
        query_lower = query.lower()
        matches = []
        
        # 检查技能关键词
        for keyword in skill.keywords:
            if keyword.lower() in query_lower:
                matches.append(keyword)
        
        # 检查技能名称
        name_parts = skill.name.lower().replace("-", " ").split()
        for part in name_parts:
            if part in query_lower and len(part) > 2:
                matches.append(part)
        
        return list(set(matches))
    
    def _match_tags(
        self,
        query: str,
        skill: SkillManifest,
    ) -> list[str]:
        """查找查询与技能之间的标签匹配。"""
        query_lower = query.lower()
        matches = []
        
        for tag in skill.tags:
            if tag.lower() in query_lower:
                matches.append(tag)
        
        return matches
    
    def _matches_domain(
        self,
        skill: SkillManifest,
        domains: list[str],
    ) -> bool:
        """检查技能是否匹配指定领域。"""
        if not skill.domains:
            return True  # 无领域限制的技能匹配所有查询
        
        return any(d in skill.domains for d in domains)
    
    def _create_skill_card(
        self,
        skill: SkillManifest,
        score: SkillScore,
        context: SkillSearchContext,
        match_reasons: list[str],
    ) -> SkillCard:
        """从技能和评分创建 SkillCard。"""
        # 获取缺失参数
        missing_params = self.scorer.get_missing_params(
            skill, context.available_params
        )
        
        # 获取必需参数
        required_params = []
        if skill.input_schema:
            required_params = skill.input_schema.get("required", [])
        
        # 判断是否需要审批
        approval_required = (
            skill.risk_level.value in ["high", "critical"] or
            skill.approval_mode.value != "auto"
        )
        
        # 构建匹配原因字符串
        match_reason = "; ".join(match_reasons) if match_reasons else "search match"
        
        return SkillCard(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            emoji=skill.emoji,
            relevance_score=score.total,
            match_reason=match_reason,
            risk_level=skill.risk_level,
            side_effect=skill.side_effect,
            approval_mode=skill.approval_mode,
            approval_required=approval_required,
            input_schema=skill.input_schema,
            required_params=required_params,
            available_params=list(context.available_params.keys()),
            missing_params=missing_params,
            schema_fit_score=score.breakdown.get("schema_fit", 0.0),
            supports_dry_run=skill.supports_dry_run,
            supports_rollback=skill.supports_rollback,
            estimated_latency_ms=skill.timeout_ms or 30000,
        )
    
    def clear_cache(self) -> None:
        """清空技能嵌入缓存。"""
        self._skill_embeddings.clear()
        self.embedder.clear_cache()
        logger.debug("发现服务缓存已清空")


# 全局发现服务实例
_discovery: SkillDiscovery | None = None


def get_discovery(registry: SkillRegistry) -> SkillDiscovery:
    """获取或创建全局发现服务实例。"""
    global _discovery
    if _discovery is None:
        _discovery = SkillDiscovery(registry)
    return _discovery
