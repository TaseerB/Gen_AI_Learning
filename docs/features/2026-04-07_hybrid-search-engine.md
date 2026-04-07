# Feature: Hybrid Search Engine

**Date:** 2026-04-07  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary

Adds a `HybridSearchEngine` that combines semantic vector retrieval from ChromaDB with SQL-backed movie hydration and filtering. The engine supports multiple ranking strategies (`semantic`, `rating`, `hybrid`, `recency`), optional filtering constraints, fallback keyword search when Chroma returns no candidates, and diversity-aware reranking to improve genre variety.

## Files Introduced

- `movie-search/search/hybrid_search.py` — hybrid retrieval orchestration, scoring strategies, filter handling, fallback behavior, and diversity reranking.
- `movie-search/search/__init__.py` — package export for `HybridSearchEngine`.

## Files Updated

None.

## Dependencies Added

None. The feature reuses existing project dependencies and services:

- `repositories.chroma_repository.ChromaRepository`
- `repositories.movie_repository.MovieRepository`
- `services.embedding_service.EmbeddingService`

## API

### Class

- `HybridSearchEngine(chroma_repository, movie_repository, embedding_service)`

### Main Method

```python
def search(
    self,
    query: str,
    filters: dict[str, object] | None = None,
    top_k: int = 10,
    ranking_strategy: str = "hybrid",
    ranking_weights: dict[str, float] | None = None,
) -> list[Movie]
```

### Supported Filters

The `filters` dict can include:

- `min_rating: float`
- `max_rating: float`
- `min_year: int`
- `max_year: int`
- `genres: list[str]` (ANY-match / OR)
- `runtime_range: tuple[int, int]`

## Search Flow

1. Validate query, `top_k`, and ranking strategy.
2. Generate query embedding with `EmbeddingService`.
3. Query Chroma with oversampling (`top_k=100`) and simple metadata filters.
4. Extract candidate IDs and hydrate full `Movie` rows from `MovieRepository`.
5. Apply complex filters (`genres`, `runtime_range`) on hydrated movies.
6. Score with selected strategy.
7. Apply diversity reranking to increase genre variety.
8. Return `top_k` results.
9. If Chroma returns zero candidates, fallback to `MovieRepository.find_by_keywords`.

## Ranking Strategies

- `semantic`: similarity-only score.
- `rating`: normalized rating score (`vote_average / 10`).
- `hybrid`: weighted score (`0.7 * similarity + 0.3 * rating` by default).
- `recency`: exponential decay by movie age (more recent movies score higher).

Custom `ranking_weights` can override defaults per search call.

## Diversity Behavior

The diversity pass preserves top relevance while reducing near-duplicate genre outputs:

- Keeps the top result.
- Reranks remaining results with a novelty bonus based on unseen genres.
- Improves list variety for broad queries.

## Error Handling and Logging

- Handles empty query and invalid `top_k` safely.
- Raises `HybridSearchError` for invalid ranking strategies and unrecoverable failures.
- Falls back to keyword search if semantic candidates are empty.
- Logs query metadata, candidate counts at each stage, and final result count.

## Usage Example

```python
from repositories.chroma_repository import ChromaRepository
from repositories.movie_repository import MovieRepository
from search.hybrid_search import HybridSearchEngine
from services.embedding_service import EmbeddingService

chroma_repo = ChromaRepository()
movie_repo = MovieRepository()
embedding_service = EmbeddingService()

engine = HybridSearchEngine(chroma_repo, movie_repo, embedding_service)

results = engine.search(
    query="mind-bending sci-fi thriller",
    filters={
        "min_rating": 7.0,
        "min_year": 2000,
        "genres": ["Sci-Fi", "Thriller"],
        "runtime_range": (90, 180),
    },
    top_k=10,
    ranking_strategy="hybrid",
    ranking_weights={"similarity": 0.75, "rating": 0.25},
)

for movie in results:
    # Note: requires `search_score` support on Movie to avoid slotted-dataclass assignment errors
    print(movie.title)
```

## Notes

- Chroma-side filtering is used for simple numeric constraints (rating/year).
- Complex filters are applied after SQL hydration for richer logic and robustness.
- If strict filters produce no matches, users should relax constraints (for example, broader genre list or larger runtime range).
- Current implementation attempts to attach `search_score` dynamically to `Movie` instances; with `Movie` defined as a slotted dataclass, model support may be needed (for example adding `search_score: float | None = None`).
