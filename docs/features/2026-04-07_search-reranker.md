# Feature: Search Reranker

**Date:** 2026-04-07  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary

Adds a `SearchReranker` class that reorders initial semantic search results using multiple configurable ranking signals: semantic similarity, vote average (rating), popularity via logarithmic vote count scaling, and exponential recency decay. It supports four strategies (`balanced`, `quality_first`, `trending`, `personalized`) with detailed per-movie debug score breakdowns and a strong diversity penalty that demotes repeated primary genres after a homogeneous top three.

## Files Introduced

- `movie-search/search/reranker.py` — `SearchReranker` implementation with four strategies, four helper scorer methods, user-preference multiplier logic, and diversity penalty pass.
- `movie-search/tests/test_search_reranker.py` — pytest coverage for each strategy ordering, helper normalization, personalized preference boosts/penalties, and diversity penalty edge cases.

## Files Modified

- `movie-search/search/__init__.py` — added `SearchReranker` to the package re-export surface (`__all__`).

## Dependencies Added

None. All scoring uses standard library math (`exp`, `log1p`) with existing `Movie` model fields.

## Usage Example

```python
from search.reranker import SearchReranker
from search.hybrid_search import HybridSearchEngine

# Retrieve initial results from the hybrid search engine
engine = HybridSearchEngine(chroma_repo, movie_repo, embedding_service)
initial: list[Movie] = engine.search("mind-bending thriller", top_k=20)

# Pair each movie with its attached similarity score for the reranker
initial_with_scores = [(m, getattr(m, "search_score", 0.0)) for m in initial]

# Rerank using balanced strategy
reranker = SearchReranker()
reranked = reranker.rerank(initial_with_scores, strategy="balanced")

# Rerank using personalized strategy
preferences = {
    "favorite_genres": ["Sci-Fi", "Thriller"],
    "disliked_genres": ["Horror"],
    "min_rating": 7.0,
}
personalized = reranker.rerank(
    initial_with_scores,
    strategy="personalized",
    user_preferences=preferences,
)

for movie, score in personalized:
    print(f"{movie.title} ({movie.release_date[:4]}): {score:.3f}")
```

## Notes

- **Strategies**:
  - `balanced`: 0.4 similarity + 0.3 rating + 0.2 popularity + 0.1 recency
  - `quality_first`: 0.6 rating + 0.4 similarity
  - `trending`: 0.5 popularity + 0.3 recency + 0.2 similarity
  - `personalized`: balanced base × user preference multiplier clamped to `[0.8, 1.2]`
- **Personalization** supports `favorite_genres`, `disliked_genres`, and `min_rating`. Director and actor preference keys are accepted but logged and skipped because those fields are not present in the current `Movie` model.
- **Diversity penalty** (multiplier `0.75`) is applied to the fourth or later result when the top three results all share the same primary genre.
- All component scores and the final score are normalized to `[0, 1]` before and after combination.
- Detailed `DEBUG`-level logs emit per-movie component breakdowns (similarity, rating, popularity, recency, preference multiplier, diversity penalty) to support ranking tuning.
- If director/actor personalization is added to the `Movie` model and data pipeline in the future, the `_apply_user_preferences` method can be extended to activate those signals without interface changes.
- Related features: [2026-04-07_hybrid-search-engine.md](2026-04-07_hybrid-search-engine.md) (initial retrieval stage that precedes reranking).
