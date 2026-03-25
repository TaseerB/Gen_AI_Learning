# Feature: Movie Repository

**Date:** 2026-03-25  
**Files Introduced:** 2  
**New Dependencies:** 0

---

## Summary
Adds a repository-layer abstraction for persisting and querying movies from the SQLite database. This encapsulates SQL, transactions, and JSON field handling behind a `MovieRepository` that returns `Movie` domain objects. It also standardizes error handling via a dedicated `RepositoryError`.

## Files Introduced
- `movie-search/repositories/__init__.py` — package marker for repository-layer code.
- `movie-search/repositories/movie_repository.py` — `MovieRepository` implementation (CRUD + search) with logging and `RepositoryError`.

## Dependencies Added
None.

## Usage Example

```python
from database.connection import initialize_database
from models.movie import Movie
from repositories.movie_repository import MovieRepository

initialize_database()
repo = MovieRepository()

repo.save(
    Movie(
        id=550,
        title="Fight Club",
        release_date="1999-10-15",
        overview="An insomniac office worker crosses paths with...",
        vote_average=8.4,
        genres=["Drama"],
    )
)

print(repo.count())          # 1
print(repo.find_by_id(550))  # Movie(...)
print(repo.find_by_title("club"))
```

## Notes
- When providing an injected SQLite connection (e.g. `:memory:`) for tests, ensure `conn.row_factory = sqlite3.Row` and that `movie-search/database/schema.sql` has been applied to that connection.

