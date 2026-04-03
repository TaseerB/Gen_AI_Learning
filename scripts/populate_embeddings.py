from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "movie-search"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from database.connection import database_session
from models.movie import Movie
from repositories.chroma_repository import ChromaRepository, ChromaRepositoryError
from repositories.movie_repository import MovieRepository, RepositoryError
from services.embedding_service import EmbeddingService


LOGGER = logging.getLogger("populate_embeddings")
CONSOLE = Console()
EMBEDDING_BATCH_SIZE = 32
DB_FETCH_BATCH_SIZE = 256


@dataclass(slots=True)
class PopulationStats:
    """Tracks summary statistics for one embedding population run."""

    total_sql_movies: int = 0
    total_processed: int = 0
    successful_embeddings: int = 0
    skipped_no_overview: int = 0
    skipped_embedding_failures: int = 0
    skipped_insertion_errors: int = 0
    elapsed_seconds: float = 0.0
    already_embedded: bool = False

    @property
    def skipped_total(self) -> int:
        """Return total skipped records across all skip/error categories."""
        return (
            self.skipped_no_overview
            + self.skipped_embedding_failures
            + self.skipped_insertion_errors
        )


def setup_logging() -> None:
    """Configure terminal and file logging for the script."""
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "populate_embeddings.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def _extract_release_year(release_date: str) -> int:
    """Extract year from YYYY-MM-DD date strings; fallback to 0 when unknown."""
    if not release_date:
        return 0
    year_part = release_date[:4]
    return int(year_part) if year_part.isdigit() else 0


def _build_document(movie: Movie) -> str:
    """Build embedding source text from title and overview."""
    return f"{movie.title}. {movie.overview.strip()}"


def _build_metadata(movie: Movie) -> dict[str, str | int | float]:
    """Build Chroma metadata including requested and compatibility fields."""
    genres = ", ".join(movie.genres or [])
    rating = float(movie.vote_average) if movie.vote_average is not None else 0.0

    return {
        "title": movie.title,
        "release_date": movie.release_date,
        "vote_average": rating,
        "genres": genres,
        # Compatibility fields required by the existing repository validator.
        "year": _extract_release_year(movie.release_date),
        "rating": rating,
    }


def _iter_movies(repo: MovieRepository, total: int, page_size: int) -> list[Movie]:
    """Yield movies from SQLite in deterministic paginated chunks."""
    offset = 0
    while offset < total:
        batch = repo.find_all(limit=page_size, offset=offset)
        if not batch:
            break
        yield batch
        offset += len(batch)


def populate_embeddings() -> PopulationStats:
    """Populate ChromaDB with movie embeddings from SQLite in batches."""
    stats = PopulationStats()
    started_at = time.perf_counter()

    chroma_repo = ChromaRepository()
    sql_repo_for_count = MovieRepository()

    try:
        stats.total_sql_movies = sql_repo_for_count.count()
    except RepositoryError:
        LOGGER.exception("Failed to count SQL movies")
        raise

    chroma_count = chroma_repo.count()
    if chroma_count >= stats.total_sql_movies and stats.total_sql_movies > 0:
        stats.already_embedded = True
        stats.elapsed_seconds = time.perf_counter() - started_at
        return stats

    embedding_service = EmbeddingService()

    try:
        with database_session() as connection:
            repo = MovieRepository(connection=connection)

            with tqdm(
                total=stats.total_sql_movies,
                desc="Processing movies",
                unit="movie",
            ) as progress:
                for db_batch in _iter_movies(
                    repo=repo,
                    total=stats.total_sql_movies,
                    page_size=DB_FETCH_BATCH_SIZE,
                ):
                    stats.total_processed += len(db_batch)
                    progress.update(len(db_batch))

                    for index in range(0, len(db_batch), EMBEDDING_BATCH_SIZE):
                        embedding_batch = db_batch[index : index + EMBEDDING_BATCH_SIZE]

                        valid_movies: list[Movie] = []
                        documents: list[str] = []
                        for movie in embedding_batch:
                            if not movie.overview.strip():
                                stats.skipped_no_overview += 1
                                LOGGER.debug(
                                    "Skipping movie id=%s title=%r due to missing overview",
                                    movie.id,
                                    movie.title,
                                )
                                continue
                            valid_movies.append(movie)
                            documents.append(_build_document(movie))

                        if not valid_movies:
                            continue

                        try:
                            embeddings = embedding_service.embed_batch(documents)
                        except Exception:
                            stats.skipped_embedding_failures += len(valid_movies)
                            LOGGER.exception(
                                "Embedding batch failed; skipping %s movie(s)",
                                len(valid_movies),
                            )
                            continue

                        records: list[dict[str, object]] = []
                        for movie, document, embedding in zip(valid_movies, documents, embeddings):
                            if not embedding or all(value == 0.0 for value in embedding):
                                stats.skipped_embedding_failures += 1
                                LOGGER.error(
                                    "Embedding failure for movie id=%s title=%r",
                                    movie.id,
                                    movie.title,
                                )
                                continue

                            records.append(
                                {
                                    "id": movie.id,
                                    "text": document,
                                    "embedding": embedding,
                                    "metadata": _build_metadata(movie),
                                }
                            )

                        if not records:
                            continue

                        try:
                            chroma_repo.add_movies_batch(records)
                            stats.successful_embeddings += len(records)
                        except ChromaRepositoryError:
                            stats.skipped_insertion_errors += len(records)
                            LOGGER.exception(
                                "Chroma insertion failed for batch size=%s",
                                len(records),
                            )
    except RepositoryError:
        LOGGER.exception("Database read error encountered; transaction rolled back")
        raise
    except Exception:
        LOGGER.exception("Unexpected population failure")
        raise
    finally:
        stats.elapsed_seconds = time.perf_counter() - started_at

    return stats


