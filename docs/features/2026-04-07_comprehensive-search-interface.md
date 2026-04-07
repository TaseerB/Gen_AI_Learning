# Feature: Comprehensive Search Interface

**Date:** 2026-04-07  
**Files Introduced:** 0  
**New Dependencies:** 0

---

## Summary

Replaces the basic menu-driven CLI in `main.py` with a comprehensive six-option search and recommendation interface that unifies semantic search, advanced filtering, query expansion, reranking, and personalized recommendations. The new interface (`_run_interactive_menu()`) integrates `HybridSearchEngine`, `SearchReranker`, and `QueryExpander` to provide users with multiple discovery paths: simple semantic queries, advanced filtered searches with strategy selection, similarity-based recommendations from a selected movie, personalized suggestions based on user ratings, and side-by-side comparison of semantic vs. keyword search methods.

## Files Introduced

None.

## Files Modified

- `movie-search/main.py` — Replaced legacy `interactive_search()` flow with a new six-option menu structure. Refactored into helper functions: `_simple_search()`, `_advanced_search()`, `_movie_recommendations()`, `_smart_recommendations()`, `_compare_search_methods()`, `_show_main_menu()`, `_display_and_detail_results()`, and `_ensure_embeddings_available()`. Maintains backward compatibility with `--import` and legacy `--interactive` flags.

## Dependencies Added

None. Integrates existing services: `HybridSearchEngine`, `SearchReranker`, `QueryExpander`, `ChromaRepository`.

## Usage

```bash
# Run the new interactive menu
python movie-search/main.py

# Force import then menu
python movie-search/main.py --import

# Legacy interactive flag (still supported)
python movie-search/main.py --interactive
```

## Menu Options

### Option 1: Simple Search (Semantic-Only)
- Prompts for a natural language query
- Uses `HybridSearchEngine` with `semantic` ranking strategy
- Returns top 10 results with scores
- Allows drilling down to movie details

**Example:** "funny space adventure" → results include Guardians of the Galaxy, The Fifth Element, etc.

### Option 2: Advanced Search (Filters + Expansion + Reranking)
- Prompts for query + optional filters:
  - Minimum/maximum rating (0-10)
  - Year range
  - Genre list (ANY match)
- Offers four ranking strategies:
  - Semantic: embedding similarity only
  - Quality First: rating-focused
  - Trending: popularity + recency
  - Balanced: all signals weighted
- Uses `QueryExpander` to expand single query into up to 3 variations
- Feeds all variations through `HybridSearchEngine`
- Deduplicates and reranks results with `SearchReranker`
- Returns top 15 results

**Example:** "romance" + min_rating=7.0, genre=["Drama"] + "balanced" strategy

### Option 3: Movie Recommendations (Similarity-Based)
- Shows top 20 rated movies
- User selects one
- Uses the movie's overview text to generate embedding
- Queries `ChromaRepository` for similar embeddings
- Returns 10 most similar movies by embedding distance

**Example:** Pick "Inception" → find similar mind-bending, visually stunning films

### Option 4: Smart Recommendations (Personalized)
- Shows 5 random movies
- User rates each (1-10) or skips
- Builds preference profile:
  - Average rating threshold
  - Favorite genres from rated movies
- Filters all movies against preferences
- Scores by rating match and genre overlap
- Reranks with `SearchReranker` using personalized strategy
- Returns 10 personalized recommendations

**Example:** Rate 5 movies (avg 7.5, genres: Sci-Fi, Thriller) → recommendations matching taste

### Option 5: Compare Search Methods (Semantic vs. Keyword)
- Runs both keyword search (SQL LIKE) and semantic search (embeddings) on same query
- Displays results side-by-side
- Highlights movies found only by semantic search
- Explains why semantic understanding finds conceptually related movies

**Example:** "space adventure" shows semantic-only matches like *Interstellar* when keyword search misses it

### Option 6: Exit
- Gracefully closes the application

## Error Handling

- Empty queries → prompt user to retry
- Invalid filter values → validate and show error
- Missing embeddings → gracefully disable embedding-dependent features (options 3, 4) with user message
- No movies in database → trigger import flow before showing menu
- Exceptions in search/rerank → catch and display friendly error, allow user to continue

## Implementation Details

- **Embeddings requirement**: Options 3 and 4 require ChromaDB with populated embeddings. If unavailable, a warning is shown at startup and those menu options are disabled.
- **Query expansion**: Option 2 expands a single query into 3 variations, searches each independently, deduplicates, and reranks results for higher recall.
- **Reranking**: Option 2 and 4 use `SearchReranker` with configurable strategy to improve result ordering based on rating, popularity, recency, or personalization signals.
- **Personalized recommendations** (Option 4) use a two-signal approach: user-rated movies inform genre preferences and rating threshold, then all movies are scored against those preferences.
- **MovieRepository integration**: All options use `MovieRepository` for detail hydration, ensuring full movie metadata is available.

## Related Features

- [2026-04-07_hybrid-search-engine.md](2026-04-07_hybrid-search-engine.md) — underlying search engine used by options 1, 2
- [2026-04-07_search-reranker.md](2026-04-07_search-reranker.md) — multi-signal reranking for options 2, 4
- [2026-04-07_query-expander.md](2026-04-07_query-expander.md) — query variation expansion for option 2
- [2026-04-02_chroma-repository.md](2026-04-02_chroma-repository.md) — embedding similarity search for options 3, 5

## Notes

- The menu persists after each search, allowing users to try different options or refine queries without restarting.
- Results tables support interactive drill-down to full movie details (overview, runtime, genres, poster, etc.) via the display utilities in `ui.display`.
- All text input is stripped and case-insensitive where appropriate.
- Progress indicators (via `rich.progress`) provide user feedback during long-running searches and reranking.
- The implementation maintains backward compatibility: legacy `--import` and `--interactive` flags still work, and the import flow is still triggered automatically if the database is empty.
