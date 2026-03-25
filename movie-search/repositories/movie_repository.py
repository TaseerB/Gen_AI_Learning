from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from database.connection import get_connection
from models.movie import Movie

logger = logging.getLogger(__name__)


class RepositoryError(Exception):
    """Raised when repository operations fail.

    This exception wraps lower-level database exceptions and provides a
    consistent error type for service/application layers.
    """


class MovieRepository:
    """Repository for persisting and querying `Movie` domain objects.

    This class follows the Repository pattern:
    - Callers work with domain objects (`Movie`) rather than SQL rows/dicts.
    - Persistence concerns (SQL, transactions, serialization) are encapsulated.

    Dependency injection is supported via an optional `sqlite3.Connection`,
    which is useful for tests (e.g., an in-memory SQLite database).

    Examples:
        Basic usage (default DB connection):

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

            movie = repo.find_by_id(550)
            assert movie is not None
            assert movie.title == "Fight Club"

        Testing with an in-memory database:

            import sqlite3
            from database.connection import initialize_database
            from repositories.movie_repository import MovieRepository

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.executescript(open("database/schema.sql", "r", encoding="utf-8").read())

            repo = MovieRepository(connection=conn)
            assert repo.count() == 0
    """

    def __init__(self, connection: sqlite3.Connection | None = None) -> None:
        """Create a `MovieRepository`.

        Args:
            connection: Optional SQLite connection to use. If omitted, the
                repository will create connections via `database.connection.get_connection`.
        """

        self._connection = connection

    @contextmanager
    def _connection_scope(self) -> Iterator[sqlite3.Connection]:
        """Provide a safe, context-managed connection and transaction.

        - Always uses a context manager for transactional safety (`with conn:`).
        - If the repository created the connection, it is closed on exit.
        - Database errors are wrapped in `RepositoryError` with logging.
        """

        conn = self._connection or get_connection()
        try:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn
        except sqlite3.Error as exc:
            logger.exception("Database operation failed")
            raise RepositoryError("Database operation failed") from exc
        finally:
            if self._connection is None:
                try:
                    conn.close()
                except sqlite3.Error:
                    logger.exception("Failed to close database connection")

    def save(self, movie: Movie) -> None:
        """Insert or update a movie in the database.

        Uses `INSERT OR REPLACE` to handle duplicates (same `id`).

        Args:
            movie: Movie domain object to persist.

        Raises:
            RepositoryError: If the insert fails.
        """

        payload = movie.to_dict()
        if "genres" in payload:
            payload["genres"] = json.dumps(payload["genres"], ensure_ascii=False)

        columns = ", ".join(payload.keys())
        placeholders = ", ".join(["?"] * len(payload))
        sql = f"INSERT OR REPLACE INTO movies ({columns}) VALUES ({placeholders})"
        values = tuple(payload.values())

        logger.debug("Saving movie id=%s title=%r", movie.id, movie.title)
        with self._connection_scope() as conn:
            try:
                conn.execute(sql, values)
            except sqlite3.Error as exc:
                logger.exception("Failed to save movie id=%s", movie.id)
                raise RepositoryError(f"Failed to save movie id={movie.id}") from exc

        logger.info("Saved movie id=%s title=%r", movie.id, movie.title)

    def find_by_id(self, movie_id: int) -> Movie | None:
        """Fetch a movie by its ID.

        Args:
            movie_id: TMDB movie ID.

        Returns:
            A `Movie` if found, otherwise `None`.

        Raises:
            RepositoryError: If the query fails.
        """

        logger.debug("Finding movie by id=%s", movie_id)
        with self._connection_scope() as conn:
            try:
                row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
            except sqlite3.Error as exc:
                logger.exception("Failed to find movie by id=%s", movie_id)
                raise RepositoryError(f"Failed to find movie by id={movie_id}") from exc

        if row is None:
            logger.info("Movie not found id=%s", movie_id)
            return None

        movie = self._row_to_movie(row)
        logger.info("Found movie id=%s title=%r", movie.id, movie.title)
        return movie

    def find_all(self, limit: int = 100, offset: int = 0) -> list[Movie]:
        """Fetch movies ordered by rating (descending) with pagination.

        Args:
            limit: Maximum number of movies to return.
            offset: Number of rows to skip.

        Returns:
            A list of `Movie` objects.

        Raises:
            RepositoryError: If the query fails.
        """

        logger.debug("Finding all movies limit=%s offset=%s", limit, offset)
        with self._connection_scope() as conn:
            try:
                rows = conn.execute(
                    "SELECT * FROM movies ORDER BY vote_average DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            except sqlite3.Error as exc:
                logger.exception("Failed to find all movies")
                raise RepositoryError("Failed to find all movies") from exc

        movies = [self._row_to_movie(r) for r in rows]
        logger.info("Found %s movie(s) (limit=%s offset=%s)", len(movies), limit, offset)
        return movies

    def find_by_title(self, title: str) -> list[Movie]:
        """Search movies by title using a case-insensitive partial match.

        Args:
            title: Title fragment to search for.

        Returns:
            A list of matching `Movie` objects.

        Raises:
            RepositoryError: If the query fails.
        """

        pattern = f"%{title}%"
        logger.debug("Finding movies by title like=%r", pattern)
        with self._connection_scope() as conn:
            try:
                rows = conn.execute(
                    "SELECT * FROM movies WHERE title LIKE ? COLLATE NOCASE ORDER BY vote_average DESC",
                    (pattern,),
                ).fetchall()
            except sqlite3.Error as exc:
                logger.exception("Failed to find movies by title=%r", title)
                raise RepositoryError(f"Failed to find movies by title={title!r}") from exc

        movies = [self._row_to_movie(r) for r in rows]
        logger.info("Found %s movie(s) matching title=%r", len(movies), title)
        return movies

    def find_by_rating_range(self, min_rating: float, max_rating: float) -> list[Movie]:
        """Fetch movies with ratings in an inclusive range.

        Movies with `NULL` ratings are excluded.

        Args:
            min_rating: Minimum rating (inclusive).
            max_rating: Maximum rating (inclusive).

        Returns:
            A list of matching `Movie` objects.

        Raises:
            RepositoryError: If the query fails.
        """

        logger.debug("Finding movies by rating range %s..%s", min_rating, max_rating)
        with self._connection_scope() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM movies
                    WHERE vote_average IS NOT NULL
                      AND vote_average >= ?
                      AND vote_average <= ?
                    ORDER BY vote_average DESC
                    """,
                    (min_rating, max_rating),
                ).fetchall()
            except sqlite3.Error as exc:
                logger.exception(
                    "Failed to find movies by rating range %s..%s", min_rating, max_rating
                )
                raise RepositoryError("Failed to find movies by rating range") from exc

        movies = [self._row_to_movie(r) for r in rows]
        logger.info("Found %s movie(s) in rating range %s..%s", len(movies), min_rating, max_rating)
        return movies

    def get_top_rated(self, limit: int = 10) -> list[Movie]:
        """Fetch the top rated movies (highest `vote_average` first)."""
        if limit <= 0:
            return []

        logger.debug("Finding top rated movies limit=%s", limit)
        with self._connection_scope() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM movies
                    WHERE vote_average IS NOT NULL
                    ORDER BY vote_average DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            except sqlite3.Error as exc:
                logger.exception("Failed to find top rated movies")
                raise RepositoryError("Failed to find top rated movies") from exc

        movies = [self._row_to_movie(r) for r in rows]
        logger.info("Found %s top rated movie(s) limit=%s", len(movies), limit)
        return movies

    def get_recent_releases(self, years: int = 2, limit: int = 10) -> list[Movie]:
        """Fetch movies released in the last `years` years."""
        if years <= 0 or limit <= 0:
            return []

        logger.debug("Finding recent releases years=%s limit=%s", years, limit)
        # SQLite stores release_date in ISO format (YYYY-MM-DD). Use string-safe date comparisons.
        modifier = f"-{int(years)} years"
        with self._connection_scope() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM movies
                    WHERE release_date IS NOT NULL
                      AND release_date != ''
                      AND release_date >= date('now', ?)
                    ORDER BY release_date DESC
                    LIMIT ?
                    """,
                    (modifier, limit),
                ).fetchall()
            except sqlite3.Error as exc:
                logger.exception("Failed to find recent releases")
                raise RepositoryError("Failed to find recent releases") from exc

        movies = [self._row_to_movie(r) for r in rows]
        logger.info("Found %s recent release(s) years=%s limit=%s", len(movies), years, limit)
        return movies

    def get_random_movie(self) -> Movie | None:
        """Return a random movie recommendation (prefers movies with ratings)."""
        with self._connection_scope() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT * FROM movies
                    WHERE vote_average IS NOT NULL
                    ORDER BY RANDOM()
                    LIMIT 1
                    """
                ).fetchone()
            except sqlite3.Error as exc:
                logger.exception("Failed to get random movie")
                raise RepositoryError("Failed to get random movie") from exc

        if row is not None:
            return self._row_to_movie(row)

        # Fallback: if no rated movies exist, pick any movie.
        with self._connection_scope() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT * FROM movies
                    ORDER BY RANDOM()
                    LIMIT 1
                    """
                ).fetchone()
            except sqlite3.Error as exc:
                logger.exception("Failed to get fallback random movie")
                raise RepositoryError("Failed to get random movie") from exc

        if row is None:
            return None
        return self._row_to_movie(row)

    def get_statistics(self) -> dict[str, Any]:
        """Return basic database statistics about stored movies."""
        logger.debug("Computing movie statistics")
        with self._connection_scope() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT
                      COUNT(*) AS total_movies,
                      SUM(CASE WHEN vote_average IS NOT NULL THEN 1 ELSE 0 END) AS rated_movies,
                      AVG(vote_average) AS avg_rating,
                      MAX(vote_average) AS max_rating,
                      MIN(vote_average) AS min_rating
                    FROM movies
                    """
                ).fetchone()
            except sqlite3.Error as exc:
                logger.exception("Failed to compute movie statistics")
                raise RepositoryError("Failed to compute movie statistics") from exc

        if row is None:
            return {
                "total_movies": 0,
                "rated_movies": 0,
                "avg_rating": None,
                "max_rating": None,
                "min_rating": None,
            }

        def _none_if_null(value: Any) -> Any:
            return None if value is None else value

        return {
            "total_movies": int(row["total_movies"]) if row["total_movies"] is not None else 0,
            "rated_movies": int(row["rated_movies"]) if row["rated_movies"] is not None else 0,
            "avg_rating": _none_if_null(row["avg_rating"]),
            "max_rating": _none_if_null(row["max_rating"]),
            "min_rating": _none_if_null(row["min_rating"]),
        }

    def count(self) -> int:
        """Return total number of movies in the database.

        Raises:
            RepositoryError: If the query fails.
        """

        logger.debug("Counting movies")
        with self._connection_scope() as conn:
            try:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM movies").fetchone()
            except sqlite3.Error as exc:
                logger.exception("Failed to count movies")
                raise RepositoryError("Failed to count movies") from exc

        total = int(row["cnt"]) if row is not None and row["cnt"] is not None else 0
        logger.info("Movie count=%s", total)
        return total

    def delete(self, movie_id: int) -> bool:
        """Delete a movie by ID.

        Args:
            movie_id: TMDB movie ID.

        Returns:
            True if a row was deleted, False if not found.

        Raises:
            RepositoryError: If the delete fails.
        """

        logger.debug("Deleting movie id=%s", movie_id)
        with self._connection_scope() as conn:
            try:
                cur = conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
            except sqlite3.Error as exc:
                logger.exception("Failed to delete movie id=%s", movie_id)
                raise RepositoryError(f"Failed to delete movie id={movie_id}") from exc

        deleted = (cur.rowcount or 0) > 0
        if deleted:
            logger.info("Deleted movie id=%s", movie_id)
        else:
            logger.info("Movie not found for deletion id=%s", movie_id)
        return deleted

    def _row_to_movie(self, row: sqlite3.Row) -> Movie:
        """Convert a database row to a `Movie`.

        - Handles NULL values by mapping them to `None` or safe defaults.
        - Deserializes JSON fields (e.g., `genres`) if present.

        Args:
            row: A `sqlite3.Row` returned from a query.

        Returns:
            A `Movie` instance.

        Raises:
            RepositoryError: If deserialization fails.
        """

        raw_genres = row["genres"] if "genres" in row.keys() else None
        genres: list[str] | None = None
        if raw_genres:
            try:
                parsed = json.loads(raw_genres)
                if isinstance(parsed, list):
                    genres = [str(x) for x in parsed]
                else:
                    genres = None
            except json.JSONDecodeError as exc:
                logger.exception("Failed to decode genres JSON for movie id=%s", row["id"])
                raise RepositoryError("Failed to decode genres JSON") from exc

        release_date = row["release_date"] if row["release_date"] is not None else ""
        overview = row["overview"] if row["overview"] is not None else ""

        return Movie(
            id=int(row["id"]),
            title=str(row["title"]),
            release_date=str(release_date),
            overview=str(overview),
            vote_average=float(row["vote_average"]) if row["vote_average"] is not None else None,
            vote_count=int(row["vote_count"]) if row["vote_count"] is not None else None,
            genres=genres,
            poster_path=str(row["poster_path"]) if row["poster_path"] is not None else None,
            runtime=int(row["runtime"]) if row["runtime"] is not None else None,
        )

