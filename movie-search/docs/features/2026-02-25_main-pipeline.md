# Feature: Main Pipeline with Rich Output

**Date:** 2026-02-25
**Files Introduced:** 0
**New Dependencies:** 1

---

## Summary

The application entry point (`main.py`) has been rewritten to demonstrate the full movie search pipeline end-to-end. It loads settings, initializes the TMDB service, fetches the first page of popular movies, converts them into `Movie` domain objects, and displays the results in a color-coded Rich table in the terminal. Ratings are green (8+), yellow (6–8), or red (<6) for quick visual scanning.

## Files Introduced

None — `main.py` already existed and was updated in place.

## Dependencies Added

| Package | Version | Purpose |
|---|---|---|
| rich | >=13.7.0 | Beautiful terminal output — tables, colors, and styled text |

## Usage Example

```bash
# Make sure your .env has a valid TMDB_API_KEY, then run:
cd movie-search
python main.py
```

Expected output:

```
                     Popular Movies on TMDB
┌───┬──────────────────────┬──────┬────────┬──────────────────────┐
│ # │ Title                │ Year │ Rating │ Overview             │
├───┼──────────────────────┼──────┼────────┼──────────────────────┤
│ 1 │ Thunderbolts*        │ 2025 │  7.2   │ After being strande… │
│ 2 │ Sinners              │ 2025 │  8.1   │ Trying to leave the… │
│ …                                                               │
└───┴──────────────────────┴──────┴────────┴──────────────────────┘

Showing 20 movie(s).
```

You can also enable debug logging:

```bash
# In your .env file, set:
DEBUG=true
```

## Notes

- A valid `TMDB_API_KEY` must be present in `.env`. The script exits with a clear error message if it is missing.
- Overviews are truncated to 100 characters to keep the table readable.
- Movies that fail validation (e.g. missing title or invalid ID from the API) are silently skipped rather than crashing the entire run.
- Install the new dependency with `pip install -r requirements.txt` (or just `pip install rich`).
