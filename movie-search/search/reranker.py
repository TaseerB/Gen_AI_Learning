"""Reranking utilities for multi-signal movie result ordering.

This module provides `SearchReranker`, which takes initial semantic search results
and improves ordering by combining multiple ranking signals such as similarity,
rating, popularity, and recency.

Example:
    Basic balanced reranking::

        from search.reranker import SearchReranker

        reranker = SearchReranker()
        reranked = reranker.rerank(results=initial_results, strategy="balanced")

    Personalized reranking::

        preferences = {
            "favorite_genres": ["Sci-Fi", "Thriller"],
            "disliked_genres": ["Horror"],
            "min_rating": 7.0,
        }
        reranked = reranker.rerank(
            results=initial_results,
            strategy="personalized",
            user_preferences=preferences,
        )
"""

from __future__ import annotations

import logging
from math import exp, log1p
from typing import TypeAlias

from models.movie import Movie

logger = logging.getLogger(__name__)

MovieWithSimilarity: TypeAlias = tuple[Movie, float]
RerankInput: TypeAlias = list[MovieWithSimilarity]

VALID_STRATEGIES = frozenset(("balanced", "quality_first", "trending", "personalized"))
REFERENCE_YEAR = 2024
DIVERSITY_REPEAT_PENALTY = 0.75


class SearchRerankerError(Exception):
    """Raised when reranking operations fail."""


