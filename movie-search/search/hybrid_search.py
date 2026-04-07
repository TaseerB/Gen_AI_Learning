"""Hybrid search engine combining vector similarity with SQL filtering and ranking strategies.

This module provides a `HybridSearchEngine` that combines ChromaDB vector embeddings with
SQL-based filtering from MovieRepository. It supports multiple ranking strategies (semantic,
rating, hybrid, recency), complex filtering (genres, runtime, rating ranges, release dates),
and genre diversity enforcement to provide diverse, high-quality movie search results.

Architecture:
    1. Generate embedding from natural language query
    2. Oversample top 100 candidates from ChromaDB with simple filters
    3. Fetch full Movie objects from MovieRepository
    4. Apply complex SQL filters (genres, runtime)
    5. Score movies based on selected ranking strategy
    6. Enforce genre diversity to maximize variety
    7. Return top_k results sorted by final score
    8. Fallback to keyword search if ChromaDB has no candidates

Example:
    Basic hybrid search with default settings::

        from search.hybrid_search import HybridSearchEngine
        from repositories.chroma_repository import ChromaRepository
        from repositories.movie_repository import MovieRepository
        from services.embedding_service import EmbeddingService

        chroma_repo = ChromaRepository()
        movie_repo = MovieRepository()
        embedding_service = EmbeddingService()

        engine = HybridSearchEngine(chroma_repo, movie_repo, embedding_service)
        results = engine.search(
            query="mind-bending sci-fi thriller",
            top_k=10
        )
        for movie in results:
            print(f"{movie.title} ({movie.release_date[:4]}) - Score: {movie.search_score:.2f}")

    Search with complex filters and custom ranking::

        results = engine.search(
            query="action movie",
            filters={
                "min_rating": 7.5,
                "max_rating": 10.0,
                "min_year": 2015,
                "max_year": 2024,
                "genres": ["Action", "Sci-Fi"],
                "runtime_range": (90, 180),
            },
            top_k=15,
            ranking_strategy="hybrid",
            ranking_weights={"similarity": 0.75, "rating": 0.25},
        )

    Using different ranking strategies::

        # Pure semantic similarity
        semantic_results = engine.search(query, ranking_strategy="semantic", top_k=10)

        # Rating-focused
        rating_results = engine.search(query, ranking_strategy="rating", top_k=10)

        # Recency boost (favors recent movies)
        recent_results = engine.search(query, ranking_strategy="recency", top_k=10)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from math import exp
from typing import TypeAlias

from models.movie import Movie
from repositories.chroma_repository import ChromaRepository
from repositories.movie_repository import MovieRepository
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Type aliases
FilterDict: TypeAlias = dict[str, object]
RankingWeights: TypeAlias = dict[str, float]
SearchResultWithScore: TypeAlias = dict[str, object]

# Constants
OVERSAMPLE_SIZE = 100
DEFAULT_WEIGHTS: dict[str, RankingWeights] = {
    "semantic": {"similarity": 1.0},
    "rating": {"rating": 1.0},
    "hybrid": {"similarity": 0.7, "rating": 0.3},
    "recency": {"recency": 1.0},
}
VALID_STRATEGIES = frozenset(DEFAULT_WEIGHTS.keys())
RECENCY_DECAY_YEARS = 1.0  # Half-life for exponential decay in years


class HybridSearchError(Exception):
    """Raised when hybrid search operations fail."""


class HybridSearchEngine:
    """Engine for hybrid movie search combining vector embeddings and SQL filtering.

    This engine orchestrates three core components:
        - ChromaRepository: Vector similarity search via embeddings
        - MovieRepository: Detailed movie data and SQL filtering
        - EmbeddingService: Text-to-embedding conversion

    It implements multiple ranking strategies, complex filtering, and diversity enforcement
    to deliver high-quality, varied search results.

    Args:
        chroma_repository: ChromaRepository instance for vector search.
        movie_repository: MovieRepository instance for data access and filtering.
        embedding_service: EmbeddingService instance for text embedding.

    Attributes:
        default_weights (dict[str, dict[str, float]]): Default ranking weights per strategy.

    Raises:
        HybridSearchError: If initialization fails or search operations error.

    Example:
        >>> from search.hybrid_search import HybridSearchEngine
        >>> engine = HybridSearchEngine(chroma_repo, movie_repo, embedding_service)
        >>> results = engine.search("space adventure", top_k=10)
        >>> print(f"Found {len(results)} movies")
    """

    def __init__(
        self,
        chroma_repository: ChromaRepository,
        movie_repository: MovieRepository,
        embedding_service: EmbeddingService,
    ) -> None:
        """Initialize the hybrid search engine with three core dependencies.

        Args:
            chroma_repository: ChromaRepository instance for vector search.
            movie_repository: MovieRepository instance for data access.
            embedding_service: EmbeddingService instance for embeddings.

        Raises:
            HybridSearchError: If any dependency is invalid.
        """
        if not chroma_repository:
            raise HybridSearchError("ChromaRepository cannot be None")
        if not movie_repository:
            raise HybridSearchError("MovieRepository cannot be None")
        if not embedding_service:
            raise HybridSearchError("EmbeddingService cannot be None")

        self._chroma = chroma_repository
        self._movie_repo = movie_repository
        self._embedding = embedding_service
        self.default_weights = DEFAULT_WEIGHTS
        logger.debug("HybridSearchEngine initialized with all dependencies")

    def search(
        self,
        query: str,
        filters: FilterDict | None = None,
        top_k: int = 10,
        ranking_strategy: str = "hybrid",
        ranking_weights: RankingWeights | None = None,
    ) -> list[Movie]:
        """Search for movies using hybrid vector + SQL filtering with customizable ranking.

        This method orchestrates the complete search pipeline:
            1. Validates inputs and normalizes query
            2. Generates query embedding
            3. Oversamples top 100 candidates from ChromaDB
            4. Loads full Movie objects from database
            5. Applies complex filtering (genres, runtime)
            6. Scores results based on ranking strategy
            7. Enforces genre diversity
            8. Returns top_k sorted results with scores attached

        Args:
            query: Natural language search query (e.g., "mind-bending sci-fi").
            filters: Optional filtering constraints with keys:
                - min_rating (float): Minimum vote_average (0-10)
                - max_rating (float): Maximum vote_average (0-10)
                - min_year (int): Earliest release year (YYYY format)
                - max_year (int): Latest release year (YYYY format)
                - genres (list[str]): Genre names; matches ANY (OR logic)
                - runtime_range (tuple[int, int]): Min and max runtime in minutes
            top_k: Number of results to return (default 10, must be > 0).
            ranking_strategy: Ranking approach to apply:
                - "semantic": Pure embedding similarity
                - "rating": Movie rating/vote_average normalized to 0-1
                - "hybrid": Weighted combination (default 0.7 similarity + 0.3 rating)
                - "recency": Exponential decay favoring recent releases
            ranking_weights: Custom weights for the selected strategy, overriding defaults.
                For "hybrid": {"similarity": 0.7, "rating": 0.3} (must sum to 1.0).
                For "recency": {"recency": 1.0, "similarity": 0.3} (can include similarity).

        Returns:
            List of Movie objects sorted by final score (highest first).
            Each movie has a `search_score` attribute attached (0-1 normalized).

        Raises:
            HybridSearchError: If search fails or ranking strategy is invalid.

        Example:
            >>> results = engine.search(
            ...     query="time travel drama",
            ...     filters={"min_year": 2010, "genres": ["Drama"]},
            ...     top_k=10,
            ...     ranking_strategy="hybrid",
            ... )
            >>> for movie in results:
            ...     print(f"{movie.title}: {movie.search_score:.2f}")
        """
        logger.info(
            "search() called: query=%r, filters=%s, strategy=%s, top_k=%s",
            query,
            filters,
            ranking_strategy,
            top_k,
        )

        # Step 0: Validate inputs
        if not isinstance(query, str) or not query.strip():
            logger.debug("Received empty query, returning empty results")
            return []

        if top_k <= 0:
            logger.warning("Invalid top_k=%s, must be > 0", top_k)
            return []

        if ranking_strategy not in VALID_STRATEGIES:
            raise HybridSearchError(
                f"Invalid ranking_strategy={ranking_strategy!r}. "
                f"Must be one of {sorted(VALID_STRATEGIES)}"
            )

        normalized_query = query.strip()

        # Step 1: Generate query embedding
        try:
            query_embedding = self._embedding.embed_text(normalized_query)
        except Exception as exc:
            logger.exception("Failed to generate embedding for query=%r", normalized_query)
            raise HybridSearchError(f"Failed to embed query") from exc

        # Step 2: Build Chroma filter for simple filters (rating, year)
        chroma_filter = self._build_chroma_filter(filters)

        # Step 3: Oversample from ChromaDB with simple filters
        try:
            chroma_results = self._chroma.search(
                query_embedding=query_embedding,
                top_k=OVERSAMPLE_SIZE,
                filter_dict=chroma_filter,
            )
            logger.info("Chroma search returned %s candidates", len(chroma_results))
        except Exception as exc:
            logger.exception("Failed to search Chroma with embedding")
            chroma_results = []

        # Step 4: Handle fallback if no Chroma results
        if not chroma_results:
            logger.info(
                "Chroma returned 0 candidates, falling back to keyword search for query=%r",
                normalized_query,
            )
            try:
                fallback_results = self._movie_repo.find_by_keywords(
                    query=normalized_query, limit=top_k
                )
                logger.info("Keyword fallback search returned %s results", len(fallback_results))

                # Attach dummy scores for consistency
                for movie in fallback_results:
                    movie.search_score = 0.5  # type: ignore
                return fallback_results[:top_k]
            except Exception as exc:
                logger.exception("Fallback keyword search also failed")
                raise HybridSearchError("Both vector and keyword search failed") from exc

        # Step 5: Extract movie IDs and build similarity map
        similarity_map: dict[int, float] = {}
        candidate_ids: list[int] = []
        for result in chroma_results:
            movie_id = result.get("id")
            distance = result.get("distance")
            if isinstance(movie_id, int) and isinstance(distance, (int, float)):
                candidate_ids.append(movie_id)
                # Normalize distance to similarity (assuming cosine: lower is better)
                similarity_map[movie_id] = 1.0 - float(distance)

        if not candidate_ids:
            logger.warning("Chroma returned results but no valid movie IDs extracted")
            return []

        logger.debug("Extracted %s candidate IDs from Chroma results", len(candidate_ids))

        # Step 6: Fetch full Movie objects from repository
        movies_by_id: dict[int, Movie] = {}
        for movie_id in candidate_ids:
            try:
                movie = self._movie_repo.find_by_id(movie_id)
                if movie:
                    movies_by_id[movie_id] = movie
            except Exception as exc:
                logger.warning("Failed to load movie id=%s from repository", movie_id, exc_info=exc)

        if not movies_by_id:
            logger.error("Could not load any movies from repository")
            raise HybridSearchError("Failed to load movie details from database")

        candidate_movies = [movies_by_id[mid] for mid in candidate_ids if mid in movies_by_id]
        logger.info(
            "Loaded %s full Movie objects from repository (matched %s from candidates)",
            len(candidate_movies),
            len(candidate_ids),
        )

        # Step 7: Apply complex filters (genres, runtime)
        if filters:
            candidate_movies = self._apply_complex_filters(candidate_movies, filters)
            logger.info(
                "After complex filters (genres, runtime): %s movies remain", len(candidate_movies)
            )

        if not candidate_movies:
            logger.info(
                "No movies remain after filtering. Consider relaxing filters: %s", filters
            )
            return []

        # Step 8: Score movies based on ranking strategy
        weights = ranking_weights or self.default_weights.get(ranking_strategy, {})
        scored_movies: list[tuple[Movie, float]] = []

        for movie in candidate_movies:
            similarity = similarity_map.get(movie.id, 0.0)
            score = self._calculate_score(
                movie=movie,
                similarity=similarity,
                strategy=ranking_strategy,
                weights=weights,
            )
            scored_movies.append((movie, score))

        logger.debug("Scored %s movies with strategy=%s", len(scored_movies), ranking_strategy)

        # Step 9: Apply diversity enforcement
        reranked = self._apply_diversity(scored_movies)
        logger.debug("Applied diversity enforcement, %s results remain", len(reranked))

        # Step 10: Sort by score, take top_k, and attach scores to Movie objects
        final_results: list[Movie] = []
        for i, (movie, score) in enumerate(reranked[:top_k]):
            movie.search_score = score  # type: ignore
            final_results.append(movie)
            if i == 0:
                logger.debug("Top result: %r (score=%.3f)", movie.title, score)

        logger.info("search() returning %s results", len(final_results))
        return final_results

    def _build_chroma_filter(self, filters: FilterDict | None) -> dict[str, object] | None:
        """Convert simple filters (rating, year) to Chroma metadata `where` format.

        Chroma supports simple metadata filtering via `where` dict with operators like
        $gte (>=), $lte (<=). This method extracts simple filters (rating, year) and
        builds the appropriate structure.

        Args:
            filters: User-provided filter dict with optional keys:
                - min_rating, max_rating, min_year, max_year

        Returns:
            Chroma `where` filter dict, or None if no simple filters.

        Example:
            >>> filters = {"min_rating": 7.5, "max_year": 2024}
            >>> chroma_filter = engine._build_chroma_filter(filters)
            >>> # Returns: {"rating": {"$gte": 7.5}, "year": {"$lte": 2024}}
        """
        if not filters:
            return None

        chroma_filter: dict[str, object] = {}

        # Handle rating range
        min_rating = filters.get("min_rating")
        max_rating = filters.get("max_rating")

        if isinstance(min_rating, (int, float)):
            chroma_filter.setdefault("rating", {})
            if isinstance(chroma_filter["rating"], dict):
                chroma_filter["rating"]["$gte"] = min_rating  # type: ignore

        if isinstance(max_rating, (int, float)):
            chroma_filter.setdefault("rating", {})
            if isinstance(chroma_filter["rating"], dict):
                chroma_filter["rating"]["$lte"] = max_rating  # type: ignore

        # Handle year range (convert to date-based filtering)
        min_year = filters.get("min_year")
        max_year = filters.get("max_year")

        if isinstance(min_year, int):
            chroma_filter.setdefault("year", {})
            if isinstance(chroma_filter["year"], dict):
                chroma_filter["year"]["$gte"] = min_year  # type: ignore

        if isinstance(max_year, int):
            chroma_filter.setdefault("year", {})
            if isinstance(chroma_filter["year"], dict):
                chroma_filter["year"]["$lte"] = max_year  # type: ignore

        result = chroma_filter if chroma_filter else None
        logger.debug("Built Chroma filter: %s", result)
        return result

    def _apply_complex_filters(
        self, movies: list[Movie], filters: FilterDict
    ) -> list[Movie]:
        """Apply complex in-memory filters (genres, runtime) to candidate movies.

        After fetching full Movie objects, this applies more complex filtering that
        requires parsed movie data (genres as list, runtime as integer).

        Args:
            movies: List of candidate Movie objects.
            filters: Dict with optional keys:
                - genres (list[str]): Match ANY genre (OR logic)
                - runtime_range (tuple[int, int]): Min and max runtime in minutes

        Returns:
            Filtered list of movies meeting all constraints.

        Example:
            >>> filters = {"genres": ["Action", "Sci-Fi"], "runtime_range": (90, 180)}
            >>> filtered = engine._apply_complex_filters(movies, filters)
        """
        filtered = movies

        # Genre filter: keep movies matching ANY provided genre (OR logic)
        genres_filter = filters.get("genres")
        if isinstance(genres_filter, list) and genres_filter:
            filtered_genres: list[Movie] = []
            for movie in filtered:
                movie_genres = movie.genres or []
                if any(g in movie_genres for g in genres_filter):
                    filtered_genres.append(movie)
            logger.debug(
                "Genre filter reduced %s → %s movies", len(filtered), len(filtered_genres)
            )
            filtered = filtered_genres

        # Runtime range filter
        runtime_range = filters.get("runtime_range")
        if isinstance(runtime_range, tuple) and len(runtime_range) == 2:
            min_runtime, max_runtime = runtime_range
            if isinstance(min_runtime, int) and isinstance(max_runtime, int):
                filtered_runtime: list[Movie] = []
                for movie in filtered:
                    runtime = movie.runtime or 0
                    if min_runtime <= runtime <= max_runtime:
                        filtered_runtime.append(movie)
                logger.debug(
                    "Runtime filter [%s-%s] reduced %s → %s movies",
                    min_runtime,
                    max_runtime,
                    len(filtered),
                    len(filtered_runtime),
                )
                filtered = filtered_runtime

        return filtered

    def _calculate_score(
        self,
        movie: Movie,
        similarity: float,
        strategy: str,
        weights: RankingWeights | None = None,
    ) -> float:
        """Calculate final score for a movie based on ranking strategy and weights.

        This method implements four ranking strategies:
            - semantic: Pure embedding similarity (0-1)
            - rating: Normalized vote_average (0-1)
            - hybrid: Weighted combination of similarity and rating
            - recency: Exponential decay favoring recent releases

        All scores are normalized to [0, 1] range.

        Args:
            movie: Movie object with metadata (vote_average, release_date).
            similarity: Embedding similarity score (0-1 normalized).
            strategy: One of "semantic", "rating", "hybrid", "recency".
            weights: Custom ranking weights (overrides defaults).

        Returns:
            Final score in [0, 1] range, higher is better.

        Raises:
            HybridSearchError: If strategy is invalid or calculation fails.

        Example:
            >>> movie = Movie(id=1, title="Inception", vote_average=8.8, ...)
            >>> score = engine._calculate_score(
            ...     movie, similarity=0.75, strategy="hybrid", 
            ...     weights={"similarity": 0.7, "rating": 0.3}
            ... )
            >>> print(f"Score: {score:.3f}")  # Score: 0.761
        """
        if strategy not in VALID_STRATEGIES:
            raise HybridSearchError(f"Invalid strategy={strategy!r}")

        if strategy == "semantic":
            return max(0.0, min(1.0, similarity))

        if strategy == "rating":
            rating_norm = max(0.0, min(1.0, (movie.vote_average or 0.0) / 10.0))
            return rating_norm

        if strategy == "hybrid":
            rating_norm = max(0.0, min(1.0, (movie.vote_average or 0.0) / 10.0))
            weight_similarity = weights.get("similarity", 0.7) if weights else 0.7
            weight_rating = weights.get("rating", 0.3) if weights else 0.3
            combined = (weight_similarity * similarity) + (weight_rating * rating_norm)
            return max(0.0, min(1.0, combined))

        if strategy == "recency":
            # Exponential decay based on release_date age
            try:
                release_date = datetime.strptime(movie.release_date[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                logger.warning("Could not parse release_date for movie id=%s", movie.id)
                recency_score = 0.5
            else:
                days_old = (datetime.now() - release_date).days
                years_old = max(0.0, days_old / 365.25)
                recency_score = exp(-years_old / RECENCY_DECAY_YEARS)

            # Optionally blend with similarity
            weight_recency = weights.get("recency", 1.0) if weights else 1.0
            weight_sim = weights.get("similarity", 0.0) if weights else 0.0
            if weight_sim > 0.0:
                total_weight = weight_recency + weight_sim
                blended = (weight_recency * recency_score + weight_sim * similarity) / total_weight
                return max(0.0, min(1.0, blended))
            return max(0.0, min(1.0, recency_score))

        raise HybridSearchError(f"Unhandled strategy: {strategy}")

    def _apply_diversity(
        self, results: list[tuple[Movie, float]]
    ) -> list[tuple[Movie, float]]:
        """Reorder results to maximize genre diversity while preserving high-scoring items.

        This method ensures the final result set has variety in genres rather than
        returning 10 similar movies. It keeps the top result, then reorders remaining
        results by combining original score with a novelty bonus.

        Strategy:
            1. Keep top result (highest original score)
            2. For remaining results, compute: (0.8 × original_score) + (0.2 × novelty_score)
            3. Novelty bonus if result's genres not yet represented in output
            4. Sort by combined score
            5. Return reordered list

        Args:
            results: List of (Movie, score) tuples, assumed pre-sorted by score.

        Returns:
            Reordered list with same movies but different sort order for diversity.

        Example:
            >>> results = [
            ...     (movie1_action_sci_fi, 0.95),
            ...     (movie2_action_sci_fi, 0.92),
            ...     (movie3_drama, 0.85),
            ... ]
            >>> diverse = engine._apply_diversity(results)
            >>> # Might reorder to: movie1, movie3, movie2 (if drama not yet represented)
        """
        if len(results) <= 1:
            return results

        reordered: list[tuple[Movie, float]] = []
        represented_genres: set[str] = set()

        # Keep top result
        if results:
            top_movie, top_score = results[0]
            reordered.append((top_movie, top_score))
            if top_movie.genres:
                represented_genres.update(top_movie.genres)

        # Reorder remaining results for diversity
        diversity_scored: list[tuple[Movie, float, float]] = []
        for movie, original_score in results[1:]:
            # Novelty bonus: 1.0 if has unrepresented genres, 0.0 if all genres already seen
            movie_genres = movie.genres or []
            novel_genres = set(movie_genres) - represented_genres
            novelty_score = 1.0 if novel_genres else 0.5

            # Combined score: mostly original, with diversity bonus
            combined_score = (0.8 * original_score) + (0.2 * novelty_score)
            diversity_scored.append((movie, combined_score, original_score))

        # Sort by diversity score, take top results
        diversity_scored.sort(key=lambda x: x[1], reverse=True)

        for movie, _, original_score in diversity_scored:
            reordered.append((movie, original_score))
            if movie.genres:
                represented_genres.update(movie.genres)

        unique_genres = len(represented_genres)
        logger.info(
            "Diversity enforcement reordered %s results, %s unique genres represented",
            len(reordered),
            unique_genres,
        )
        return reordered
