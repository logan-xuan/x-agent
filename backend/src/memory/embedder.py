"""Embedder module for generating text embeddings.

This module provides:
- MockEmbedder: Simple embedder for testing (random embeddings)
- Embedder: Interface for embedding generation
"""

from typing import Any
import hashlib
import random

from ..utils.logger import get_logger

logger = get_logger(__name__)


class MockEmbedder:
    """Mock embedder for testing and development.
    
    Generates deterministic embeddings based on text content hash.
    Not suitable for production - use a real embedding model.
    """
    
    def __init__(self, dimension: int = 384) -> None:
        """Initialize mock embedder.
        
        Args:
            dimension: Embedding dimension (default: 384)
        """
        self.dimension = dimension
        self._is_mock = True  # Marker for detection
        logger.info(
            "MockEmbedder initialized",
            extra={"dimension": dimension, "note": "Not suitable for production"}
        )
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.
        
        Uses hash-based deterministic generation for consistency.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
        """
        # Use hash for deterministic but varied embeddings
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Seed random with hash for consistency
        random.seed(text_hash)
        
        # Generate random embedding
        embedding = [random.gauss(0, 1) for _ in range(self.dimension)]
        
        # Normalize to unit vector
        magnitude = sum(x * x for x in embedding) ** 0.5
        embedding = [x / magnitude for x in embedding]
        
        logger.debug(
            "Mock embedding generated",
            extra={"text_length": len(text), "dimension": self.dimension}
        )
        
        return embedding


class Embedder:
    """Embedder that wraps external embedding services.
    
    Supports multiple backends:
    - openai: OpenAI text-embedding-ada-002
    - huggingface: Local HuggingFace models
    - mock: Mock embedder for testing
    """
    
    def __init__(
        self,
        backend: str = "mock",
        model: str | None = None,
        api_key: str | None = None,
        dimension: int = 384,
    ) -> None:
        """Initialize embedder.
        
        Args:
            backend: Backend type ('openai', 'huggingface', 'mock')
            model: Model name/ID
            api_key: API key for cloud services
            dimension: Embedding dimension
        """
        self.backend = backend
        self.model = model
        self.dimension = dimension
        
        if backend == "mock":
            self._impl = MockEmbedder(dimension)
        elif backend == "openai":
            self._impl = self._init_openai(model, api_key, dimension)
        elif backend == "huggingface":
            self._impl = self._init_huggingface(model, dimension)
        else:
            logger.warning(
                f"Unknown backend '{backend}', using mock embedder",
                extra={"backend": backend}
            )
            self._impl = MockEmbedder(dimension)
        
        logger.info(
            "Embedder initialized",
            extra={"backend": backend, "model": model, "dimension": dimension}
        )
    
    def _init_openai(
        self,
        model: str | None,
        api_key: str | None,
        dimension: int,
    ) -> Any:
        """Initialize OpenAI embedder."""
        try:
            import openai
            
            client = openai.OpenAI(api_key=api_key)
            
            class OpenAIEmbedder:
                def __init__(self, client, model: str, dimension: int):
                    self.client = client
                    self.model = model or "text-embedding-ada-002"
                    self.dimension = dimension
                
                def embed(self, text: str) -> list[float]:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=text,
                    )
                    return response.data[0].embedding
            
            return OpenAIEmbedder(client, model, dimension)
            
        except ImportError:
            logger.warning(
                "OpenAI package not installed, falling back to mock",
                extra={"backend": "openai"}
            )
            return MockEmbedder(dimension)
    
    def _init_huggingface(self, model: str | None, dimension: int) -> Any:
        """Initialize HuggingFace embedder."""
        try:
            from sentence_transformers import SentenceTransformer
            
            model_name = model or "all-MiniLM-L6-v2"
            hf_model = SentenceTransformer(model_name)
            
            class HFEmbedder:
                def __init__(self, model, dimension: int):
                    self.model = model
                    self.dimension = dimension
                
                def embed(self, text: str) -> list[float]:
                    embedding = self.model.encode(text)
                    return embedding.tolist()
            
            return HFEmbedder(hf_model, dimension)
            
        except ImportError:
            logger.warning(
                "sentence-transformers not installed, falling back to mock",
                extra={"backend": "huggingface"}
            )
            return MockEmbedder(dimension)
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding
        """
        return self._impl.embed(text)


# Global embedder instance
_embedder: Embedder | None = None


def get_embedder(
    backend: str = "auto",
    model: str | None = None,
    api_key: str | None = None,
    dimension: int = 384,
) -> Embedder:
    """Get or create global embedder instance.
    
    Args:
        backend: Backend type ('auto', 'huggingface', 'openai', 'mock')
            - auto: Automatically detect available backend (huggingface > mock)
            - huggingface: Use sentence-transformers
            - openai: Use OpenAI embeddings API
            - mock: Use mock embedder for testing
        model: Model name/ID
        api_key: API key for cloud services
        dimension: Embedding dimension
        
    Returns:
        Embedder instance
    """
    global _embedder
    if _embedder is None:
        actual_backend = backend
        
        if backend == "auto":
            # Try backends in order of preference
            try:
                from sentence_transformers import SentenceTransformer
                actual_backend = "huggingface"
                logger.info("Auto-detected huggingface backend (sentence-transformers)")
            except ImportError:
                actual_backend = "mock"
                logger.info("No huggingface available, using mock backend")
        
        _embedder = Embedder(backend=actual_backend, model=model, api_key=api_key, dimension=dimension)
    return _embedder


def init_embedder(
    backend: str = "auto",
    model: str | None = None,
    api_key: str | None = None,
    dimension: int = 384,
) -> Embedder:
    """Initialize global embedder instance.
    
    Args:
        backend: Backend type ('auto', 'huggingface', 'openai', 'mock')
        model: Model name/ID
        api_key: API key
        dimension: Embedding dimension
        
    Returns:
        Embedder instance
    """
    global _embedder
    
    actual_backend = backend
    if backend == "auto":
        try:
            from sentence_transformers import SentenceTransformer
            actual_backend = "huggingface"
        except ImportError:
            actual_backend = "mock"
    
    _embedder = Embedder(backend=actual_backend, model=model, api_key=api_key, dimension=dimension)
    return _embedder
