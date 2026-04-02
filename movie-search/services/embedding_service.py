"""Thread-safe singleton service for sentence embeddings.

This module provides a production-friendly wrapper around
``sentence_transformers.SentenceTransformer`` with:

- Lazy-safe singleton construction (single model instance in memory)
- Input normalization and truncation safeguards
- Consistent list-based output for downstream vector DB usage
- Robust logging and graceful fallback behavior for invalid inputs

Example:
    Basic usage for a single query::

        from services.embedding_service import EmbeddingService

        service = EmbeddingService()
        vector = service.embed_text("The Matrix is a sci-fi classic")
        print(len(vector))  # 384

    Batch usage::

        service = EmbeddingService()
        vectors = service.embed_batch([
            "Action movie with strong visuals",
            "Romantic comedy set in New York",
        ])
        print(len(vectors), len(vectors[0]))
"""

from __future__ import annotations

import logging
import math
import threading

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_DIMENSION = 384
MAX_TOKENS = 512
BATCH_SIZE = 32


class EmbeddingService:
    """Singleton embedding service backed by SentenceTransformers.

    The class guarantees that only one model object is instantiated in process
    memory, while keeping `encode` calls thread-safe for future async/multi-
    worker integration.

    Example:
        Single text embedding::

            service = EmbeddingService()
            embedding = service.embed_text("Inception explores layered dreams")
            assert len(embedding) == service.get_embedding_dimension()

        Batch embedding::

            service = EmbeddingService()
            embeddings = service.embed_batch(["A", "B", "C"])
            assert len(embeddings) == 3
    """

    _instance: EmbeddingService | None = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> EmbeddingService:
        """Create or return a singleton instance in a thread-safe manner."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize the embedding model once and log model metadata.

        Raises:
            RuntimeError: If the sentence-transformers model cannot be loaded.
        """
        if getattr(self, "_initialized", False):
            return

        with self._instance_lock:
            if getattr(self, "_initialized", False):
                return

            self._encode_lock = threading.RLock()
            try:
                self._model = SentenceTransformer(MODEL_NAME)
                self._embedding_dimension = int(
                    self._model.get_sentence_embedding_dimension()
                )
                self._max_seq_length = int(self._model.max_seq_length)
                logger.info(
                    "Loaded embedding model '%s' (dimension=%s, max_seq_length=%s)",
                    MODEL_NAME,
                    self._embedding_dimension,
                    self._max_seq_length,
                )
            except Exception as exc:
                logger.exception("Failed to load embedding model '%s'", MODEL_NAME)
                raise RuntimeError(
                    f"Unable to load embedding model '{MODEL_NAME}'"
                ) from exc

            self._initialized = True

    def embed_text(self, text: str) -> list[float]:
        """Embed one text string and return a normalized vector.

        Empty or invalid input returns a zero vector with this model's
        embedding dimension.

        Args:
            text: Input text to embed.

        Returns:
            A normalized embedding vector as a list of floats.

        Example:
            >>> service = EmbeddingService()
            >>> vec = service.embed_text("Interstellar explores space and time")
            >>> len(vec)
            384
        """
        if not isinstance(text, str) or not text.strip():
            logger.debug("Received empty or invalid text for embedding")
            return self._zero_vector()

        normalized_text = self._normalize_text(text)

        try:
            with self._encode_lock:
                encoded = self._model.encode(
                    normalized_text,
                    convert_to_numpy=False,
                    show_progress_bar=False,
                    batch_size=BATCH_SIZE,
                )
            vector = [float(value) for value in encoded]
            return self._normalize_vector(vector)
        except Exception:
            logger.exception("Failed to embed single text")
            return self._zero_vector()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many text strings efficiently using model batch encoding.

        Args:
            texts: Collection of text inputs.

        Returns:
            A list of normalized embedding vectors.

        Example:
            >>> service = EmbeddingService()
            >>> vectors = service.embed_batch(["Drama movie", "Comedy movie"])
            >>> len(vectors)
            2
            >>> len(vectors[0])
            384
        """
        if not texts:
            return []

        prepared_texts: list[str] = [self._normalize_text(text) for text in texts]
        valid_mask: list[bool] = [bool(text) for text in prepared_texts]

        if not any(valid_mask):
            return [self._zero_vector() for _ in texts]

        show_progress = len(texts) > 10

        try:
            with self._encode_lock:
                encoded_vectors = self._model.encode(
                    prepared_texts,
                    convert_to_numpy=False,
                    show_progress_bar=show_progress,
                    batch_size=BATCH_SIZE,
                )
        except Exception:
            logger.exception("Failed to embed text batch")
            return [self._zero_vector() for _ in texts]

        results: list[list[float]] = []
        for is_valid, raw_vector in zip(valid_mask, encoded_vectors):
            if not is_valid:
                results.append(self._zero_vector())
                continue

            vector = [float(value) for value in raw_vector]
            results.append(self._normalize_vector(vector))

        return results

    def get_embedding_dimension(self) -> int:
        """Return the embedding size used by this service.

        Returns:
            The static embedding dimension for ``all-MiniLM-L6-v2`` (384).

        Example:
            >>> service = EmbeddingService()
            >>> service.get_embedding_dimension()
            384
        """
        return MODEL_DIMENSION

    def _normalize_text(self, text: str) -> str:
        """Normalize and truncate text before embedding.

        Steps:
        1. Lowercase input.
        2. Collapse repeated whitespace.
        3. Truncate to 512 whitespace tokens.

        Args:
            text: Raw user or document text.

        Returns:
            Cleaned text ready for embedding.
        """
        if not isinstance(text, str):
            return ""

        normalized = " ".join(text.lower().split())
        if not normalized:
            return ""

        tokens = normalized.split(" ")
        if len(tokens) > MAX_TOKENS:
            logger.warning(
                "Input text truncated from %s tokens to %s tokens",
                len(tokens),
                MAX_TOKENS,
            )
            tokens = tokens[:MAX_TOKENS]
        return " ".join(tokens)

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        """Scale a vector to unit length; return zero vector for zero norm."""
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return self._zero_vector()
        return [value / norm for value in vector]

    def _zero_vector(self) -> list[float]:
        """Return a zero-filled vector matching the model dimension."""
        return [0.0] * self.get_embedding_dimension()