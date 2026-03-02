"""TMDB API client – handles all communication with The Movie Database."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from config.settings import Settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5

RATE_LIMIT_CALLS = 40
RATE_LIMIT_WINDOW = 10.0

DEFAULT_CACHE_TTL = 300.0


class TMDBAPIError(Exception):
    """Raised when the TMDB API returns an unexpected or error response.

    Attributes:
        status_code: HTTP status code returned by TMDB (``None`` for
            network-level failures such as timeouts).
        message: Human-readable description of the failure.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class _RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, max_calls: int, window: float) -> None:
        self._max_calls = max_calls
        self._window = window
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self._window
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._max_calls:
                sleep_for = self._timestamps[0] - cutoff
                logger.debug("Rate limit reached – sleeping %.2fs", sleep_for)
                time.sleep(sleep_for)

            self._timestamps.append(time.monotonic())


class _ResponseCache:
    """Simple in-memory TTL cache keyed by URL + params."""

    def __init__(self, ttl: float = DEFAULT_CACHE_TTL) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)


class TMDBService:
    """Client for the TMDB REST API.

    Uses ``requests.Session`` for connection pooling, adds automatic
    retry with exponential backoff, a sliding-window rate limiter, and
    a simple TTL response cache.

    Example::

        from config.settings import get_settings

        settings = get_settings()
        with TMDBService(settings) as tmdb:
            popular = tmdb.fetch_popular_movies()
            details = tmdb.fetch_movie_details(550)
    """

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.tmdb_base_url.rstrip("/")
        self._api_key = settings.tmdb_api_key
        self._session = requests.Session()
        self._limiter = _RateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_WINDOW)
        self._cache = _ResponseCache()

    def __enter__(self) -> TMDBService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def _request(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Send a GET request with retry, rate-limiting, and caching.

        Args:
            endpoint: Path relative to the TMDB base URL (e.g. ``/movie/popular``).
            params: Extra query-string parameters.

        Returns:
            Parsed JSON body.

        Raises:
            TMDBAPIError: On HTTP errors or network failures after all
                retry attempts are exhausted.
        """
        url = f"{self._base_url}{endpoint}"
        merged_params: dict[str, Any] = {"api_key": self._api_key}
        if params:
            merged_params.update(params)

        cache_key = f"{url}?{sorted(merged_params.items())}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", endpoint)
            return cached

        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._limiter.wait()
            try:
                logger.debug(
                    "GET %s (attempt %d/%d)", endpoint, attempt, MAX_RETRIES
                )
                response = self._session.get(
                    url, params=merged_params, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
                self._cache.set(cache_key, data)
                return data

            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                logger.warning(
                    "HTTP %s for %s (attempt %d/%d)",
                    status, endpoint, attempt, MAX_RETRIES,
                )
                if status and 400 <= status < 500 and status != 429:
                    raise TMDBAPIError(
                        f"Client error {status} for {endpoint}: {exc}",
                        status_code=status,
                    ) from exc
                last_exc = exc

            except requests.exceptions.Timeout as exc:
                logger.warning(
                    "Timeout for %s (attempt %d/%d)",
                    endpoint, attempt, MAX_RETRIES,
                )
                last_exc = exc

            except requests.exceptions.ConnectionError as exc:
                logger.warning(
                    "Connection error for %s (attempt %d/%d)",
                    endpoint, attempt, MAX_RETRIES,
                )
                last_exc = exc

            if attempt < MAX_RETRIES:
                backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                logger.debug("Retrying in %.1fs", backoff)
                time.sleep(backoff)

        raise TMDBAPIError(
            f"Request to {endpoint} failed after {MAX_RETRIES} attempts: {last_exc}",
            status_code=getattr(getattr(last_exc, "response", None), "status_code", None),
        ) from last_exc

    def fetch_popular_movies(self, page: int = 1) -> list[dict[str, Any]]:
        """Fetch a page of currently popular movies.

        Args:
            page: Result page (1-indexed, max 500).

        Returns:
            A list of raw movie dictionaries from the TMDB response.

        Raises:
            TMDBAPIError: If the API call fails after retries.

        Example::

            movies = tmdb.fetch_popular_movies(page=2)
            for m in movies:
                print(m["title"])
        """
        data = self._request("/movie/popular", params={"page": page})
        return data.get("results", [])

    def fetch_movie_details(self, movie_id: int) -> dict[str, Any]:
        """Fetch full details for a single movie.

        Args:
            movie_id: TMDB movie identifier.

        Returns:
            The complete movie-detail JSON object.

        Raises:
            TMDBAPIError: If the API call fails after retries.

        Example::

            details = tmdb.fetch_movie_details(550)
            print(details["title"])  # "Fight Club"
        """
        return self._request(f"/movie/{movie_id}")