class SearchReranker:
    """Reorder movie search results using configurable multi-signal strategies.

    Strategies:
        - balanced:
            40% semantic similarity
            30% rating score
            20% popularity score
            10% recency score
        - quality_first:
            60% rating score
            40% semantic similarity
        - trending:
            50% popularity score
            30% recency score
            20% semantic similarity
        - personalized:
            Balanced base score with user preference boost/penalty multiplier.

    Note:
        The current `Movie` model does not include director/actor fields.
        Preference keys related to directors/actors are accepted but ignored.
    """

    def rerank(
        self,
        results: RerankInput,
        strategy: str = "balanced",
        user_preferences: dict[str, object] | None = None,
    ) -> list[tuple[Movie, float]]:
        """Rerank initial movie results using a selected strategy.

        Args:
            results: Initial list of `(Movie, similarity_score)` tuples.
                Similarity scores are expected in `[0, 1]` and are clamped safely.
            strategy: Reranking strategy. Must be one of:
                `balanced`, `quality_first`, `trending`, `personalized`.
            user_preferences: Optional personalization preferences dictionary.

        Returns:
            List of `(Movie, final_score)` tuples sorted by `final_score` descending.

        Raises:
            SearchRerankerError: If strategy is invalid.

        Example:
            >>> reranker = SearchReranker()
            >>> reranked = reranker.rerank(results, strategy="trending")
            >>> top_movie, top_score = reranked[0]
        """
        logger.info(
            "Reranking %s result(s) with strategy=%s", len(results), strategy
        )

        if not results:
            logger.debug("Received empty rerank results, returning empty list")
            return []

        if strategy not in VALID_STRATEGIES:
            raise SearchRerankerError(
                f"Invalid strategy={strategy!r}. Must be one of {sorted(VALID_STRATEGIES)}"
            )

        base_scored: list[tuple[Movie, float]] = []
        for movie, similarity_score in results:
            similarity = self._clamp01(similarity_score)
            rating = self._clamp01((movie.vote_average or 0.0) / 10.0)
            popularity = self._calculate_popularity_score(movie.vote_count or 0)
            release_year = self._extract_release_year(movie.release_date)
            recency = self._calculate_recency_score(release_year)

            if strategy == "balanced":
                score = (0.4 * similarity) + (0.3 * rating) + (0.2 * popularity) + (0.1 * recency)
            elif strategy == "quality_first":
                score = (0.6 * rating) + (0.4 * similarity)
            elif strategy == "trending":
                score = (0.5 * popularity) + (0.3 * recency) + (0.2 * similarity)
            else:
                base_score = (0.4 * similarity) + (0.3 * rating) + (0.2 * popularity) + (0.1 * recency)
                if user_preferences:
                    preference_multiplier = self._apply_user_preferences(movie, user_preferences)
                else:
                    preference_multiplier = 1.0
                score = self._clamp01(base_score * preference_multiplier)

            score = self._clamp01(score)
            base_scored.append((movie, score))

            logger.debug(
                "Score breakdown movie_id=%s title=%r strategy=%s "
                "similarity=%.4f rating=%.4f popularity=%.4f recency=%.4f final_pre_diversity=%.4f",
                movie.id,
                movie.title,
                strategy,
                similarity,
                rating,
                popularity,
                recency,
                score,
            )

        base_scored.sort(key=lambda item: item[1], reverse=True)

        diversity_adjusted: list[tuple[Movie, float]] = []
        for index, (movie, score) in enumerate(base_scored):
            penalty_multiplier = self._calculate_diversity_penalty(base_scored, index)
            adjusted_score = self._clamp01(score * penalty_multiplier)
            diversity_adjusted.append((movie, adjusted_score))

            logger.debug(
                "Diversity adjustment movie_id=%s title=%r index=%s "
                "base_score=%.4f penalty=%.4f adjusted_score=%.4f",
                movie.id,
                movie.title,
                index,
                score,
                penalty_multiplier,
                adjusted_score,
            )

        diversity_adjusted.sort(key=lambda item: item[1], reverse=True)
        logger.info("Reranking complete, returning %s result(s)", len(diversity_adjusted))
        return diversity_adjusted

    def _calculate_popularity_score(self, vote_count: int) -> float:
        """Calculate normalized popularity score from vote count using a log scale.

        Uses logarithmic scaling for diminishing returns, then normalizes to `[0, 1]`.

        Args:
            vote_count: Number of votes from rating sources.

        Returns:
            Popularity score in `[0, 1]`.
        """
        safe_votes = max(0, vote_count)
        normalization_cap = log1p(1_000_000)
        popularity = log1p(safe_votes) / normalization_cap
        return self._clamp01(popularity)

    def _calculate_recency_score(self, release_year: int) -> float:
        """Calculate recency score using exponential decay from reference year 2024.

        Formula:
            `exp(-0.1 * years_old)`

        Examples:
            - 2024 movie: ~1.0
            - 2020 movie: ~0.67
            - 2010 movie: ~0.25

        Args:
            release_year: Movie release year as integer.

        Returns:
            Recency score in `[0, 1]`.
        """
        if release_year >= REFERENCE_YEAR:
            return 1.0

        years_old = max(0, REFERENCE_YEAR - release_year)
        recency = exp(-0.1 * years_old)
        return self._clamp01(recency)

    def _calculate_diversity_penalty(
        self,
        results: list[tuple[Movie, float]],
        current_index: int,
    ) -> float:
        """Calculate diversity penalty multiplier for a candidate position.

        Rule:
            If the top 3 ranked results all share the same primary genre,
            penalize the 4th+ result when it repeats that same primary genre.

        Args:
            results: Ranked `(Movie, score)` tuples before diversity adjustment.
            current_index: Index of the current movie in `results`.

        Returns:
            Penalty multiplier in `[0, 1]` where lower means stronger penalty.
        """
        if current_index < 3 or len(results) < 4:
            return 1.0

        top_three = results[:3]
        top_primary_genres = [self._primary_genre(movie) for movie, _ in top_three]
        if any(genre is None for genre in top_primary_genres):
            return 1.0

        dominant_genres = {genre for genre in top_primary_genres if genre is not None}
        if len(dominant_genres) != 1:
            return 1.0

        dominant_genre = next(iter(dominant_genres))
        current_movie, _ = results[current_index]
        current_primary_genre = self._primary_genre(current_movie)

        if current_primary_genre == dominant_genre:
            return DIVERSITY_REPEAT_PENALTY
        return 1.0

    def _apply_user_preferences(
        self,
        movie: Movie,
        preferences: dict[str, object],
    ) -> float:
        """Apply user preference multipliers and return a bounded boost/penalty factor.

        Supported keys:
            - favorite_genres: list[str]
            - disliked_genres: list[str]
            - min_rating: float

        Notes:
            Director/actor preference keys are currently ignored because the `Movie`
            model does not include that metadata.

        Args:
            movie: Candidate movie.
            preferences: User preference dictionary.

        Returns:
            Multiplier in `[0.8, 1.2]`.
        """
        multiplier = 1.0

        favorite_genres = preferences.get("favorite_genres")
        if isinstance(favorite_genres, list) and favorite_genres:
            movie_genres = set(movie.genres or [])
            overlap_count = len(movie_genres.intersection(set(str(g) for g in favorite_genres)))
            if overlap_count > 0:
                multiplier += min(0.15, 0.05 * overlap_count)

        disliked_genres = preferences.get("disliked_genres")
        if isinstance(disliked_genres, list) and disliked_genres:
            movie_genres = set(movie.genres or [])
            disliked_overlap = len(movie_genres.intersection(set(str(g) for g in disliked_genres)))
            if disliked_overlap > 0:
                multiplier -= min(0.2, 0.1 * disliked_overlap)

        min_rating = preferences.get("min_rating")
        if isinstance(min_rating, (int, float)):
            movie_rating = movie.vote_average or 0.0
            if movie_rating < float(min_rating):
                multiplier -= 0.1

        if "favorite_directors" in preferences or "favorite_actors" in preferences:
            logger.debug(
                "Director/actor preferences provided but ignored for movie id=%s "
                "because Movie model has no director/actor fields",
                movie.id,
            )

        bounded = max(0.8, min(1.2, multiplier))
        logger.debug(
            "User preference multiplier movie_id=%s title=%r multiplier=%.4f",
            movie.id,
            movie.title,
            bounded,
        )
        return bounded

    def _extract_release_year(self, release_date: str) -> int:
        """Extract release year safely from `YYYY-MM-DD` date strings."""
        if not release_date:
            logger.debug("Missing release_date, defaulting release_year to 1900")
            return 1900
        year_part = release_date[:4]
        try:
            return int(year_part)
        except ValueError:
            logger.warning("Invalid release_date=%r, defaulting release_year to 1900", release_date)
            return 1900

    def _primary_genre(self, movie: Movie) -> str | None:
        """Return the movie primary genre (first genre) if available."""
        if movie.genres and len(movie.genres) > 0:
            return movie.genres[0]
        return None

    def _clamp01(self, value: float) -> float:
        """Clamp a numeric value into the `[0, 1]` interval."""
        return max(0.0, min(1.0, float(value)))
