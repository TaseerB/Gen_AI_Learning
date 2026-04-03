"""Persistent repository for storing and querying movie embeddings in ChromaDB.

Example:
    Add and query one movie embedding::

        from repositories.chroma_repository import ChromaRepository
        from services.embedding_service import EmbeddingService

        embedding_service = EmbeddingService()
        repository = ChromaRepository()

        text = "A hacker discovers reality is a simulation."
        embedding = embedding_service.embed_text(text)
        repository.add_movie(
            movie_id=1,
            text=text,
            embedding=embedding,
            metadata={
                "title": "The Matrix",
                "year": 1999,
                "rating": 8.7,
                "genres": ["Action", "Sci-Fi"],
            },
        )

        results = repository.search_by_text("simulation action movie", top_k=5)
        print(results[0]["metadata"])
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection
from tqdm import tqdm

from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "movies"
DEFAULT_PERSIST_DIRECTORY = "data/chroma"
BATCH_SIZE = 100
REQUIRED_METADATA_KEYS = ("title", "year", "rating", "genres")

MetadataPrimitive = str | int | float | bool
MetadataInputValue = MetadataPrimitive | list[str] | tuple[str, ...] | set[str] | None
MetadataInput = dict[str, MetadataInputValue]
MetadataOutput = dict[str, MetadataPrimitive]
SearchFilter = dict[str, object]
SearchResult = dict[str, object]
MovieEmbeddingRecord = dict[str, object]


class ChromaRepositoryError(Exception):
    """Raised when ChromaRepository operations fail."""


class ChromaRepository:
    """Repository for persistent movie embeddings stored in ChromaDB.

    This repository wraps Chroma's persistent client behind an application-
    friendly API with dimension validation, logging, and thread-safe access.

    Example:
        Basic usage::

            repository = ChromaRepository(collection_name="movies")
            repository.count()

        Filtered search::

            results = repository.search(
                query_embedding=[0.1] * 384,
                top_k=10,
                filter_dict={"rating": {"$gte": 8.0}},
            )
            for result in results:
                print(result["id"], result["distance"])
    """

    def __init__(
        self,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
    ) -> None:
        """Initialize the persistent Chroma collection.

        Args:
            collection_name: Name of the Chroma collection to use.
            persist_directory: Relative or absolute path for persistent Chroma data.

        Raises:
            ChromaRepositoryError: If the Chroma client or collection cannot be initialized.
        """
        self._collection_name = collection_name.strip() or DEFAULT_COLLECTION_NAME
        self._persist_directory = self._resolve_persist_directory(persist_directory)
        self._persist_directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._embedding_service = EmbeddingService()
        self._embedding_dimension = self._embedding_service.get_embedding_dimension()

        try:
            self._client = chromadb.PersistentClient(path=str(self._persist_directory))
            self._collection: Collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"embedding_dimension": self._embedding_dimension},
            )
        except Exception as exc:
            logger.exception(
                "Failed to initialize Chroma collection '%s' at %s",
                self._collection_name,
                self._persist_directory,
            )
            raise ChromaRepositoryError(
                f"Failed to initialize Chroma collection '{self._collection_name}'"
            ) from exc

        logger.info(
            "Initialized Chroma collection '%s' at %s (dimension=%s)",
            self._collection_name,
            self._persist_directory,
            self._embedding_dimension,
        )

    def add_movie(
        self,
        movie_id: int,
        text: str,
        embedding: list[float],
        metadata: MetadataInput,
    ) -> None:
        """Add or update one movie embedding in the collection.

        Args:
            movie_id: Unique movie identifier.
            text: Source text associated with the embedding.
            embedding: Embedding vector matching the configured model dimension.
            metadata: Flat movie metadata including title, year, rating, and genres.

        Raises:
            ChromaRepositoryError: If validation fails or Chroma upsert fails.

        Example:
            >>> repository = ChromaRepository()
            >>> repository.add_movie(
            ...     movie_id=42,
            ...     text="A time-bending sci-fi thriller.",
            ...     embedding=[0.0] * 384,
            ...     metadata={
            ...         "title": "Tenet",
            ...         "year": 2020,
            ...         "rating": 7.3,
            ...         "genres": ["Action", "Sci-Fi"],
            ...     },
            ... )
        """
        record_id = self._normalize_movie_id(movie_id)
        validated_text = self._validate_text(text)
        validated_embedding = self._validate_embedding(embedding)
        sanitized_metadata = self._sanitize_metadata(metadata)

        try:
            with self._lock:
                self._collection.upsert(
                    ids=[record_id],
                    documents=[validated_text],
                    embeddings=[validated_embedding],
                    metadatas=[sanitized_metadata],
                )
        except Exception as exc:
            logger.exception("Failed to upsert movie id=%s into Chroma", movie_id)
            raise ChromaRepositoryError(f"Failed to add movie id={movie_id}") from exc

        logger.info("Upserted movie id=%s into Chroma collection", movie_id)

    def add_movies_batch(self, movies: list[MovieEmbeddingRecord]) -> None:
        """Batch upsert many movies into the collection.

        Each payload must contain `id`, `text`, `embedding`, and `metadata` keys.

        Args:
            movies: Batch payload for Chroma upsert operations.

        Raises:
            ChromaRepositoryError: If payload validation or Chroma upsert fails.

        Example:
            >>> repository = ChromaRepository()
            >>> repository.add_movies_batch([
            ...     {
            ...         "id": 1,
            ...         "text": "Dream infiltration thriller",
            ...         "embedding": [0.0] * 384,
            ...         "metadata": {
            ...             "title": "Inception",
            ...             "year": 2010,
            ...             "rating": 8.8,
            ...             "genres": ["Action", "Thriller"],
            ...         },
            ...     }
            ... ])
        """
        if not movies:
            logger.debug("Received empty batch for Chroma upsert")
            return

        prepared_records: list[tuple[str, str, list[float], MetadataOutput]] = []
        for movie in movies:
            prepared_records.append(self._prepare_batch_record(movie))

        try:
            with self._lock:
                for start in tqdm(
                    range(0, len(prepared_records), BATCH_SIZE),
                    desc="Upserting Chroma records",
                    unit="batch",
                ):
                    chunk = prepared_records[start : start + BATCH_SIZE]
                    self._collection.upsert(
                        ids=[record[0] for record in chunk],
                        documents=[record[1] for record in chunk],
                        embeddings=[record[2] for record in chunk],
                        metadatas=[record[3] for record in chunk],
                    )
        except Exception as exc:
            logger.exception("Failed to batch upsert %s Chroma records", len(movies))
            raise ChromaRepositoryError("Failed to batch add movies") from exc

        logger.info("Upserted %s movie embeddings into Chroma", len(prepared_records))

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        filter_dict: SearchFilter | None = None,
    ) -> list[SearchResult]:
        """Search for the most similar movies by embedding.

        Args:
            query_embedding: Query vector matching the configured embedding dimension.
            top_k: Maximum number of results to return.
            filter_dict: Optional Chroma `where` filter.

        Returns:
            A list of dictionaries with `id`, `distance`, and `metadata` keys.

        Raises:
            ChromaRepositoryError: If search validation or execution fails.

        Example:
            >>> repository = ChromaRepository()
            >>> results = repository.search(
            ...     query_embedding=[0.0] * 384,
            ...     top_k=5,
            ...     filter_dict={"year": {"$gte": 2020}},
            ... )
        """
        if top_k <= 0:
            return []

        validated_embedding = self._validate_embedding(query_embedding)

        try:
            with self._lock:
                response = self._collection.query(
                    query_embeddings=[validated_embedding],
                    n_results=top_k,
                    where=filter_dict,
                    include=["metadatas", "distances"],
                )
        except Exception as exc:
            logger.exception("Failed Chroma search top_k=%s filter=%s", top_k, filter_dict)
            raise ChromaRepositoryError("Failed to search Chroma collection") from exc

        results = self._format_search_results(response)
        logger.info("Chroma search returned %s result(s)", len(results))
        return results

    def search_by_text(self, query_text: str, top_k: int = 10) -> list[SearchResult]:
        """Embed a text query and search for similar movies.

        Args:
            query_text: Natural language movie query.
            top_k: Maximum number of results to return.

        Returns:
            Search results from :meth:`search`.

        Example:
            >>> repository = ChromaRepository()
            >>> repository.search_by_text("mind-bending science fiction", top_k=3)
        """
        if not isinstance(query_text, str) or not query_text.strip():
            logger.debug("Received empty text query for Chroma search")
            return []

        query_embedding = self._embedding_service.embed_text(query_text)
        return self.search(query_embedding=query_embedding, top_k=top_k)

    def get_by_id(self, movie_id: int) -> SearchResult | None:
        """Fetch one stored movie record by ID.

        Args:
            movie_id: Movie identifier.

        Returns:
            A dictionary containing `id`, `text`, and `metadata`, or `None`.

        Raises:
            ChromaRepositoryError: If retrieval fails.
        """
        record_id = self._normalize_movie_id(movie_id)

        try:
            with self._lock:
                response = self._collection.get(ids=[record_id], include=["metadatas", "documents"])
        except Exception as exc:
            logger.exception("Failed to fetch movie id=%s from Chroma", movie_id)
            raise ChromaRepositoryError(f"Failed to fetch movie id={movie_id}") from exc

        ids = response.get("ids") or []
        if not ids:
            logger.info("Chroma movie id=%s not found", movie_id)
            return None

        documents = response.get("documents") or []
        metadatas = response.get("metadatas") or []
        return {
            "id": self._deserialize_movie_id(ids[0]),
            "text": documents[0] if documents else "",
            "metadata": metadatas[0] if metadatas else {},
        }

    def delete(self, movie_id: int) -> bool:
        """Delete one movie embedding from the collection.

        Args:
            movie_id: Movie identifier.

        Returns:
            `True` when a record was deleted, else `False`.

        Raises:
            ChromaRepositoryError: If deletion fails.
        """
        if self.get_by_id(movie_id) is None:
            return False

        record_id = self._normalize_movie_id(movie_id)
        try:
            with self._lock:
                self._collection.delete(ids=[record_id])
        except Exception as exc:
            logger.exception("Failed to delete movie id=%s from Chroma", movie_id)
            raise ChromaRepositoryError(f"Failed to delete movie id={movie_id}") from exc

        logger.info("Deleted Chroma movie id=%s", movie_id)
        return True

    def count(self) -> int:
        """Return the number of stored embeddings."""
        try:
            with self._lock:
                total = int(self._collection.count())
        except Exception as exc:
            logger.exception("Failed to count Chroma records")
            raise ChromaRepositoryError("Failed to count Chroma records") from exc

        logger.info("Chroma collection count=%s", total)
        return total

    def reset(self) -> None:
        """Delete and recreate the current collection.

        This is intended for tests and local development utilities.

        Raises:
            ChromaRepositoryError: If the collection cannot be recreated.
        """
        try:
            with self._lock:
                self._client.delete_collection(self._collection_name)
                self._collection = self._client.get_or_create_collection(
                    name=self._collection_name,
                    metadata={"embedding_dimension": self._embedding_dimension},
                )
        except Exception as exc:
            logger.exception("Failed to reset Chroma collection '%s'", self._collection_name)
            raise ChromaRepositoryError("Failed to reset Chroma collection") from exc

        logger.info("Reset Chroma collection '%s'", self._collection_name)

    def _resolve_persist_directory(self, persist_directory: str) -> Path:
        """Resolve the persistent Chroma directory relative to the app root."""
        candidate = Path(persist_directory)
        if candidate.is_absolute():
            return candidate
        return Path(__file__).resolve().parents[1] / candidate

    def _prepare_batch_record(
        self,
        movie: MovieEmbeddingRecord,
    ) -> tuple[str, str, list[float], MetadataOutput]:
        """Validate and normalize one batch payload."""
        raw_id = movie.get("id")
        raw_text = movie.get("text")
        raw_embedding = movie.get("embedding")
        raw_metadata = movie.get("metadata")

        if not isinstance(raw_id, int):
            raise ChromaRepositoryError("Batch movie payload requires integer 'id'")
        if not isinstance(raw_text, str):
            raise ChromaRepositoryError(f"Batch movie id={raw_id} requires string 'text'")
        if not isinstance(raw_embedding, list):
            raise ChromaRepositoryError(f"Batch movie id={raw_id} requires list 'embedding'")
        if not isinstance(raw_metadata, dict):
            raise ChromaRepositoryError(f"Batch movie id={raw_id} requires dict 'metadata'")

        return (
            self._normalize_movie_id(raw_id),
            self._validate_text(raw_text),
            self._validate_embedding([float(value) for value in raw_embedding]),
            self._sanitize_metadata(raw_metadata),
        )

    def _normalize_movie_id(self, movie_id: int) -> str:
        """Convert a numeric movie ID to the string ID used by Chroma."""
        if not isinstance(movie_id, int) or movie_id <= 0:
            raise ChromaRepositoryError(f"movie_id must be a positive integer, got {movie_id!r}")
        return str(movie_id)

    def _deserialize_movie_id(self, movie_id: str) -> int | str:
        """Convert stored Chroma IDs back to integers when possible."""
        try:
            return int(movie_id)
        except ValueError:
            return movie_id

    def _validate_text(self, text: str) -> str:
        """Validate text payloads before persistence."""
        cleaned = text.strip()
        if not cleaned:
            raise ChromaRepositoryError("Movie text must be a non-empty string")
        return cleaned

    def _validate_embedding(self, embedding: list[float]) -> list[float]:
        """Validate embedding shape and convert values to floats."""
        if len(embedding) != self._embedding_dimension:
            raise ChromaRepositoryError(
                f"Embedding dimension {len(embedding)} does not match expected {self._embedding_dimension}"
            )

        try:
            return [float(value) for value in embedding]
        except (TypeError, ValueError) as exc:
            raise ChromaRepositoryError("Embedding contains non-numeric values") from exc

    def _sanitize_metadata(self, metadata: MetadataInput) -> MetadataOutput:
        """Normalize metadata into Chroma-compatible primitive values."""
        missing = [key for key in REQUIRED_METADATA_KEYS if key not in metadata]
        if missing:
            raise ChromaRepositoryError(
                f"Metadata must include {', '.join(REQUIRED_METADATA_KEYS)}; missing {', '.join(missing)}"
            )

        sanitized: MetadataOutput = {}
        for key, value in metadata.items():
            converted = self._coerce_metadata_value(value)
            if converted is not None:
                sanitized[str(key)] = converted
        return sanitized

    def _coerce_metadata_value(self, value: object) -> MetadataPrimitive | None:
        """Convert metadata values into Chroma-supported primitives."""
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (str, int, float)):
            return value
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _format_search_results(self, response: dict[str, object]) -> list[SearchResult]:
        """Normalize Chroma query payloads into the repository response shape."""
        nested_ids = response.get("ids")
        nested_distances = response.get("distances")
        nested_metadatas = response.get("metadatas")

        if not isinstance(nested_ids, list) or not nested_ids:
            return []

        ids = nested_ids[0] if isinstance(nested_ids[0], list) else []
        distances = (
            nested_distances[0]
            if isinstance(nested_distances, list) and nested_distances and isinstance(nested_distances[0], list)
            else []
        )
        metadatas = (
            nested_metadatas[0]
            if isinstance(nested_metadatas, list) and nested_metadatas and isinstance(nested_metadatas[0], list)
            else []
        )

        results: list[SearchResult] = []
        for index, item_id in enumerate(ids):
            if not isinstance(item_id, str):
                continue
            distance = distances[index] if index < len(distances) else None
            metadata = metadatas[index] if index < len(metadatas) else {}
            results.append(
                {
                    "id": self._deserialize_movie_id(item_id),
                    "distance": float(distance) if isinstance(distance, (int, float)) else None,
                    "metadata": metadata if isinstance(metadata, dict) else {},
                }
            )
        return results