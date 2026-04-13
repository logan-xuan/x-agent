"""SkillEmbedder - 技能语义嵌入向量生成器。

使用 M3E-small 模型 (384维) 生成中英文双语文本嵌入。
支持缓存机制以优化性能。
"""

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from ...utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EmbeddingResult:
    """嵌入生成结果。"""

    embedding: list[float]
    model_name: str = "m3e-small"
    text_hash: str = ""


class SkillEmbedder:
    """使用 sentence-transformers 生成文本嵌入向量。

    使用 M3E-small 模型生成 384 维嵌入向量，
    针对中英文文本进行了优化。

    示例:
        embedder = SkillEmbedder()
        result = embedder.embed("将文档转换为 PDF")
        print(f"嵌入维度: {len(result.embedding)}")
    """

    # M3E-small 生成 384 维嵌入向量
    EMBEDDING_DIM = 384
    MODEL_NAME = "moka-ai/m3e-small"

    def __init__(self, lazy_load: bool = True) -> None:
        """初始化嵌入器。

        Args:
            lazy_load: 为 True 时，模型在首次使用时才加载
        """
        self._model: Any = None
        self._lazy_load = lazy_load
        self._cache: dict[str, EmbeddingResult] = {}

        if not lazy_load:
            self._load_model()

    def _load_model(self) -> None:
        """加载 sentence-transformer 模型。"""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"正在加载嵌入模型: {self.MODEL_NAME}")
            self._model = SentenceTransformer(self.MODEL_NAME)
            logger.info("嵌入模型加载成功")
        except ImportError:
            logger.warning("sentence-transformers 未安装，使用随机嵌入作为降级方案。")
            self._model = _FallbackModel()
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e}")
            self._model = _FallbackModel()

    def _ensure_model(self) -> None:
        """确保模型已加载。"""
        if self._model is None:
            self._load_model()

    def embed(self, text: str) -> EmbeddingResult:
        """为单个文本生成嵌入向量。

        Args:
            text: 待嵌入的文本

        Returns:
            包含 384 维嵌入向量的 EmbeddingResult
        """
        # 检查缓存
        text_hash = self._hash_text(text)
        if text_hash in self._cache:
            return self._cache[text_hash]

        self._ensure_model()

        # 生成嵌入向量
        embedding = self._model.encode([text])[0]

        # 归一化
        embedding = embedding / np.linalg.norm(embedding)

        result = EmbeddingResult(
            embedding=embedding.tolist(),
            model_name="m3e-small",
            text_hash=text_hash,
        )

        # 写入缓存
        self._cache[text_hash] = result

        return result

    def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """为多个文本批量生成嵌入向量。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            EmbeddingResult 列表
        """
        self._ensure_model()

        results = []
        texts_to_embed = []
        text_hashes = []
        cached_indices = []

        # 优先检查缓存
        for i, text in enumerate(texts):
            text_hash = self._hash_text(text)
            if text_hash in self._cache:
                cached_indices.append(i)
            else:
                texts_to_embed.append(text)
                text_hashes.append(text_hash)

        # 对未缓存的文本生成嵌入
        if texts_to_embed:
            embeddings = self._model.encode(texts_to_embed)

            for j, embedding in enumerate(embeddings):
                embedding = embedding / np.linalg.norm(embedding)
                result = EmbeddingResult(
                    embedding=embedding.tolist(),
                    model_name="m3e-small",
                    text_hash=text_hashes[j],
                )
                self._cache[text_hashes[j]] = result

        # 按原始顺序组装结果
        for text in texts:
            text_hash = self._hash_text(text)
            results.append(self._cache[text_hash])

        return results

    def clear_cache(self) -> None:
        """清空嵌入缓存。"""
        self._cache.clear()
        logger.debug("嵌入缓存已清空")

    def cosine_similarity(
        self,
        vec1: list[float],
        vec2: list[float],
    ) -> float:
        """计算两个向量的余弦相似度。

        Args:
            vec1: 第一个向量
            vec2: 第二个向量

        Returns:
            余弦相似度，范围 [-1, 1]
        """
        a = np.array(vec1)
        b = np.array(vec2)

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def _hash_text(text: str) -> str:
        """生成文本哈希值（用于缓存）。"""
        return hashlib.md5(text.encode()).hexdigest()


class _FallbackModel:
    """sentence-transformers 不可用时的降级模型。"""

    def encode(self, texts: list[str]) -> np.ndarray:
        """生成随机嵌入向量作为降级方案。"""
        logger.warning("正在使用随机嵌入降级方案")
        return np.random.randn(len(texts), SkillEmbedder.EMBEDDING_DIM)


# 全局嵌入器实例
_embedder: SkillEmbedder | None = None


def get_embedder() -> SkillEmbedder:
    """获取或创建全局嵌入器实例。"""
    global _embedder
    if _embedder is None:
        _embedder = SkillEmbedder()
    return _embedder
