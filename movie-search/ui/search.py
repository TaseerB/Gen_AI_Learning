"""Interactive movie search and menu handling."""

from __future__ import annotations

from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from database.connection import initialize_database
from models.movie import Movie
from repositories.chroma_repository import ChromaRepository, ChromaRepositoryError
from repositories.movie_repository import MovieRepository, RepositoryError
from ui.display import display_movie_details, render_movie_table

console = Console()

SEMANTIC_RESULT_LIMIT = 10
KEYWORD_RESULT_LIMIT = 10


def prompt_and_maybe_show_details(repo: MovieRepository, movies: list) -> None:
    """Let the user choose a row number to view full details.
    
    Args:
        repo: MovieRepository instance
        movies: List of Movie objects to choose from
    """
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

        display_movie_details(details_movie)
        console.input("Press Enter to continue...")


def _similarity_from_distance(distance: object) -> float:
    """Convert Chroma distance values into an approximate similarity score."""
    if not isinstance(distance, (int, float)):
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance)))


def _similarity_style(similarity: float) -> str:
    """Return a rich style name for a similarity score."""
    if similarity > 0.7:
        return "green"
    if similarity >= 0.4:
        return "yellow"
    return "red"


def _truncate_text(value: str, max_chars: int = 60) -> str:
    """Truncate long text for compact table rendering."""
    cleaned = value.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max_chars - 1].rstrip()}..."


def _movie_year(movie: Movie) -> str:
    """Return the release year for display."""
    return movie.release_date.split("-")[0] if movie.release_date else "-"