def print_summary(stats: PopulationStats) -> None:
    """Render final run summary with rich tables."""
    table = Table(title="Embedding Population Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("Total SQL movies", f"{stats.total_sql_movies}")
    table.add_row("Total processed", f"{stats.total_processed}")
    table.add_row("Successful embeddings", f"{stats.successful_embeddings}")
    table.add_row("Skipped (missing overview)", f"{stats.skipped_no_overview}")
    table.add_row("Skipped (embedding failures)", f"{stats.skipped_embedding_failures}")
    table.add_row("Skipped (insertion errors)", f"{stats.skipped_insertion_errors}")
    table.add_row("Skipped (total)", f"{stats.skipped_total}")
    table.add_row("Time taken", f"{stats.elapsed_seconds:.2f}s")

    average_time = (
        stats.elapsed_seconds / stats.total_processed if stats.total_processed > 0 else 0.0
    )
    table.add_row("Average time per movie", f"{average_time:.4f}s")

    CONSOLE.print(table)


def main() -> int:
    """Script entrypoint for embedding population."""
    setup_logging()

    CONSOLE.print(
        Panel.fit(
            "Populate Movie Embeddings\n"
            "Source: SQLite movies table\n"
            "Target: ChromaDB movies collection",
            border_style="green",
        )
    )

    try:
        movie_repo = MovieRepository()
        chroma_repo = ChromaRepository()

        sql_count = movie_repo.count()
        chroma_count = chroma_repo.count()

        if sql_count == 0:
            CONSOLE.print("[yellow]No movies found in SQLite. Nothing to process.[/yellow]")
            return 0

        if chroma_count >= sql_count:
            CONSOLE.print(
                f"[green]Embeddings already populated ({chroma_count}/{sql_count}).[/green]"
            )
            return 0

        remaining = max(sql_count - chroma_count, 0)
        CONSOLE.print(
            f"SQLite movies: [bold]{sql_count}[/bold] | "
            f"Chroma embeddings: [bold]{chroma_count}[/bold] | "
            f"Estimated remaining: [bold]{remaining}[/bold]"
        )

        confirmed = Confirm.ask(
            f"Proceed with embedding population for up to {sql_count} movies?",
            default=False,
        )
        if not confirmed:
            CONSOLE.print("[yellow]Cancelled by user.[/yellow]")
            return 0

        stats = populate_embeddings()

        if stats.already_embedded:
            CONSOLE.print("[green]All movies are already embedded. Nothing to do.[/green]")
            return 0

        print_summary(stats)
        return 0
    except KeyboardInterrupt:
        CONSOLE.print("[yellow]Interrupted by user.[/yellow]")
        return 1
    except Exception as exc:
        LOGGER.exception("Population script failed")
        CONSOLE.print(f"[red]Population failed:[/red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())