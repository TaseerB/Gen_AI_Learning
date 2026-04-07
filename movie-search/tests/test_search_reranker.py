"""Unit tests for SearchReranker."""

from __future__ import annotations

from models.movie import Movie
from search.reranker import SearchReranker


def _movie(
    movie_id: int,
    title: str,
    release_date: str,
    vote_average: float,
    vote_count: int,
    genres: list[str],
) -> Movie:
    return Movie(
        id=movie_id,
        title=title,
        release_date=release_date,
        overview=f"Overview for {title}",
        vote_average=vote_average,
        vote_count=vote_count,
        genres=genres,
    )


def test_rerank_balanced_returns_sorted_scores() -> None:
    reranker = SearchReranker()
    results = [
        (_movie(1, "A", "2024-01-01", 8.0, 10000, ["Sci-Fi"]), 0.70),
        (_movie(2, "B", "2020-01-01", 9.0, 30000, ["Drama"]), 0.60),
        (_movie(3, "C", "2015-01-01", 7.0, 5000, ["Action"]), 0.80),
    ]

    reranked = reranker.rerank(results, strategy="balanced")

    assert len(reranked) == 3
    assert reranked[0][1] >= reranked[1][1] >= reranked[2][1]
    for _, score in reranked:
        assert 0.0 <= score <= 1.0


def test_quality_first_favors_higher_rating() -> None:
    reranker = SearchReranker()
    high_similarity_low_rating = _movie(10, "LowRating", "2022-01-01", 4.0, 5000, ["Action"])
    low_similarity_high_rating = _movie(11, "HighRating", "2022-01-01", 9.5, 5000, ["Action"])

    results = [
        (high_similarity_low_rating, 0.95),
        (low_similarity_high_rating, 0.50),
    ]

    reranked = reranker.rerank(results, strategy="quality_first")

    assert reranked[0][0].id == 11


def test_trending_favors_popularity_and_recency() -> None:
    reranker = SearchReranker()
    old_movie = _movie(20, "Old", "2010-01-01", 8.0, 120000, ["Drama"])
    recent_popular = _movie(21, "Recent", "2024-01-01", 7.0, 500000, ["Drama"])

    results = [
        (old_movie, 0.80),
        (recent_popular, 0.60),
    ]

    reranked = reranker.rerank(results, strategy="trending")

    assert reranked[0][0].id == 21


def test_personalized_applies_genre_and_min_rating_preferences() -> None:
    reranker = SearchReranker()
    favorite_movie = _movie(30, "Fav", "2021-01-01", 8.5, 15000, ["Sci-Fi", "Thriller"])
    disliked_movie = _movie(31, "Disliked", "2021-01-01", 6.5, 15000, ["Horror"])

    results = [
        (favorite_movie, 0.70),
        (disliked_movie, 0.72),
    ]

    preferences: dict[str, object] = {
        "favorite_genres": ["Sci-Fi", "Thriller"],
        "disliked_genres": ["Horror"],
        "min_rating": 7.0,
    }

    reranked = reranker.rerank(
        results,
        strategy="personalized",
        user_preferences=preferences,
    )

    assert reranked[0][0].id == 30


def test_diversity_penalizes_fourth_same_genre_when_top_three_match() -> None:
    reranker = SearchReranker()

    m1 = _movie(40, "S1", "2023-01-01", 8.0, 10000, ["Sci-Fi"])
    m2 = _movie(41, "S2", "2023-01-01", 8.0, 10000, ["Sci-Fi"])
    m3 = _movie(42, "S3", "2023-01-01", 8.0, 10000, ["Sci-Fi"])
    m4 = _movie(43, "S4", "2023-01-01", 8.0, 10000, ["Sci-Fi"])
    m5 = _movie(44, "D1", "2023-01-01", 8.0, 10000, ["Drama"])

    base_scored = [
        (m1, 0.95),
        (m2, 0.90),
        (m3, 0.88),
        (m4, 0.87),
        (m5, 0.86),
    ]

    penalty_for_fourth = reranker._calculate_diversity_penalty(base_scored, 3)
    no_penalty_for_fifth = reranker._calculate_diversity_penalty(base_scored, 4)

    assert penalty_for_fourth < 1.0
    assert no_penalty_for_fifth == 1.0


def test_popularity_and_recency_scores_are_normalized() -> None:
    reranker = SearchReranker()

    popularity_zero = reranker._calculate_popularity_score(0)
    popularity_high = reranker._calculate_popularity_score(1_000_000)
    recency_2024 = reranker._calculate_recency_score(2024)
    recency_2010 = reranker._calculate_recency_score(2010)

    assert 0.0 <= popularity_zero <= 1.0
    assert 0.0 <= popularity_high <= 1.0
    assert popularity_high >= popularity_zero

    assert 0.0 <= recency_2010 <= 1.0
    assert recency_2024 == 1.0
    assert recency_2024 > recency_2010
