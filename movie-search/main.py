"""Movie Search Application – fetch popular movies and display them."""

from __future__ import annotations

import logging
import sys

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from config.settings import get_settings
from models.movie import Movie
from services.tmdb_service import TMDBAPIError, TMDBService

console = Console()

OVERVIEW_MAX_LEN = 100


def _rating_color(rating: float | None) -> str:
    if rating is None:
        return "dim"
    if rating >= 8.0:
        return "green"
    if rating >= 6.0:
        return "yellow"
    return "red"


def _truncate(text: str, length: int = OVERVIEW_MAX_LEN) -> str:
    if len(text) <= length:
        return text
    return text[: length - 1] + "…"


def _extract_year(release_date: str) -> str:
    """Return the four-digit year from a YYYY-MM-DD string, or '—' if unavailable."""
    return release_date[:4] if len(release_date) >= 4 else "—"


def main() -> None:
    """Load settings, fetch popular movies, and print a formatted table."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        console.print(f"[bold red]Configuration error:[/]\n{exc}")
        sys.exit(1)

    if settings.debug:
        logging.basicConfig(level=logging.DEBUG)

    table = Table(
        title="Popular Movies on TMDB",
        show_lines=True,
        title_style="bold cyan",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Title", style="bold", min_width=20)
    table.add_column("Year", justify="center", width=6)
    table.add_column("Rating", justify="center", width=8)
    table.add_column("Overview", min_width=30)

    try:
        with TMDBService(settings) as tmdb:
            raw_movies = tmdb.fetch_popular_movies(page=1)
    except TMDBAPIError as exc:
        console.print(f"[bold red]API error:[/] {exc.message}")
        sys.exit(1)

    if not raw_movies:
        console.print("[yellow]No movies returned by TMDB.[/]")
        sys.exit(0)

    movies: list[Movie] = []
    for raw in raw_movies[:20]:
        try:
            movies.append(Movie.from_tmdb_response(raw))
        except ValueError:
            continue

    for idx, movie in enumerate(movies, start=1):
        year = _extract_year(movie.release_date)
        color = _rating_color(movie.vote_average)
        rating_text = f"[{color}]{movie.vote_average:.1f}[/]" if movie.vote_average is not None else "[dim]—[/]"
        overview = _truncate(movie.overview) if movie.overview else "—"
        table.add_row(str(idx), movie.title, year, rating_text, overview)

    console.print()
    console.print(table)
    console.print(f"\n[dim]Showing {len(movies)} movie(s).[/]")


if __name__ == "__main__":
    main()
