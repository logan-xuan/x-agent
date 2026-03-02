"""SkillScorer - 技能匹配多维度加权评分器。

实现 5 维度评分体系:
- semantic (0.35): 基于嵌入的语义相似度
- schema_fit (0.25): 参数可用性匹配度
- policy (0.20): 风险等级与权限兼容性
- latency (0.10): 预期响应时间
- reliability (0.10): 历史可靠性评分
"""

from ...models.skill import (
    SkillManifest,
    SkillSearchContext,
    SkillScore,
    RiskLevel,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)


class SkillScorer:
    """技能相关性多维度评分器。
    
    计算 5 个维度的加权分数，确定技能
    对给定搜索上下文的相关性。
    
    示例:
        scorer = SkillScorer()
        score = scorer.score(
            manifest=skill_manifest,
            context=search_context,
            semantic_similarity=0.85,
        )
        print(f"总分: {score.total}")
    """
    
    # 评分权重（总和必须为 1.0）
    WEIGHT_SEMANTIC = 0.35
    WEIGHT_SCHEMA_FIT = 0.25
    WEIGHT_POLICY = 0.20
    WEIGHT_LATENCY = 0.10
    WEIGHT_RELIABILITY = 0.10
    
    # 风险等级惩罚系数
    RISK_PENALTIES = {
        RiskLevel.LOW: 0.0,
        RiskLevel.MEDIUM: 0.1,
        RiskLevel.HIGH: 0.3,
        RiskLevel.CRITICAL: 0.5,
    }
    
    def score(
        self,
        manifest: SkillManifest,
        context: SkillSearchContext,
        semantic_similarity: float = 0.0,
    ) -> SkillScore:
        """计算技能的加权总分。
        
        Args:
            manifest: 待评分的技能清单
            context: 包含用户输入和参数的搜索上下文
            semantic_similarity: 预计算的语义相似度 [0, 1]
            
        Returns:
            包含总分和各维度分数的 SkillScore
        """
        # 计算各维度分数
        semantic = self.score_semantic(semantic_similarity)
        schema_fit = self.score_schema_fit(manifest, context.available_params)
        policy = self.score_policy(manifest, context.user_permissions)
        latency = self.score_latency(manifest)
        reliability = self.score_reliability(manifest)
        
        # 构建分数明细
        breakdown = {
            "semantic": semantic,
            "schema_fit": schema_fit,
            "policy": policy,
            "latency": latency,
            "reliability": reliability,
        }
        
        # 计算加权总分
        total = (
            semantic * self.WEIGHT_SEMANTIC +
            schema_fit * self.WEIGHT_SCHEMA_FIT +
            policy * self.WEIGHT_POLICY +
            latency * self.WEIGHT_LATENCY +
            reliability * self.WEIGHT_RELIABILITY
        )
        
        return SkillScore(
            skill_id=manifest.skill_id,
            total=total,
            breakdown=breakdown,
        )
    
    def score_semantic(self, similarity: float) -> float:
        """基于语义相似度评分。
        
        Args:
            similarity: 余弦相似度 [-1, 1]
            
        Returns:
            归一化分数 [0, 1]
        """
        # 将负相似度截断为 0
        return max(0.0, min(1.0, similarity))
    
    def score_schema_fit(
        self,
        manifest: SkillManifest,
        available_params: dict,
    ) -> float:
        """基于参数可用性评分。
        
        Args:
            manifest: 包含 input_schema 的技能清单
            available_params: 上下文中可用的参数
            
        Returns:
            分数 [0, 1]，基于必需参数的满足比例
        """
        if not manifest.input_schema:
            # 无 schema = 无要求 = 满分
            return 1.0
        
        # 从 schema 中获取必需参数
        required = manifest.input_schema.get("required", [])
        
        if not required:
            return 1.0
        
        # 统计已满足的必需参数数量
        available_count = sum(
            1 for param in required
            if param in available_params
        )
        
        return available_count / len(required)
    
    def score_policy(
        self,
        manifest: SkillManifest,
        permissions: list[str],
    ) -> float:
        """基于风险等级和权限评分。
        
        Args:
            manifest: 包含风险信息的技能清单
            permissions: 用户可用权限列表
            
        Returns:
            分数 [0, 1]，含风险和权限惩罚
        """
        score = 1.0
        
        # 应用风险惩罚
        risk_penalty = self.RISK_PENALTIES.get(manifest.risk_level, 0.0)
        score -= risk_penalty
        
        # 检查必需权限
        if manifest.required_auth:
            missing = [
                auth for auth in manifest.required_auth
                if auth not in permissions
            ]
            if missing:
                # 缺失权限的重度惩罚
                score -= 0.5 * (len(missing) / len(manifest.required_auth))
        
        return max(0.0, score)
    
    def score_latency(self, manifest: SkillManifest) -> float:
        """基于预期延迟评分。
        
        Args:
            manifest: 包含 timeout_ms 的技能清单
            
        Returns:
            分数 [0, 1]，响应越快分数越高
        """
        # 基线: 30 秒为中性分 (0.5)
        # < 5 秒: 高分 (0.9+)
        # > 60 秒: 低分 (0.3)
        timeout_ms = manifest.timeout_ms or 30000
        
        if timeout_ms <= 5000:
            return 0.95
        elif timeout_ms <= 15000:
            return 0.85
        elif timeout_ms <= 30000:
            return 0.75
        elif timeout_ms <= 60000:
            return 0.6
        else:
            return 0.4
    
    def score_reliability(self, manifest: SkillManifest) -> float:
        """基于技能可靠性评分。
        
        当前返回默认分数，后续可扩展为
        使用历史执行数据进行评估。
        
        Args:
            manifest: 技能清单
            
        Returns:
            分数 [0, 1]，基于可靠性指标
        """
        # 默认可靠性基础分
        # TODO: 集成遥测数据以获取实际可靠性指标
        base_score = 0.8
        
        # 幂等技能加分
        if manifest.idempotency:
            base_score += 0.1
        
        # 支持回滚的技能加分
        if manifest.supports_rollback:
            base_score += 0.05
        
        return min(1.0, base_score)
    
    def get_missing_params(
        self,
        manifest: SkillManifest,
        available_params: dict,
    ) -> list[str]:
        """获取缺失的必需参数列表。
        
        Args:
            manifest: 技能清单
            available_params: 可用参数
            
        Returns:
            缺失的必需参数名称列表
        """
        if not manifest.input_schema:
            return []
        
        required = manifest.input_schema.get("required", [])
        return [p for p in required if p not in available_params]
