"""Rendering movie tables and detailed information displays."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from models.movie import Movie

console = Console()


def movie_row_display(movie: Movie) -> tuple[str, str, str, str]:
    """Return (Title, Year, Rating, Genres) for table display."""
    year = movie.release_date.split("-")[0] if movie.release_date else ""
    rating = f"{movie.vote_average:.1f}" if movie.vote_average is not None else "-"
    genres = ", ".join(movie.genres) if movie.genres else "-"
    return movie.title, year, rating, genres


def render_movie_table(title: str, movies: list[Movie]) -> None:
    """Render up to 10 movies as a rich table.
    
    Args:
        title: Table title
        movies: List of Movie objects to display
    """
    table = Table(title=title, title_style="bold cyan", show_lines=False)
    table.add_column("No", style="dim", justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Year", justify="right")
    table.add_column("Rating", justify="right")
    table.add_column("Genres")

    for idx, m in enumerate(movies, start=1):
        t, y, r, g = movie_row_display(m)
        table.add_row(str(idx), t, y, r, g)
    console.print(table)


def display_movie_details(movie: Movie) -> None:
    """Show a single movie's full details in a panel.
    
    Args:
        movie: Movie object to display
    """
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
