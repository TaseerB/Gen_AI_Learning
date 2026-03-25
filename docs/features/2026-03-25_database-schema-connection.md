# Feature: SQLite Database Schema & Connection Management

**Date:** 2026-03-25  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary
Adds a local SQLite database for persisting movie data and a small connection/transaction management layer. This enables the project to store TMDB results locally for faster repeat queries and offline access. The schema is idempotent and can be applied multiple times safely.

## Files Introduced
- `database/schema.sql` — Defines the SQLite `movies` table and supporting indexes.
- `database/connection.py` — Provides connection creation, schema initialization, and a transaction-scoped context manager.

## Dependencies Added
None.

## Usage Example

```python
from database.connection import database_session, initialize_database

initialize_database()

with database_session() as conn:
    conn.execute(
        "INSERT OR REPLACE INTO movies (id, title, release_date, vote_average) VALUES (?, ?, ?, ?)",
        (550, "Fight Club", "1999-10-15", 8.4),
    )

with database_session() as conn:
    row = conn.execute("SELECT * FROM movies WHERE id = ?", (550,)).fetchone()
    print(dict(row))  # sqlite3.Row -> dict-like
```

## Notes
- The database file is created at `data/movies.db` automatically (the `data/` directory will be created if missing).
- `genres` is stored as JSON text (e.g. `["Drama","Thriller"]`).

