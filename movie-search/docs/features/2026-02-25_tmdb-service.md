# Feature: TMDB Service

**Date:** 2026-02-25
**Files Introduced:** 2
**New Dependencies:** 0

---

## Summary

A dedicated API client for The Movie Database (TMDB) that encapsulates all HTTP communication behind a clean, injectable interface. The service provides connection pooling via `requests.Session`, automatic retry with exponential backoff, a thread-safe sliding-window rate limiter (40 req / 10 s), and an in-memory TTL response cache — keeping the rest of the application fully decoupled from network concerns.

## Files Introduced

- `services/tmdb_service.py` — Contains the `TMDBService` class (TMDB API client with retry, rate-limiting, and caching), the `TMDBAPIError` custom exception, and two internal helpers (`_RateLimiter`, `_ResponseCache`).
- `services/__init__.py` — Re-exports `TMDBService` and `TMDBAPIError` for convenient imports.

## Dependencies Added

None.

## Usage Example

```python
from config.settings import get_settings
from services import TMDBService
from models import Movie

settings = get_settings()

with TMDBService(settings) as tmdb:
    # Fetch the first page of popular movies
    popular = tmdb.fetch_popular_movies(page=1)
    movies = [Movie.from_tmdb_response(m) for m in popular]
    for movie in movies:
        print(f"{movie.title} ({movie.release_date})")

    # Fetch full details for a specific movie
    details = tmdb.fetch_movie_details(550)
    fight_club = Movie.from_tmdb_response(details)
    print(fight_club.to_dict())
```

## Notes

- A valid `TMDB_API_KEY` must be set in the `.env` file before using the service. Register for a free key at https://www.themoviedb.org/settings/api.
- All requests have a 5-second timeout. Failed requests are retried up to 3 times with exponential backoff (0.5 s, 1.0 s). Client errors (4xx, except 429) are **not** retried.
- Cached responses expire after 5 minutes (`DEFAULT_CACHE_TTL = 300`).
- The rate limiter and cache are both thread-safe, so the service can be shared across threads if needed.
