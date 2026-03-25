# Feature: Batch Popular Movie Import

**Date:** 2026-03-25  
**Files Introduced:** 1  
**New Dependencies:** 1

---

## Summary
Adds a batch import workflow to the movie-search CLI that fetches popular movies across multiple TMDB pages, validates payloads, and persists results in a single transactional write path. The importer supports partial success across API-page failures, duplicate skipping, per-movie error tolerance, and progress tracking.

## Files Introduced
- `docs/features/2026-03-25_batch-popular-movie-import.md` — feature documentation for the batch import capability and dependency addition.

## Dependencies Added
- `tqdm>=4.66.0` — progress bars for page fetch, validation, and DB preparation stages.

## Usage Example

```bash
python movie-search/main.py
```

At runtime:
- Prompts for number of movies to import.
- Imports popular movies from TMDB using concurrent page fetches.
- Prints an import summary table (imported, skipped, errors, time taken).

## Notes
- API-page failures do not stop the full import; successful pages are still saved.
- Movie transformation/validation errors are logged and skipped.
- Database rollback occurs only for critical transaction failures.
