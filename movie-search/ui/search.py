"""Interactive movie search and menu handling."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from database.connection import initialize_database
from repositories.movie_repository import MovieRepository, RepositoryError
from ui.display import display_movie_details, render_movie_table

console = Console()


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

        except RepositoryError as exc:
            console.print(f"[bold red]Database error:[/] {exc}")
        except ValueError:
            console.print("[bold red]Invalid input.[/] Please enter numeric values for ratings.")
