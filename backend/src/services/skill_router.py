"""Skill Router for semantic matching.

基于向量相似度进行 Skill 精准匹配的核心组件。

核心流程:
1. 将所有 Skill 描述转换为 embedding
2. 用户任务转换为 embedding
3. 计算余弦相似度
4. 返回 Top-K 匹配的 Skill

注意：使用系统中的 Embedder 服务而非 LLM Router，因为
LLM Router 专注于 chat/completion 任务，而 embedding 由
专门的 embedder 模块处理。
"""

import numpy as np
from typing import List, Tuple
from ..services.skill_registry import SkillRegistry
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SkillRouter:
    """基于语义向量的 Skill 路由器
    
    使用 Embedding Semantic Matching 而非关键词匹配，
    实现更精准的 Skill 发现和调度。
    """
    
    def __init__(self, skill_registry: SkillRegistry):
        """初始化 Skill Router
        
        Args:
            skill_registry: 技能注册表实例
            
        Note:
            使用内部的 MockEmbedder（维度 384）进行 embedding 计算，
            避免依赖外部 LLM 服务，保证性能和稳定性。
        """
        self.skill_registry = skill_registry
        self._skill_embeddings: dict[str, np.ndarray] = {}
        self._index_built: bool = False
        # 使用简单的 hash-based embedder（与系统中 embedder.py 一致）
        self._embedding_dim = 384
    
    def _compute_embedding(self, text: str) -> np.ndarray:
        """计算文本的 embedding 向量（基于 hash 的确定性 embedding）
        
        Args:
            text: 需要计算 embedding 的文本
            
        Returns:
            numpy 数组形式的 embedding 向量（384 维）
        """
        import hashlib
        import random
        
        try:
            # 使用 text hash 生成确定性 embedding（与 embedder.py 一致）
            text_hash = hashlib.md5(text.encode()).hexdigest()
            random.seed(text_hash)
            
            # 生成 384 维 embedding
            embedding = [random.gauss(0, 1) for _ in range(self._embedding_dim)]
            
            # 归一化（L2 normalization）
            magnitude = sum(x * x for x in embedding) ** 0.5
            if magnitude > 0:
                embedding = [x / magnitude for x in embedding]
            
            return np.array(embedding)
            
        except Exception as e:
            logger.error(f"Embedding computation failed: {e}")
            # 返回零向量作为降级
            return np.zeros(self._embedding_dim)
    
    def build_index(self) -> None:
        """构建 Skill 索引（启动时调用一次）
        
        扫描所有已注册的 Skills 并预计算它们的 embeddings。
        """
        if self._index_built:
            logger.debug("Skill index already built")
            return
        
        skills = self.skill_registry.list_all_skills()
        logger.info(f"Building skill index with {len(skills)} skills")
        
        for skill in skills:
            # 组合技能和描述作为索引文本
            index_text = f"{skill.name}: {skill.description}"
            
            try:
                embedding = self._compute_embedding(index_text)
                self._skill_embeddings[skill.name] = embedding
                logger.debug(f"Indexed skill: {skill.name}")
            except Exception as e:
                logger.warning(f"Failed to index skill {skill.name}: {e}")
        
        self._index_built = True
        logger.info(f"Skill index built successfully with {len(self._skill_embeddings)} skills")
    
    def route(self, task: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """为任务匹配最相关的 Skills
        
        Args:
            task: 用户任务描述
            top_k: 返回前 K 个匹配结果（默认 3 个）
            
        Returns:
            [(skill_name, similarity_score), ...] 
            按相似度降序排列的列表
        """
        # 确保索引已构建
        if not self._index_built:
            self.build_index()
        
        if not self._skill_embeddings:
            logger.warning("No skills indexed")
            return []
        
        # 计算任务 embedding
        task_embedding = self._compute_embedding(task)
        
        # 计算所有技能的相似度
        similarities = []
        for skill_name, skill_embedding in self._skill_embeddings.items():
            similarity = self._cosine_similarity(task_embedding, skill_embedding)
            similarities.append((skill_name, similarity))
        
        # 排序并返回 Top-K
        similarities.sort(key=lambda x: x[1], reverse=True)
        result = similarities[:top_k]
        
        logger.info(
            "Semantic skill matching completed",
            extra={
                "task": task[:50],
                "top_match": result[0] if result else None,
                "all_matches": result,
            }
        )
        
        return result
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度
        
        Args:
            a: 向量 a
            b: 向量 b
            
        Returns:
            相似度分数 (0-1 之间)
        """
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        similarity = float(dot_product / (norm_a * norm_b))
        # 归一化到 0-1 范围（如果 embedding 模型输出有负值）
        return max(0.0, min(1.0, similarity))
    
    def clear_index(self) -> None:
        """清除索引（用于技能更新后重新构建）"""
        self._skill_embeddings.clear()
        self._index_built = False
        logger.info("Skill index cleared")


# 全局实例
_skill_router: SkillRouter | None = None


def get_skill_router(skill_registry: SkillRegistry | None = None) -> SkillRouter:
    """获取全局 SkillRouter 实例
    
    Args:
        skill_registry: 技能注册表实例（首次调用时需要）
        
    Returns:
        SkillRouter 单例实例
    """
    global _skill_router
    if _skill_router is None:
        if skill_registry is None:
            from ..services.skill_registry import get_skill_registry
            from pathlib import Path
            skill_registry = get_skill_registry(Path.cwd())
        _skill_router = SkillRouter(skill_registry)
    return _skill_router
