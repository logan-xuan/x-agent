"""Embedder module for generating text embeddings.

This module provides:
- ONNXEmbedder: ONNX Runtime based embedding (PyTorch-free)
- MockEmbedder: Simple embedder for testing (random embeddings)

All embedding functionality is self-contained in this module.
Only requires: onnxruntime, numpy
"""

import hashlib
import json
import os
import random
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from ._logger import get_memory_logger

logger = get_memory_logger(__name__)


class MockEmbedder:
    """Mock embedder for testing and development.
    
    Generates deterministic embeddings based on text content hash.
    Not suitable for production - use ONNX embedder.
    """
    
    EMBEDDING_DIM = 384
    
    def __init__(self, dimension: int = 384) -> None:
        """Initialize mock embedder.
        
        Args:
            dimension: Embedding dimension (default: 384)
        """
        self.dimension = dimension
        self._is_mock = True
        logger.info(
            "MockEmbedder initialized",
            extra={"dimension": dimension, "note": "Not suitable for production"}
        )
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        random.seed(text_hash)
        
        embedding = [random.gauss(0, 1) for _ in range(self.dimension)]
        magnitude = sum(x * x for x in embedding) ** 0.5
        
        return [x / magnitude for x in embedding]
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(text) for text in texts]


class ONNXEmbedder:
    """ONNX-based embedder using all-MiniLM-L6-v2.
    
    Downloads and uses a pre-converted ONNX model.
    No PyTorch required - only onnxruntime and numpy.
    """
    
    EMBEDDING_DIM = 384
    DEFAULT_MODEL_URL = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model.onnx"
    
    def __init__(self, model_path: str | None = None) -> None:
        """Initialize ONNX embedder.
        
        Args:
            model_path: Path to ONNX model file. If None, downloads default model.
        """
        self.model_path = model_path
        self._session: Any = None
        self._initialized = False
        
        logger.info(
            "ONNXEmbedder created",
            extra={"model_path": model_path or "default"}
        )
    
    def _load_model(self) -> Any:
        """Load the ONNX model."""
        if self._session is not None:
            return self._session
        
        try:
            import onnxruntime as ort
            
            providers = ['CPUExecutionProvider']
            
            if self.model_path and Path(self.model_path).exists():
                logger.info("Loading ONNX model from path", extra={"path": self.model_path})
                self._session = ort.InferenceSession(self.model_path, providers=providers)
            else:
                self._session = self._download_and_load_default_model(ort, providers)
            
            if self._session:
                self._initialized = True
                logger.info("ONNX model loaded successfully")
            
            return self._session
            
        except ImportError:
            logger.warning("onnxruntime not installed, cannot use ONNX embedder")
            return None
        except Exception as e:
            logger.error("Failed to load ONNX model", extra={"error": str(e)})
            return None
    
    def _download_and_load_default_model(self, ort: Any, providers: list[str]) -> Any:
        """Download and load the default ONNX model."""
        cache_dir = Path.home() / ".cache" / "x-agent" / "models"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        model_file = cache_dir / "all-MiniLM-L6-v2.onnx"
        
        if not model_file.exists():
            logger.info("Downloading ONNX model...", extra={"url": self.DEFAULT_MODEL_URL})
            try:
                urllib.request.urlretrieve(self.DEFAULT_MODEL_URL, model_file)
                logger.info("ONNX model downloaded", extra={"path": str(model_file)})
            except Exception as e:
                logger.error("Failed to download model", extra={"error": str(e)})
                return None
        
        return ort.InferenceSession(str(model_file), providers=providers)
    
    def _tokenize(self, text: str) -> dict[str, np.ndarray]:
        """Tokenize text for ONNX model.
        
        Uses bert-base-uncased tokenizer which is compatible with all-MiniLM-L6-v2.
        """
        try:
            from transformers import AutoTokenizer
            
            # Load tokenizer (cached after first download)
            tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
            
            # Tokenize with padding and truncation
            encoded = tokenizer(
                text,
                padding=True,
                truncation=True,
                max_length=256,
                return_tensors="np"
            )
            
            return {
                "input_ids": encoded["input_ids"].astype(np.int64),
                "attention_mask": encoded["attention_mask"].astype(np.int64),
                "token_type_ids": encoded.get("token_type_ids", np.zeros_like(encoded["input_ids"])).astype(np.int64),
            }
        except ImportError:
            logger.warning("transformers not installed, using fallback tokenization")
            return self._fallback_tokenize(text)
        except Exception as e:
            logger.error(f"Tokenization failed: {e}, using fallback")
            return self._fallback_tokenize(text)
    
    def _fallback_tokenize(self, text: str) -> dict[str, np.ndarray]:
        """Fallback character-based tokenization."""
        # Use character-level encoding as fallback
        chars = list(text.lower())[:256]
        
        # Simple char-to-id mapping (not ideal but better than hash)
        char_ids = [ord(c) % 30000 for c in chars]
        
        # Pad to reasonable length
        while len(char_ids) < 16:
            char_ids.append(0)
        
        input_ids = np.array([char_ids], dtype=np.int64)
        attention_mask = np.ones_like(input_ids, dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids, dtype=np.int64)
        
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (384 dimensions)
        """
        session = self._load_model()
        
        if session is None:
            logger.warning("ONNX session not available, using mock fallback")
            mock = MockEmbedder(self.EMBEDDING_DIM)
            return mock.embed(text)
        
        try:
            inputs = self._tokenize(text)
            outputs = session.run(None, inputs)
            
            output = outputs[0]
            if len(output.shape) == 3:
                embedding = output[0, 0, :]
            elif len(output.shape) == 2:
                if output.shape[0] == 1:
                    embedding = output[0]
                else:
                    embedding = output[0, :]
            else:
                embedding = output.flatten()[:self.EMBEDDING_DIM]
            
            if len(embedding) > self.EMBEDDING_DIM:
                embedding = embedding[:self.EMBEDDING_DIM]
            elif len(embedding) < self.EMBEDDING_DIM:
                embedding = np.pad(embedding, (0, self.EMBEDDING_DIM - len(embedding)))
            
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            
            return embedding.tolist()
            
        except Exception as e:
            logger.error("Failed to generate embedding", extra={"error": str(e)})
            mock = MockEmbedder(self.EMBEDDING_DIM)
            return mock.embed(text)
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(text) for text in texts]


class Embedder:
    """Main embedder interface.
    
    Uses ONNX Runtime by default, with Mock fallback.
    PyTorch-free implementation.
    """
    
    EMBEDDING_DIM = 384
    
    def __init__(
        self,
        backend: str = "auto",
        model_path: str | None = None,
        dimension: int = 384,
    ) -> None:
        """Initialize embedder.
        
        Args:
            backend: Backend type ('onnx', 'mock')
            model_path: Path to ONNX model (optional)
            dimension: Embedding dimension
        """
        self.backend = backend
        self.model_path = model_path
        self.dimension = dimension
        self._impl: Any = None
        
        if backend == "mock":
            self._impl = MockEmbedder(dimension)
        elif backend == "onnx" or backend == "auto":
            self._impl = self._init_onnx(model_path, dimension)
        else:
            logger.warning(f"Unknown backend '{backend}', using ONNX")
            self._impl = self._init_onnx(model_path, dimension)
        
        logger.info(
            "Embedder initialized",
            extra={"backend": backend, "dimension": dimension}
        )
    
    def _init_onnx(self, model_path: str | None, dimension: int) -> Any:
        """Initialize ONNX embedder."""
        try:
            embedder = ONNXEmbedder(model_path)
            # Test if it works
            test_embedding = embedder.embed("test")
            if len(test_embedding) == dimension:
                logger.info("ONNX embedder initialized successfully")
                return embedder
            else:
                raise ValueError(f"Unexpected embedding dimension: {len(test_embedding)}")
        except Exception as e:
            logger.warning(
                f"ONNX embedder failed: {e}, falling back to mock",
                extra={"error": str(e)}
            )
            return MockEmbedder(dimension)
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return self._impl.embed(text)
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return self._impl.embed_batch(texts)


# Global embedder instance
_embedder: Embedder | None = None


def get_embedder(
    backend: str = "auto",
    model_path: str | None = None,
    dimension: int = 384,
) -> Embedder:
    """Get or create global embedder instance.
    
    Args:
        backend: Backend type ('auto', 'onnx', 'mock')
            - auto: Try ONNX first, fallback to mock
            - onnx: Use ONNX Runtime
            - mock: Use mock embedder
        model_path: Path to ONNX model file
        dimension: Embedding dimension
        
    Returns:
        Embedder instance
    """
    global _embedder
    if _embedder is None:
        _embedder = Embedder(backend=backend, model_path=model_path, dimension=dimension)
    return _embedder


def init_embedder(
    backend: str = "auto",
    model_path: str | None = None,
    dimension: int = 384,
) -> Embedder:
    """Initialize global embedder instance.
    
    Args:
        backend: Backend type ('auto', 'onnx', 'mock')
        model_path: Path to ONNX model
        dimension: Embedding dimension
        
    Returns:
        Embedder instance
    """
    global _embedder
    _embedder = Embedder(backend=backend, model_path=model_path, dimension=dimension)
    return _embedder
