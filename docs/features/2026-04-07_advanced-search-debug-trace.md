# Feature: Advanced Search Debug Trace

**Date:** 2026-04-07  
**Files Introduced:** 0  
**New Dependencies:** 0

---

## Summary

Adds an optional debug trace mode to Advanced Search so users can inspect query expansion and progressive filter-stage hit counts directly in the CLI. This makes troubleshooting easier when a query returns few or no results by showing exactly which expanded terms were used and how many candidates each relaxation stage produced.

## Files Introduced

None.

## Files Modified

- `movie-search/main.py` — Updated `_advanced_search()` with:
  - A user prompt to enable debug trace (`Show debug trace ... [y/N]`).
  - Display of expanded query variations.
  - Stage-level hit tracking for the progressive relaxation pipeline.
  - A Rich debug table showing each stage and resulting hit count.

## Dependencies Added

None.

## Usage Example

```bash
python3 movie-search/main.py
```

Then:

1. Choose option `2` (Advanced Search).
2. Enter your query and filters.
3. When prompted `Show debug trace ... [y/N]`, enter `y`.

Sample debug output:

- Expanded queries: `space adventure, outer space adventure, galaxy adventure`
- Stage table:
  - your exact filters -> 0
  - without genre filter -> 4

## Notes

- Debug trace is opt-in and defaults to off (`N`) to keep normal UX clean.
- Stage counts are collected in order of progressive relaxation and stop once a stage returns results.
- This feature complements the previously added automatic filter relaxation by explaining why fallback stages were needed.
