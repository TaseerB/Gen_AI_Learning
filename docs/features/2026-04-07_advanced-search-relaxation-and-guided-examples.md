# Feature: Advanced Search Relaxation And Guided Examples

**Date:** 2026-04-07  
**Files Introduced:** 0  
**New Dependencies:** 0

---

## Summary

Improves the Advanced Search UX by introducing progressive filter relaxation when strict user filters produce zero results. Instead of returning an empty screen immediately, the search now retries in stages (remove genre filter, then year filter, then rating filter, then no filters) and informs the user which relaxed stage produced results. The UI also now shows practical starter queries and clearer guidance for avoiding over-constrained inputs.

## Files Introduced

None.

## Files Modified

- `movie-search/main.py` — Updated `_advanced_search()` to:
  - Show recommended example queries before input.
  - Normalize swapped min/max rating and year ranges.
  - Execute progressive search fallback stages when strict filters return no matches.
  - Display a user-facing message when relaxed filters are applied.
  - Provide actionable guidance when still no results are found.

## Dependencies Added

None.

## Usage Example

```bash
python3 movie-search/main.py
```

Then choose:

1. `2` (Advanced Search)
2. Query: `space adventure`
3. Optional filters:
   - Min rating: `6`
   - Max rating: `8`
   - Min year: `2000`
   - Max year: `2020`
   - Genres: `Action,Sci-Fi`
4. Strategy: `4` (Balanced)

If no strict matches exist, the app now automatically relaxes filters and continues searching.

## Notes

- Relaxation order is intentionally conservative:
  1. exact filters
  2. without genre filter
  3. without year filter
  4. without rating filter
  5. no filters
- If no results remain after all stages, users receive specific suggestions for widening the search.
- Existing reranking behavior remains unchanged; only candidate retrieval resilience was enhanced.
