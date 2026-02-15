"""Embedding service using sentence-transformers.

This module provides:
- Local embedding model loading
- Text to embedding conversion
- Embedding caching for performance
"""

from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class Embedder:
    """Local embedding service using sentence-transformers.
    
    Provides text embedding generation using the all-MiniLM-L6-v2 model
    for semantic similarity search.
    """
    
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384
    
    def __init__(self, model_name: str | None = None) -> None:
        """Initialize embedder.
        
        Args:
            model_name: Name of the sentence-transformers model to use
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model: Any = None
        self._initialized = False
        
        logger.info(
            "Embedder created",
            extra={"model_name": self.model_name}
        )
    
    def _load_model(self) -> Any:
        """Load the embedding model."""
        if self._model is not None:
            return self._model
            
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(
                "Loading embedding model",
                extra={"model_name": self.model_name}
            )
            self._model = SentenceTransformer(self.model_name)
            logger.info(
                "Embedding model loaded successfully",
                extra={
                    "model_name": self.model_name,
                    "embedding_dim": self.EMBEDDING_DIM
                }
            )
            return self._model
        except ImportError:
            logger.warning(
                "sentence-transformers not installed, using fallback embedding"
            )
            return None
        except Exception as e:
            logger.error(
                "Failed to load embedding model",
                extra={"error": str(e)}
            )
            return None
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (384 dimensions)
        """
        model = self._load_model()
        
        if model is None:
            # Fallback: return zero vector
            logger.warning("Using zero vector fallback for embedding")
            return [0.0] * self.EMBEDDING_DIM
        
        try:
            embedding = model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(
                "Failed to generate embedding",
                extra={"text_length": len(text), "error": str(e)}
            )
            return [0.0] * self.EMBEDDING_DIM
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        model = self._load_model()
        
        if model is None:
            logger.warning("Using zero vector fallback for batch embedding")
            return [[0.0] * self.EMBEDDING_DIM for _ in texts]
        
        try:
            embeddings = model.encode(texts, convert_to_numpy=True)
            return [e.tolist() for e in embeddings]
        except Exception as e:
            logger.error(
                "Failed to generate batch embeddings",
                extra={"batch_size": len(texts), "error": str(e)}
            )
            return [[0.0] * self.EMBEDDING_DIM for _ in texts]


# Global embedder instance
_embedder: Embedder | None = None


def get_embedder(model_name: str | None = None) -> Embedder:
    """Get or create global embedder instance.
    
    Args:
        model_name: Optional model name override
        
    Returns:
        Embedder instance
    """
    global _embedder
    if _embedder is None:
        _embedder = Embedder(model_name)
    return _embedder
