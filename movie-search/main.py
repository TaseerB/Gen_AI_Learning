"""CLI entry point for the movie search application."""

from __future__ import annotations

import logging
import sys

from pydantic import ValidationError
from rich.console import Console

from config.settings import get_settings
from database.connection import initialize_database
from importer import run_import_flow
from repositories.movie_repository import MovieRepository, RepositoryError
from ui.search import interactive_search

console = Console()


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
        run_import_flow()
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
        run_import_flow()

    interactive_search()


if __name__ == "__main__":
    main()
