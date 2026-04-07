# Feature: Advanced Search Intent Alignment Boost

**Date:** 2026-04-07  
**Files Introduced:** 0  
**New Dependencies:** 0

---

## Summary

Improves Advanced Search result relevance by adding a final intent-alignment boost pass after reranking. The boost promotes movies that better match query tokens in title/overview/genres and prioritizes overlap with inferred genre intent (for example, `romantic comedy` infers `Romance` + `Comedy`). This helps reduce cases where semantically broad results (such as unrelated crime/drama titles) outrank clearly aligned genre results.

## Files Introduced

None.

## Files Modified

- `movie-search/main.py` — Updated `_advanced_search()` to add a post-rerank score boost based on:
  - Query token hits in movie title/overview/genres.
  - Inferred genre overlap with movie genres.
  - Final boosted sort before deduplication and display.

## Dependencies Added

None.

## Usage Example

```bash
python3 movie-search/main.py
```

Then choose `2` (Advanced Search) and test:

- Query: `romantic comedy`
- Leave filters blank
- Strategy: `4` (Balanced)
- Optional debug trace: `y`

Expected behavior: romance/comedy-aligned movies should rank above less aligned semantic matches.

## Notes

- This is a ranking refinement, not a hard exclusion filter.
- Boost values are intentionally capped to preserve semantic quality while improving topical precision.
- Works in combination with existing progressive filter relaxation and debug trace output.
