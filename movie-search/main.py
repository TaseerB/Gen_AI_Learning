"""Batch import popular movies from TMDB into SQLite."""

from __future__ import annotations

import logging
import math
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from tqdm import tqdm

from config.settings import get_settings
from database.connection import database_session, initialize_database
from models.movie import Movie
from repositories.movie_repository import MovieRepository, RepositoryError
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


def _print_summary(summary: ImportSummary, elapsed_seconds: float) -> None:
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


def _read_num_movies(default: int = 100) -> int:
    """Prompt user for number of movies to import."""
    raw = input(f"How many movies should be imported? [{default}]: ").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def _movie_row_display(movie: Movie) -> tuple[str, str, str, str]:
    """Return (Title, Year, Rating, Genres) for table display."""
    year = movie.release_date.split("-")[0] if movie.release_date else ""
    rating = f"{movie.vote_average:.1f}" if movie.vote_average is not None else "-"
    genres = ", ".join(movie.genres) if movie.genres else "-"
    return movie.title, year, rating, genres


def _render_movie_table(title: str, movies: list[Movie]) -> None:
    """Render up to 10 movies as a rich table."""
    table = Table(title=title, title_style="bold cyan", show_lines=False)
    table.add_column("No", style="dim", justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Year", justify="right")
    table.add_column("Rating", justify="right")
    table.add_column("Genres")

    for idx, m in enumerate(movies, start=1):
        t, y, r, g = _movie_row_display(m)
        table.add_row(str(idx), t, y, r, g)
    console.print(table)


def _display_movie_details(movie: Movie) -> None:
    """Show a single movie's full details."""
    year = movie.release_date.split("-")[0] if movie.release_date else ""
    genres = ", ".join(movie.genres) if movie.genres else "-"
    rating = f"{movie.vote_average:.1f}" if movie.vote_average is not None else "-"
    runtime = f"{movie.runtime} min" if movie.runtime is not None else "-"

    details = Table(show_header=False)
    details.add_row("Title", movie.title)
    details.add_row("Year", year or "-")
    details.add_row("Rating", rating)
    details.add_row("Genres", genres)
    details.add_row("Release Date", movie.release_date or "-")
    details.add_row("Runtime", runtime)
    details.add_row("Overview", movie.overview or "-")

    console.print(Panel(details, title="Movie Details"))


def _prompt_and_maybe_show_details(repo: MovieRepository, movies: list[Movie]) -> None:
    """Let the user choose a row number to view full details."""
    if not movies:
        return

    while True:
        raw = console.input(f"Enter a number (1-{len(movies)}) for details, or press Enter to return: ").strip()
        if raw == "":
            return
        try:
            idx = int(raw)
        except ValueError:
            console.print("[bold red]Invalid input.[/] Please enter a number from the table.")
            continue
        if not (1 <= idx <= len(movies)):
            console.print(f"[bold red]Out of range.[/] Choose between 1 and {len(movies)}.")
            continue

        selected = movies[idx - 1]
        with console.status("[bold cyan]Loading full details..."):
            try:
                details_movie = repo.find_by_id(selected.id)
            except RepositoryError as exc:
                console.print(f"[bold red]Database error:[/] {exc}")
                return

        if details_movie is None:
            console.print("[bold red]That movie could not be found anymore.[/]")
            return

        _display_movie_details(details_movie)
        console.input("Press Enter to continue...")


def interactive_search() -> None:
    """Interactive query mode for searching movies."""
    initialize_database()
    repo = MovieRepository()

    menu_title = Panel(
        "[bold cyan]Movie Explorer[/]\n"
        "[dim]Search, filter, and discover from your local SQLite library.[/]",
        title="",
    )

    while True:
        console.print(menu_title)
        console.print(
            "[bold green]1.[/] Search by title (partial match, case-insensitive)\n"
            "[bold green]2.[/] Filter by rating (min/max range)\n"
            "[bold green]3.[/] Show top rated (limit 10)\n"
            "[bold green]4.[/] Show recent releases (last 2 years)\n"
            "[bold green]5.[/] Random movie recommendation\n"
            "[bold green]6.[/] Statistics (total movies, avg rating, etc.)\n"
            "[bold green]7.[/] Exit"
        )

        choice_raw = console.input("[bold yellow]Choose an option:[/] ").strip()
        if choice_raw == "7":
            console.print("[bold cyan]Bye![/]")
            return

        if choice_raw not in {"1", "2", "3", "4", "5", "6"}:
            console.print("[bold red]Invalid menu choice.[/] Please enter 1-7.")
            continue

        try:
            if choice_raw == "1":
                fragment = console.input("Enter title fragment to search: ").strip()
                if not fragment:
                    console.print("[bold red]Please enter a non-empty title fragment.[/]")
                    continue
                with console.status("[bold cyan]Searching by title..."):
                    movies = repo.find_by_title(fragment)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No movies found for that title.[/]")
                    continue
                _render_movie_table(f"Title search: {fragment!r}", movies)
                _prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "2":
                min_raw = console.input("Min rating (0-10) [0]: ").strip()
                max_raw = console.input("Max rating (0-10) [10]: ").strip()
                try:
                    min_rating = float(min_raw) if min_raw else 0.0
                    max_rating = float(max_raw) if max_raw else 10.0
                except ValueError:
                    console.print("[bold red]Invalid rating range.[/] Please enter numbers between 0 and 10.")
                    continue

                if not (0.0 <= min_rating <= 10.0 and 0.0 <= max_rating <= 10.0 and min_rating <= max_rating):
                    console.print("[bold red]Invalid rating range.[/] Use 0-10 and ensure min <= max.")
                    continue

                with console.status("[bold cyan]Filtering by rating..."):
                    movies = repo.find_by_rating_range(min_rating=min_rating, max_rating=max_rating)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No movies matched that rating range.[/]")
                    continue
                _render_movie_table(f"Rating range: {min_rating:.1f} - {max_rating:.1f}", movies)
                _prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "3":
                with console.status("[bold cyan]Fetching top rated movies..."):
                    movies = repo.get_top_rated(limit=10)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No rated movies available yet.[/]")
                    continue
                _render_movie_table("Top rated movies", movies)
                _prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "4":
                with console.status("[bold cyan]Fetching recent releases..."):
                    movies = repo.get_recent_releases(years=2, limit=10)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No recent releases found in the last 2 years.[/]")
                    continue
                _render_movie_table("Recent releases (last 2 years)", movies)
                _prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "5":
                with console.status("[bold cyan]Picking a random recommendation..."):
                    movie = repo.get_random_movie()
                if movie is None:
                    console.print("[bold yellow]Your database is empty. Import movies first.[/]")
                    continue
                _render_movie_table("Random recommendation", [movie])
                _prompt_and_maybe_show_details(repo, [movie])

            elif choice_raw == "6":
                with console.status("[bold cyan]Computing statistics..."):
                    stats = repo.get_statistics()

                stats_table = Table(title="Library Statistics", title_style="bold cyan")
                stats_table.add_column("Metric", style="bold")
                stats_table.add_column("Value", justify="right")
                stats_table.add_row("Total movies", str(stats.get("total_movies", 0)))
                stats_table.add_row("Rated movies", str(stats.get("rated_movies", 0)))
                avg = stats.get("avg_rating")
                stats_table.add_row("Avg rating", f"{avg:.2f}" if isinstance(avg, (int, float)) else "-")
                stats_table.add_row("Max rating", f"{stats.get('max_rating'):.1f}" if isinstance(stats.get("max_rating"), (int, float)) else "-")
                stats_table.add_row("Min rating", f"{stats.get('min_rating'):.1f}" if isinstance(stats.get("min_rating"), (int, float)) else "-")

                console.print(stats_table)
                console.input("Press Enter to return to the menu...")

        except RepositoryError as exc:
            console.print(f"[bold red]Database error:[/] {exc}")
        except ValueError:
            # Covers float parsing for rating input.
            console.print("[bold red]Invalid input.[/] Please enter numeric values for ratings.")


def _run_import_flow() -> None:
    """Prompt for movie count, import, and print summary."""
    console.print("[bold cyan]Welcome to Movie Importer[/]")
    num_movies = _read_num_movies(default=100)

    start = time.perf_counter()
    summary = import_popular_movies(num_movies=num_movies)
    elapsed = time.perf_counter() - start
    _print_summary(summary, elapsed)


def main() -> None:
    """CLI entrypoint.

    Usage:
        python main.py              # interactive search (imports first if DB is empty)
        python main.py --import     # force import, then offer interactive search
        python main.py --interactive  # interactive search only
    """
    try:
        settings = get_settings()
    except ValidationError as exc:
        console.print(f"[bold red]Configuration error:[/]\n{exc}")
        sys.exit(1)

    if settings.debug:
        logging.basicConfig(level=logging.DEBUG)

    args = set(sys.argv[1:])

    # Explicit import mode
    if "--import" in args:
        _run_import_flow()
        go_interactive = console.input("Start interactive movie search? [y/N]: ").strip().lower()
        if go_interactive in {"y", "yes"}:
            interactive_search()
        return

    # Explicit interactive mode (legacy flag kept for compatibility)
    if "--interactive" in args:
        interactive_search()
        return

    # Default: go straight to interactive search; import first if DB is empty
    initialize_database()
    repo = MovieRepository()
    try:
        movie_count = repo.count()
    except RepositoryError:
        movie_count = 0

    if movie_count == 0:
        console.print("[bold yellow]Your database is empty.[/] Let's import some movies first.\n")
        _run_import_flow()

    interactive_search()


if __name__ == "__main__":
    main()
