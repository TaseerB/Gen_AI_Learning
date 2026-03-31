"""TMDB movie import pipeline: fetch, validate, and batch insert."""

from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from config.settings import get_settings
from database.connection import database_session, initialize_database
from models.movie import Movie
from repositories.movie_repository import MovieRepository
from services.tmdb_service import TMDBAPIError, TMDBService

console = Console()
logger = logging.getLogger(__name__)

MOVIES_PER_PAGE = 20
MAX_TMDB_PAGE = 500
MAX_WORKERS = 4


@dataclass(slots=True)
class ImportSummary:
    """Tracks aggregate import results."""

    inserted: int = 0
    skipped: int = 0
    errors: int = 0


def _pages_needed(num_movies: int) -> int:
    """Return number of TMDB pages needed for the requested movie count."""
    if num_movies <= 0:
        return 0
    return min(math.ceil(num_movies / MOVIES_PER_PAGE), MAX_TMDB_PAGE)


def _fetch_page(page: int) -> tuple[int, list[dict], str | None]:
    """Fetch a single TMDB popular page and return (page, results, error)."""
    try:
        settings = get_settings()
        with TMDBService(settings) as tmdb:
            return page, tmdb.fetch_popular_movies(page=page), None
    except (TMDBAPIError, ValidationError) as exc:
        logger.exception("Failed to fetch TMDB page %s", page)
        return page, [], str(exc)


def _fetch_popular_pages_concurrently(pages: int) -> tuple[list[dict], int]:
    """Fetch multiple TMDB pages in parallel and return (raw_movies, page_errors)."""
    if pages == 0:
        return [], 0

    page_errors = 0
    page_results: dict[int, list[dict]] = {}
    page_numbers = list(range(1, pages + 1))
    workers = min(MAX_WORKERS, pages)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_fetch_page, p) for p in page_numbers]
        for future in tqdm(
            as_completed(futures),
            total=len(futures),
            desc="Fetching TMDB pages",
            unit="page",
        ):
            page, movies, err = future.result()
            if err is not None:
                page_errors += 1
                logger.error("Page %s failed: %s", page, err)
                continue
            page_results[page] = movies

    ordered_movies: list[dict] = []
    for page in page_numbers:
        ordered_movies.extend(page_results.get(page, []))
    return ordered_movies, page_errors


def _is_valid_movie(movie: Movie) -> bool:
    """Run additional import-time validation checks."""
    if not movie.title.strip():
        return False
    if movie.vote_average is not None and not (0.0 <= movie.vote_average <= 10.0):
        return False
    return True


def _validate_and_transform(raw_movies: list[dict], limit: int) -> tuple[list[Movie], int]:
    """Convert TMDB payloads to validated Movie objects."""
    movies: list[Movie] = []
    errors = 0
    for raw in tqdm(raw_movies[:limit], desc="Validating movies", unit="movie"):
        try:
            movie = Movie.from_tmdb_response(raw)
            if not _is_valid_movie(movie):
                errors += 1
                logger.warning("Skipping invalid movie payload id=%s", raw.get("id"))
                continue
            movies.append(movie)
        except Exception:
            errors += 1
            logger.exception("Failed to transform movie payload id=%s", raw.get("id"))
            continue
    return movies, errors


def _insert_movies_batch(movies: list[Movie]) -> tuple[int, int]:
    """Insert movies in a single transaction; duplicates are skipped."""
    if not movies:
        return 0, 0

    insert_sql = """
        INSERT OR IGNORE INTO movies (
            id, title, release_date, overview, vote_average, vote_count, genres, poster_path, runtime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        with database_session() as conn:
            repo = MovieRepository(connection=conn)
            params: list[tuple] = []
            skipped_duplicates = 0
            seen_ids: set[int] = set()
            for movie in tqdm(movies, desc="Preparing DB rows", unit="movie"):
                if movie.id in seen_ids:
                    skipped_duplicates += 1
                    continue
                seen_ids.add(movie.id)

                if repo.find_by_id(movie.id) is not None:
                    skipped_duplicates += 1
                    continue

                payload = movie.to_dict()
                params.append(
                    (
                        payload["id"],
                        payload["title"],
                        payload.get("release_date", ""),
                        payload.get("overview", ""),
                        payload.get("vote_average"),
                        payload.get("vote_count"),
                        None
                        if payload.get("genres") is None
                        else json.dumps(payload.get("genres"), ensure_ascii=False),
                        payload.get("poster_path"),
                        payload.get("runtime"),
                    )
                )

            if not params:
                return 0, skipped_duplicates
            cur = conn.executemany(insert_sql, params)
            inserted = cur.rowcount if cur.rowcount is not None else 0
        skipped = skipped_duplicates + max(len(params) - inserted, 0)
        return inserted, skipped
    except Exception:
        logger.exception("Critical database error during batch insert")
        raise


def import_popular_movies(num_movies: int = 100) -> ImportSummary:
    """Import popular TMDB movies into local database."""
    initialize_database()
    pages = _pages_needed(num_movies)
    if pages == 0:
        return ImportSummary()

    raw_movies, page_errors = _fetch_popular_pages_concurrently(pages)
    movies, movie_errors = _validate_and_transform(raw_movies, limit=num_movies)

    inserted = 0
    skipped = 0
    critical_errors = 0
    try:
        inserted, skipped = _insert_movies_batch(movies)
    except Exception:
        critical_errors += 1

    return ImportSummary(
        inserted=inserted,
        skipped=skipped,
        errors=page_errors + movie_errors + critical_errors,
    )


def print_import_summary(summary: ImportSummary, elapsed_seconds: float) -> None:
    """Print a formatted import summary table."""
    table = Table(title="Import Summary", title_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Imported", str(summary.inserted))
    table.add_row("Skipped", str(summary.skipped))
    table.add_row("Errors", str(summary.errors))
    table.add_row("Time Taken (s)", f"{elapsed_seconds:.2f}")
    console.print()
    console.print(table)


def read_num_movies(default: int = 100) -> int:
    """Prompt user for number of movies to import."""
    raw = input(f"How many movies should be imported? [{default}]: ").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def run_import_flow() -> None:
    """Prompt for movie count, import, and print summary."""
    import time

    console.print("[bold cyan]Welcome to Movie Importer[/]")
    num_movies = read_num_movies(default=100)

    start = time.perf_counter()
    summary = import_popular_movies(num_movies=num_movies)
    elapsed = time.perf_counter() - start
    print_import_summary(summary, elapsed)
