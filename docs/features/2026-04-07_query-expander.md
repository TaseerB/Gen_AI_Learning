# Feature: Query Expander

**Date:** 2026-04-07  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary

Adds a `QueryExpander` utility that converts a single user query into up to `max_expansions` semantically related variations, improving downstream search recall. Expansion is driven by three layered strategies: synonym replacement (word-level vocabulary substitution), domain phrase expansion (multi-word concept substitution), and genre-aware expansion (appending or replacing genre keywords with related sub-genre variants). The expander always returns the original query first and guarantees unique, whitespace-normalised, lowercase output.

## Files Introduced

- `movie-search/utils/__init__.py` — package marker that re-exports `QueryExpander`.
- `movie-search/utils/query_expander.py` — `QueryExpander` implementation with `expand_query()`, three helper methods, and two predefined dictionaries (`SYNONYMS`, `GENRE_EXPANSIONS`).

## Files Modified

None.

## Dependencies Added

None. The implementation uses only the Python standard library (`re`, `logging`).

## Usage Example

```python
from utils.query_expander import QueryExpander

expander = QueryExpander()

# Synonym + domain expansions
variations = expander.expand_query("funny space movie", max_expansions=4)
# ['funny space movie', 'comedy space movie', 'humorous space movie', 'hilarious space movie']

# Multi-word phrase expansion
variations = expander.expand_query("time travel adventure", max_expansions=4)
# ['time travel adventure', 'time machine adventure', 'temporal paradox adventure', 'alternate timeline adventure']

# Genre-aware expansions
variations = expander.expand_query("romantic drama", max_expansions=3)
# ['romantic drama', 'love story drama', 'romance drama']

# Integration with HybridSearchEngine
from search.hybrid_search import HybridSearchEngine

engine = HybridSearchEngine(chroma_repo, movie_repo, embedding_service)
all_results: list = []
for q in expander.expand_query("scary action", max_expansions=3):
    all_results.extend(engine.search(q, top_k=5))
```

## Notes

- The original query is always element `[0]` of the returned list.
- Empty or whitespace-only queries return an empty list without raising.
- Multi-word synonym keys (e.g. `"time travel"`) are matched before their component words to avoid partial substitutions; keys are sorted longest-first at module load time.
- Genre detection uses whole-word regex matching (`\b...\b`) to avoid false positives on partial matches.
- Synonym and genre dictionaries are module-level constants (`SYNONYMS`, `GENRE_EXPANSIONS`) — extend those dicts to add vocabulary coverage without changing any logic.
- Related feature: [2026-04-07_hybrid-search-engine.md](2026-04-07_hybrid-search-engine.md) — query variations can be fed to `HybridSearchEngine.search()` to broaden recall.

## Unit Test Strategy

```python
# Happy path — synonym replacement
def test_synonym_expansion_replaces_known_word():
    result = QueryExpander().expand_query("funny movie", max_expansions=3)
    assert result[0] == "funny movie"
    assert any("comedy" in r for r in result[1:])

# Edge case — unknown query returns only original
def test_unknown_query_returns_only_original():
    result = QueryExpander().expand_query("xyzzy zork", max_expansions=5)
    assert result == ["xyzzy zork"]

# Edge case — empty query returns empty list
def test_empty_query_returns_empty_list():
    assert QueryExpander().expand_query("") == []

# Genre expansion
def test_genre_expansion_is_applied():
    result = QueryExpander().expand_query("action hero", max_expansions=4)
    assert any("action thriller" in r or "action adventure" in r for r in result)

# max_expansions respected
def test_max_expansions_limit_is_respected():
    result = QueryExpander().expand_query("scary space war movie", max_expansions=2)
    assert len(result) <= 2
```