def _render_semantic_results_table(
    query: str,
    semantic_results: list[dict[str, Any]],
    repo: MovieRepository,
) -> tuple[Table, list[Movie]]:
    """Build the semantic search result table and resolved movie details."""
    table = Table(
        title=f"Semantic Search: {escape(query)}",
        title_style="bold cyan",
        show_lines=False,
    )
    table.add_column("No", style="dim", justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Year", justify="right")
    table.add_column("Rating", justify="right")
    table.add_column("Similarity", justify="right")
    table.add_column("Overview", overflow="fold")

    resolved_movies: list[Movie] = []
    for index, result in enumerate(semantic_results, start=1):
        movie_id = result.get("id")
        if not isinstance(movie_id, int):
            continue

        movie = repo.find_by_id(movie_id)
        if movie is None:
            continue

        similarity = _similarity_from_distance(result.get("distance"))
        similarity_style = _similarity_style(similarity)
        rating = f"{movie.vote_average:.1f}" if movie.vote_average is not None else "-"

        table.add_row(
            str(index),
            movie.title,
            _movie_year(movie),
            rating,
            f"[{similarity_style}]{similarity:.3f}[/{similarity_style}]",
            _truncate_text(movie.overview or "-"),
        )
        resolved_movies.append(movie)

    return table, resolved_movies


def _render_keyword_results_table(query: str, movies: list[Movie]) -> Table:
    """Build the SQL keyword-search comparison table."""
    table = Table(
        title=f"Keyword Search: {escape(query)}",
        title_style="bold magenta",
        show_lines=False,
    )
    table.add_column("No", style="dim", justify="right")
    table.add_column("Title", style="bold")
    table.add_column("Year", justify="right")
    table.add_column("Rating", justify="right")
    table.add_column("Overview", overflow="fold")

    for index, movie in enumerate(movies[:KEYWORD_RESULT_LIMIT], start=1):
        rating = f"{movie.vote_average:.1f}" if movie.vote_average is not None else "-"
        table.add_row(
            str(index),
            movie.title,
            _movie_year(movie),
            rating,
            _truncate_text(movie.overview or "-"),
        )

    return table


def _render_search_comparison(
    query: str,
    keyword_movies: list[Movie],
    semantic_results: list[dict[str, Any]],
    semantic_movies: list[Movie],
) -> None:
    """Show SQL keyword search and semantic search side by side."""
    keyword_table = _render_keyword_results_table(query, keyword_movies)
    semantic_table, _ = _render_semantic_results_table(query, semantic_results, MovieRepository())

    console.print(Columns([Panel(keyword_table, border_style="magenta"), Panel(semantic_table, border_style="cyan")]))

    if semantic_movies and keyword_movies:
        semantic_titles = {movie.title for movie in semantic_movies}
        keyword_titles = {movie.title for movie in keyword_movies}
        semantic_only_titles = sorted(semantic_titles - keyword_titles)
    else:
        semantic_only_titles = []

    explanation = (
        "Keyword search relies on exact word overlap in titles and overviews. "
        "Semantic search uses embeddings, so it can retrieve conceptually related movies "
        "even when the exact terms do not appear."
    )
    if semantic_only_titles:
        explanation = f"{explanation} Semantic-only matches here include: {', '.join(semantic_only_titles[:3])}."

    if query.lower().strip() == "space adventure":
        explanation = (
            f"{explanation} For 'space adventure', keyword search often misses films whose text does not "
            "contain both exact words, while semantic search can still surface titles such as Star Wars, "
            "Interstellar, or Guardians-style results based on meaning."
        )

    console.print(Panel(explanation, title="Why Semantic Search Helps", border_style="green"))


def _prompt_semantic_result_details(movies: list[Movie]) -> None:
    """Prompt the user to view full details for a semantic result."""
    if not movies:
        return

    while True:
        raw = console.input(
            f"Enter a number (1-{len(movies)}) for details, or press Enter to return: "
        ).strip()
        if raw == "":
            return
        try:
            index = int(raw)
        except ValueError:
            console.print("[bold red]Invalid input.[/] Please enter a number from the table.")
            continue
        if not (1 <= index <= len(movies)):
            console.print(f"[bold red]Out of range.[/] Choose between 1 and {len(movies)}.")
            continue

        display_movie_details(movies[index - 1])
        console.input("Press Enter to continue...")
        return


def _semantic_search_interactive(repo: MovieRepository) -> None:
    """Run semantic search, optional keyword comparison, and result drill-down."""
    try:
        chroma_repo = ChromaRepository()
    except ChromaRepositoryError as exc:
        console.print(f"[bold red]Semantic search is unavailable:[/] {exc}")
        console.print("[bold yellow]Populate embeddings first with:[/] python ../scripts/populate_embeddings.py")
        return

    try:
        if chroma_repo.count() == 0:
            console.print("[bold yellow]No embeddings found in ChromaDB.[/]")
            console.print("[bold yellow]Populate embeddings first with:[/] python ../scripts/populate_embeddings.py")
            return
    except ChromaRepositoryError as exc:
        console.print(f"[bold red]Failed to read ChromaDB:[/] {exc}")
        return

    console.print(
        Panel(
            "[bold]Examples[/]\n"
            "- movies about time travel\n"
            "- romantic comedies with happy endings\n"
            "- mind-bending psychological thrillers",
            title="Semantic Search",
            border_style="cyan",
        )
    )

    query = console.input("Enter a natural language query: ").strip()
    if not query:
        console.print("[bold red]Please enter a non-empty query.[/]")
        return

    try:
        with console.status("[bold cyan]Running semantic search..."):
            semantic_results = chroma_repo.search_by_text(query, top_k=SEMANTIC_RESULT_LIMIT)
    except ChromaRepositoryError as exc:
        console.print(f"[bold red]Semantic search failed:[/] {exc}")
        return

    if not semantic_results:
        console.print("[bold yellow]No semantic matches found for that query.[/]")
        return

    semantic_table, semantic_movies = _render_semantic_results_table(query, semantic_results, repo)
    if not semantic_movies:
        console.print("[bold yellow]No matching movie details could be loaded from SQLite.[/]")
        return

    console.print(semantic_table)

    compare_searches = console.input("Compare keyword vs semantic search side by side? [Y/n]: ").strip().lower()
    if compare_searches not in {"n", "no"}:
        try:
            with console.status("[bold cyan]Running keyword comparison..."):
                keyword_movies = repo.find_by_keywords(query, limit=KEYWORD_RESULT_LIMIT)
        except RepositoryError as exc:
            console.print(f"[bold red]Keyword comparison failed:[/] {exc}")
        else:
            _render_search_comparison(query, keyword_movies, semantic_results, semantic_movies)

    _prompt_semantic_result_details(semantic_movies)


def interactive_search() -> None:
    """Interactive query mode for searching movies.
    
    Provides a menu for searching by title, rating, showing top-rated,
    recent releases, random recommendations, and viewing statistics.
    """
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
            "[bold green]7.[/] Semantic Search (AI-powered)\n"
            "[bold green]8.[/] Exit"
        )

        choice_raw = console.input("[bold yellow]Choose an option:[/] ").strip()
        if choice_raw == "8":
            console.print("[bold cyan]Bye![/]")
            return

        if choice_raw not in {"1", "2", "3", "4", "5", "6", "7"}:
            console.print("[bold red]Invalid menu choice.[/] Please enter 1-8.")
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
                render_movie_table(f"Title search: {fragment!r}", movies)
                prompt_and_maybe_show_details(repo, movies)

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
                render_movie_table(f"Rating range: {min_rating:.1f} - {max_rating:.1f}", movies)
                prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "3":
                with console.status("[bold cyan]Fetching top rated movies..."):
                    movies = repo.get_top_rated(limit=10)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No rated movies available yet.[/]")
                    continue
                render_movie_table("Top rated movies", movies)
                prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "4":
                with console.status("[bold cyan]Fetching recent releases..."):
                    movies = repo.get_recent_releases(years=2, limit=10)
                movies = movies[:10]
                if not movies:
                    console.print("[bold yellow]No recent releases found in the last 2 years.[/]")
                    continue
                render_movie_table("Recent releases (last 2 years)", movies)
                prompt_and_maybe_show_details(repo, movies)

            elif choice_raw == "5":
                with console.status("[bold cyan]Picking a random recommendation..."):
                    movie = repo.get_random_movie()
                if movie is None:
                    console.print("[bold yellow]Your database is empty. Import movies first.[/]")
                    continue
                render_movie_table("Random recommendation", [movie])
                prompt_and_maybe_show_details(repo, [movie])

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

            elif choice_raw == "7":
                _semantic_search_interactive(repo)

        except RepositoryError as exc:
            console.print(f"[bold red]Database error:[/] {exc}")
        except ChromaRepositoryError as exc:
            console.print(f"[bold red]Semantic search error:[/] {exc}")
        except ValueError:
            console.print("[bold red]Invalid input.[/] Please enter numeric values for ratings.")
