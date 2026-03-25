# Database Module Relocation Into `movie-search`

## Overview
- Relocated database module files from repository root `database/` into `movie-search/database/`.
- Kept import path as `database.connection`, but now it resolves from within the `movie-search` app package.
- Removed `sys.path` fallback logic from `movie-search/main.py` since imports are now package-local.

## Why
- Running app/test code from `movie-search` failed with `ModuleNotFoundError: No module named 'database'` when the database module lived outside the app package.
- Co-locating database code with the app improves import reliability and package cohesion.

## Files Added
- `movie-search/database/__init__.py`
- `movie-search/database/connection.py`
- `movie-search/database/schema.sql`

## Files Updated
- `movie-search/main.py`
- `movie-search/tests/conftest.py`

## Files Removed
- `database/connection.py`
- `database/schema.sql`

## Validation
- Executed: `pytest -q` in `movie-search`
- Result: `4 passed`
