# Feature: Module Entrypoint for Movie Import

**Date:** 2026-03-25  
**Files Introduced:** 3  
**New Dependencies:** 0

---

## Summary
Adds a package-style module entrypoint so the importer can be launched with `python -m movie_search`. This avoids relying on direct-script path bootstrapping in `movie-search/main.py` and provides a cleaner execution path.

## Files Introduced
- `movie_search/__init__.py` — package marker for module execution.
- `movie_search/__main__.py` — module runner that loads and executes `movie-search/main.py`.
- `docs/features/2026-03-25_module-entrypoint-movie-search.md` — this feature documentation record.

## Dependencies Added
None.

## Usage Example

```bash
python -m movie_search
```

## Notes
- The existing `movie-search` directory name contains a hyphen, so it cannot be used directly as a Python module name.
- The new `movie_search` package provides a valid module name while preserving the current project layout.
